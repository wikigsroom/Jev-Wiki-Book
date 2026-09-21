import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def test_private_desktop_backend_requires_token_and_exact_origin(monkeypatch):
    import app
    monkeypatch.setenv("JEV_DESKTOP_TOKEN", "test-token")
    monkeypatch.setenv("JEV_DESKTOP_ORIGIN", "http://127.0.0.1:49999")
    with TestClient(app.app, base_url="http://127.0.0.1:49999") as client:
        assert client.get("/api/health").status_code == 403
        assert client.get("/", headers={"X-JEV-Desktop-Token": "wrong"}).status_code == 403
        good = {"X-JEV-Desktop-Token": "test-token", "Origin": "http://127.0.0.1:49999"}
        assert client.get("/api/health", headers=good).status_code == 200
        for origin in ["https://evil.test", "http://127.0.0.1:8765", "null"]:
            assert client.get("/api/health", headers={**good, "Origin": origin}).status_code == 403


def test_runtime_directories_are_independent_of_packaged_code(tmp_path):
    env = {**os.environ, "JEV_STORAGE_DIR": str(tmp_path / "JEV-data"), "JEV_MODELS_DIR": str(tmp_path / "JEV-models"), "JEV_SOURCE_ROOT": str(tmp_path / "JEV")}
    code = "from jev_core.common import *; assert STORAGE_DIR.name == 'JEV-data'; assert MODELS_DIR.name == 'JEV-models'; assert DEFAULT_ROOT.name == 'JEV'; assert BASE_DIR != STORAGE_DIR"
    subprocess.run([sys.executable, "-c", code], env=env, check=True, cwd=Path(__file__).resolve().parents[2])


def test_desktop_python_blocks_external_network_without_os_changes():
    code = "from desktop.backend_entry import enforce_offline; import socket; enforce_offline(); s=socket.socket(); assert s.connect_ex(('203.0.113.1',443)) == 10013\ntry: socket.getaddrinfo('example.com',443)\nexcept OSError: pass\nelse: raise AssertionError('external DNS was not blocked')"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).resolve().parents[2])
