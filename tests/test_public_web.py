import threading
from pathlib import Path

from fastapi.testclient import TestClient

from jev_core.parsing import DocumentParser
from jev_core.storage import KnowledgeStore
from jev_core.web import DesktopSharing, PublicReader, SharingSettings, create_public_app


class Model:
    def rank(self, question, candidates):
        return [{**item, "jev": {"supports_over_none": True, "choice": "c0", "batch": 0, "probability": .9}}
                for item in candidates]

    def status(self):
        return {"model": "test", "private_path": "SECRET-PATH"}


def library(tmp_path):
    root = tmp_path / "private-root"
    root.mkdir()
    (root / "事实.md").write_text("资料借阅期限是十四天。", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "storage", root, DocumentParser())
    store.build(root, lambda _: None, threading.Event())
    return store


def test_query_surface_has_no_management_or_source_disclosure(tmp_path):
    store = library(tmp_path)
    reader = PublicReader(lambda: (store.snapshot(), "same"), Model())
    client = TestClient(create_public_app(reader, lambda: True), base_url="http://127.0.0.1")
    result = client.post("/api/query", json={"question": "资料借阅期限"})
    assert result.status_code == 200
    assert result.json()["evidence"][0]["text"] == "资料借阅期限是十四天。"
    assert "private-root" not in result.text and "SECRET-PATH" not in result.text
    assert "source_url" not in result.text and "generation" not in result.text
    for route in ["/api/documents", "/api/source-root", "/api/config", "/api/sharing", "/openapi.json", "/docs", "/ui/admin.js"]:
        assert client.get(route).status_code == 404
    for route in ["/api/source-root", "/api/index/rebuild", "/api/documents/upload"]:
        assert client.post(route, json={"path": str(tmp_path)}).status_code == 404
    assert client.post("/api/query", json={"question": "资料", "library_id": "private"}).status_code == 422
    assert client.post("/api/query", json={"question": "资料"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/query", json={"question": "x" * 70000}).status_code == 413


def test_revocation_during_query_does_not_return_old_evidence(tmp_path):
    from jev_core.web import AccessChanged
    import pytest
    store = library(tmp_path)
    revision = [0]

    class RevokingModel(Model):
        def rank(self, question, candidates):
            revision[0] += 1
            return super().rank(question, candidates)

    reader = PublicReader(lambda: (store.snapshot(), revision[0]), RevokingModel())
    with pytest.raises(AccessChanged):
        reader.query("资料借阅期限")


def test_desktop_enable_persist_and_stop(tmp_path):
    import socket
    import urllib.request
    store = library(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    sharing = DesktopSharing(store, Model(), tmp_path / "sharing.json")
    assert not sharing.status()["enabled"]
    try:
        active = sharing.update(SharingSettings(enabled=True, port=port))
        assert active["running"]
        with urllib.request.urlopen(active["url"] + "/api/health", timeout=3) as response:
            assert response.status == 200
        assert DesktopSharing(store, Model(), sharing.path).settings.enabled
        assert not sharing.update(SharingSettings(enabled=False, port=port))["running"]
    finally:
        sharing.close()


def test_port_conflict_and_corrupt_settings_fail_closed(tmp_path):
    import pytest
    import socket
    store = library(tmp_path)
    file = tmp_path / "sharing.json"
    file.write_text("bad json", encoding="utf-8")
    sharing = DesktopSharing(store, Model(), file)
    assert not sharing.status()["enabled"]
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(RuntimeError):
            sharing.update(SharingSettings(enabled=True, port=occupied.getsockname()[1]))
    assert not sharing.status()["running"]


def test_settings_write_failure_closes_new_listener(tmp_path, monkeypatch):
    import pytest
    import socket
    store = library(tmp_path)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    def fail(*_):
        raise OSError("read only")
    monkeypatch.setattr("jev_core.web.atomic_json", fail)
    sharing = DesktopSharing(store, Model(), tmp_path / "sharing.json")
    with pytest.raises(RuntimeError):
        sharing.update(SharingSettings(enabled=True, port=port))
    assert not sharing.status()["running"] and not sharing.status()["enabled"]
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
