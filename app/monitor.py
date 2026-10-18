"""monitor.py — probes used by the poller (and the RCON clients the games use).

A few keep small caches between polls: which address answers Steam queries, and how
far each server log has been read. Everything here is best-effort and fails soft: a probe that errors or times out
returns None / [] rather than raising, so one dead server never blocks the rest.
"""
from __future__ import annotations

import os
import re
import socket
import struct
import threading

import a2s
import psutil

HOST = "127.0.0.1"
A2S_TIMEOUT = 2.5
RCON_TIMEOUT = 4.0


# ---- Steam A2S query (player count + reachability) -------------------------

# Some servers (older Source games, a few Unity ones) ignore queries that come
# from the loopback address but answer on the machine's own network address.
# Remember which address worked for each port so we don't wait out a timeout
# on every poll.
_a2s_host: dict[int, str] = {}


_ROUTE_PROBE = ("192.0.2.1", 9)   # a documentation-only address: nothing is ever sent to it


def lan_ip() -> str:
    """This computer's address on the home network (what the router forwards to). Connecting
    a UDP socket sends nothing; it only makes the system pick the outgoing interface."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(_ROUTE_PROBE)
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return ""


def _a2s_hosts(port: int, host: str | None) -> list[str]:
    if host:
        return [host]
    first = _a2s_host.get(port, HOST)
    return [first] + [h for h in (HOST, lan_ip()) if h and h != first]


def a2s_info(port: int, host: str | None = None) -> dict | None:
    """Return {'players', 'max_players', 'name', 'map'} or None if unreachable."""
    for h in _a2s_hosts(port, host):
        try:
            info = a2s.info((h, port), timeout=A2S_TIMEOUT)
        except Exception:
            continue
        if not host:
            _a2s_host[port] = h
        return {
            "players": info.player_count,
            "max_players": info.max_players,
            "name": info.server_name,
            "map": info.map_name,
        }
    return None


def a2s_player_names(port: int, host: str | None = None) -> list[str]:
    """Player names via A2S. Some games omit names (return blank entries)."""
    try:
        players = a2s.players((host or _a2s_host.get(port, HOST), port), timeout=A2S_TIMEOUT)
        return [p.name for p in players if p.name]
    except Exception:
        return []


# ---- RCON (names + control) ------------------------------------------------

def source_rcon(port: int, password: str, command: str, timeout: float = RCON_TIMEOUT,
                host: str = HOST) -> str | None:
    """Run one command over Valve's Source RCON protocol and return the reply text
    ("" if the server sent none). None if the console can't be reached or the
    password is refused. Written here rather than taken from a library so WorldCradle
    carries no GPL dependency."""
    def send(s, pid: int, ptype: int, body: str) -> None:
        payload = struct.pack("<ii", pid, ptype) + body.encode("utf-8") + b"\x00\x00"
        s.sendall(struct.pack("<i", len(payload)) + payload)

    def read_exact(s, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def read_packet(s) -> tuple[int, int, str]:
        (length,) = struct.unpack("<i", read_exact(s, 4))
        if not 10 <= length <= 1_000_000:
            raise ValueError("bad packet length")
        data = read_exact(s, length)
        pid, ptype = struct.unpack("<ii", data[:8])
        return pid, ptype, data[8:-2].decode("utf-8", "replace")

    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return None
    try:
        s.settimeout(timeout)
        send(s, 1, 3, password)                    # SERVERDATA_AUTH
        while True:                                # some servers send an empty reply first
            pid, ptype, _ = read_packet(s)
            if ptype == 2:                         # SERVERDATA_AUTH_RESPONSE
                if pid == -1:
                    return None                    # wrong password
                break
        send(s, 2, 2, command)                     # SERVERDATA_EXECCOMMAND
        pid, ptype, body = read_packet(s)
        parts = [body] if pid == 2 else []
        s.settimeout(0.3)                          # long replies arrive as several packets
        try:
            while True:
                pid, ptype, body = read_packet(s)
                if pid == 2:
                    parts.append(body)
        except (OSError, ValueError, ConnectionError):
            pass
        return "".join(parts)
    except (OSError, ValueError, ConnectionError, struct.error):
        return None
    finally:
        s.close()


def rcon_run(port: int, password: str, command: str) -> str | None:
    """Run one RCON command (strict Source protocol — ARK and others). None on failure."""
    return source_rcon(port, password, command)


_RCON_MAX_REPLY = 1 << 20   # stop reading a reply after 1 MB


def palworld_rcon(port: int, password: str, command: str,
                  timeout: float = RCON_TIMEOUT) -> str | None:
    """A lenient RCON client for servers whose RCON only resembles Valve's — Palworld,
    Conan Exiles, HumanitZ, Squad: a strict client fails on them with a 'packet ID
    mismatch'. This one doesn't check response IDs and reads whatever packets come back.
    (Its name is kept because servers' generated stop scripts call it.)"""
    def pkt(pid: int, ptype: int, body: str) -> bytes:
        payload = struct.pack("<ii", pid, ptype) + body.encode("utf-8") + b"\x00\x00"
        return struct.pack("<i", len(payload)) + payload

    try:
        s = socket.create_connection((HOST, port), timeout=timeout)
    except Exception:
        return None
    try:
        s.settimeout(timeout)
        s.sendall(pkt(1, 3, password))  # SERVERDATA_AUTH
        s.recv(4096)                    # auth response (not strictly checked)
        s.sendall(pkt(2, 2, command))   # SERVERDATA_EXECCOMMAND
        chunks = b""
        s.settimeout(1.5)
        try:
            while len(chunks) < _RCON_MAX_REPLY:
                d = s.recv(4096)
                if not d:
                    break
                chunks += d
        except socket.timeout:
            pass
        out, i = [], 0
        while i + 12 <= len(chunks):
            (length,) = struct.unpack("<i", chunks[i:i + 4])
            if length < 10:   # smallest real packet (id + type + two NULs); anything less is garbage
                break
            body = chunks[i + 12:i + 4 + length - 2]
            out.append(body.decode("utf-8", "replace"))
            i += 4 + length
        return "".join(out)
    except Exception:
        return None
    finally:
        s.close()


_ARK_PLAYER = re.compile(r"^\s*\d+\.\s*(.+?),\s*(\d+)\s*$")


def parse_ark_players(text: str) -> list[dict]:
    """Parse ARK `ListPlayers` into [{name, id}] (id is the SteamID64)."""
    if not text or "no players" in text.lower():
        return []
    out = []
    for line in text.splitlines():
        m = _ARK_PLAYER.match(line)
        if m:
            out.append({"name": m.group(1).strip(), "id": m.group(2).strip()})
    return out


def parse_palworld_players(text: str) -> list[dict]:
    """Parse Palworld `ShowPlayers` CSV (header: name,playeruid,steamid) into
    [{name, id}] where id is the SteamID (used for kick/ban)."""
    if not text:
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name,"):
            continue
        parts = [p.strip() for p in line.split(",")]
        name = parts[0]
        if not name:
            continue
        steamid = parts[2] if len(parts) >= 3 else (parts[-1] if len(parts) > 1 else "")
        out.append({"name": name, "id": steamid})
    return out


# ---- raw TCP reachability (for servers without A2S, e.g. Satisfactory) -----

def port_listening(port: int) -> bool:
    """Is a program on this computer listening on this TCP port? Asks the operating system, so the
    game itself is never contacted — some servers (Terraria) crash when a client connects and
    immediately hangs up, which is what a connection test does."""
    try:
        return any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == int(port)
                   for c in psutil.net_connections(kind="tcp"))
    except (psutil.Error, OSError, ValueError):
        return False


