"""Publish verified local assets with an authenticated official GitHub CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from release_portable import PROJECT, RELEASE, VERSION


def find_release(api, tag):
    # The release-by-tag endpoint excludes unpublished drafts. The authenticated
    # list endpoint includes drafts and lets a retry reuse the existing release.
    page = 1
    while True:
        releases = api(f"/releases?per_page=100&page={page}")
        for release in releases:
            if release["tag_name"] == tag:
                return release
        if len(releases) < 100:
            return None
        page += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gh", default="gh", help="Path to official gh executable")
    parser.add_argument("--repo", default="wikigsroom/Jev-Wiki-Book")
    parser.add_argument("--check", action="store_true", help="Validate access, tag and files without external writes")
    args = parser.parse_args()
    tag = "v" + VERSION
    folder = RELEASE / ("github-" + tag)
    manifest_path = folder / f"JEV-{VERSION}-downloads.json"
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))

    def gh(*command, optional=False):
        result = subprocess.run([args.gh, *command], cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        if result.returncode:
            if optional and "HTTP 404" in result.stderr:
                return None
            raise RuntimeError(result.stderr.strip() or "GitHub CLI command failed")
        return result.stdout.strip()

    def api(route, optional=False):
        result = gh("api", "repos/" + args.repo + route, optional=optional)
        return json.loads(result) if result is not None else None

    repository = api("")
    if not repository.get("permissions", {}).get("push"):
        raise RuntimeError("Current GitHub login lacks repository write permission")
    reference = api("/git/ref/tags/" + tag)["object"]
    if reference["type"] == "tag":
        reference = api("/git/tags/" + reference["sha"])["object"]
    local = subprocess.check_output(["git", "rev-parse", tag + "^{commit}"], cwd=PROJECT, text=True).strip()
    if reference["sha"] != local:
        raise RuntimeError("Remote release tag does not match local commit")
    assets = list(metadata["assets"])
    assets.append({"name": manifest_path.name, "size": manifest_path.stat().st_size,
                   "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()})
    if len({entry["name"] for entry in assets}) != len(assets):
        raise RuntimeError("Duplicate asset names")
    for entry in assets:
        if Path(entry["name"]).name != entry["name"]:
            raise RuntimeError("Asset path must be a filename")
        file = folder / entry["name"]
        if file.stat().st_size != entry["size"] or file.stat().st_size >= 2 * 1024**3:
            raise RuntimeError("Wrong asset size or GitHub asset limit exceeded: " + file.name)
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                raise RuntimeError("Local checksum mismatch: " + file.name)
    print(f"Verified {len(assets)} local assets and write access to {args.repo} at {tag}", flush=True)
    if args.check:
        return
    release = find_release(api, tag)
    notes = str(PROJECT / "docs/releases" / (tag + ".md"))
    title = f"JEV {VERSION} · Windows x64 offline portable"
    if release is None:
        gh("release", "create", tag, "--repo", args.repo, "--verify-tag", "--draft", "--title", title, "--notes-file", notes)
        release = find_release(api, tag)
    if release is None:
        raise RuntimeError("Created release is not visible; retry without creating a duplicate")
    release_route = "/releases/" + str(release["id"])
    existing = {asset["name"]: asset for asset in release["assets"]}
    for entry in assets:
        remote = existing.get(entry["name"])
        if remote:
            if remote["state"] != "uploaded" or remote["size"] != entry["size"] or remote.get("digest") != "sha256:" + entry["sha256"]:
                raise RuntimeError("Existing asset cannot be verified; refusing to overwrite: " + entry["name"])
            print("Already uploaded: " + entry["name"], flush=True)
            continue
        print("Uploading: " + entry["name"], flush=True)
        gh("release", "upload", tag, str(folder / entry["name"]), "--repo", args.repo)
    uploaded = api(release_route)
    uploaded_files = {asset["name"]: asset for asset in uploaded["assets"]}
    for entry in assets:
        remote = uploaded_files.get(entry["name"], {})
        if remote.get("state") != "uploaded" or remote.get("size") != entry["size"] or remote.get("digest") != "sha256:" + entry["sha256"]:
            raise RuntimeError("Remote verification failed; release remains in its previous state: " + entry["name"])
    gh("release", "edit", tag, "--repo", args.repo, "--draft=false", "--title", title, "--notes-file", notes, "--latest")
    final = api(release_route)
    if final["draft"]:
        raise RuntimeError("Release still marked as draft")
    receipt = {"repository": args.repo, "tag": tag, "commit": local, "url": final["html_url"], "assets": [{key: asset.get(key) for key in ["name", "size", "digest", "browser_download_url"]} for asset in final["assets"]]}
    (RELEASE / "github-published.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
