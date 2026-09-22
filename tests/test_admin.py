import json
import threading

import pytest
from fastapi.testclient import TestClient

from jev_core.admin import Credentials, DEFAULT_PASSWORD, Publication, create_admin_app
from jev_core.parsing import DocumentParser
from jev_core.storage import KnowledgeStore, IndexJobs
from jev_core.web import PublicReader, create_public_app
from test_public_web import Model


@pytest.fixture
def system(tmp_path):
    root = tmp_path / "confidential-folder"
    root.mkdir()
    (root / "公开.md").write_text("服务联系电话是 12345。", encoding="utf-8")
    (root / "保密.md").write_text("保密项目代号是 TOP-SECRET-749。", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "storage", root, DocumentParser())
    store.build(root, lambda _: None, threading.Event())
    credentials = Credentials(tmp_path / "admin.json")
    publication = Publication(store, credentials, tmp_path / "publication.json")
    model = Model()
    admin = TestClient(create_admin_app(store, IndexJobs(store), model, credentials, publication, {}), base_url="http://127.0.0.1:18765")
    web = TestClient(create_public_app(PublicReader(publication.source, model), publication.available), base_url="http://127.0.0.1:18766")
    return admin, web, store, credentials, publication


def login(admin, password=DEFAULT_PASSWORD):
    response = admin.post("/api/admin/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    return {"x-csrf-token": response.json()["csrf_token"]}


def activate(admin):
    headers = login(admin)
    result = admin.post("/api/admin/password", headers=headers, json={"current_password": DEFAULT_PASSWORD, "new_password": "Different-Password-2026!"})
    assert result.status_code == 200
    return {"x-csrf-token": result.json()["csrf_token"]}


def test_auth_initial_password_csrf_and_session_revocation(system):
    admin, web, store, credentials, publication = system
    assert admin.get("/api/admin/libraries").status_code == 401
    assert web.post("/api/query", json={"question": "联系电话"}).status_code == 503
    headers = login(admin)
    old_cookie = admin.cookies.get(credentials.cookie_name)
    assert admin.get("/api/admin/status").status_code == 403
    assert admin.post("/api/admin/password", json={"current_password": DEFAULT_PASSWORD, "new_password": "Different-Password-2026!"}).status_code == 403
    assert admin.post("/api/admin/password", headers=headers, json={"current_password": "wrong", "new_password": "Different-Password-2026!"}).status_code == 400
    headers = activate(admin)
    assert admin.get("/api/admin/status").status_code == 200
    with pytest.raises(Exception) as error:
        credentials.authenticate(old_cookie)
    assert error.value.status_code == 401
    assert DEFAULT_PASSWORD not in credentials.file.read_text()
    assert "Different-Password" not in credentials.file.read_text()
    assert admin.post("/api/admin/scan", json={"path": "/tmp"}).status_code == 403
    assert admin.post("/api/admin/logout", headers=headers, json={}).status_code == 200
    assert admin.get("/api/admin/status").status_code == 401


def test_selected_documents_only_and_revocation_persist(system):
    admin, web, store, credentials, publication = system
    headers = activate(admin)
    snapshot = store.snapshot()
    public_doc = next(doc for doc in snapshot["documents"] if doc["name"] == "公开.md")
    grants = [{"library_id": snapshot["library_id"], "generation": snapshot["generation"], "document_ids": [public_doc["id"]]}]
    assert admin.post("/api/admin/publication", headers=headers, json={"grants": grants}).status_code == 200
    answer = web.post("/api/query", json={"question": "服务联系电话"})
    assert answer.status_code == 200 and "12345" in answer.text
    assert "confidential-folder" not in answer.text
    assert "TOP-SECRET" not in web.post("/api/query", json={"question": "保密项目代号"}).text
    assert web.get("/api/admin/libraries").status_code == 404
    assert web.post("/api/admin/publication", json={"grants": grants}).status_code == 404
    restored = Publication(store, Credentials(credentials.file), publication.file)
    assert len(restored.source()[0]["documents"]) == 1
    assert admin.post("/api/admin/publication", headers=headers, json={"grants": []}).status_code == 200
    assert web.post("/api/query", json={"question": "服务联系电话"}).status_code == 503


def test_publish_rejects_foreign_documents_and_stale_snapshot(system):
    admin, web, store, credentials, publication = system
    headers = activate(admin)
    snapshot = store.snapshot()
    grant = {"library_id": snapshot["library_id"], "generation": snapshot["generation"], "document_ids": ["foreign"]}
    assert admin.post("/api/admin/publication", headers=headers, json={"grants": [grant]}).status_code == 409
    grant["document_ids"] = [snapshot["documents"][0]["id"]]
    store.build(store.default_root, lambda _: None, threading.Event())
    assert admin.post("/api/admin/publication", headers=headers, json={"grants": [grant]}).status_code == 409
    assert not publication.available()


def test_login_rate_limit_and_origin(system):
    admin, *_ = system
    for _ in range(8):
        assert admin.post("/api/admin/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert admin.post("/api/admin/login", json={"username": "admin", "password": DEFAULT_PASSWORD}).status_code == 429
    assert admin.post("/api/admin/login", json={"username": "admin", "password": DEFAULT_PASSWORD}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_publish_5000_documents_exceeds_old_body_limit(system, monkeypatch):
    admin, web, store, credentials, publication = system
    headers = activate(admin)
    snapshot = store.snapshot()
    snapshot["documents"] = [{"id": f"{i:024x}"} for i in range(5000)]
    monkeypatch.setattr(store, "snapshot", lambda *args: snapshot)
    grant = {"library_id": snapshot["library_id"], "generation": snapshot["generation"],
             "document_ids": [doc["id"] for doc in snapshot["documents"]]}
    assert len(json.dumps({"grants": [grant]}).encode()) > 65536
    response = admin.post("/api/admin/publication", headers=headers, json={"grants": [grant]})
    assert response.status_code == 200, response.text
    assert len(publication.value["grants"][0]["document_ids"]) == 5000
    assert web.post("/api/query", json={"question": "x" * 70000}).status_code == 413


def test_revoked_session_cannot_commit_queued_publication(system, monkeypatch):
    import asyncio
    admin, _, store, credentials, publication = system
    headers = activate(admin)
    snapshot = store.snapshot()
    original = asyncio.to_thread

    async def revoke_before_worker(function, *args, **kwargs):
        with credentials.lock:
            credentials.sessions.clear()
        return await original(function, *args, **kwargs)

    monkeypatch.setattr("jev_core.admin.asyncio.to_thread", revoke_before_worker)
    grant = {"library_id": snapshot["library_id"], "generation": snapshot["generation"], "document_ids": [snapshot["documents"][0]["id"]]}
    response = admin.post("/api/admin/publication", headers=headers, json={"grants": [grant]})
    assert response.status_code == 401 and not publication.available()


def test_instances_keep_independent_admin_cookies(system, tmp_path):
    admin, _, store, credentials, _ = system
    activate(admin)
    other = Credentials(tmp_path / "other/admin.json")
    publication = Publication(store, other, tmp_path / "other/publication.json")
    second = TestClient(create_admin_app(store, IndexJobs(store), Model(), other, publication, {}),
                        base_url="http://127.0.0.1:19765", cookies=admin.cookies)
    activate(second)
    assert credentials.cookie_name != other.cookie_name
    admin.cookies.update(second.cookies)
    assert admin.get("/api/admin/status").status_code == 200
    assert second.get("/api/admin/status").status_code == 200


@pytest.mark.parametrize("change", [{"salt": "broken"}, {"password_hash": ""}, {"must_change": "false"}, {"username": []}])
def test_corrupt_credentials_never_reset_to_default(tmp_path, change):
    file = tmp_path / "admin.json"
    record = Credentials(file).value
    record.update(change)
    content = json.dumps(record)
    file.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="凭据损坏"):
        Credentials(file)
    assert file.read_text(encoding="utf-8") == content


def test_corrupt_publication_and_missing_snapshots_fail_closed(system):
    _, _, store, credentials, publication = system
    for value in [{"grants": []}, {"revision": "a" * 32, "grants": [{"library_id": "missing", "generation": "missing", "document_ids": ["missing"]}]}]:
        publication.file.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError, match="访问范围文件"):
            Publication(store, credentials, publication.file)


def test_rescan_keeps_only_explicitly_published_generation(system):
    admin, web, store, credentials, publication = system
    headers = activate(admin)
    snapshot = store.snapshot()
    public_doc = next(doc for doc in snapshot["documents"] if doc["name"] == "公开.md")
    grant = {"library_id": snapshot["library_id"], "generation": snapshot["generation"], "document_ids": [public_doc["id"]]}
    assert admin.post("/api/admin/publication", headers=headers, json={"grants": [grant]}).status_code == 200
    (store.default_root / "公开.md").write_text("服务联系电话是 SECRET-UNAPPROVED-678。", encoding="utf-8")
    store.build(store.default_root, lambda _: None, threading.Event())
    answer = web.post("/api/query", json={"question": "服务联系电话"})
    assert "12345" in answer.text and "SECRET-UNAPPROVED" not in answer.text
    restored = Publication(store, Credentials(credentials.file), publication.file)
    assert restored.source()[0]["generation"] == publication.value["revision"]
    assert "SECRET-UNAPPROVED" not in json.dumps(restored.source()[0])
