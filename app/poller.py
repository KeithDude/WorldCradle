"""poller.py — background fleet poller.

Runs a daemon thread that refreshes a snapshot of every server into an
in-memory cache on a fixed interval. Web requests read the cache (cheap, never
block on a slow/dead server). Each server's CPU and RAM come from its systemd
service's control group (see service_usage); also here: crash detection.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import psutil

import alerts
import backups
import games
import paths
import systemd
from applog import app_log
from registry import Server, load_servers

POLL_INTERVAL = 5.0  # seconds between fleet refreshes
# Each server's player limit, as last reported while it ran — so a stopped server's card still
# says "— / 10 players", even after the dashboard restarts.
PLAYER_LIMITS_FILE = paths.data("player-limits.json")


def _load_player_limits() -> dict[str, int]:
    try:
        with open(PLAYER_LIMITS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_player_limits(limits: dict[str, int]) -> None:
    tmp = PLAYER_LIMITS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(limits, f)
        os.replace(tmp, PLAYER_LIMITS_FILE)
    except OSError:
        app_log.warning("couldn't save %s", PLAYER_LIMITS_FILE)

# ---- per-server resource use, measured for the whole service ----------------------
# A server is often several processes (Wine helpers, a launcher script, a second level),
# so its CPU and RAM are read from its systemd control group, which holds all of them.
_cg_path: dict[str, str] = {}                     # unit -> /sys/fs/cgroup/... directory
_cg_last: dict[str, tuple[int, float]] = {}      # unit -> (cpu usage µs, time) at the last poll
_cg_lock = threading.Lock()


# ---- crash detection --------------------------------------------------------------
# systemd restarts a crashed server by itself and counts it (NRestarts). A server that keeps
# crashing therefore looks "running" most of the time; watch the counter instead.
CRASH_WINDOW = 15 * 60          # seconds
_crash_seen: dict[str, dict] = {}   # unit -> {"count": last NRestarts, "events": [times], "alerted": bool}


def crash_warning(unit: str, name: str) -> str:
    """'' normally; a plain-language warning while this server keeps crashing."""
    vals = systemd.show(unit, "NRestarts", "SubState")
    try:
        count = int(vals.get("NRestarts", "0") or 0)
    except ValueError:
        return ""
    now = time.monotonic()
    seen = _crash_seen.setdefault(unit, {"count": count, "events": [], "alerted": False})
    if count < seen["count"]:            # the counter starts again when someone restarts the server
        seen.update(count=count, events=[])
    elif count > seen["count"]:
        seen["events"] += [now] * (count - seen["count"])
        seen["count"] = count
    seen["events"] = [t for t in seen["events"] if now - t < CRASH_WINDOW]
    n = len(seen["events"])
    if n >= 2 or vals.get("SubState") == "auto-restart":
        if not seen["alerted"]:
            seen["alerted"] = True
            try:
                alerts.notify(f"⚠️ realmcradle: {name} keeps crashing",
                              f"{name} has crashed and restarted itself {max(n, 1)} time(s) in the last "
                              f"{CRASH_WINDOW // 60} minutes. Check its Logs on the dashboard.", "bad")
            except Exception:
                app_log.exception("crash alert failed for %s", unit)
        return (f"Keeps crashing — it restarted itself {max(n, 1)} time(s) in the last "
                f"{CRASH_WINDOW // 60} minutes. Open Logs to see why.")
    seen["alerted"] = False
    return ""


def _cgroup_dir(unit: str, pid: int | None) -> str | None:
    path = _cg_path.get(unit)
    if path and os.path.isdir(path):
        return path
    rel = ""
    try:
        if pid:
            with open(f"/proc/{pid}/cgroup", encoding="utf-8") as f:
                rel = f.read().strip().split("::", 1)[-1]
        if not rel.endswith(f"/{unit}"):
            rel = systemd.show(unit, "ControlGroup").get("ControlGroup", "")
    except (OSError, ValueError):
        return None
    path = "/sys/fs/cgroup" + rel
    if rel and os.path.isdir(path):
        _cg_path[unit] = path
        return path
    return None


def service_usage(unit: str, pid: int | None) -> tuple[float | None, int | None]:
    """(CPU as a percentage of the WHOLE computer, RAM in binary MB) used by every process
    of this server's service. CPU needs two polls to measure, so the first one gives None."""
    path = _cgroup_dir(unit, pid)
    if not path:
        return None, None
    cpu = mem = None
    try:
        with open(os.path.join(path, "cpu.stat"), encoding="utf-8") as f:
            usage = int(next(l for l in f if l.startswith("usage_usec")).split()[1])
        now = time.monotonic()
        with _cg_lock:
            last = _cg_last.get(unit)
            _cg_last[unit] = (usage, now)
        if last and now > last[1] and usage >= last[0]:
            cpus = psutil.cpu_count() or 1
            cpu = round(100.0 * (usage - last[0]) / ((now - last[1]) * 1e6 * cpus), 1)
    except (OSError, StopIteration, ValueError):
        pass
    try:
        with open(os.path.join(path, "cgroup.procs"), encoding="utf-8") as f:
            pids = [int(x) for x in f.read().split()]
        rss = 0
        for p in pids:
            try:
                rss += psutil.Process(p).memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        mem = round(rss / 2**20) if pids else None
    except (OSError, ValueError):
        pass
    return cpu, mem


