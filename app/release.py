"""release.py — WorldCradle's published versions, for `worldcradle update` when WorldCradle was installed
from its package.

Each release on GitHub carries the package (worldcradle_<version>_all.deb) and its SHA-256 checksum
(<package>.sha256). A download is used only if it matches that checksum.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess

import requests

import project

PACKAGE = "worldcradle"
# GitHub's list of releases. WORLDCRADLE_RELEASES_URL points it at a stand-in instead, to test
# updates before anything is published (tools/test-releases.py).
API = os.environ.get("WORLDCRADLE_RELEASES_URL") or \
    project.PROJECT_URL.replace("https://github.com/", "https://api.github.com/repos/") + "/releases"
DEB_RE = re.compile(r"^worldcradle_(?P<version>[A-Za-z0-9.+~-]+)_all\.deb$")
TIMEOUT = 30


class ReleaseError(Exception):
    """Something the owner can act on, in plain words."""


def installed_version() -> str | None:
    """The installed package's version, or None when WorldCradle didn't come from the package."""
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", PACKAGE],
                           capture_output=True, text=True, timeout=30)
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def is_newer(candidate: str, current: str) -> bool:
    """Debian's own version comparison (so 0.2.0~dev sorts before 0.2.0)."""
    return subprocess.run(["dpkg", "--compare-versions", candidate, "gt", current]).returncode == 0


def _get(url: str) -> requests.Response:
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"Accept": "application/vnd.github+json"})
    except requests.RequestException:
        raise ReleaseError("couldn't reach GitHub — check the internet connection")
    if r.status_code == 404:
        raise ReleaseError("no published version was found")
    if r.status_code >= 400:
        raise ReleaseError(f"GitHub answered with an error ({r.status_code})")
    return r


def _describe(release: dict) -> dict:
    assets = {a.get("name", ""): a.get("browser_download_url", "") for a in release.get("assets") or []}
    deb = next((n for n in assets if DEB_RE.match(n)), None)
    if not deb or f"{deb}.sha256" not in assets:
        raise ReleaseError(f"the release {release.get('tag_name', '')} has no package to install")
    return {"tag": release.get("tag_name", ""), "version": DEB_RE.match(deb)["version"],
            "notes": release.get("body") or "", "name": deb,
            "deb_url": assets[deb], "sha_url": assets[f"{deb}.sha256"]}


def latest() -> dict:
    """The newest published release: {tag, version, notes, name, deb_url, sha_url}."""
    return _describe(_get(f"{API}/latest").json())


def for_version(version: str) -> dict:
    """The release that published this package version (to put it back after a failed update)."""
    upstream = version.rsplit("-", 1)[0]          # 0.2.1-1 → 0.2.1
    return _describe(_get(f"{API}/tags/v{upstream}").json())


def download(release: dict, folder: str) -> str:
    """Download a release's package into folder and check it against its published checksum.
    Returns the file's path; raises ReleaseError (and keeps nothing) if it doesn't match."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, release["name"])
    expected = _get(release["sha_url"]).text.split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReleaseError("the published checksum is unreadable — not installing")
    digest = hashlib.sha256()
    try:
        with requests.get(release["deb_url"], stream=True, timeout=TIMEOUT) as r, open(path, "wb") as f:
            r.raise_for_status()
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                digest.update(chunk)
    except (requests.RequestException, OSError) as e:
        _remove(path)
        raise ReleaseError(f"downloading the new version failed: {e}")
    if digest.hexdigest() != expected:
        _remove(path)
        raise ReleaseError("the download doesn't match its published checksum — not installing")
    return path


def install(path: str) -> None:
    """Install a downloaded package (asks for the computer's password). The package restarts the
    dashboard itself."""
    r = subprocess.run(["sudo", "apt-get", "install", "-y", "--allow-downgrades", os.path.abspath(path)])
    if r.returncode != 0:
        raise ReleaseError("installing the package failed (see the messages above)")


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
