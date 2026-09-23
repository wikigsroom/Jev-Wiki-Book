"""Assemble an offline release from explicit application/model allowlists."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from prepare_runtime import BACKEND, DESKTOP, PROJECT, WEIGHT_SHA256, copy, sha256, write_json

sys.path.insert(0, str(PROJECT))
from jev_core.release_info import VERSION, DESKTOP_PROGRAM, DESKTOP_STEM, DOWNLOADS_MANIFEST, SERVER_PROGRAM, server_stem

RELEASE = PROJECT / "release"
BUNDLE = RELEASE / DESKTOP_STEM


def download_license(url, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    mirrors = [url]
    if url.startswith("https://raw.githubusercontent.com/"):
        owner, repo, ref, *rest = url.removeprefix("https://raw.githubusercontent.com/").split("/")
        mirrors.append(f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{ref}/{'/'.join(rest)}")
    if url.startswith("https://huggingface.co/"):
        mirrors.append(url.replace("https://huggingface.co/", "https://hf-mirror.com/", 1))
    for source_url in mirrors:
        result = subprocess.run(["curl.exe", "--fail", "--silent", "--show-error", "--location", "--connect-timeout", "8", "--max-time", "25", source_url, "--output", str(temporary)], capture_output=True)
        if result.returncode == 0:
            break
    else:
        raise RuntimeError(f"Unable to download upstream license: {url}")
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--assets-only", action="store_true")
    parser.add_argument("--reuse-runtime", type=Path, help="Hardlink identical runtime files from an existing release")
    args = parser.parse_args()
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    if (package["version"] != VERSION or package["build"]["productName"] != DESKTOP_PROGRAM
            or package["build"]["portable"]["artifactName"].replace("${version}", VERSION) != DESKTOP_STEM + ".exe"):
        raise RuntimeError("Desktop package name/version differs from the release manifest")
    BUNDLE.mkdir(parents=True, exist_ok=True)
    exe_name = DESKTOP_STEM + ".exe"
    exe = DESKTOP / "dist" / exe_name
    if not args.assets_only and not exe.is_file():
        raise RuntimeError("Build the portable EXE first")
    if not args.assets_only:
        copy(exe, BUNDLE / exe_name)
    model_files = [PROJECT / "models/nanojev/best.safetensors", PROJECT / "models/nanojev/config.json"]
    for folder in ["models/nanojev/backbone_config", "models/nanojev/tokenizer", "models/ocr"]:
        model_files.extend(path for path in (PROJECT / folder).rglob("*") if path.is_file() and ".cache" not in path.parts)
    if sha256(model_files[0]) != WEIGHT_SHA256:
        raise RuntimeError("NanoJev weight SHA256 does not match the reviewed checkpoint")
    for source in model_files:
        target = BUNDLE / "JEV-models" / source.relative_to(PROJECT / "models")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                copy(source, target)
    for source in BACKEND.rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts and source.suffix not in {".pyc", ".pyo"}:
            relative = source.relative_to(BACKEND)
            target = BUNDLE / "JEV-runtime" / relative
            previous = args.reuse_runtime / relative if args.reuse_runtime else None
            if not target.exists() and previous and previous.is_file() and previous.stat().st_size == source.stat().st_size and sha256(previous) == sha256(source):
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(previous, target)
            else:
                copy(source, target)
    copy(DESKTOP / "assets/开始使用.md", BUNDLE / "JEV/开始使用.md")
    copy(DESKTOP / "README.md", BUNDLE / "使用说明.md")
    copy(DESKTOP / "VERIFICATION.md", BUNDLE / "验证记录.md")
    sources = [PROJECT / name for name in [
        "app.py", "requirements.txt", "requirements-dev.txt", ".env.example",
        ".gitignore", ".gitattributes", "AGENTS.md", "README.md", "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md", "download_nanojev.py", "setup_ocr.py",
        "evals/README.md", "evals/example-questions.json", "evals/run_eval.py",
    ]]
    sources += [PROJECT / "frontend" / name for name in ["package.json", "package-lock.json", "vite.config.js", "index.html"]]
    sources += [DESKTOP / name for name in ["package.json", "package-lock.json", "main.cjs", "preload.cjs", "lifecycle.cjs", "backend_entry.py", "README.md", "VERIFICATION.md", "requirements-runtime.lock.txt"]]
    for folder in ["jev_core", "static", "web_ui", "tests", "docs", "frontend/src", "desktop/renderer", "desktop/scripts", "desktop/tests", "desktop/assets"]:
        sources.extend(path for path in (PROJECT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    for source in sources:
        copy(source, BUNDLE / "SOURCE" / source.relative_to(PROJECT))
    third_party = BUNDLE / "THIRD-PARTY"
    copy(BACKEND / "runtime-manifest.json", third_party / "runtime-manifest.json")
    copy(DESKTOP / "build/requirements-runtime.lock.txt", third_party / "requirements-runtime.lock.txt")
    copy(DESKTOP / "dist/win-unpacked/LICENSE.electron.txt", third_party / "Electron-LICENSE.txt")
    copy(DESKTOP / "dist/win-unpacked/LICENSES.chromium.html", third_party / "Chromium-LICENSES.html")
    copy(BACKEND / "python/LICENSE.txt", third_party / "Python-LICENSE.txt")
    for source in (BACKEND / "python/Lib/site-packages").rglob("*"):
        if source.is_file() and (source.name.lower().startswith(("license", "copying", "notice")) or "licenses" in source.parts):
            copy(source, third_party / "python-packages" / source.relative_to(BACKEND / "python/Lib/site-packages"))
    for package in ["react", "react-dom", "scheduler"]:
        copy(PROJECT / "frontend/node_modules" / package / "LICENSE", third_party / f"{package}-LICENSE.txt")
    licenses = {
        "NanoJev-LICENSE.txt": "https://raw.githubusercontent.com/TianyuCodings/NanoJev/main/LICENSE",
        "Qwen3-LICENSE.txt": "https://huggingface.co/Qwen/Qwen3-0.6B/resolve/main/LICENSE",
        "RapidOCR-LICENSE.txt": "https://raw.githubusercontent.com/RapidAI/RapidOCR/main/LICENSE",
        "PaddleOCR-LICENSE.txt": "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE",
    }
    for name, url in licenses.items():
        download_license(url, third_party / name)
    write_json(third_party / "model-provenance.json", {"nanojev": {"repository": "https://huggingface.co/C-Tianyu/NanoJev", "revision": "047b927b30882a1138fc504821b82ac145a4b81a", "weight_sha256": WEIGHT_SHA256, "weights_modified": False, "implementation": "https://github.com/TianyuCodings/NanoJev"}, "ocr": {"provider": "RapidAI / PaddleOCR PP-OCRv4", "setup_source": "SOURCE/setup_ocr.py"}, "license_sources": licenses})
    if args.assets_only:
        print(f"Prepared offline models, source and notices: {BUNDLE}", flush=True)
        return
    # Only release allowlisted files; never package JEV-data or source documents.
    files = [BUNDLE / exe_name, BUNDLE / "使用说明.md", BUNDLE / "验证记录.md"]
    for folder in ["JEV-models", "JEV-runtime", "SOURCE", "THIRD-PARTY"]:
        files += [p for p in (BUNDLE / folder).rglob("*") if p.is_file()]
    files.append(BUNDLE / "JEV/开始使用.md")
    files = sorted(set(files))
    checksums = "\n".join(f"{sha256(file)}  {file.relative_to(BUNDLE).as_posix()}" for file in files) + "\n"
    (BUNDLE / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    files.append(BUNDLE / "SHA256SUMS.txt")
    print(json.dumps({"bundle": str(BUNDLE), "files": len(files), "bytes": sum(file.stat().st_size for file in files)}, ensure_ascii=False), flush=True)
    if not args.no_archive:
        archive = RELEASE / f"{DESKTOP_STEM}-Offline.zip"
        print("Creating ZIP64 offline package…", flush=True)
        with zipfile.ZipFile(archive.with_suffix(".partial"), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as zf:
            for file in files:
                zf.write(file, arcname=str(Path(BUNDLE.name) / file.relative_to(BUNDLE)))
        archive.with_suffix(".partial").replace(archive)
        (RELEASE / (archive.name + ".sha256")).write_text(f"{sha256(archive)}  {archive.name}\n", encoding="ascii")
        print(f"Release ready: {archive} ({archive.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
