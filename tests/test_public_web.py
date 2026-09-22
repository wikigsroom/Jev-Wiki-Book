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
    sharing.update(SharingSettings(enabled=False))
    restored = DesktopSharing(store, Model(), file)
    assert not restored.settings.enabled and restored.error is None


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


def test_cancelled_request_keeps_worker_admission_slot():
    import asyncio
    import pytest
    from fastapi import HTTPException
    entered, release = threading.Event(), threading.Event()
    reader = PublicReader(None, None)

    def slow_query(question):
        entered.set()
        assert release.wait(5)
        return {"question": question}

    reader.query = slow_query

    async def verify():
        task = asyncio.create_task(reader.answer("first"))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(HTTPException) as error:
                await reader.answer("second")
            assert error.value.status_code == 429
        finally:
            release.set()
        for _ in range(100):
            if reader.busy.acquire(blocking=False):
                reader.busy.release()
                break
            await asyncio.sleep(.01)
        assert await reader.answer("third") == {"question": "third"}

    asyncio.run(verify())


def test_native_listener_immediate_restart_and_conflict():
    import socket
    import urllib.request
    import pytest
    from jev_core.web import ThreadServer
    app = create_public_app(PublicReader(None, None), lambda: False)
    port = 0
    for _ in range(3):
        server = ThreadServer(app, "127.0.0.1", port)
        port = server.port
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/health", headers={"Connection": "close"})
            with opener.open(request, timeout=3) as response:
                assert response.status == 200
                response.read()
            with pytest.raises(OSError):
                ThreadServer(app, "127.0.0.1", port)
        finally:
            server.stop()
            server.wait()
        assert not server.thread.is_alive()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_shared_reader_survives_listener_replacement(tmp_path):
    import socket
    store = library(tmp_path)
    sharing = DesktopSharing(store, Model(), tmp_path / "sharing.json")
    reader = sharing.reader
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    try:
        sharing.update(SharingSettings(enabled=True, port=port))
        assert sharing.available()
        assert reader.busy.acquire(blocking=False)
        sharing.update(SharingSettings(enabled=False, port=port))
        sharing.update(SharingSettings(enabled=True, port=port))
        assert sharing.reader is reader
        assert not sharing.reader.busy.acquire(blocking=False)
        reader.busy.release()
    finally:
        sharing.close(wait=True)


def test_disable_revokes_active_query_without_holding_source_lock(tmp_path):
    import concurrent.futures
    import socket
    import time
    import urllib.request
    import urllib.error
    entered, release = threading.Event(), threading.Event()

    class SlowModel(Model):
        def rank(self, question, candidates):
            entered.set()
            assert release.wait(5)
            return super().rank(question, candidates)

    sharing = DesktopSharing(library(tmp_path), SlowModel(), tmp_path / "sharing.json")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    sharing.update(SharingSettings(enabled=True, port=port))

    def query():
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/query", data=b'{"question":"test"}', headers={"Content-Type": "application/json"})
        # Ensure the fixture query actually reaches the model.
        request.data = '{"question":"资料借阅期限"}'.encode()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=8) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        result = executor.submit(query)
        try:
            assert entered.wait(3)
            stopped = executor.submit(sharing.update, SharingSettings(enabled=False, port=port))
            deadline = time.monotonic() + 2
            while sharing.settings.enabled and time.monotonic() < deadline:
                time.sleep(.01)
            assert not sharing.settings.enabled
            release.set()
            assert not stopped.result(timeout=3)["running"]
            assert result.result(timeout=3) == 409
        finally:
            release.set()
            sharing.close(wait=True)
