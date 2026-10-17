#!/usr/bin/env python3
"""Try one game end to end through the dashboard, the way its owner would:

    install it → add a server (and start it) → wait until it runs and answers → read its log →
    stop it (and check it stopped cleanly) → remove the server → uninstall the game

    venv/bin/python tools/test-game.py <game kind> [--keep] [--wait MINUTES] [--set field=value …]

Run it on the computer GameDash runs on. It asks for the dashboard password (or reads
GAMEDASH_TEST_PASSWORD). --keep leaves the game installed afterwards; --set fills in a form
field (e.g. a token the game requires). Prints what happened at each step and a verdict.
It doesn't play the game: whether players can join still needs a person with the game.
"""
from __future__ import annotations

import getpass
import glob
import json
import os
import re
import subprocess
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()
BASE = os.environ.get("GAMEDASH_URL", "https://localhost:8443")


class Dashboard:
    def __init__(self, password: str):
        self.s = requests.Session()
        self.s.verify = False                    # the dashboard's own certificate
        self.s.post(BASE + "/login", data={"password": password}, timeout=30)
        page = self.s.get(BASE + "/admin", timeout=30).text
        m = re.search(r'name="csrf" content="([^"]+)"', page)
        if not m:
            sys.exit("Couldn't sign in to the dashboard — wrong password?")
        self.headers = {"X-CSRF-Token": m.group(1)}

    def get(self, path):
        return self.s.get(BASE + path, timeout=60).json()

    def post(self, path, body):
        return self.s.post(BASE + path, json=body, headers=self.headers, timeout=300).json()

    def feed(self):
        return self.get("/api/admin.json")

    def wait_job(self, field, minutes=60):
        last, end = None, time.time() + minutes * 60
        while time.time() < end:
            job = self.feed().get(field) or {}
            now = f"{job.get('step', '')} {job.get('percent', '')}".strip()
            if now and now != last:
                say(f"   … {now}")
                last = now
            if job.get("state") in ("done", "failed"):
                return job
            time.sleep(5)
        return {"state": "failed", "message": f"still running after {minutes} minutes"}


def expected_ports(v) -> list:
    """The ports a running server must have open: its game port, and its query port when the
    game answers Steam queries (some only open it when listed publicly)."""
    return [p for p in (v.get("game_port"), v.get("query_port") if v.get("rows", {}).get("answering") else None) if p]


def say(text=""):
    print(text, flush=True)


