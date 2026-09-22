"""Exercise sharing through the real embedded backend in a disposable directory."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Version-specific report; previous release reports are preserved")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    project = Path(__file__).resolve().parents[2]
    root = Path(tempfile.mkdtemp(prefix="sharing-", dir=project / "desktop/build"))
    docs = root / "documents"
    docs.mkdir()
    (docs / "借阅规则.md").write_text("资料室文档借阅期限为十四天。每位读者最多同时借阅三份文档。", encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = secrets.token_hex(32)
    runtime = bundle / "JEV-runtime"
    env = {**os.environ, "JEV_DESKTOP_TOKEN": token, "JEV_PARENT_PID": str(os.getpid()),
           "JEV_STORAGE_DIR": str(root / "storage"), "JEV_SOURCE_ROOT": str(docs),
           "JEV_MODELS_DIR": str(bundle / "JEV-models"), "NANOJEV_CHECKPOINT_DIR": str(bundle / "JEV-models/nanojev"),
           "NANOJEV_DEVICE": "cpu", "NANOJEV_PRECISION": "fp32"}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = (root / "backend.log").open("w", encoding="utf-8")
    process = None
    origin = ""

    def request(url, data=None, authorized=False):
        headers = {"X-JEV-Desktop-Token": token} if authorized else {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            with opener.open(req, timeout=180) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def start():
        nonlocal process, origin
        process = subprocess.Popen([str(runtime / "python/python.exe"), "-I", "-B", "-X", "utf8", "-u", str(runtime / "backend_entry.py")],
                                   cwd=runtime, env=env, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8")
        line = process.stdout.readline().strip()
        assert line.startswith("JEV_READY "), line
        ready = json.loads(line[10:])
        assert ready["pid"] == process.pid
        origin = f"http://127.0.0.1:{ready['port']}"
        for _ in range(100):
            try:
                if request(origin + "/api/health", authorized=True)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        raise AssertionError("Backend not ready")

    def shutdown():
        assert request(origin + "/api/desktop/shutdown", {}, True)[0] == 200
        process.wait(timeout=15)
        assert process.returncode == 0

    try:
        start()
        assert request(origin + "/api/sharing")[0] == 403
        assert not request(origin + "/api/sharing", authorized=True)[1]["enabled"]
        assert request(origin + "/api/index/rebuild", {}, True)[0] in {200, 202}
        for _ in range(100):
            job = request(origin + "/api/index/job", authorized=True)[1]["job"]
            if job["state"] != "running":
                assert job["state"] == "completed", job
                break
            time.sleep(.1)
        assert request(origin + "/api/sharing", {"enabled": True, "port": port, "lan": False}, True)[0] == 200
        query_origin = f"http://127.0.0.1:{port}"
        assert request(query_origin + "/api/health")[0] == 200
        for path in ["/api/documents", "/api/source-root", "/api/config", "/api/sharing"]:
            assert request(query_origin + path)[0] == 404
        started = time.monotonic()
        code, answer = request(query_origin + "/api/query", {"question": "资料室文档借阅期限是多久？"})
        elapsed = round(time.monotonic() - started, 3)
        assert code == 200 and answer["evidence"] and "十四天" in answer["evidence"][0]["text"], answer
        assert str(docs) not in json.dumps(answer)
        shutdown()
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        start()
        assert request(origin + "/api/sharing", authorized=True)[1]["running"]
        assert request(query_origin + "/api/health")[0] == 200
        assert request(origin + "/api/sharing", {"enabled": False, "port": port, "lan": False}, True)[0] == 200
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        shutdown()
        report = {"passed": True, "bundle": bundle.name, "public_routes_restricted": True, "cpu_query_seconds": elapsed,
                  "real_model_original_evidence": answer["evidence"], "settings_survive_restart": True, "listeners_closed": True}
        output = args.output or project / "desktop/build" / (bundle.name + "-sharing-verification.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    main()
