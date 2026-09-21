"""Build a relocatable, isolated CPython runtime from the tested local dependencies.

No installer, virtual machine, global pip changes or model precision conversion.
The source distribution RECORDs are used as an allowlist; user configuration,
databases, tokens, documents and model-training scripts are never copied.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

DESKTOP = Path(__file__).resolve().parents[1]
PROJECT = DESKTOP.parent
BUILD = DESKTOP / "build"
BACKEND = BUILD / "backend"
PYTHON_VERSION = "3.13.12"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
SEEDS = ["fastapi", "uvicorn", "python-multipart", "pypdf", "python-docx", "PyMuPDF", "beautifulsoup4", "torch", "transformers", "safetensors", "rapidocr", "onnxruntime", "Pillow"]
WEIGHT_SHA256 = "f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def distributions():
    available = {}
    # Use the same global-first resolution order as the source application.
    for dist in metadata.distributions():
        if dist.metadata["Name"]:
            available.setdefault(canonicalize_name(dist.metadata["Name"]), dist)
    for dist in metadata.distributions(path=[str(PROJECT / ".runtime" / "ocr")]):
        available.setdefault(canonicalize_name(dist.metadata["Name"]), dist)
    selected = {}
    pending = [Requirement(name) for name in SEEDS]
    examined = set()
    while pending:
        req = pending.pop()
        key = canonicalize_name(req.name)
        dist = available.get(key)
        if dist is None:
            raise RuntimeError(f"Missing tested dependency: {req}")
        if req.specifier and dist.version not in req.specifier:
            raise RuntimeError(f"Dependency mismatch: {req}, installed {dist.version}")
        selected[key] = dist
        extras = frozenset(req.extras)
        if (key, extras) in examined:
            continue
        examined.add((key, extras))
        for dependency in dist.requires or []:
            item = Requirement(dependency)
            if item.marker is None or any(item.marker.evaluate({"extra": extra}) for extra in {"", *extras}):
                pending.append(item)
    return selected


def distribution_files(dist):
    if dist.files is None:
        raise RuntimeError(f"No RECORD allowlist for {dist.metadata['Name']}")
    for relative in dist.files:
        parts = relative.parts
        if ".." in parts or "__pycache__" in parts or relative.suffix in {".pyc", ".pyo"}:
            continue
        source = Path(dist.locate_file(relative))
        if source.is_file():
            yield relative, source


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and source.stat().st_size == target.stat().st_size and source.stat().st_mtime_ns == target.stat().st_mtime_ns:
        return
    shutil.copy2(source, target)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    selected = distributions()
    manifest = [{"name": dist.metadata["Name"], "version": dist.version, "license": str(dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See distribution license files")[:1000]} for _, dist in sorted(selected.items())]
    total = sum(source.stat().st_size for dist in selected.values() for _, source in distribution_files(dist))
    print(json.dumps({"packages": len(selected), "dependency_bytes": total, "versions": {item["name"]: item["version"] for item in manifest}}, ensure_ascii=False), flush=True)
    if args.plan:
        return
    cache = BUILD / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if not archive.exists():
        print("Downloading official CPython embeddable runtime", flush=True)
        partial = archive.with_suffix(".partial")
        urllib.request.urlretrieve(PYTHON_URL, partial)
        partial.replace(archive)
    python_dir = BACKEND / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for name in zf.namelist():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise RuntimeError("Unsafe Python archive path")
        zf.extractall(python_dir)
    # _pth isolation disables registry, PYTHONPATH, user site and .pth startup code.
    (python_dir / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n..\n", encoding="utf-8")
    target_packages = python_dir / "Lib" / "site-packages"
    for key, dist in sorted(selected.items()):
        print(f"Bundling {key} {dist.version}", flush=True)
        for relative, source in distribution_files(dist):
            copy(source, target_packages / relative)
    for source in [PROJECT / "app.py", DESKTOP / "backend_entry.py"]:
        copy(source, BACKEND / source.name)
    for folder in ["jev_core", "static", "frontend/dist"]:
        for source in (PROJECT / folder).rglob("*"):
            if source.is_file() and "__pycache__" not in source.parts:
                copy(source, BACKEND / source.relative_to(PROJECT))
    # CPU PyTorch needs the MSVC C++ runtime, which CPython itself need not ship.
    for name in ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        source = Path(os.environ["SystemRoot"]) / "System32" / name
        if source.exists() and not (python_dir / name).exists():
            copy(source, python_dir / name)
    write_json(BACKEND / "runtime-manifest.json", {"python": PYTHON_VERSION, "python_url": PYTHON_URL, "python_archive_sha256": sha256(archive), "architecture": "win-amd64", "packages": manifest})
    (BUILD / "requirements-runtime.lock.txt").write_text("\n".join(f"{item['name']}=={item['version']}" for item in manifest) + "\n", encoding="utf-8")
    print(f"Prepared isolated runtime: {BACKEND}", flush=True)


if __name__ == "__main__":
    main()
