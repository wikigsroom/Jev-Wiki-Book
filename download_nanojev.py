"""Download the open NanoJev checkpoint once for offline local inference."""

from __future__ import annotations

import os
import hashlib
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TARGET_DIR = BASE_DIR / "models" / "nanojev"
REPO_ID = "C-Tianyu/NanoJev"
# Verified public snapshot behind unified-games-v1; a moving tag is not reproducible.
REVISION = "047b927b30882a1138fc504821b82ac145a4b81a"
WEIGHTS_SHA256 = "f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b"


def main() -> None:
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_download(
        repo_id=REPO_ID,
        revision=REVISION,
        local_dir=str(TARGET_DIR),
        token=False,
        allow_patterns=[
            "best.safetensors",
            "config.json",
            "backbone_config/*",
            "tokenizer/*",
            "README.md",
            "LICENSE*",
        ],
    )
    with (TARGET_DIR / "best.safetensors").open("rb") as weights:
        actual = hashlib.file_digest(weights, "sha256").hexdigest()
    if actual != WEIGHTS_SHA256:
        raise RuntimeError("NanoJev 权重校验失败，请重新下载；不会启动远程模型")
    print(f"NanoJev checkpoint ready: {snapshot}; revision={REVISION}; SHA-256 verified")
    print("Runtime mode: local checkpoint only; no automatic model downloads or cloud inference")


if __name__ == "__main__":
    main()
