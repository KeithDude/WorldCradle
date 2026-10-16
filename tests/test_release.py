"""Updating a packaged install: finding the newest release and refusing a download that doesn't
match its published checksum (against a stand-in for GitHub on this machine)."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import release

DEB = b"pretend package contents"
FILES = {}


class _GitHub(BaseHTTPRequestHandler):
    def do_GET(self):
        body = FILES.get(self.path)
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(body or b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def github(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _GitHub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setattr(release, "API", base + "/releases")
    name = "gamedash_0.2.1-1_all.deb"
    FILES.clear()
    FILES["/releases/latest"] = json.dumps({"tag_name": "v0.2.1", "body": "- better things", "assets": [
        {"name": name, "browser_download_url": f"{base}/dl/{name}"},
        {"name": name + ".sha256", "browser_download_url": f"{base}/dl/{name}.sha256"}]}).encode()
    FILES[f"/dl/{name}"] = DEB
    FILES[f"/dl/{name}.sha256"] = f"{hashlib.sha256(DEB).hexdigest()}  {name}\n".encode()
    yield base, name
    srv.shutdown()


def test_versions_compare_like_debian():
    assert release.is_newer("0.2.0-1", "0.2.0~dev+20261016.abc1234-1")
    assert release.is_newer("0.2.1-1", "0.2.0-1")
    assert not release.is_newer("0.2.0-1", "0.2.0-1")


def test_latest_release_and_a_verified_download(github, tmp_path):
    new = release.latest()
    assert new["version"] == "0.2.1-1" and new["tag"] == "v0.2.1"
    path = release.download(new, str(tmp_path))
    assert open(path, "rb").read() == DEB


def test_a_download_that_does_not_match_is_refused_and_deleted(github, tmp_path):
    base, name = github
    FILES[f"/dl/{name}"] = b"something else"
    with pytest.raises(release.ReleaseError, match="checksum"):
        release.download(release.latest(), str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_a_release_without_a_package_is_reported(github):
    FILES["/releases/latest"] = json.dumps({"tag_name": "v9", "assets": []}).encode()
    with pytest.raises(release.ReleaseError, match="no package"):
        release.latest()
