from __future__ import annotations

import asyncio
import hmac
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from jev_core.common import BASE_DIR, DEFAULT_ROOT, MAX_BYTES, STORAGE_DIR, SUPPORTED, load_env

load_env()

from jev_core.nanojev import LocalNanoJev
from jev_core.parsing import DocumentParser, LocalOCR
from jev_core.retrieval import RagService
from jev_core.storage import IndexJobs, KnowledgeStore
from jev_core.web import DesktopSharing, SharingSettings, VERSION

ocr = LocalOCR(STORAGE_DIR / "ocr")
store = KnowledgeStore(STORAGE_DIR, DEFAULT_ROOT, DocumentParser(ocr))
local_jev = LocalNanoJev()
rag_service = RagService(store, local_jev)
jobs = IndexJobs(store)
sharing = DesktopSharing(store, local_jev, STORAGE_DIR / "web-sharing.json")


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(sharing.start_saved)
    yield
    await asyncio.to_thread(sharing.close, wait=True)
    await asyncio.to_thread(jobs.close)


app = FastAPI(title="JEV · 本地文档检索", version=VERSION, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
dist = BASE_DIR / "frontend" / "dist"
if (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def local_origin_only(request, call_next):
    from fastapi.responses import JSONResponse
    desktop_token = os.getenv("JEV_DESKTOP_TOKEN", "")
    if desktop_token and not hmac.compare_digest(request.headers.get("x-jev-desktop-token", ""), desktop_token):
        return JSONResponse({"detail": "此桌面服务仅允许当前 JEV 程序访问"}, status_code=403)
    origin = request.headers.get("origin")
    allowed = {"http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5173", "http://localhost:5173"}
    if desktop_token:
        allowed = {os.getenv("JEV_DESKTOP_ORIGIN", "")}
    if origin and origin not in allowed:
        return JSONResponse({"detail": "仅允许本机 JEV 页面访问"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class SourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=3000)
    top_k: int = Field(default=12, ge=1, le=30)
    max_evidence: int = Field(default=3, ge=1, le=6)
    library_id: str | None = None

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("请输入问题")
        return value.strip()


@app.get("/")
async def index():
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
@app.get("/api/config")
async def config():
    return {"service": "JEV", "version": VERSION, **store.status(), "local_jev": local_jev.status(),
            "ocr": ocr.status(), "libraries": store.libraries(), "job": jobs.status(),
            "answer_mode": "original-text-only", "retrieval_top_k": 12}


@app.get("/api/sharing")
async def sharing_status():
    return sharing.status()


@app.post("/api/sharing")
async def sharing_update(body: SharingSettings):
    try:
        return await asyncio.to_thread(sharing.update, body)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/source-root")
async def source_root():
    return {"source_root": store.status()["source_root"], "libraries": store.libraries()}


def start_index(root, uploads=None):
    try:
        return {"job": jobs.start(root, uploads), "current": store.status()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/source-root", status_code=202)
async def update_source_root(request: SourceRequest):
    return start_index(request.path)


def choose_directory():
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return filedialog.askdirectory(initialdir=store.status()["source_root"]["path"], title="选择 JEV 文档目录")
    finally:
        if root is not None:
            root.destroy()


picker_lock = asyncio.Lock()


@app.post("/api/source-root/pick")
async def pick_source_root():
    if picker_lock.locked():
        raise HTTPException(409, "目录选择窗口已经打开")
    try:
        async with picker_lock:
            path = await asyncio.to_thread(choose_directory)
        return {"cancelled": not bool(path), "path": path or None}
    except Exception as exc:
        raise HTTPException(400, "无法打开系统目录选择器，请直接输入路径。" + str(exc)) from exc


@app.post("/api/documents/scan-workspace", status_code=202)
@app.post("/api/index/rebuild", status_code=202)
async def scan_workspace():
    return start_index(store.status()["source_root"]["path"])


@app.get("/api/index/job")
async def index_job():
    return {"job": jobs.status()}


@app.post("/api/index/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    return {"job": jobs.cancel(job_id)}


@app.get("/api/documents")
async def documents():
    snapshot = store.snapshot()
    return {"documents": [{k: v for k, v in d.items() if k != "blob"} for d in snapshot["documents"]],
            "status": store.status(snapshot)}


def find_document(document_id, library_id, generation):
    try:
        return store.document(document_id, library_id, generation)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/documents/{document_id}")
async def document_content(document_id: str, library_id: str | None = None, generation: str | None = None):
    document, blocks, snapshot = find_document(document_id, library_id, generation)
    return {"document": {k: v for k, v in document.items() if k != "blob"}, "blocks": blocks,
            "library_id": snapshot["library_id"], "generation": snapshot["generation"]}


@app.get("/api/documents/{document_id}/raw")
async def raw_document(document_id: str, library_id: str | None = None, generation: str | None = None):
    document, _, _ = find_document(document_id, library_id, generation)
    return FileResponse(store.raw_path(document), filename=document["name"], media_type="application/octet-stream")


@app.get("/api/media/{asset_id}")
async def media(asset_id: str):
    if not re.fullmatch(r"[0-9a-f]{64}", asset_id):
        raise HTTPException(404, "图片不存在")
    path = STORAGE_DIR / "ocr" / (asset_id + ".png")
    if not path.is_file():
        raise HTTPException(404, "图片不存在")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@app.post("/api/documents/upload", status_code=202)
async def upload_documents(files: list[UploadFile] = File(...)):
    if len(files) > 30:
        raise HTTPException(400, "一次最多导入 30 份文档")
    uploads = []
    for upload in files:
        name = Path((upload.filename or "document.txt").replace("\\", "/")).name
        if Path(name).suffix.lower() not in SUPPORTED:
            raise HTTPException(415, f"不支持此文件格式：{name}")
        data = await upload.read(MAX_BYTES + 1)
        await upload.close()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"{name} 超过 32 MB")
        if data:
            uploads.append((name, data))
    if not uploads:
        raise HTTPException(400, "没有可导入的内容")
    return start_index(store.status()["source_root"]["path"], uploads)


@app.delete("/api/documents/{document_id}")
async def delete_document(document_id: str, generation: str):
    if jobs.status() and jobs.status()["state"] == "running":
        raise HTTPException(409, "索引期间无法移除文档，请等待或取消索引")
    try:
        await asyncio.to_thread(store.delete, document_id, generation)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": document_id, **store.status()}


@app.post("/api/query")
async def query(request: QueryRequest):
    try:
        return await asyncio.to_thread(rag_service.query, request.question, request.top_k, request.max_evidence, request.library_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
