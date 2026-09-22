"""Password-protected administration and explicit, immutable publication grants."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .common import atomic_json, now
from .web import VERSION, mount_ui, secure_surface

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Jev-Change-Me-2026!"
COOKIE = "jev_admin_session"


class Credentials:
    def __init__(self, file):
        self.file = Path(file)
        self.lock = threading.RLock()
        self.sessions = {}
        self.attempts = defaultdict(deque)
        if self.file.exists():
            self.value = json.loads(self.file.read_text(encoding="utf-8"))
            if not {"username", "salt", "password_hash", "must_change"} <= self.value.keys():
                raise ValueError("管理员凭据损坏，请从备份恢复")
        else:
            self.value = self.record(DEFAULT_PASSWORD, True)
            atomic_json(self.file, self.value)
            self.file.chmod(0o600)

    @staticmethod
    def encode(password, salt):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 600000).hex()

    def record(self, password, must_change=False):
        salt = secrets.token_hex(16)
        return {"username": DEFAULT_USERNAME, "salt": salt,
                "password_hash": self.encode(password, salt), "must_change": must_change}

    def matches(self, password):
        return hmac.compare_digest(self.encode(password, self.value["salt"]), self.value["password_hash"])

    def session(self):
        token = secrets.token_urlsafe(32)
        value = {"csrf": secrets.token_urlsafe(32), "expires": time.monotonic() + 8 * 3600}
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = value
        return token, value

    def login(self, username, password, peer):
        with self.lock:
            now_mono = time.monotonic()
            for key in list(self.attempts):
                while self.attempts[key] and self.attempts[key][0] < now_mono - 600:
                    self.attempts[key].popleft()
                if not self.attempts[key]:
                    del self.attempts[key]
            if len(self.attempts[peer]) >= 8 or len(self.attempts["all"]) >= 64:
                raise HTTPException(429, "登录尝试过多，请十分钟后重试")
            valid = self.matches(password)
            if username != self.value["username"] or not valid:
                self.attempts[peer].append(now_mono)
                self.attempts["all"].append(now_mono)
                raise HTTPException(401, "用户名或密码错误")
            self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now_mono}
            if len(self.sessions) >= 32:
                self.sessions.pop(next(iter(self.sessions)))
            return self.session()

    def authenticate(self, token, csrf=None, write=False, allow_initial=False):
        with self.lock:
            value = self.sessions.get(hashlib.sha256((token or "").encode()).hexdigest())
            if not value or value["expires"] <= time.monotonic():
                raise HTTPException(401, "请先登录管理端")
            if write and not hmac.compare_digest(csrf or "", value["csrf"]):
                raise HTTPException(403, "会话校验失败，请刷新页面")
            if self.value["must_change"] and not allow_initial:
                raise HTTPException(403, "首次登录必须修改默认密码")
            return value

    def change(self, old, new):
        with self.lock:
            if not self.matches(old):
                raise HTTPException(400, "当前密码错误")
            if new == DEFAULT_PASSWORD or self.matches(new):
                raise HTTPException(400, "新密码不能与当前密码或默认密码相同")
            updated = self.record(new)
            atomic_json(self.file, updated)
            self.file.chmod(0o600)
            self.value = updated
            self.sessions.clear()
            return self.session()


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    library_id: str = Field(min_length=1, max_length=40)
    generation: str = Field(min_length=1, max_length=40)
    document_ids: list[str] = Field(max_length=5000)


class Publication:
    def __init__(self, store, credentials, file):
        self.store, self.credentials, self.file = store, credentials, Path(file)
        self.lock = threading.RLock()
        self.value = {"revision": secrets.token_hex(16), "grants": []}
        if self.file.exists():
            self.value = json.loads(self.file.read_text(encoding="utf-8"))
            for grant in self.value["grants"]:
                Grant.model_validate(grant)

    def set(self, grants):
        prepared, seen = [], set()
        for grant in grants:
            snapshot = self.store.snapshot(grant.library_id)
            if snapshot["generation"] != grant.generation:
                raise ValueError("索引已更新，请刷新文档列表后重新设置")
            ids = set(grant.document_ids)
            if not ids <= {doc["id"] for doc in snapshot["documents"]}:
                raise ValueError("所选文档不在此目录的当前索引中")
            if grant.library_id in seen:
                raise ValueError("目录重复")
            seen.add(grant.library_id)
            if ids:
                prepared.append({**grant.model_dump(), "document_ids": sorted(ids)})
        value = {"revision": secrets.token_hex(16), "updated_at": now(), "grants": prepared}
        with self.lock:
            atomic_json(self.file, value)
            self.value = value
        return value

    def source(self):
        with self.lock:
            revision = (self.value["revision"], self.credentials.value["must_change"])
            if self.credentials.value["must_change"]:
                return None, revision
            snapshot = {"library_id": "published", "generation": self.value["revision"],
                        "source_root": "", "documents": [], "blocks": []}
            for grant in self.value["grants"]:
                original = self.store.snapshot(grant["library_id"], grant["generation"])
                ids = set(grant["document_ids"])
                snapshot["documents"].extend(doc for doc in original["documents"] if doc["id"] in ids)
                snapshot["blocks"].extend(block for block in original["blocks"] if block["document_id"] in ids)
            return snapshot, revision

    def available(self):
        with self.lock:
            return not self.credentials.value["must_change"] and bool(self.value["grants"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class Scan(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class Publish(BaseModel):
    grants: list[Grant] = Field(max_length=100)


def create_admin_app(store, jobs, model, credentials, publication, web_info, external_origin=None, secure_cookie=False):
    app = FastAPI(title="JEV 管理端", docs_url=None, redoc_url=None, openapi_url=None)
    secure_surface(app, external_origin)
    mount_ui(app, "admin.html")

    def auth(request, *, write=False, initial=False):
        return credentials.authenticate(request.cookies.get(COOKIE), request.headers.get("x-csrf-token"),
                                        write=write, allow_initial=initial)

    def signed_in(response, token, session):
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=secure_cookie,
                            max_age=8 * 3600, path="/")
        return {"username": credentials.value["username"], "must_change": credentials.value["must_change"], "csrf_token": session["csrf"]}

    def audit(action, request):
        # Audit actions, not passwords, query contents or document text.
        with credentials.lock:
            with (credentials.file.parent / "audit.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"at": now(), "action": action, "peer": request.client.host}, ensure_ascii=False) + "\n")

    @app.post("/api/admin/login")
    async def login(body: Login, request: Request, response: Response):
        token, session = await asyncio.to_thread(credentials.login, body.username, body.password, request.client.host)
        audit("login", request)
        return signed_in(response, token, session)

    @app.get("/api/admin/session")
    async def session(request: Request):
        value = auth(request, initial=True)
        return {"username": credentials.value["username"], "must_change": credentials.value["must_change"], "csrf_token": value["csrf"]}

    @app.post("/api/admin/password")
    async def password(body: PasswordChange, request: Request, response: Response):
        auth(request, write=True, initial=True)
        token, session = await asyncio.to_thread(credentials.change, body.current_password, body.new_password)
        audit("change_password", request)
        return signed_in(response, token, session)

    @app.post("/api/admin/logout")
    async def logout(request: Request, response: Response):
        auth(request, write=True, initial=True)
        with credentials.lock:
            credentials.sessions.pop(hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(), None)
        response.delete_cookie(COOKIE, path="/")
        return {"logged_out": True}

    @app.get("/api/admin/status")
    async def status(request: Request):
        auth(request)
        return {"service": "JEV-admin", "version": VERSION, "model": model.status(),
                "job": jobs.status(), "publication": publication.value, "web": web_info}

    @app.get("/api/admin/libraries")
    async def libraries(request: Request):
        auth(request)
        output = []
        for library in store.libraries():
            snapshot = store.snapshot(library["id"])
            output.append({**library, "generation": snapshot["generation"],
                           "documents": [{key: doc[key] for key in ["id", "name", "relative_path", "size"]} for doc in snapshot["documents"]]})
        return {"libraries": output, "publication": publication.value}

    @app.post("/api/admin/scan", status_code=202)
    async def scan(body: Scan, request: Request):
        auth(request, write=True)
        try:
            job = jobs.start(body.path)
            audit("scan", request)
            return {"job": job}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/admin/cancel")
    async def cancel(request: Request):
        auth(request, write=True)
        job = jobs.status()
        return {"job": jobs.cancel(job["id"]) if job else None}

    @app.post("/api/admin/publication")
    async def publish(body: Publish, request: Request):
        auth(request, write=True)
        try:
            result = await asyncio.to_thread(publication.set, body.grants)
            audit("publish_access", request)
            return result
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    return app
