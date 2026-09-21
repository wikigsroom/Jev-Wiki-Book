"""Verify the actual embedded backend handshake, authorization, and clean exit."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

PROJECT = Path(__file__).resolve().parents[2]
BACKEND = PROJECT / "desktop/build/backend"
ROOT = PROJECT / "desktop/build/process-smoke"
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "JEV").mkdir(exist_ok=True)
secret = secrets.token_hex(32)
env = {**os.environ, "JEV_DESKTOP_TOKEN": secret, "JEV_PARENT_PID": str(os.getpid()), "JEV_STORAGE_DIR": str(ROOT / "storage"), "JEV_SOURCE_ROOT": str(ROOT / "JEV"), "JEV_MODELS_DIR": str(PROJECT / "models")}
log = (ROOT / "stderr.log").open("w", encoding="utf-8")
process = subprocess.Popen([str(BACKEND / "python/python.exe"), "-I", "-B", "-X", "utf8", "-u", str(BACKEND / "backend_entry.py")], cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8")
try:
    line = process.stdout.readline().strip()
    assert line.startswith("JEV_READY "), line
    ready = json.loads(line[10:])
    assert ready["pid"] == process.pid
    origin = f"http://127.0.0.1:{ready['port']}"
    assert ready["port"] != 8765
    def request(route, token=None, method="GET", request_origin=None):
        headers = {"X-JEV-Desktop-Token": token} if token else {}
        if request_origin:
            headers["Origin"] = request_origin
        try:
            with urllib.request.urlopen(urllib.request.Request(origin + route, method=method, headers=headers), timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
    for _ in range(50):
        try:
            status, body = request("/api/health", secret)
            if status == 200:
                break
        except OSError:
            pass
        time.sleep(.1)
    else:
        raise AssertionError("Backend never became healthy")
    assert request("/api/health")[0] == 403
    assert request("/api/health", "wrong")[0] == 403
    assert request("/api/health", secret, request_origin="https://unrelated.example")[0] == 403
    assert request("/api/health", secret, request_origin=origin)[0] == 200
    assert request("/api/desktop/shutdown", method="POST")[0] == 403
    assert request("/api/desktop/shutdown", secret, "POST")[0] == 200
    process.wait(timeout=10)
    assert process.returncode == 0
    result = {"passed": True, "ephemeral_port": ready["port"], "unauthenticated_requests_rejected": True, "foreign_origins_rejected": True, "clean_exit": True, "embedded_python": str(BACKEND / "python/python.exe")}
    (ROOT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
finally:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    log.close()
