"""Archive the verified native runtime; preserve Linux executable permissions."""
import hashlib
import json
from pathlib import Path
import platform
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "server_build"
bundle = BUILD / "dist/JEV-server"
target = BUILD / "packages"
target.mkdir(exist_ok=True)
system = "windows" if platform.system() == "Windows" else "linux"
name = f"JEV-cli-0.6.0-{system}-x64"
files = sorted(file for file in bundle.rglob("*") if file.is_file())


def sha256(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


manifest = bundle / "SHA256SUMS.txt"
manifest.write_text("\n".join(f"{sha256(file)}  {file.relative_to(bundle).as_posix()}" for file in files if file != manifest) + "\n", encoding="utf-8")
files = sorted(file for file in bundle.rglob("*") if file.is_file())
if system == "windows":
    archive = target / (name + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=3) as output:
        for file in files:
            output.write(file, "JEV-server/" + file.relative_to(bundle).as_posix())
else:
    archive = target / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz", compresslevel=3) as output:
        output.add(bundle, arcname="JEV-server")
(target / (archive.name + ".sha256")).write_text(f"{sha256(archive)}  {archive.name}\n", encoding="ascii")
print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files)}))
