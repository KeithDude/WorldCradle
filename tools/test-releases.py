#!/usr/bin/env python3
"""A stand-in for GitHub's release list, to test `worldcradle update` before anything is published.

    tools/test-releases.py <folder with worldcradle_*.deb files> [port]

Serves every package in the folder as a release (the newest version is "latest") with its
checksum, on http://127.0.0.1:<port> (default 8765). Then, on the same computer:

    WORLDCRADLE_RELEASES_URL=http://127.0.0.1:8765/releases worldcradle update

To test the roll-back, put in a newer package that doesn't start: update installs it, sees it
doesn't answer, and puts the previous release back (also served from here).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from functools import cmp_to_key
from http.server import BaseHTTPRequestHandler, HTTPServer

FOLDER = os.path.abspath(sys.argv[1])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
BASE = f"http://127.0.0.1:{PORT}"
DEB_RE = re.compile(r"^worldcradle_(?P<version>[A-Za-z0-9.+~-]+)_all\.deb$")


def _compare(a: str, b: str) -> int:
    if a == b:
        return 0
    return 1 if subprocess.run(["dpkg", "--compare-versions", a, "gt", b]).returncode == 0 else -1


def releases() -> list[dict]:
    debs = {DEB_RE.match(n)["version"]: n for n in os.listdir(FOLDER) if DEB_RE.match(n)}
    out = []
    for version in sorted(debs, key=cmp_to_key(_compare), reverse=True):
        name = debs[version]
        out.append({"tag_name": "v" + version.rsplit("-", 1)[0], "body": f"Test release {version}",
                    "assets": [{"name": name, "browser_download_url": f"{BASE}/files/{name}"},
                               {"name": name + ".sha256", "browser_download_url": f"{BASE}/files/{name}.sha256"}]})
    return out


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        rel = releases()
        body, status = b"{}", 404
        if self.path == "/releases/latest" and rel:
            body, status = json.dumps(rel[0]).encode(), 200
        elif self.path.startswith("/releases/tags/"):
            tag = self.path.rsplit("/", 1)[1]
            match = next((r for r in rel if r["tag_name"] == tag), None)
            if match:
                body, status = json.dumps(match).encode(), 200
        elif self.path.startswith("/files/"):
            name = os.path.basename(self.path)
            deb = os.path.join(FOLDER, name.removesuffix(".sha256"))
            if DEB_RE.match(os.path.basename(deb)) and os.path.isfile(deb):
                data = open(deb, "rb").read()
                body = (f"{hashlib.sha256(data).hexdigest()}  {os.path.basename(deb)}\n".encode()
                        if name.endswith(".sha256") else data)
                status = 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("  " + fmt % args, flush=True)


print(f"Serving {len(releases())} test release(s) from {FOLDER} on {BASE}/releases", flush=True)
HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
