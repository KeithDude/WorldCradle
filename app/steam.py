"""steam.py — everything that talks to steamcmd (Valve's server downloader).

One place for: finding steamcmd, fetching a private copy when the system has
none (no root needed), and installing/updating a dedicated server while
reporting download progress. Used by the game installer (installs.py), the
update checker (updates.py) and update-apply (controls.py).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from applog import app_log
from games.base import ActionError

# Our own copy lives beside the backups, outside the code and the config dir.
PRIVATE_DIR = os.path.expanduser("~/.local/share/gamedash/steamcmd")
TARBALL_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
_PROGRESS = re.compile(r"Update state \(0x[0-9a-f]+\) ([a-z ]+?), progress: ([\d.]+) \((\d+) / (\d+)\)")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_BUILDID = re.compile(r'"buildid"\s*"(\d+)"')


def find() -> str | None:
    """Path of a usable steamcmd, or None. Prefers the system package."""
    for cand in (shutil.which("steamcmd"), "/usr/games/steamcmd",
                 os.path.join(PRIVATE_DIR, "steamcmd.sh")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def ensure() -> str:
    """Return a steamcmd path, downloading Valve's copy into PRIVATE_DIR if the
    system doesn't have one. Raises ActionError with a next step on failure."""
    path = find()
    if path:
        return path
    try:
        os.makedirs(PRIVATE_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=PRIVATE_DIR, suffix=".tar.gz", delete=False) as tmp:
            with urllib.request.urlopen(TARBALL_URL, timeout=60) as r:
                shutil.copyfileobj(r, tmp)
        try:
            with tarfile.open(tmp.name, "r:gz") as tf:
                tf.extractall(PRIVATE_DIR, filter="data")
        finally:
            os.unlink(tmp.name)
    except Exception as e:
        app_log.warning("steamcmd download failed: %r", e)
        raise ActionError("Couldn't download the Steam server tool (steamcmd). Check this "
                          "computer's internet connection and try again.")
    path = find()
    if not path:
        raise ActionError("The Steam server tool (steamcmd) downloaded but isn't usable.")
    # It is a 32-bit program: without the system's 32-bit libraries it can't start.
    try:
        r = subprocess.run([path, "+quit"], capture_output=True, text=True, timeout=600)
        broken = r.returncode != 0 and "No such file" in (r.stdout + r.stderr)
    except Exception:
        broken = True
    if broken:
        raise ActionError("The Steam server tool needs this computer's 32-bit support libraries, "
                          "which aren't installed. Run the GameDash installer again (it adds "
                          "them), or ask whoever manages this computer to install 'lib32gcc-s1'.")
    return path


def installed_build(install_dir: str, app: int) -> str | None:
    try:
        acf = os.path.join(install_dir, "steamapps", f"appmanifest_{app}.acf")
        m = _BUILDID.search(open(acf, encoding="utf-8", errors="replace").read())
        return m.group(1) if m else None
    except OSError:
        return None


def latest_build(app: int) -> str | None:
    path = find()
    if not path:
        return None
    try:
        r = subprocess.run([path, "+login", "anonymous", "+app_info_update", "1",
                            "+app_info_print", str(app), "+quit"],
                           capture_output=True, text=True, timeout=150)
    except Exception as e:
        app_log.warning("steamcmd update-check for %s failed: %r", app, e)
        return None
    m = _BUILDID.search(r.stdout)  # first buildid = public branch
    return m.group(1) if m else None


def app_update(app: int, install_dir: str, platform: str | None = None,
               on_progress=None, timeout: int = 6 * 3600, beta: str | None = None) -> tuple[bool, str]:
    """Install or update a dedicated server into `install_dir`.

    `platform="windows"` fetches the Windows build (for servers run under
    Wine). `on_progress(phase, percent)` is called as steamcmd reports
    ("downloading"/"verifying"..., 0-100). Returns (ok, last lines of output).

    steamcmd often exits non-zero the first time (it updates itself, or leaves
    the app in a half-configured state), so a failed pass is retried."""
    path = ensure()
    os.makedirs(install_dir, exist_ok=True)
    cmd = [path]
    if platform:
        cmd += ["+@sSteamCmdForcePlatformType", platform]
    cmd += ["+force_install_dir", install_dir, "+login", "anonymous",
            "+app_update", str(app), *(["-beta", beta] if beta else []), "validate", "+quit"]
    tail: list[str] = []
    for attempt in range(1, 4):
        tail = []
        ok = False
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, errors="replace", bufsize=1)
        except OSError as e:
            return False, f"could not start steamcmd: {e}"
        try:
            for line in p.stdout:
                line = _ANSI.sub("", line).strip()   # steamcmd colours its output
                if not line:
                    continue
                tail = (tail + [line])[-12:]
                m = _PROGRESS.search(line)
                if m and on_progress:
                    try:
                        on_progress(m.group(1).strip(), float(m.group(2)))
                    except Exception:
                        pass
                if "Success! App" in line and "fully installed" in line:
                    ok = True
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            return False, "steamcmd took too long and was stopped"
        if ok:
            return True, "\n".join(tail)
        app_log.warning("steamcmd app_update %s attempt %d did not finish: %s",
                        app, attempt, " | ".join(tail[-3:]))
    return False, "\n".join(tail)
