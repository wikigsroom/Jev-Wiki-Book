"""Release names shared by the runtime and native packaging tools."""

VERSION = "0.6.2"
DESKTOP_PROGRAM = "JevDocumentSearchDesktop"
SERVER_PROGRAM = "JevDocumentAdminQueryServer"
DESKTOP_STEM = f"{DESKTOP_PROGRAM}WindowsX64Portable-{VERSION}"
DOWNLOADS_MANIFEST = f"JevWikiBookDownloads-{VERSION}.json"


def server_stem(platform, version=VERSION):
    if platform not in {"Windows", "Linux"}:
        raise ValueError("Supported release platforms are Windows and Linux")
    return f"{SERVER_PROGRAM}{platform}X64-{version}"
