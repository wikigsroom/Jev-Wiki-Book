"""Split a verified offline ZIP into GitHub-sized assets without changing its bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

from release_portable import BUNDLE, DESKTOP, RELEASE, VERSION

PART_SIZE = 1536 * 1024 * 1024


def fingerprint(file):
    with file.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"name": file.name, "size": file.stat().st_size, "sha256": digest}


def combined_hash(files):
    digest = hashlib.sha256()
    for file in files:
        with file.open("rb") as stream:
            while block := stream.read(4 * 1024 * 1024):
                digest.update(block)
    return digest.hexdigest()


def merge_command(metadata):
    archive = metadata["archive"]
    parts = metadata["parts"]
    lines = ["@echo off", "setlocal", 'cd /d "%~dp0"']
    for part in parts:
        lines += [f'if not exist "{part["name"]}" goto missing',
                  f'for %%F in ("{part["name"]}") do if not "%%~zF"=="{part["size"]}" goto corrupt',
                  f'certutil -hashfile "{part["name"]}" SHA256 | findstr /i /x "{part["sha256"]}" >nul',
                  "if errorlevel 1 goto corrupt", f'echo Verified {part["name"]}']
    lines += ['if /i "%~1"=="/verify" exit /b 0',
              f'if exist "{archive["name"]}" goto existing',
              f'if exist "{archive["name"]}.assembling" goto unfinished',
              f'copy /b "{parts[0]["name"]}"+"{parts[1]["name"]}" "{archive["name"]}.assembling" >nul',
              "if errorlevel 1 goto corrupt",
              f'certutil -hashfile "{archive["name"]}.assembling" SHA256 | findstr /i /x "{archive["sha256"]}" >nul',
              "if errorlevel 1 goto corrupt",
              f'ren "{archive["name"]}.assembling" "{archive["name"]}"',
              "if errorlevel 1 goto unfinished", "goto ready", ":existing",
              f'certutil -hashfile "{archive["name"]}" SHA256 | findstr /i /x "{archive["sha256"]}" >nul',
              "if errorlevel 1 goto conflict", ":ready",
              f'echo Ready: {archive["name"]}',
              "echo Extract the entire ZIP, then run the portable EXE.", "exit /b 0",
              ":missing", "echo Missing part. Download both 001 and 002 into this folder.", "exit /b 1",
              ":corrupt", "echo Checksum or copy failed. Original parts were preserved.", "exit /b 1",
              ":conflict", "echo Output ZIP already exists with different contents. Nothing was overwritten.", "exit /b 1",
              ":unfinished", "echo An incomplete output exists. Preserve it and use a clean output folder.", "exit /b 1"]
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def write_support_files(output, metadata):
    archive = metadata["archive"]
    parts = metadata["parts"]
    (output / "Merge-JEV.cmd").write_bytes(merge_command(metadata))
    for source in [DESKTOP / "scripts/Merge-JEV.ps1", RELEASE / "verification-result.json", RELEASE / (archive["name"] + ".sha256")]:
        shutil.copy2(source, output / source.name)
    names = [f"JEV-{VERSION}-windows-x64-portable.exe", "Merge-JEV.cmd", "Merge-JEV.ps1", "verification-result.json", archive["name"] + ".sha256"]
    metadata["assets"] = parts + [fingerprint(output / name) for name in names]
    (output / f"JEV-{VERSION}-downloads.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--consume-archive", action="store_true", help="Convert original ZIP to recoverable parts to reduce peak disk usage")
    args = parser.parse_args()
    output = RELEASE / f"github-v{VERSION}"
    output.mkdir(parents=True, exist_ok=True)
    archive = RELEASE / f"JEV-{VERSION}-windows-x64-offline.zip"
    manifest = output / f"JEV-{VERSION}-downloads.json"
    if manifest.exists():
        previous = json.loads(manifest.read_text(encoding="utf-8"))
        files = [output / part["name"] for part in previous["parts"]]
        # A crash after renaming but before truncating leaves the full ZIP as .001.
        if args.consume_archive and files[0].exists() and files[0].stat().st_size == previous["archive"]["size"]:
            if fingerprint(files[0])["sha256"] != previous["archive"]["sha256"] or fingerprint(files[1]) != previous["parts"][1]:
                raise RuntimeError("Cannot recover interrupted split: checksum mismatch")
            with files[0].open("r+b") as stream:
                stream.truncate(previous["parts"][0]["size"])
        if all(file.exists() and fingerprint(file) == part for file, part in zip(files, previous["parts"])):
            if combined_hash(files) != previous["archive"]["sha256"]:
                raise RuntimeError("Combined ZIP hash mismatch")
            write_support_files(output, previous)
            print(f"Existing release parts verified: {output}")
            return
        raise RuntimeError("Incomplete output exists; preserve it and resolve before retrying")
    if not archive.is_file():
        raise RuntimeError("Build and verify the offline ZIP first")
    details = fingerprint(archive)
    verified = json.loads((RELEASE / "verification-result.json").read_text(encoding="utf-8"))
    if not verified.get("passed") or verified["sha256"] != details["sha256"] or verified["archive_bytes"] != details["size"]:
        raise RuntimeError("Offline ZIP differs from its verified release report")
    if not PART_SIZE < details["size"] < 2 * PART_SIZE:
        raise RuntimeError("This release layout expects a ZIP between 1.5 and 3 GiB")
    first = output / (archive.name + ".001")
    second = output / (archive.name + ".002")
    if first.exists() or second.exists():
        raise RuntimeError("Output parts already exist without a manifest")
    required = details["size"] - PART_SIZE if args.consume_archive else details["size"]
    if shutil.disk_usage(output).free < required + 200 * 1024 * 1024:
        raise RuntimeError("Insufficient disk space for a safe split")
    with archive.open("rb") as source:
        first_digest = hashlib.sha256()
        remaining = PART_SIZE
        target = None if args.consume_archive else first.open("xb")
        try:
            while remaining:
                block = source.read(min(4 * 1024 * 1024, remaining))
                if not block:
                    raise RuntimeError("Unexpected end of archive")
                first_digest.update(block)
                if target:
                    target.write(block)
                remaining -= len(block)
        finally:
            if target:
                target.close()
        with second.open("xb") as target:
            shutil.copyfileobj(source, target, 4 * 1024 * 1024)
    parts = [{"name": first.name, "size": PART_SIZE, "sha256": first_digest.hexdigest()}, fingerprint(second)]
    exe = output / f"JEV-{VERSION}-windows-x64-portable.exe"
    if not exe.exists():
        try:
            os.link(BUNDLE / exe.name, exe)
        except OSError:
            shutil.copy2(BUNDLE / exe.name, exe)
    for source in [DESKTOP / "scripts/Merge-JEV.ps1", RELEASE / "verification-result.json", RELEASE / (archive.name + ".sha256")]:
        shutil.copy2(source, output / source.name)
    assets = [fingerprint(file) for file in [exe, output / "Merge-JEV.ps1", output / "verification-result.json", output / (archive.name + ".sha256")]]
    metadata = {"version": VERSION, "archive": details, "parts": parts, "assets": parts + assets}
    manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.consume_archive:
        # The tail is persisted before moving/truncating the original. Prefix + saved
        # tail are checked against the verified original before changing that file.
        digest = hashlib.sha256()
        with archive.open("rb") as source:
            remaining = PART_SIZE
            while remaining:
                block = source.read(min(4 * 1024 * 1024, remaining))
                digest.update(block)
                remaining -= len(block)
        with second.open("rb") as source:
            while block := source.read(4 * 1024 * 1024):
                digest.update(block)
        if digest.hexdigest() != details["sha256"]:
            raise RuntimeError("Saved tail did not preserve the original archive")
        archive.rename(first)
        with first.open("r+b") as stream:
            stream.truncate(PART_SIZE)
    if fingerprint(first) != parts[0] or combined_hash([first, second]) != details["sha256"]:
        raise RuntimeError("Split verification failed")
    write_support_files(output, metadata)
    print(json.dumps({"output": str(output), "archive_sha256": details["sha256"], "parts": parts, "original_zip_converted": args.consume_archive}, indent=2), flush=True)


if __name__ == "__main__":
    main()