def ports_in_use() -> set[int]:
    """Every port a program on this computer is using to accept players or connections (TCP
    listening, or UDP bound). Asks the operating system; nothing is contacted."""
    try:
        return {c.laddr.port for c in psutil.net_connections(kind="inet")
                if c.laddr and (c.type == socket.SOCK_DGRAM or c.status == psutil.CONN_LISTEN)}
    except (psutil.Error, OSError):
        return set()


def tcp_open(port: int, host: str = HOST, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ---- Valheim (no RCON/A2S): derive player count from its log ----------------

_VAL_CONN = re.compile(r"Connections (\d+)")
_VAL_JOIN = re.compile(r"Got character ZDOID from (.+?) :")


def _tail_bytes(path: str, nbytes: int = 65536) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > nbytes:
                f.seek(size - nbytes)
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def valheim_players_from_log(path: str) -> tuple[int | None, list[str]]:
    """Latest 'Connections N' line gives the count (refreshed ~every 10 min).
    Names are best-effort from recent 'Got character ZDOID from <name>' lines."""
    text = _tail_bytes(path)
    if not text:
        return None, []
    count = None
    for m in _VAL_CONN.finditer(text):
        count = int(m.group(1))  # keep the last match
    names = _VAL_JOIN.findall(text)[-count:] if count else []
    # de-dupe preserving order
    seen, uniq = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    return count, uniq


# ---- Abiotic Factor (no RCON; who's online comes from the server log) -------
# The game does not report its players to Steam (A2S says 0 with a full lobby),
# so the log is the only source. It is followed incrementally: each call reads
# just the bytes added since the last one and applies the join/exit lines to
# the remembered roster, so a long session never scrolls out of a "tail" window.
_AF_EVENT = re.compile(
    r"LogNet: Join succeeded: (?P<joined>.+?)\s*$"
    r"|LogAbiotic: Display: CHAT LOG:  (?P<left>.+?) has exited the facility\.\s*$",
    re.M)
_roster_state: dict[str, dict] = {}   # log path -> {"ino", "pos", "online": [names]}
_roster_lock = threading.Lock()


def roster_from_log(path: str, events: re.Pattern) -> list[str] | None:
    """Names currently online according to a server log (None if the log can't
    be read). `events` has named groups `joined` and `left`. The log is followed
    incrementally; a new file (different inode, or shorter than where we were —
    servers start a fresh log on boot) resets the roster."""
    with _roster_lock:
        try:
            st = os.stat(path)
            state = _roster_state.get(path)
            if state is None or state["ino"] != st.st_ino or st.st_size < state["pos"]:
                state = _roster_state[path] = {"ino": st.st_ino, "pos": 0, "online": []}
            if st.st_size > state["pos"]:
                with open(path, "rb") as f:
                    f.seek(state["pos"])
                    chunk = f.read(st.st_size - state["pos"])
                end = chunk.rfind(b"\n") + 1          # only whole lines; keep the rest for next time
                state["pos"] += end
                for m in events.finditer(chunk[:end].decode("utf-8", "replace")):
                    if m.group("joined"):
                        if m.group("joined") not in state["online"]:
                            state["online"].append(m.group("joined"))
                    elif m.group("left") in state["online"]:
                        state["online"].remove(m.group("left"))
            return list(state["online"])
        except OSError:
            return None


def abiotic_players_from_log(path: str) -> list[str] | None:
    return roster_from_log(path, _AF_EVENT)


# Don't Starve Together: the master shard's log announces joins and leaves.
_DST_EVENT = re.compile(
    r"\[Join Announcement\] (?P<joined>.+?)\s*$|\[Leave Announcement\] (?P<left>.+?)\s*$", re.M)


def dst_players_from_log(path: str) -> list[str] | None:
    return roster_from_log(path, _DST_EVENT)


# ---- Satisfactory HTTPS Dedicated Server API (port 7777) --------------------

def _sf_api(port: int, function: str, token: str | None = None,
            data: dict | None = None, timeout: float = 5.0) -> dict | None:
    """POST to the Satisfactory HTTPS API. Self-signed cert → verify off.
    Returns the parsed JSON dict ({} for a successful empty 2xx body, e.g.
    SaveGame's 204), or None on transport failure. Error responses (4xx with a
    JSON body) are returned as-is so callers can read errorCode."""
    import json
    import ssl
    import urllib.error
    import urllib.request

    body = {"function": function}
    if data is not None:
        body["data"] = data
    req = urllib.request.Request(
        f"https://{HOST}:{port}/api/v1/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            return json.loads(raw.decode("utf-8", "replace")) if raw else {}
    except urllib.error.HTTPError as e:  # 4xx/5xx — may carry a JSON error body
        raw = e.read() or b""
        try:
            return json.loads(raw.decode("utf-8", "replace")) if raw else None
        except Exception:
            return None
    except Exception:
        return None


def satisfactory_health(port: int) -> bool:
    r = _sf_api(port, "HealthCheck", data={"clientCustomData": ""})
    return bool(r and r.get("data", {}).get("health") == "healthy")


def satisfactory_login(port: int, password: str,
                       level: str = "Administrator") -> str | None:
    """PasswordLogin → a Bearer token, or None if the password is wrong/unreachable."""
    r = _sf_api(port, "PasswordLogin",
                data={"password": password, "minimumPrivilegeLevel": level})
    if r and "data" in r and r["data"].get("authenticationToken"):
        return r["data"]["authenticationToken"]
    return None


def satisfactory_claim(port: int, server_name: str, admin_password: str,
                       join_password: str = "") -> str | None:
    """Claim a server nobody has claimed yet (what the game's Server Manager asks the first
    player to do): name it, set its admin password and, if given, its join password. Returns
    an Administrator token, or None if it is already claimed or can't be reached."""
    r = _sf_api(port, "PasswordlessLogin", data={"minimumPrivilegeLevel": "InitialAdmin"})
    initial = (r or {}).get("data", {}).get("authenticationToken")
    if not initial:
        return None                        # already claimed (or not answering)
    r = _sf_api(port, "ClaimServer", token=initial,
                data={"serverName": server_name, "adminPassword": admin_password})
    token = (r or {}).get("data", {}).get("authenticationToken")
    if token and join_password:
        _sf_api(port, "SetClientPassword", token=token, data={"password": join_password})
    return token


def satisfactory_state(port: int, token: str) -> dict | None:
    """QueryServerState (needs an admin/client Bearer token). Returns the
    serverGameState dict (numConnectedPlayers, playerLimit, ...) or None."""
    r = _sf_api(port, "QueryServerState", token=token)
    if r and "data" in r and "serverGameState" in r["data"]:
        return r["data"]["serverGameState"]
    return None


def satisfactory_save(port: int, token: str, save_name: str) -> tuple[bool, str]:
    """SaveGame to the given save (needs an Administrator token). Returns
    (ok, message)."""
    r = _sf_api(port, "SaveGame", token=token, data={"saveName": save_name}, timeout=20.0)
    if r is None:
        return False, "no response from Satisfactory API"
    if "errorCode" in r:
        return False, r.get("errorMessage") or r["errorCode"]
    return True, "saved"