class Poller:
    def __init__(self, interval: float = POLL_INTERVAL):
        self.interval = interval
        self._lock = threading.Lock()
        self._snapshot: dict = {"servers": {}, "box": {}, "ts": 0.0}
        self._max_players = _load_player_limits()   # key -> last known player limit
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._alerts = alerts.AlertEngine()
        psutil.cpu_percent(interval=None)  # prime system-wide CPU sampling

    # ---- lifecycle --------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="poller", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot

    # ---- polling ----------------------------------------------------------

    def _loop(self):
        while not self._stop.is_set():
            try:
                snap = self._poll_once()
                with self._lock:
                    self._snapshot = snap
                self._alerts.process(snap)  # fire transition alerts (best-effort)
            except Exception as e:  # never let the thread die
                app_log.exception("poll cycle failed")
                with self._lock:
                    self._snapshot = {**self._snapshot, "error": repr(e)}
            self._stop.wait(self.interval)

    @staticmethod
    def _index_processes() -> list[tuple[int, str]]:
        """(pid, command line) of every process, read once per cycle."""
        out = []
        for p in psutil.process_iter(["cmdline"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
                if cmd:
                    out.append((p.pid, cmd))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out

    @staticmethod
    def _find_pid(match: str, procs) -> int | None:
        """The server's main process, if running: a hint for finding its control group."""
        return next((pid for pid, cmd in procs if match and match in cmd), None)

    def _poll_once(self) -> dict:
        procs = self._index_processes()
        defs = load_servers()

        # Local probes (systemd + /proc) are quick: one after another in this thread.
        base = {s.key: self._poll_base(s, procs) for s in defs}

        # Network probes (RCON / A2S / TCP) are slow and independent — fan out so
        # total poll time is the slowest single server, not the sum.
        to_probe = [s for s in defs if base[s.key].pop("_probe", False)]
        if to_probe:
            with ThreadPoolExecutor(max_workers=len(to_probe)) as ex:
                results = ex.map(self._probe_network, to_probe)
            for s, net in zip(to_probe, results):
                base[s.key].update(net)
        changed = False
        for key, st in base.items():
            if st.get("max_players"):
                changed |= self._max_players.get(key) != st["max_players"]
                self._max_players[key] = st["max_players"]
            else:
                st["max_players"] = self._max_players.get(key)
        if changed:
            _save_player_limits(self._max_players)

        servers = base
        vm = psutil.virtual_memory()
        try:
            load1, load5, load15 = os.getloadavg()
        except OSError:
            load1 = load5 = load15 = 0.0
        try:   # the disk the game servers are installed on (home folder)
            du = psutil.disk_usage(os.path.expanduser("~"))
            disk = {"disk_used_gb": round(du.used / 2**30, 1), "disk_total_gb": round(du.total / 2**30, 1),
                    "disk_percent": du.percent}
        except OSError:
            disk = {}
        # sizes in binary gigabytes (1 GB = 1024 × 1024 × 1024 bytes), as operating systems show them
        box = {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_count": psutil.cpu_count(),
            "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "mem_used_gb": round((vm.total - vm.available) / 2**30, 1),
            "mem_total_gb": round(vm.total / 2**30, 1),
            "mem_percent": vm.percent,
            **disk,
        }
        return {"servers": servers, "box": box, "ts": time.time()}

    @staticmethod
    def _backup_warn(s: Server) -> str:
        """Non-empty when this server has save data on disk but no recent backup
        — the daily job failing must be visible, not just a line in a log."""
        try:
            if not any(os.path.exists(p["path"]) for p in backups.save_paths(s)):
                return ""  # nothing to back up (no save yet / no save folder set)
            age = backups.newest_age_hours(s.key)
        except Exception:
            return ""
        if age is None:
            return "No backup of this server's save exists yet"
        if age > backups.STALE_HOURS:
            return f"Last backup is {age / 24:.0f} day(s) old — backups may be failing"
        return ""

    def _poll_base(self, s: Server, procs) -> dict:
        """Local-only probe: systemd state + resource use. Sets a private
        '_probe' flag telling _poll_once whether network probes are warranted."""
        online = systemd.is_active(s.unit)
        game = games.get(s.kind)
        st: dict = {
            "key": s.key, "name": s.name, "kind": s.kind, "unit": s.unit,
            "server_name": s.server_name, "join_port": s.join_port,
            "steam_app": s.steam_app, "managed": s.managed,
            "game_port": s.game_port, "query_port": s.query_port,
            "rcon_port": s.rcon_port,
            "online": online,
            "enabled": systemd.is_enabled(s.unit),
            "cpu_percent": None, "mem_mb": None,
            "players": None, "player_names": [], "player_detail": [], "max_players": None,
            "reachable": None, "note": "",  # reachable: True / False / None=unknown
            "sf": None,  # Satisfactory extra state (tick rate, phase, uptime, …)
            "actions": sorted(game.actions) if game else [],   # which in-game buttons it has
            # which rows the card shows: they depend on the game, not on whether it's running
            "rows": game.card_rows(s) if game else {"players": False, "answering": False, "server_stats": False},
            "backup_warn": self._backup_warn(s),
            "crash_warn": crash_warning(s.unit, s.name) if (online or s.managed == "realmcradle") else "",
            "_probe": False,
        }

        if online:
            # share of the whole computer's processor, and RAM in binary MB, for all of
            # this server's processes together
            st["cpu_percent"], st["mem_mb"] = service_usage(s.unit, self._find_pid(s.proc_match, procs))
            st["_probe"] = True
        return st

    def _probe_network(self, s: Server) -> dict:
        """Slow network probes — dispatched to the server's game type, which
        returns players / player_names / player_detail / max_players / reachable
        (/ sf). Runs in a worker thread; touches no shared poller state."""
        game = games.get(s.kind)
        if game is None:
            return {}
        try:
            return game.probe(s)
        except Exception:
            app_log.exception("probe failed for %s", s.key)
            return {}


# Module singleton.
poller = Poller()


if __name__ == "__main__":
    poller.start()
    time.sleep(POLL_INTERVAL + 6)  # let it prime CPU then take a real sample
    print(json.dumps(poller.snapshot(), indent=2, default=str))
