"""Build on the target OS. No cross-compilation, Docker, or model conversion."""
from pathlib import Path
import json
import platform
import shutil
import subprocess
import sys
import importlib.metadata

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "server_build"


def main():
    name = "JEV-server"
    options = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--name", name,
               "--distpath", str(OUTPUT / "dist"), "--workpath", str(OUTPUT / "work"),
               "--specpath", str(OUTPUT), "--add-data", str(ROOT / "web_ui") + ":web_ui",
               "--collect-submodules", "transformers", "--collect-data", "transformers",
               "--collect-all", "rapidocr", "--collect-all", "onnxruntime",
               "--collect-all", "tokenizers", "--collect-all", "safetensors",
               "--collect-data", "certifi", "--copy-metadata", "torch", "--copy-metadata", "transformers",
               "--hidden-import", "uvicorn.logging", "--hidden-import", "uvicorn.loops.asyncio",
               "--hidden-import", "uvicorn.protocols.http.h11_impl", "--hidden-import", "uvicorn.lifespan.on",
               "--exclude-module", "tkinter", "--exclude-module", "matplotlib", "--exclude-module", "scipy",
               "--exclude-module", "pandas", "--exclude-module", "IPython", "--exclude-module", "tensorflow",
               str(ROOT / "server.py")]
    OUTPUT.mkdir(exist_ok=True)
    subprocess.run(options, cwd=ROOT, check=True)
    bundle = OUTPUT / "dist" / name
    for file in ["README.md", "THIRD_PARTY_NOTICES.md", "docs/CLI_DEPLOYMENT.md"]:
        shutil.copy2(ROOT / file, bundle / Path(file).name)
    # Bundle readable source and licenses alongside compiled code.
    sources = [ROOT / "server.py"] + list((ROOT / "jev_core").glob("*.py"))
    for source in sources:
        target = bundle / "SOURCE" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or []:
            if ".." in entry.parts:
                continue
            if entry.name.lower().startswith(("license", "copying", "notice")) or "licenses" in entry.parts:
                source = Path(distribution.locate_file(entry))
                if source.is_file():
                    target = bundle / "THIRD-PARTY" / distribution.metadata["Name"] / entry
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    metadata = {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version,
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "models_included": False}
    (bundle / "build-info.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"bundle": str(bundle), **metadata}), flush=True)


if __name__ == "__main__":
    main()
