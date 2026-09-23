"""Stage a verified patch release, reusing the unchanged v0.6.0 model assets."""
import argparse
import json
import os
from pathlib import Path

from prepare_runtime import sha256, WEIGHT_SHA256
from release_portable import VERSION, PROJECT, RELEASE, BUNDLE, DESKTOP_PROGRAM, SERVER_PROGRAM, DESKTOP_STEM, DOWNLOADS_MANIFEST, server_stem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli-commit", required=True)
    parser.add_argument("--desktop-commit", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    destination = RELEASE / f"github-v{VERSION}"
    destination.mkdir(exist_ok=True)
    assets = []

    def stage(source, name=None):
        target = destination / (name or source.name)
        if target.exists():
            if sha256(target) != sha256(source):
                raise ValueError(f"Refusing to replace staged asset: {target.name}")
        else:
            os.link(source, target)
        assets.append({"name": target.name, "size": target.stat().st_size, "sha256": sha256(target)})

    for suffix in [".zip", ".zip.sha256"]:
        stage(RELEASE / (DESKTOP_STEM + suffix))
    stage(BUNDLE / (DESKTOP_STEM + ".exe"))
    for platform, extension in [("Windows", "zip"), ("Linux", "tar.gz")]:
        stem = server_stem(platform)
        root = RELEASE / f"native-{VERSION}" / stem
        for suffix in ["", ".sha256"]:
            stage(root / f"packages/{stem}.{extension}{suffix}")
        report = json.loads((root / "native-verification.json").read_text(encoding="utf-8"))
        if not all(report.get(field) for field in ["passed", "ui_checked", "immediate_restart_same_ports", "data_directory_lock", "missing_models_exit_nonzero"]):
            raise ValueError(f"Incomplete native verification: {platform}")
        stage(root / "native-verification.json", f"{stem}-Verification.json")
    for kind in ["sharing", "portable"]:
        source = PROJECT / f"desktop/build/{kind}-verification-{VERSION}.json"
        if not json.loads(source.read_text(encoding="utf-8"))["passed"]:
            raise ValueError(f"Failed {kind} verification")
        stage(source, f"{DESKTOP_STEM}-{kind.title()}Verification.json")
    matches = list((RELEASE / f"native-{VERSION}/JevDocumentSearchDesktopUiVerification-{VERSION}").rglob("electron-ui-verification.json"))
    if len(matches) != 1:
        raise ValueError("Expected exactly one Electron UI report")
    source = matches[0]
    ui = json.loads(source.read_text(encoding="utf-8"))
    if not ui["passed"] or ui["commit"] != args.desktop_commit:
        raise ValueError("Electron UI verification failed")
    stage(source, f"{DESKTOP_STEM}-UiVerification.json")
    source = RELEASE / f"native-archive-verification-{VERSION}.json"
    verified = json.loads(source.read_text(encoding="utf-8"))
    if len(verified) != 2 or not all(item["verified"] and item["build_commit"] == args.cli_commit for item in verified):
        raise ValueError("Native archive verification incomplete")
    stage(source, f"JevNativeArchiveVerification-{VERSION}.json")
    sums = destination / f"SHA256SUMS-{VERSION}.txt"
    sums.write_text("\n".join(f"{item['sha256']}  {item['name']}" for item in assets) + "\n", encoding="utf-8")
    assets.append({"name": sums.name, "size": sums.stat().st_size, "sha256": sha256(sums)})
    metadata = {"version": VERSION, "desktop_application_commit": args.desktop_commit, "cli_build_commit": args.cli_commit,
                "programs": [{"name": DESKTOP_PROGRAM, "role": "Desktop document search with optional restricted Web query", "platforms": ["WindowsX64"]},
                             {"name": SERVER_PROGRAM, "role": "Document administration and restricted Web query server", "platforms": ["WindowsX64", "LinuxX64"]}],
                "native_build_run": f"https://github.com/wikigsroom/Jev-Wiki-Book/actions/runs/{args.run_id}",
                "models_release": "https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0",
                "models_manifest": "https://github.com/wikigsroom/Jev-Wiki-Book/releases/download/v0.6.0/JEV-models-0.6.0-downloads.json",
                "nanojev_weights_sha256": WEIGHT_SHA256, "assets": assets}
    (destination / DOWNLOADS_MANIFEST).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"assets": len(assets) + 1, "bytes": sum(item["size"] for item in assets), "directory": str(destination)}))


if __name__ == "__main__":
    main()
