"""Exercise Windows file joining, corruption refusal and overwrite protection."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_github_release import merge_command

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows release helper")


def fixture(tmp_path):
    content = bytes(range(256)) * 73
    parts = []
    for index, data in enumerate([content[:9001], content[9001:]], 1):
        name = f"sample archive.zip.{index:03}"
        (tmp_path / name).write_bytes(data)
        parts.append({"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    metadata = {"archive": {"name": "sample archive.zip", "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}, "parts": parts}
    script = tmp_path / "Merge-JEV.cmd"
    script.write_bytes(merge_command(metadata))
    def run(*arguments):
        return subprocess.run(["cmd.exe", "/d", "/c", str(script), *arguments], cwd=tmp_path, capture_output=True)
    return content, metadata, run


def test_cmd_merges_exact_bytes_and_preserves_existing_different_file(tmp_path):
    content, metadata, run = fixture(tmp_path)
    output = tmp_path / metadata["archive"]["name"]
    assert run().returncode == 0
    assert output.read_bytes() == content
    assert run().returncode == 0
    output.write_bytes(b"keep this user's existing output")
    assert run().returncode != 0
    assert output.read_bytes() == b"keep this user's existing output"


def test_cmd_rejects_corrupt_same_size_part_before_writing_output(tmp_path):
    _, metadata, run = fixture(tmp_path)
    part = tmp_path / metadata["parts"][0]["name"]
    part.write_bytes(b"X" * part.stat().st_size)
    assert run().returncode != 0
    assert not (tmp_path / metadata["archive"]["name"]).exists()


def test_cmd_verify_only_does_not_create_archive(tmp_path):
    _, metadata, run = fixture(tmp_path)
    assert run("/verify").returncode == 0
    assert not (tmp_path / metadata["archive"]["name"]).exists()
