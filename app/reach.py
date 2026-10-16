"""reach.py — "can my friends connect?" for one server.

Tells the operator exactly which ports to forward on their router and to which
address, then tries to confirm the server is reachable from the internet.

A computer can't reliably test its own public address (most home routers don't
loop such traffic back), so the answer is honest about what it could and
couldn't establish:
  * "yes"     — Steam's server directory lists it, or it answered on the public
                address;
  * "unknown" — neither worked, which does NOT mean it's unreachable;
  * "stopped" — the server isn't running, so there is nothing to test.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.request

import config
import games
import monitor
from applog import app_log
from games.base import ActionError
from registry import by_key

_IP_ECHO = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip")
_cache: dict = {"ip": "", "ts": 0.0}
_cache_lock = threading.Lock()


lan_ip = monitor.lan_ip


def router_ip() -> str:
    try:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                             text=True, timeout=5).stdout.split()
        return out[out.index("via") + 1] if "via" in out else ""
    except Exception:
        return ""


def public_ip() -> str:
    """This network's public address, asked of an outside service (cached 10 min)."""
    with _cache_lock:
        if _cache["ip"] and time.time() - _cache["ts"] < 600:
            return _cache["ip"]
    for url in _IP_ECHO:
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                ip = r.read(64).decode("ascii", "replace").strip()
            socket.inet_aton(ip)
            with _cache_lock:
                _cache.update(ip=ip, ts=time.time())
            return ip
        except Exception:
            continue
    return ""


def forward_list(s) -> list[dict]:
    """The router rules this server needs: [{"port": "7780-7781", "proto", "what"}]."""
    game = games.get(s.kind)
    legacy = {"game": s.game_port, "query": s.query_port, "rcon": s.rcon_port}
    out = []
    layout = game.port_layout if game and s.kind != "custom" else []
    for p in layout:
        if not p.get("forward"):
            continue
        port = (s.port_map or {}).get(p["name"]) or legacy.get(p["name"])
        if not port:
            continue
        span = p.get("span", 1)
        out.append({"port": f"{port}-{int(port) + span - 1}" if span > 1 else str(port),
                    "first": int(port), "proto": p.get("proto", "UDP"),
                    "what": p["label"].split(" (")[0]})
    if s.kind == "custom" or not layout:
        if s.game_port:
            out.append({"port": str(s.game_port), "first": int(s.game_port),
                        "proto": "UDP and TCP", "what": "Game port"})
        if s.query_port:
            out.append({"port": str(s.query_port), "first": int(s.query_port),
                        "proto": "UDP", "what": "Query port"})
    return out


def _steam_lists(ip: str, ports: set[int]) -> bool | None:
    """Does Steam's public server directory show a server on this address using
    one of `ports`? None if Steam couldn't be asked."""
    try:
        url = ("https://api.steampowered.com/ISteamApps/GetServersAtAddress/v0001"
               f"?addr={ip}&format=json")
        with urllib.request.urlopen(url, timeout=8) as r:
            servers = json.load(r).get("response", {}).get("servers", [])
    except Exception as e:
        app_log.info("reach: steam directory lookup failed: %r", e)
        return None
    seen = set()
    for x in servers:
        seen.add(int(x.get("gameport") or 0))
        try:
            seen.add(int(str(x.get("addr", "")).rsplit(":", 1)[1]))
        except (IndexError, ValueError):
            pass
    return bool(seen & ports)


def _answers_publicly(s, ip: str, rules: list[dict]) -> bool:
    """Try the server on the public address from here. Only a success means
    anything — a failure is normal on routers that don't loop traffic back."""
    if s.has_a2s:
        try:
            import a2s
            a2s.info((ip, s.query_port), timeout=3)
            return True
        except Exception:
            pass
    game = games.get(s.kind)
    if game is not None and not getattr(game, "survives_connect_test", True):
        return False      # don't test by connecting: this game's server crashes on it
    for r in rules:
        if "TCP" in r["proto"] and monitor.tcp_open(r["first"], host=ip, timeout=3):
            return True
    return False


def closed_list(s) -> list[dict]:
    """Ports this server opens that must NOT be forwarded: admin consoles and other control
    channels. They are listed so nobody adds them to their router "just in case"."""
    game = games.get(s.kind)
    if not game or s.kind == "custom":
        return [{"port": str(s.rcon_port), "what": "Admin console"}] if s.rcon_port else []
    out = []
    for p in game.port_layout:
        if p.get("forward") or p.get("klass") != "rcon":
            continue
        port = (s.port_map or {}).get(p["name"]) or (s.rcon_port if p["name"] == "rcon" else None)
        if port:
            out.append({"port": str(port), "what": p["label"].split(" (")[0]})
    return out


def check(key: str) -> dict:
    s = by_key().get(key)
    if s is None:
        raise ActionError(f"unknown server: {key}")
    rules = forward_list(s)
    pub = public_ip()
    host = config.load().get("public_host") or pub
    out = {
        "ok": True, "name": s.name, "lan_ip": lan_ip(), "router_ip": router_ip(),
        "public_ip": pub, "join_address": f"{host}:{s.join_port or s.game_port}" if host else "",
        "rules": [{k: r[k] for k in ("port", "proto", "what")} for r in rules],
        "keep_closed": closed_list(s),
        "running": monitor.unit_active(s.unit),
    }
    if not out["running"]:
        out.update(verdict="stopped", evidence="")
        return out
    if not pub:
        out.update(verdict="unknown", evidence="no-internet")
        return out
    ports = {r["first"] for r in rules} | {int(p) for p in (s.game_port, s.query_port) if p}
    if _steam_lists(pub, ports):
        out.update(verdict="yes", evidence="steam")
    elif _answers_publicly(s, pub, rules):
        out.update(verdict="yes", evidence="answered")
    else:
        out.update(verdict="unknown", evidence="")
    return out
