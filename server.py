"""JEV native CLI: independent admin/query listeners, no Electron dependency."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
from jev_core.release_info import SERVER_PROGRAM, VERSION


def port(value):
    number = int(value)
    if not 1024 <= number <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1024 and 65535")
    return number


def main():
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(prog=SERVER_PROGRAM, description="Local CPU document administration and query server")
    parser.add_argument("--version", action="version", version=f"{SERVER_PROGRAM} {VERSION}")
    parser.add_argument("--data-dir", type=Path, default=root / "server_data")
    parser.add_argument("--models-dir", type=Path, default=root / "JEV-models")
    parser.add_argument("--admin-host", default="127.0.0.1", choices=["127.0.0.1", "0.0.0.0"])
    parser.add_argument("--admin-port", type=port, default=18765)
    parser.add_argument("--web-host", default="0.0.0.0", choices=["127.0.0.1", "0.0.0.0"])
    parser.add_argument("--web-port", type=port, default=18766)
    parser.add_argument("--admin-origin", help="HTTPS origin of a trusted reverse proxy")
    parser.add_argument("--web-origin", help="Origin of a trusted reverse proxy")
    parser.add_argument("--tls-cert", type=Path)
    parser.add_argument("--tls-key", type=Path)
    parser.add_argument("--check", action="store_true", help="Check bundled imports, CPU runtime and model files, then exit")
    args = parser.parse_args()
    if args.admin_port == args.web_port:
        parser.error("admin and web ports must differ")
    if bool(args.tls_cert) != bool(args.tls_key):
        parser.error("--tls-cert and --tls-key must be supplied together")
    from urllib.parse import urlsplit
    for origin in [args.admin_origin, args.web_origin]:
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.username or parsed.query or parsed.fragment:
                parser.error("external origins must be HTTP(S) origins without path or credentials")
    if args.admin_host != "127.0.0.1" and not args.tls_cert:
        parser.error("remote admin requires --tls-cert and --tls-key; use the loopback listener for a reverse proxy")
    if args.admin_origin and urlsplit(args.admin_origin).scheme != "https":
        parser.error("--admin-origin must use HTTPS for remote administration")
    args.admin_origin = args.admin_origin.rstrip("/") if args.admin_origin else None
    args.web_origin = args.web_origin.rstrip("/") if args.web_origin else None
    data = args.data_dir.resolve()
    models = args.models_dir.resolve()
    for name, value in {"JEV_STORAGE_DIR": str(data / "storage"), "JEV_SOURCE_ROOT": str(data / "JEV"),
                        "JEV_MODELS_DIR": str(models), "NANOJEV_CHECKPOINT_DIR": str(models / "nanojev"),
                        "NANOJEV_DEVICE": "cpu", "NANOJEV_PRECISION": "fp32", "HF_HUB_OFFLINE": "1",
                        "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                        "TOKENIZERS_PARALLELISM": "false"}.items():
        os.environ[name] = value
    # Direct imports let native bundlers discover the query dependencies.
    from jev_core.offline import enforce_offline
    enforce_offline()
    from jev_core.nanojev import LocalNanoJev
    from jev_core.parsing import DocumentParser, LocalOCR
    from jev_core.storage import KnowledgeStore, IndexJobs
    from jev_core.web import PublicReader, ThreadServer, create_public_app
    from jev_core.admin import Credentials, Publication, create_admin_app, DEFAULT_PASSWORD
    from filelock import FileLock, Timeout

    if args.check:
        import torch
        import onnxruntime
        import rapidocr
        import pymupdf
        import transformers
        from transformers.models.qwen3.modeling_qwen3 import Qwen3Model
        model_status = LocalNanoJev().status()
        ocr_status = LocalOCR(data / "storage/ocr", models / "ocr").status()
        ready = model_status["checkpoint_configured"] and ocr_status["configured"]
        print(json.dumps({"version": VERSION, "ready": ready, "python": sys.version.split()[0], "torch": torch.__version__,
                          "cuda_build": torch.version.cuda, "onnx_providers": onnxruntime.get_available_providers(),
                          "model": model_status, "ocr": ocr_status}, ensure_ascii=False, indent=2))
        return 0 if ready else 2

    data.mkdir(parents=True, exist_ok=True)
    data.chmod(0o700)
    (data / "JEV").mkdir(exist_ok=True)
    lock = FileLock(str(data / ".server.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise SystemExit("This data directory is already in use by another JEV server")
    listeners = []
    jobs = None
    try:
        ocr = LocalOCR(data / "storage/ocr", models / "ocr")
        store = KnowledgeStore(data / "storage", data / "JEV", DocumentParser(ocr))
        model = LocalNanoJev(models / "nanojev")
        credentials = Credentials(data / "admin.json")
        publication = Publication(store, credentials, data / "publication.json")
        jobs = IndexJobs(store)
        tls = {"ssl_certfile": str(args.tls_cert), "ssl_keyfile": str(args.tls_key)} if args.tls_cert else {}
        scheme = "https" if tls else "http"
        web_info = {"host": args.web_host, "port": args.web_port, "url": args.web_origin or f"{scheme}://127.0.0.1:{args.web_port}"}
        public = create_public_app(PublicReader(publication.source, model), publication.available, args.web_origin)
        admin = create_admin_app(store, jobs, model, credentials, publication, web_info, args.admin_origin,
                                 secure_cookie=bool(tls) or bool(args.admin_origin and args.admin_origin.startswith("https://")))
        listeners.append(ThreadServer(admin, args.admin_host, args.admin_port, **tls))
        listeners.append(ThreadServer(public, args.web_host, args.web_port, **tls))
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda *_: stop.set())
        print(f"JEV_READY {json.dumps({'admin': args.admin_origin or f'{scheme}://127.0.0.1:{args.admin_port}', 'web': web_info, 'version': VERSION})}", flush=True)
        if credentials.value["must_change"]:
            print(f"First login: admin / {DEFAULT_PASSWORD} (password change required before sharing)", flush=True)
        while not stop.wait(.5):
            if any(not listener.thread.is_alive() for listener in listeners):
                raise RuntimeError("A listener stopped unexpectedly; shutting down both services")
    finally:
        for listener in reversed(listeners):
            listener.stop()
        if jobs:
            jobs.close()
        for listener in listeners:
            listener.wait()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
