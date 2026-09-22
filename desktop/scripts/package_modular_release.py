"""Package desktop code and one shared model set without duplicating large ZIPs."""
from __future__ import annotations
import bisect
import hashlib
import io
import json
from pathlib import Path
import zipfile

from release_portable import BUNDLE, RELEASE, VERSION
from prepare_runtime import sha256


class PartsWriter(io.RawIOBase):
    def __init__(self, stem, limit=1536 * 1024 * 1024):
        self.stem, self.limit = stem, limit
        self.position, self.part_size = 0, 0
        self.files, self.records = [], []
        self.stream = None
        self.total_hash = hashlib.sha256()

    def tell(self):
        return self.position

    def write(self, data):
        length = len(data)
        self.total_hash.update(data)
        while data:
            if self.stream is None:
                path = Path(str(self.stem) + f".{len(self.files) + 1:03d}")
                self.stream = path.open("xb")
                self.files.append(path)
                self.part_hash = hashlib.sha256()
                self.part_size = 0
            size = min(len(data), self.limit - self.part_size)
            block, data = data[:size], data[size:]
            self.stream.write(block)
            self.part_hash.update(block)
            self.part_size += size
            self.position += size
            if self.part_size == self.limit:
                self.finish_part()
        return length

    def finish_part(self):
        if self.stream:
            self.stream.close()
            self.stream = None
            self.records.append({"name": self.files[-1].name, "bytes": self.part_size, "sha256": self.part_hash.hexdigest()})


class PartsReader(io.RawIOBase):
    def __init__(self, paths):
        self.streams = [path.open("rb") for path in paths]
        self.offsets, self.position = [0], 0
        for path in paths:
            self.offsets.append(self.offsets[-1] + path.stat().st_size)

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        target = offset + (self.position if whence == 1 else self.offsets[-1] if whence == 2 else 0)
        if target < 0:
            raise ValueError("Negative seek")
        self.position = target
        return target

    def read(self, size=-1):
        remaining = self.offsets[-1] - self.position
        size = remaining if size < 0 else min(size, remaining)
        chunks = []
        while size > 0:
            index = bisect.bisect_right(self.offsets, self.position) - 1
            take = min(size, self.offsets[index + 1] - self.position)
            stream = self.streams[index]
            stream.seek(self.position - self.offsets[index])
            block = stream.read(take)
            if not block:
                raise OSError("Truncated archive part")
            chunks.append(block)
            self.position += len(block)
            size -= len(block)
        return b"".join(chunks)

    def close(self):
        for stream in self.streams:
            stream.close()
        super().close()


def verify(archive, expected):
    with zipfile.ZipFile(archive) as source:
        assert set(source.namelist()) == set(expected)
        for name, checksum in expected.items():
            with source.open(name) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == checksum, name


def main():
    payload = {}
    for line in (BUNDLE / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        checksum, name = line.split("  ", 1)
        payload[name] = checksum
    desktop = RELEASE / f"JEV-{VERSION}-windows-x64-app.zip"
    app_checksums = {name: value for name, value in payload.items() if not name.startswith("JEV-models/")}
    app_checksums["SHA256SUMS.txt"] = sha256(BUNDLE / "SHA256SUMS.txt")
    with zipfile.ZipFile(desktop, "x", zipfile.ZIP_DEFLATED, compresslevel=3) as output:
        for name in app_checksums:
            output.write(BUNDLE / name, BUNDLE.name + "/" + name)
    verify(desktop, {BUNDLE.name + "/" + name: value for name, value in app_checksums.items()})
    desktop.with_name(desktop.name + ".sha256").write_text(f"{sha256(desktop)}  {desktop.name}\n", encoding="ascii")
    print(f"Desktop archive verified: {desktop.name}", flush=True)

    models = {name: BUNDLE / name for name in payload if name.startswith("JEV-models/")}
    for name in ["NanoJev-LICENSE.txt", "Qwen3-LICENSE.txt", "RapidOCR-LICENSE.txt", "PaddleOCR-LICENSE.txt", "model-provenance.json"]:
        models["JEV-models/THIRD-PARTY/" + name] = BUNDLE / "THIRD-PARTY" / name
    model_checksums = {name: sha256(path) for name, path in models.items()}
    writer = PartsWriter(RELEASE / f"JEV-models-{VERSION}.zip")
    try:
        with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as output:
            for name, path in models.items():
                output.write(path, name)
    finally:
        writer.finish_part()
    with PartsReader(writer.files) as reader:
        verify(reader, model_checksums)
    manifest = {"version": VERSION, "archive": f"JEV-models-{VERSION}.zip", "bytes": writer.position,
                "sha256": writer.total_hash.hexdigest(), "parts": writer.records, "payload_verified": True}
    (RELEASE / f"JEV-models-{VERSION}-downloads.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
