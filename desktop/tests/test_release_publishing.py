"""Release discovery must find unpublished drafts before attempting creation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publish_github_release import find_release


def test_existing_draft_is_found_after_first_page():
    pages = {
        "/releases?per_page=100&page=1": [
            {"id": index, "tag_name": f"v1.{index}", "draft": False}
            for index in range(100)
        ],
        "/releases?per_page=100&page=2": [
            {"id": 101, "tag_name": "v0.5.0", "draft": True}
        ],
    }
    assert find_release(pages.__getitem__, "v0.5.0") == pages[
        "/releases?per_page=100&page=2"
    ][0]


def test_missing_release_allows_creation():
    assert find_release(lambda route: [], "v0.5.0") is None
