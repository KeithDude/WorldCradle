"""installs.py — install a game's dedicated server from the dashboard.

A catalog of the games GameDash knows how to run (what each needs, whether it
is installed) and a single background job that downloads one with steamcmd,
reporting progress for the admin page.
"""
from __future__ import annotations

import os
import shutil
import threading

import config
import games
import jobs
from applog import app_log, audit_log
from games.base import ActionError

install_job = jobs.Job("install")


def status() -> dict:
    return install_job.status()


def _installable() -> list:
    return sorted((g for g in games.all_types() if g.install_marker),
                  key=lambda g: (g.title or g.label).lower())


def is_installed(game) -> bool:
    return os.path.exists(os.path.join(config.install_dir(game.kind), game.install_marker))


def _missing(game) -> list[str]:
    """Programs this game's server needs that aren't on this computer."""
    import ctypes.util
    return [prog for prog in game.requires if not shutil.which(prog)] + \
           [f"lib{lib}" for lib in game.requires_libs if not ctypes.util.find_library(lib)]


def steam_terms_url() -> str:
    from games.eulas import STEAM_TERMS
    return STEAM_TERMS


def catalog() -> list[dict]:
    out = []
    for g in _installable():
        d = config.install_dir(g.kind)
        try:
            free_gb = shutil.disk_usage(os.path.dirname(d.rstrip("/")) or "/").free / 2**30
        except OSError:
            free_gb = None
        out.append({
            "kind": g.kind, "label": g.label, "title": g.title or g.label,
            "installed": is_installed(g), "dir": d,
            "size_gb": g.install_gb, "ram_note": g.ram_note, "about": g.about,
            "eula": g.eula, "steam": bool(g.steam_app),
            "missing": _missing(g), "free_gb": round(free_gb, 1) if free_gb is not None else None,
        })
    return out


def start(kind: str) -> dict:
    game = games.get(kind)
    if game is None or game not in _installable():
        raise ActionError("That isn't a game GameDash can install.")
    import controls
    if controls.update_status().get("state") == "running":
        raise ActionError("A game update is running — wait for it to finish, then try again.")
    missing = _missing(game)
    if missing:
        raise ActionError(f"{game.label} needs {', '.join(missing)} on this computer first. "
                          f"Run the GameDash installer again with that option, then come back.")
    if is_installed(game):
        raise ActionError(f"{game.label} is already installed. To get a newer version, use "
                          f"“Update now” on one of its servers.")
    d = config.install_dir(kind)
    try:
        free = shutil.disk_usage(os.path.dirname(d.rstrip("/")) or "/").free
    except OSError:
        free = None
    need = int(game.install_gb * 1.15 * 2**30)
    if free is not None and free < need:
        raise ActionError(f"Not enough disk space for {game.label}: it needs about "
                          f"{game.install_gb:g} GB and only {free / 2**30:.0f} GB is free.")
    install_job.begin(f"{install_job.get('label', 'Another game')} is still installing — one at a time.",
                      kind=kind, label=game.label, percent=0.0, step="Getting ready")
    audit_log.info("game INSTALL started kind=%s dir=%s", kind, d)
    threading.Thread(target=_run, args=(game, d), name=f"install-{kind}", daemon=True).start()
    return {"ok": True, "message": f"Installing {game.label} — this page shows the progress. "
                                   f"You can leave the page; it keeps going."}


def _reason(tail: str) -> str:
    """The most useful line of an installer's output: an error line if there is one."""
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    errors = [ln for ln in lines if "error" in ln.lower() or "failed" in ln.lower()]
    return ((errors or lines or ["unknown error"])[-1]).strip()[:200]


_PHASES = {"downloading": "Downloading", "verifying install": "Checking files",
           "verifying update": "Checking files", "preallocating": "Reserving disk space",
           "reconfiguring": "Preparing", "committing": "Finishing up"}


def _run(game, d: str) -> None:
    def progress(phase: str, pct: float) -> None:
        if phase == "unknown":   # steamcmd's idle state between phases — not progress
            return
        install_job.update(step=_PHASES.get(phase, phase.capitalize()), percent=round(pct, 1))
    try:
        install_job.update(step="Getting ready")
        ok, tail = game.install(d, progress)
        if ok and not is_installed(game):
            ok, tail = False, "the download finished but the server files weren't found"
        if ok:
            install_job.finish(True, f"{game.label} is installed. Use “Add a server” to create your first one.",
                               percent=100.0)
            audit_log.info("game INSTALL ok kind=%s", game.kind)
        else:
            install_job.finish(False, f"{game.label} couldn't be installed: {_reason(tail)}")
            audit_log.warning("game INSTALL FAILED kind=%s", game.kind)
    except ActionError as e:
        install_job.finish(False, str(e))
    except Exception as e:
        app_log.exception("install %s crashed", game.kind)
        install_job.finish(False, f"Something went wrong installing {game.label}: {e}")


def uninstall(kind: str) -> dict:
    """Delete a game's server files. Refused while any server of that game
    exists (remove those first — their saved worlds may live in the same
    folder) or while an install/update is running."""
    import registry
    game = games.get(kind)
    if game is None or game not in _installable():
        raise ActionError("That isn't a game GameDash installed.")
    if not is_installed(game):
        raise ActionError(f"{game.label} isn't installed.")
    using = [s.name for s in registry.load_servers() if s.kind == kind]
    if using:
        raise ActionError(f"{game.label} is still used by: {', '.join(using)}. Remove those "
                          f"servers first (back up their worlds if you want to keep them).")
    if install_job.running:
        raise ActionError("A game is being installed — wait for it to finish.")
    d = os.path.realpath(config.install_dir(kind))
    home = os.path.realpath(os.path.expanduser("~"))
    # only ever delete a real game folder that sits inside the home directory
    if not d.startswith(home + os.sep) or d.count(os.sep) < home.count(os.sep) + 1 \
            or not os.path.exists(os.path.join(d, game.install_marker)):
        raise ActionError(f"Refusing to delete {d}: it doesn't look like a game folder GameDash manages.")
    shutil.rmtree(d)
    audit_log.info("game UNINSTALL kind=%s dir=%s", kind, d)
    return {"ok": True, "message": f"{game.label} was uninstalled and its files deleted."}
