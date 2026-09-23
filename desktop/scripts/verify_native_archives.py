"""Verify CI archive payloads and platform executable headers before delivery."""
import hashlib
import argparse
import json
from pathlib import Path
import tarfile
import zipfile
from release_portable import VERSION, SERVER_PROGRAM

PROJECT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--version", default=VERSION)
args = parser.parse_args()
ROOT = PROJECT / f"release/native-{args.version}"
reports = []
for path in sorted(ROOT.rglob(f"{SERVER_PROGRAM}*X64-{args.version}.*")):
    if not path.is_file() or not (path.name.endswith(".zip") or path.name.endswith(".tar.gz")):
        continue
    with path.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    assert archive_hash == path.with_name(path.name + ".sha256").read_text().split()[0]
    archive = zipfile.ZipFile(path) if path.suffix == ".zip" else tarfile.open(path)
    with archive:
        def open_entry(name):
            return archive.open(name) if isinstance(archive, zipfile.ZipFile) else archive.extractfile(name)
        with open_entry(f"{SERVER_PROGRAM}/SHA256SUMS.txt") as stream:
            entries = [line.split("  ", 1) for line in stream.read().decode("utf-8").splitlines()]
        for expected, relative in entries:
            assert not relative.startswith("/") and ".." not in Path(relative).parts
            assert "server_data" not in Path(relative).parts
            with open_entry(SERVER_PROGRAM + "/" + relative) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == expected, relative
        executable = f"{SERVER_PROGRAM}/{SERVER_PROGRAM}" + (".exe" if path.suffix == ".zip" else "")
        with open_entry(executable) as stream:
            prefix = stream.read(4096)
        if path.suffix == ".zip":
            assert prefix[:2] == b"MZ"
            start = int.from_bytes(prefix[60:64], "little")
            assert prefix[start:start + 6] == b"PE\0\0\x64\x86"
        else:
            assert prefix[:5] == b"\x7fELF\x02" and prefix[18:20] == b"\x3e\x00"
            assert archive.getmember(executable).mode & 0o111
        with open_entry(f"{SERVER_PROGRAM}/build-info.json") as stream:
            build = json.load(stream)
        reports.append({"archive": path.name, "sha256": archive_hash, "payload_files": len(entries), "build_commit": build["commit"], "verified": True})
assert len(reports) == 2, reports
output = PROJECT / f"release/native-archive-verification-{args.version}.json"
output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
print(json.dumps(reports), flush=True)
