"""Restricted query surface: no filesystem, library listing, or management routes."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import ipaddress
import json
import logging
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BASE_DIR, atomic_json
from .retrieval import RagService

VERSION = "0.6.0"
UI_DIR = BASE_DIR / "web_ui"


def secure_surface(app, external_origin=None):
    """Reject browser cross-origin requests and unconfigured DNS hostnames."""
    extra_host = urlsplit(external_origin).hostname if external_origin else None

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        host = request.url.hostname or ""
        try:
            address = ipaddress.ip_address(host)
            accepted = address.is_private or address.is_loopback
        except ValueError:
            accepted = host in {"localhost", extra_host}
        origin = request.headers.get("origin")
        expected = str(request.base_url).rstrip("/")
        if not accepted or (origin and origin not in {expected, external_origin}):
            return JSONResponse({"detail": "不允许的访问来源"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "需要 JSON 请求"}, status_code=415)
            # Bound chunked bodies too; content-length alone is insufficient.
            size = 0
            body = bytearray()
            async for part in request.stream():
                size += len(part)
                if size > 65536:
                    return JSONResponse({"detail": "请求过大"}, status_code=413)
                body.extend(part)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response


def mount_ui(app, page):
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(UI_DIR / page)

    @app.get("/ui/{name}", include_in_schema=False)
    async def asset(name: str):
        allowed = {"site.css", "query.js"} if page == "query.html" else {"site.css", "admin.js"}
        if name not in allowed:
            raise HTTPException(404, "不存在")
        return FileResponse(UI_DIR / name)


class PublicQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("请输入问题")
        return value.strip()


class AccessChanged(Exception):
    pass


class PublicReader:
    def __init__(self, source, model):
        self.source = source
        self.model = model
        self.busy = threading.BoundedSemaphore(1)

    def query(self, question):
        snapshot, revision = self.source()
        if snapshot is None:
            raise AccessChanged()

        class FrozenStore:
            def snapshot(self, library_id=None):
                return snapshot

        result = RagService(FrozenStore(), self.model).query(question, 12, 3)
        if self.source()[1] != revision:
            raise AccessChanged()
        # Explicit response allowlist. Never expose full documents, paths, raw
        # URLs, model errors, library/generation IDs or candidate diagnostics.
        evidence = [{"citation_id": item["citation_id"],
                     "document_name": Path(item["document_name"].replace("\\", "/")).name,
                     "label": item["locator"]["label"], "text": item["text"]}
                    for item in result["evidence"]]
        return {"question": question, "status": result["status"], "evidence": evidence,
                "message": "" if evidence else "已开放的资料中未找到足以回答问题的原文。",
                "answer_mode": "original-text-only"}


def create_public_app(reader, available, external_origin=None):
    app = FastAPI(title="JEV 资料查询", docs_url=None, redoc_url=None, openapi_url=None)
    secure_surface(app, external_origin)
    mount_ui(app, "query.html")

    @app.get("/api/health")
    async def health():
        return {"service": "JEV-query", "version": VERSION, "available": bool(available())}

    @app.post("/api/query")
    async def query(body: PublicQuestion):
        if not available():
            raise HTTPException(503, "管理员尚未开放可查询资料")
        if not reader.busy.acquire(blocking=False):
            raise HTTPException(429, "正在处理其他查询，请稍后重试")
        try:
            return await asyncio.to_thread(reader.query, body.question)
        except AccessChanged:
            raise HTTPException(409, "可访问资料已变更，请重新查询") from None
        except Exception:
            logging.getLogger(__name__).exception("Public query failed")
            raise HTTPException(503, "查询暂时无法完成，请联系管理员检查本地服务") from None
        finally:
            reader.busy.release()
    return app


class ThreadServer:
    """Native Uvicorn listener with explicit bind failure and owned shutdown."""
    def __init__(self, app, host, port, **tls):
        import uvicorn
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind((host, port))
            self.socket.listen(128)
            self.port = self.socket.getsockname()[1]
            config = uvicorn.Config(app, host=host, port=self.port, log_level="warning", access_log=False,
                                    loop="asyncio", http="h11", ws="none", proxy_headers=False,
                                    timeout_graceful_shutdown=2, **tls)
            self.server = uvicorn.Server(config)
            self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
            self.thread.start()
            for _ in range(100):
                if self.server.started:
                    return
                if not self.thread.is_alive():
                    break
                time.sleep(.05)
            raise RuntimeError("服务启动失败")
        except BaseException:
            if hasattr(self, "server"):
                self.server.should_exit = True
            self.socket.close()
            raise

    def stop(self):
        self.server.should_exit = True
        self.thread.join(4)
        if self.thread.is_alive():
            self.server.force_exit = True
        self.socket.close()


class SharingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    port: int = Field(default=18766, ge=1024, le=65535)
    lan: bool = False


class DesktopSharing:
    def __init__(self, store, model, path):
        self.store, self.model, self.path = store, model, path
        self.lock = threading.RLock()
        self.settings = SharingSettings()
        self.server = None
        self.revision = 0
        self.error = None
        if path.exists():
            try:
                self.settings = SharingSettings.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.error = "共享设置无法读取，查询端已关闭。请重新保存设置。"

    def source(self):
        with self.lock:
            if not self.settings.enabled:
                return None, (self.revision, None)
            snapshot = self.store.snapshot()
            return snapshot, (self.revision, snapshot["library_id"], snapshot["generation"])

    def status(self):
        with self.lock:
            return {**self.settings.model_dump(), "running": self.server is not None,
                    "url": f"http://127.0.0.1:{self.settings.port}" if self.server else None, "error": self.error}

    def update(self, settings, persist=True):
        with self.lock:
            if settings == self.settings and (self.server is not None) == settings.enabled:
                return self.status()
            old_server = self.server
            # Revoke in-flight results before replacing the owned listener.
            self.server = None
            self.revision += 1
            if old_server:
                old_server.stop()
            self.settings = settings
            self.error = None
            try:
                if settings.enabled:
                    reader = PublicReader(self.source, self.model)
                    app = create_public_app(reader, lambda: self.settings.enabled)
                    self.server = ThreadServer(app, "0.0.0.0" if settings.lan else "127.0.0.1", settings.port)
                if persist:
                    atomic_json(self.path, settings.model_dump())
            except Exception as exc:
                self.settings = settings.model_copy(update={"enabled": False})
                failed_server, self.server = self.server, None
                if failed_server:
                    failed_server.stop()
                self.error = "查询端未能启用，请检查端口占用和设置目录的写入权限。"
                raise RuntimeError(self.error) from exc
            return self.status()

    def start_saved(self):
        try:
            self.update(self.settings, persist=False)
        except RuntimeError:
            logging.getLogger(__name__).warning("Saved web listener could not start")

    def close(self):
        with self.lock:
            self.revision += 1
            self.settings = self.settings.model_copy(update={"enabled": False})
            server, self.server = self.server, None
        if server:
            server.stop()
