"""osupdates.py — periodic OS (apt) update checker for the host box.

Why this doesn't just read the system apt state: the usual sources for "how many
updates are pending" (``/usr/lib/update-notifier/apt-check``, or apt's own
lists in /var/lib/apt/lists) are only as fresh as the last ``apt update``, and
refreshing those needs root. On a box where the periodic refresh is off
(``APT::Periodic::Update-Package-Lists "0"``) those lists go stale and apt-check
happily reports "0 updates" forever — a false all-clear, which is worse than no
indicator at all.

So we keep our OWN package lists under the data root and refresh them with an
unprivileged ``apt-get update`` pointed at that private directory. Reading the
installed set still uses the real ``/var/lib/dpkg/status`` (read-only), so the
comparison is accurate. Nothing here touches system apt state, needs sudo, or
installs anything — it is strictly read-only reporting.

Refreshing downloads package lists (tens of MB) so it runs on a long interval
on its own thread, same shape as updates.py; the dashboard reads the cache.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time

import paths
from applog import app_log

CHECK_INTERVAL = 6 * 3600   # seconds between automatic checks
UPDATE_TIMEOUT = 300        # apt-get update — network bound
SIMULATE_TIMEOUT = 120      # apt-get --just-print dist-upgrade — local
MAX_PACKAGE_NAMES = 40      # cap what we hand the UI

REBOOT_FLAG = "/var/run/reboot-required"
REBOOT_PKGS = "/var/run/reboot-required.pkgs"

# "Inst pkg [1.0-1] (1.0-2 Ubuntu:25.10/questing-security [amd64])", sometimes
# with a trailing dependency annotation: "... [amd64]) [perl:amd64 ]". We only
# read the tail for the security flag, so leave it unanchored rather than trying
# to model every suffix apt can append.
_INST = re.compile(
    r"^Inst\s+(?P<name>\S+)\s+"
    r"(?:\[(?P<cur>[^\]]*)\]\s+)?"
    r"\((?P<new>\S+)\s+(?P<origin>.*)$"
)


def _apt_root() -> str:
    """Private apt list/cache dir, created on demand."""
    root = paths.data("aptcache")
    for sub in ("lists/partial", "cache/archives/partial"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    return root


def _apt_opts(root: str) -> list[str]:
    opts = [
        "-o", f"Dir::State::Lists={root}/lists",
        "-o", f"Dir::Cache={root}/cache",
        # Compare against the REAL installed set (read-only).
        "-o", "Dir::State::status=/var/lib/dpkg/status",
        # We own these dirs and never write system apt state, so no lock needed.
        "-o", "Debug::NoLocking=1",
        # Skip translation files — we only parse package names/versions.
        "-o", "Acquire::Languages=none",
        # Don't persist apt's multi-hundred-MB binary caches; re-parsing the
        # lists costs a few seconds and this only runs every few hours.
        "-o", "Dir::Cache::pkgcache=",
        "-o", "Dir::Cache::srcpkgcache=",
    ]
    # AppStream (DEP-11) metadata and command-not-found indexes are for desktop
    # tooling; we never read them. NB: do NOT similarly restrict architectures —
    # foreign arches (i386 here, for steamcmd) have real installed packages whose
    # updates we'd otherwise miss.
    for target in ("DEP-11", "DEP-11-icons-small", "DEP-11-icons",
                   "DEP-11-icons-hidpi", "CNF"):
        opts += ["-o", f"Acquire::IndexTargets::deb::{target}::DefaultEnabled=false"]
    return opts


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "LC_ALL": "C", "DEBIAN_FRONTEND": "noninteractive"},
    )


def _refresh_lists(root: str) -> str | None:
    """apt-get update into the private dir. Returns an error string, or None."""
    try:
        r = _run(["apt-get", "update", *_apt_opts(root)], UPDATE_TIMEOUT)
    except Exception as e:
        return f"apt-get update failed: {e!r}"
    if r.returncode != 0:
        # Partial failures (one dead mirror) still leave usable lists, so log
        # and continue — the counts below just may be slightly incomplete.
        app_log.warning("os update: apt-get update rc=%s: %s",
                        r.returncode, (r.stderr or "").strip()[:300])
    return None


def _upgradable(root: str) -> tuple[list[dict], str | None]:
    """Simulate a dist-upgrade and parse the resulting Inst lines."""
    try:
        r = _run(["apt-get", "--just-print", "dist-upgrade", *_apt_opts(root)],
                 SIMULATE_TIMEOUT)
    except Exception as e:
        return [], f"apt-get dist-upgrade simulation failed: {e!r}"
    if r.returncode != 0:
        return [], (r.stderr or "apt-get dist-upgrade simulation failed").strip()[:300]

    pkgs: list[dict] = []
    for line in r.stdout.splitlines():
        m = _INST.match(line.strip())
        if not m:
            continue
        origin = m.group("origin")
        pkgs.append({
            "name": m.group("name"),
            "current": m.group("cur") or "",
            "new": m.group("new"),
            "security": "-security" in origin,
        })
    # Security first, then alphabetical — the UI shows a truncated head.
    pkgs.sort(key=lambda p: (not p["security"], p["name"]))
    return pkgs, None


def _reboot_required() -> tuple[bool, list[str]]:
    if not os.path.exists(REBOOT_FLAG):
        return False, []
    try:
        with open(REBOOT_PKGS, encoding="utf-8", errors="replace") as fh:
            pkgs = sorted({ln.strip() for ln in fh if ln.strip()})
    except OSError:
        pkgs = []
    return True, pkgs


def _os_name() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


class OSUpdateChecker:
    def __init__(self, interval: int = CHECK_INTERVAL):
        self.interval = interval
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._data: dict = {"ok": False, "checking": False, "os_name": _os_name()}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="osupdates", daemon=True)
        self._thread.start()

    def trigger(self):
        """Ask the background thread to refresh now (non-blocking)."""
        self._wake.set()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)

    def _set(self, **kw):
        with self._lock:
            self._data.update(kw)

    def _loop(self):
        self._stop.wait(60)  # let the app settle before the first (slow) check
        while not self._stop.is_set():
            self.refresh()
            self._wake.wait(self.interval)
            self._wake.clear()

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False):
            return  # one already running
        try:
            self._set(checking=True)
            root = _apt_root()
            err = _refresh_lists(root)
            # Our own fetch stamp: apt preserves each list file's remote
            # Last-Modified, so their mtimes are repo publish times, not ours.
            # On a failed refresh keep the previous stamp — the counts below
            # are then answered from those older lists.
            lists_ts = time.time() if err is None else self.snapshot().get("lists_ts", 0.0)
            pkgs, perr = ([], err) if err else _upgradable(root)
            err = err or perr
            reboot, reboot_pkgs = _reboot_required()

            rec = {
                "ok": err is None,
                "error": err,
                "checking": False,
                "os_name": _os_name(),
                "count": len(pkgs),
                "security_count": sum(1 for p in pkgs if p["security"]),
                "packages": pkgs[:MAX_PACKAGE_NAMES],
                "truncated": max(0, len(pkgs) - MAX_PACKAGE_NAMES),
                "reboot_required": reboot,
                "reboot_packages": reboot_pkgs,
                "lists_ts": lists_ts,
                "checked_ts": time.time(),
            }
            self._set(**rec)
            if err:
                app_log.warning("os update check failed: %s", err)
            else:
                app_log.info("os update check: %d upgradable (%d security)%s",
                             rec["count"], rec["security_count"],
                             ", reboot required" if reboot else "")
        except Exception as e:  # never let the thread die
            app_log.exception("os update check crashed: %r", e)
            self._set(ok=False, checking=False, error=repr(e), checked_ts=time.time())
        finally:
            self._refresh_lock.release()


checker = OSUpdateChecker()
