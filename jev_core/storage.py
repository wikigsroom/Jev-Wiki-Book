from __future__ import annotations

import copy
import json
import logging
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Callable

from .common import BASE_DIR, MODELS_DIR, MAX_BYTES, SUPPORTED, atomic_json, digest, now, resolve_root
from .parsing import DocumentParser, PARSER_VERSION


class Cancelled(Exception):
    pass


class KnowledgeStore:
    """Independent directory libraries, immutable snapshots and atomic activation."""

    def __init__(self, storage: Path, default_root: Path, parser: DocumentParser):
        self.storage = storage
        self.default_root = default_root.resolve()
        self.parser = parser
        self.lock = threading.RLock()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.blobs = storage / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self.db_path = storage / "knowledge.sqlite3"
        self.config_path = storage / "source-root.json"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS libraries (id TEXT PRIMARY KEY, path TEXT NOT NULL, generation TEXT);
                CREATE TABLE IF NOT EXISTS snapshots (library_id TEXT, generation TEXT, payload TEXT NOT NULL,
                    PRIMARY KEY (library_id, generation));
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS parse_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            active = db.execute("SELECT value FROM metadata WHERE key='active' ").fetchone()
        if active:
            self.active_id = active[0]
        else:
            configured = self.default_root
            if self.config_path.exists():
                try:
                    configured = Path(json.loads(self.config_path.read_text(encoding="utf-8"))["path"])
                except (OSError, ValueError, KeyError):
                    pass
            # Preserve a missing selected path too: show an error instead of mixing its index with another root.
            configured = configured.resolve()
            self.active_id = self.library_id(configured)
            self._ensure_library(configured)
            with self.connect() as db:
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('active', ?)", (self.active_id,))

    def connect(self):
        return sqlite3.connect(self.db_path, timeout=30)

    @staticmethod
    def library_id(root: Path) -> str:
        return digest(os.path.normcase(str(root.resolve())))[:20]

    def _ensure_library(self, root: Path) -> str:
        library_id = self.library_id(root)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO libraries (id,path) VALUES (?,?)", (library_id, str(root)))
        return library_id

    def snapshot(self, library_id: str | None = None, generation: str | None = None) -> dict:
        with self.lock, self.connect() as db:
            key = library_id or self.active_id
            row = db.execute("SELECT path,generation FROM libraries WHERE id=?", (key,)).fetchone()
            if row is None:
                raise KeyError("知识库不存在")
            version = generation or row[1]
            if version:
                stored = db.execute("SELECT payload FROM snapshots WHERE library_id=? AND generation=?", (key, version)).fetchone()
                if stored is None:
                    raise KeyError("该索引版本不存在，请重新检索")
                return json.loads(stored[0])
            return {"library_id": key, "generation": None, "source_root": row[0], "indexed_at": None,
                    "documents": [], "blocks": [], "needs_reindex": True, "warnings": []}

    def status(self, snapshot: dict | None = None) -> dict:
        value = snapshot if snapshot is not None else self.snapshot()
        docs = value["documents"]
        coverage = {field: sum(d.get("coverage", {}).get(field, 0) for d in docs)
                    for field in ("native_blocks", "images", "images_recognized", "images_no_text", "images_unread", "searchable_blocks")}
        return {"library_id": value["library_id"], "generation": value["generation"],
                "source_root": {"path": value["source_root"], "is_default": Path(value["source_root"]) == self.default_root,
                                "default_path": str(self.default_root), "available": Path(value["source_root"]).is_dir()},
                "documents": len(docs), "blocks": len(value["blocks"]),
                "chunks": coverage["searchable_blocks"], "coverage": coverage,
                "indexed_at": value["indexed_at"], "needs_reindex": value.get("needs_reindex", False),
                "warnings": value.get("warnings", []), "errors": sum(bool(d.get("error")) for d in docs)}

    def libraries(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id,path,generation FROM libraries ORDER BY path").fetchall()
        return [{"id": row[0], "path": row[1], "indexed": bool(row[2]), "active": row[0] == self.active_id} for row in rows]

    def _commit(self, snapshot: dict, activate: bool) -> None:
        snapshot["generation"] = uuid.uuid4().hex
        snapshot["indexed_at"] = now()
        snapshot["needs_reindex"] = False
        encoded = json.dumps(snapshot, ensure_ascii=False)
        with self.lock, self.connect() as db:
            db.execute("INSERT OR IGNORE INTO libraries(id,path) VALUES (?,?)", (snapshot["library_id"], snapshot["source_root"]))
            db.execute("INSERT INTO snapshots VALUES (?,?,?)", (snapshot["library_id"], snapshot["generation"], encoded))
            db.execute("UPDATE libraries SET generation=? WHERE id=?", (snapshot["generation"], snapshot["library_id"]))
            if activate:
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('active',?)", (snapshot["library_id"],))
            db.commit()
            if activate:
                self.active_id = snapshot["library_id"]
        # The SQLite active pointer is authoritative; JSON is a human-readable compatibility record.
        if activate:
            try:
                atomic_json(self.config_path, {"path": snapshot["source_root"], "library_id": snapshot["library_id"]})
            except OSError:
                logging.getLogger(__name__).warning("索引已提交；兼容路径记录写入失败，仍以 SQLite 为准", exc_info=True)

    def _blob(self, data: bytes, suffix: str) -> tuple[str, str]:
        sha = digest(data)
        filename = sha + suffix.lower()
        target = self.blobs / filename
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".pending")
            temporary.write_bytes(data)
            os.replace(temporary, target)
        return filename, sha

    def raw_path(self, document: dict) -> Path:
        path = (self.blobs / document["blob"]).resolve()
        if path.parent != self.blobs.resolve():
            raise ValueError("无效的文档路径")
        return path

    def _parse(self, document: dict, progress: Callable[[str], None]) -> dict:
        key = document["sha256"] + ":" + digest(document["name"])[:12] + ":" + PARSER_VERSION + ":" + str(bool(self.parser.ocr and self.parser.ocr.status()["configured"]))
        with self.connect() as db:
            row = db.execute("SELECT payload FROM parse_cache WHERE key=?", (key,)).fetchone()
        if row:
            return json.loads(row[0])
        parsed = self.parser.parse(self.raw_path(document), document["name"], progress)
        # Retry unread images on future scans; never cache incomplete OCR as a completed parse.
        if not parsed["coverage"]["images_unread"]:
            with self.connect() as db:
                db.execute("INSERT OR REPLACE INTO parse_cache VALUES (?,?)", (key, json.dumps(parsed, ensure_ascii=False)))
        return parsed

    def _files(self, root: Path):
        generic = {".git", ".venv", "venv", "__pycache__", "node_modules", ".runtime", ".skills", "worktrees", "web_ui", "server_data", "build", "dist"}
        private = {p.resolve() for p in (self.storage, MODELS_DIR, BASE_DIR / "frontend", BASE_DIR / "static", BASE_DIR / "tests", BASE_DIR / "evals", BASE_DIR / "desktop", BASE_DIR / "release")}
        def on_error(exc):
            raise OSError(f"无法扫描目录：{exc}") from exc
        for current, directories, files in os.walk(root, topdown=True, followlinks=False, onerror=on_error):
            directories[:] = sorted(d for d in directories if d.lower() not in generic
                                    and (Path(current) / d).resolve() not in private
                                    and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                path = Path(current) / name
                if path.resolve() in {self.storage.parent / name for name in ("admin.json", "publication.json", "audit.jsonl", ".server.lock")}:
                    continue
                if path.suffix.lower() in SUPPORTED and not path.is_symlink() and not name.startswith("~$"):
                    yield path

    def _legacy_uploads(self, library_id: str) -> list[tuple[str, bytes]]:
        manifest_path = self.storage / "manifest.json"
        if library_id != self.active_id or not manifest_path.exists():
            return []
        try:
            legacy = json.loads(manifest_path.read_text(encoding="utf-8"))
            return [(d["name"], (self.storage / "documents" / Path(d["stored_name"]).name).read_bytes())
                    for d in legacy if d.get("origin") == "upload"]
        except (OSError, KeyError, ValueError):
            return []

    def build(self, root_value: str | Path, progress: Callable[[dict], None], cancel: threading.Event,
              uploads: list[tuple[str, bytes]] | None = None, activate: bool = True) -> dict:
        root = resolve_root(root_value)
        library_id = self.library_id(root)
        try:
            old = self.snapshot(library_id)
        except KeyError:
            old = {"documents": [], "generation": None}
        fresh = {"library_id": library_id, "source_root": str(root), "documents": [], "blocks": [], "warnings": []}

        def check(message: str = ""):
            if cancel.is_set():
                raise Cancelled("已取消；原知识库保持可用")
            if message:
                progress({"message": message})

        inputs = []
        if uploads is None:
            for path in self._files(root):
                check()
                if path.stat().st_size > MAX_BYTES:
                    raise ValueError(f"文件超过 32 MB：{path.relative_to(root)}；原索引未更改")
                inputs.append(("workspace", path.relative_to(root).as_posix(), path))
            inputs.extend(("upload", d["relative_path"], self.raw_path(d)) for d in old["documents"] if d["origin"] == "upload")
            if not old["generation"]:
                inputs.extend(("upload", name, data) for name, data in self._legacy_uploads(library_id))
        else:
            replacement_names = {name for name, _ in uploads}
            inputs.extend((d["origin"], d["relative_path"], self.raw_path(d)) for d in old["documents"]
                          if d["origin"] != "upload" or d["relative_path"] not in replacement_names)
            inputs.extend(("upload", name, data) for name, data in uploads)
        # Identity includes library, origin and exact relative path; identical content keeps all sources.
        seen = set()
        progress({"total": len(inputs), "completed": 0})
        for index, (origin, relative, data) in enumerate(inputs):
            check(f"解析 {relative}")
            if isinstance(data, Path):
                with data.open("rb") as source:
                    data = source.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError(f"文件超过 32 MB：{relative}；原索引未更改")
            identity = (origin, relative)
            if identity in seen:
                continue
            seen.add(identity)
            blob, sha = self._blob(data, Path(relative).suffix)
            document_id = digest(library_id + "\0" + origin + "\0" + relative)[:24]
            document = {"id": document_id, "name": Path(relative).name, "relative_path": relative,
                        "origin": origin, "blob": blob, "sha256": sha, "size": len(data), "library_id": library_id}
            try:
                parsed = self._parse(document, check)
            except Cancelled:
                raise
            except Exception as exc:
                raise RuntimeError(f"{relative} 解析失败：{exc}。原知识库未更改。") from exc
            document["coverage"] = parsed["coverage"]
            fresh["warnings"].extend(f"{relative}：{warning}" for warning in parsed["coverage"].get("warnings", []))
            document["block_count"] = len(parsed["blocks"])
            document["chunk_count"] = parsed["coverage"]["searchable_blocks"]
            document["error"] = None
            fresh["documents"].append(document)
            for block in parsed["blocks"]:
                value = copy.deepcopy(block)
                value.update(id=document_id + ":" + block["id"], document_id=document_id, document_name=document["name"],
                             relative_path=relative, library_id=library_id, origin=origin)
                if value["section"] == Path(blob).name:
                    value["section"] = document["name"]
                fresh["blocks"].append(value)
            progress({"completed": index + 1})
        check()
        self._commit(fresh, activate)
        return self.status(fresh)

    def document(self, document_id: str, library_id=None, generation=None) -> tuple[dict, list[dict], dict]:
        snapshot = self.snapshot(library_id, generation)
        document = next((d for d in snapshot["documents"] if d["id"] == document_id), None)
        if document is None:
            raise KeyError("文档不在这个索引版本中")
        return document, [b for b in snapshot["blocks"] if b["document_id"] == document_id], snapshot

    def delete(self, document_id: str, expected_generation: str) -> None:
        with self.lock:
            current = self.snapshot()
            if current["generation"] != expected_generation:
                raise ValueError("索引已更新，请刷新后再移除文档")
            if not any(d["id"] == document_id for d in current["documents"]):
                raise KeyError("文档不存在")
            current["documents"] = [d for d in current["documents"] if d["id"] != document_id]
            current["blocks"] = [b for b in current["blocks"] if b["document_id"] != document_id]
            self._commit(current, False)


class IndexJobs:
    def __init__(self, store: KnowledgeStore):
        self.store = store
        self.lock = threading.Lock()
        self.current: dict | None = None
        self.cancel_event = threading.Event()

    def status(self):
        with self.lock:
            return copy.deepcopy(self.current)

    def start(self, root: str, uploads=None) -> dict:
        resolve_root(root)
        with self.lock:
            if self.current and self.current["state"] == "running":
                raise RuntimeError("已有索引任务正在运行，请等待完成或取消")
            self.cancel_event = threading.Event()
            self.current = {"id": uuid.uuid4().hex, "state": "running", "source_root": root,
                            "message": "正在读取目录…", "total": 0, "completed": 0, "started_at": now()}
            initial = copy.deepcopy(self.current)
        def progress(fields):
            with self.lock:
                self.current.update(fields)
        def run():
            try:
                result = self.store.build(root, progress, self.cancel_event, uploads=uploads)
                progress({"state": "completed", "message": "索引已更新", "result": result, "finished_at": now()})
            except Cancelled as exc:
                progress({"state": "cancelled", "message": str(exc), "finished_at": now()})
            except Exception as exc:
                progress({"state": "failed", "message": str(exc), "finished_at": now()})
        threading.Thread(target=run, name="jev-index", daemon=True).start()
        return initial

    def cancel(self, job_id: str):
        with self.lock:
            if self.current and self.current["id"] == job_id and self.current["state"] == "running":
                self.cancel_event.set()
                self.current["message"] = "正在取消；当前文件处理完成后停止…"
            return copy.deepcopy(self.current)