def unit(key, *props):
    out = subprocess.run(["systemctl", "--user", "show", f"gamedash-{key}.service",
                          *[a for p in props for a in ("-p", p)]], capture_output=True, text=True).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def main(argv) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    kind, keep, wait_minutes, fields = argv[0], "--keep" in argv, 15, {}
    for i, a in enumerate(argv):
        if a == "--wait":
            wait_minutes = float(argv[i + 1])
        if a == "--set":
            k, _, v = argv[i + 1].partition("=")
            fields[k] = v
    password = os.environ.get("GAMEDASH_TEST_PASSWORD") or getpass.getpass("Dashboard password: ")
    d = Dashboard(password)
    key = f"gt-{kind}"[:31].replace("_", "-")
    result = {"game": kind, "steps": {}}

    def step(name, ok, detail=""):
        result["steps"][name] = {"ok": ok, "detail": detail}
        say(f"{'✓' if ok else '✗'} {name}{': ' + detail if detail else ''}")
        return ok

    games = {g["kind"]: g for g in d.get("/admin/games")["games"]}
    if kind not in games:
        say(f"Unknown game: {kind}")
        return 2
    game = games[kind]
    say(f"== {game['label']} ({kind})")
    installed_before = game["installed"]
    try:
        # 1. install
        if not installed_before:
            t0 = time.time()
            r = d.post("/admin/games/install", {"kind": kind})
            if not r.get("ok"):
                return finish(result, step("install", False, r.get("error", "")))
            job = d.wait_job("install_job", 120)
            if not step("install", job.get("ok", False), f"{job.get('message', '')} ({(time.time() - t0) / 60:.1f} min)"):
                return finish(result, False)
        else:
            step("install", True, "already installed")

        # 2. add a server and start it
        types = {t["kind"]: t for t in d.get("/admin/servers/types")["types"]}
        spec = {"kind": kind, "key": key, "name": f"GameDash test {kind}", "start": True, "confirm": True,
                "eula": True}
        for f in types[kind]["extra_fields"]:
            if f.get("default") is not None and not f["name"].startswith("port_"):
                spec[f["name"]] = f["default"]
        spec.update(fields)
        r = d.post("/admin/servers/add", spec)
        if r.get("confirm_required") or (r.get("ok") and "Provisioning" in r.get("message", "")):
            job = d.wait_job("provision_job", 60)
            r = {"ok": job.get("ok", False), "message": job.get("message", ""), "error": job.get("message", "")}
        if not step("add server", r.get("ok", False), r.get("message") or r.get("error", "")):
            return finish(result, False)

        # 3. wait until it runs (and answers, for games that can be asked)
        t0, seen = time.time(), {}
        while time.time() - t0 < wait_minutes * 60:
            v = d.feed()["servers"].get(key, {})
            seen = v
            rows = v.get("rows", {})
            listening = subprocess.run(["ss", "-tulnH"], capture_output=True, text=True).stdout
            ports_open = all(re.search(rf"[:.]{p}\s", listening) for p in expected_ports(v))
            ready = v.get("online") and ports_open and (not rows.get("answering") or v.get("reachable")) \
                and (not rows.get("players") or v.get("players") is not None)
            if ready:
                break
            time.sleep(10)
        took = f"after {(time.time() - t0) / 60:.1f} min"
        rows = seen.get("rows", {})
        step("running", bool(seen.get("online")), took)
        if rows.get("answering"):
            step("answering", bool(seen.get("reachable")), took)
        if rows.get("players"):
            step("reports players", seen.get("players") is not None,
                 f"{seen.get('players')} / {seen.get('max_players')}")
        listening = subprocess.run(["ss", "-tulnH"], capture_output=True, text=True).stdout
        ports = expected_ports(seen)
        missing = [p for p in ports if not re.search(rf"[:.]{p}\s", listening)]
        step("listening on its ports", not missing, f"{ports}" + (f", not {missing}" if missing else ""))
        # the in-game buttons the game offers (Save, Message), pressed for real
        for action in [a for a in ("save", "broadcast") if a in seen.get("actions", [])]:
            body = {"key": key, "action": action, "message": "GameDash test message"}
            r = d.post("/admin/action", body)
            step(f"{'Save' if action == 'save' else 'Message'} button", r.get("ok", False),
                 r.get("message") or r.get("error", ""))
            time.sleep(3)
        log = d.get(f"/admin/logs/{key}?lines=40").get("text", "")
        result["log_tail"] = log[-3000:]
        say("   last log lines:\n" + "\n".join("     " + l for l in log.splitlines()[-12:]))

        # 4. stop, and check it stopped cleanly
        t0 = time.time()
        r = d.post("/admin/action", {"key": key, "action": "stop", "confirm": True})
        state = unit(key, "ActiveState", "Result", "ExecMainStatus")
        clean = r.get("ok") and state.get("ActiveState") in ("inactive", "failed")
        step("stop", bool(clean), f"{r.get('message') or r.get('error')} in {time.time() - t0:.0f} s; "
                                  f"systemd: {state.get('Result')} (exit {state.get('ExecMainStatus')})")
        return finish(result, True)
    finally:
        # 5. clean up
        if any(s for s in d.feed()["servers"] if s == key):
            r = d.post("/admin/servers/remove", {"key": key})
            step("remove server", r.get("ok", False), r.get("message") or r.get("error", ""))
        # a game that needs its own copy per server leaves that copy behind on removal (some keep
        # their world in it) — delete the test's own copy
        for leftover in glob.glob(os.path.expanduser(f"~/*-{key}")):
            if os.path.isdir(leftover) and key.startswith("gt-"):
                subprocess.run(["rm", "-rf", "--", leftover])
                say(f"✓ deleted the test server's copy of the game ({leftover})")
        if not installed_before and not keep:
            r = d.post("/admin/games/uninstall", {"kind": kind})
            step("uninstall", r.get("ok", False), r.get("message") or r.get("error", ""))
        with open(f"gametest-{kind}.json", "w") as f:
            json.dump(result, f, indent=1)


def finish(result, ok) -> int:
    failed = [n for n, s in result["steps"].items() if not s["ok"]]
    say(f"== {'PASSED' if ok and not failed else 'FAILED: ' + ', '.join(failed)}")
    return 0 if ok and not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
