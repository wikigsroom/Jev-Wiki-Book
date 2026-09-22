import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_runtime import copy


def test_updating_bundle_does_not_change_hardlinked_old_release(tmp_path):
    previous, target, source = (tmp_path / name for name in ["previous", "target", "source"])
    previous.write_bytes(b"old release")
    os.link(previous, target)
    source.write_bytes(b"new release content")
    copy(source, target)
    assert previous.read_bytes() == b"old release"
    assert target.read_bytes() == source.read_bytes()
