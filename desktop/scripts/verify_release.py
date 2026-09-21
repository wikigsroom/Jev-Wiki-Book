"""Verify every offline ZIP payload against its bundled SHA256 manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from release_portable import BUNDLE, RELEASE, VERSION, WEIGHT_SHA256


def main():
    archive = RELEASE / f"JEV-{VERSION}-windows-x64-offline.zip"
    prefix = BUNDLE.name + "/"
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Duplicate ZIP entries")
        for name in names:
            if not name.startswith(prefix) or ".." in PurePosixPath(name).parts:
                raise RuntimeError(f"Unsafe archive path: {name}")
            if "JEV-data" in PurePosixPath(name).parts:
                raise RuntimeError("Runtime user data must never enter a release")
        checksum_name = prefix + "SHA256SUMS.txt"
        entries = {}
        for line in zf.read(checksum_name).decode("utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            entries[prefix + relative] = digest
        if set(names) != set(entries) | {checksum_name}:
            raise RuntimeError("Archive and checksum manifest contents differ")
        if entries[prefix + "JEV-models/nanojev/best.safetensors"] != WEIGHT_SHA256:
            raise RuntimeError("Original NanoJev checkpoint hash mismatch")
        required = [f"JEV-{VERSION}-windows-x64-portable.exe", "JEV-runtime/python/python.exe", "JEV-runtime/app.py", "JEV/开始使用.md", "使用说明.md", "验证记录.md"]
        if any(prefix + name not in entries for name in required):
            raise RuntimeError("Missing release component")
        total = 0
        for index, (name, expected) in enumerate(entries.items(), 1):
            digest = hashlib.sha256()
            with zf.open(name) as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
                    total += len(block)
            if digest.hexdigest() != expected:
                raise RuntimeError(f"Checksum mismatch: {name}")
            if index % 5000 == 0:
                print(f"Verified {index}/{len(entries)} files", flush=True)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    expected_archive = archive.with_name(archive.name + ".sha256").read_text(encoding="ascii").split()[0]
    if digest.hexdigest() != expected_archive:
        raise RuntimeError("ZIP checksum sidecar mismatch")
    result = {"passed": True, "archive": archive.name, "archive_bytes": archive.stat().st_size, "sha256": digest.hexdigest(), "verified_payload_files": len(entries), "payload_bytes": total, "original_model_verified": True, "runtime_user_data_excluded": True}
    (RELEASE / "verification-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
