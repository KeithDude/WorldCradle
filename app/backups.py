"""backups.py — per-server save backup & restore.

A backup is a `.tar.gz` under `<backup folder>/<key>/` plus a JSON manifest
(stored inside the archive) recording each archived path's original absolute
location, so restore puts everything back exactly where it came from. The save
locations are game-specific and come from `GameType.save_paths(server)`.

Robustness:
  * backup first asks the game to save (for games that have a save command)
    so the on-disk copy is current;
  * restore is disruptive — it re-checks live players (ConfirmRequired), takes an
    automatic pre-restore snapshot of the CURRENT save, stops the server, swaps
    each save path aside before replacing it (rollback on failure), then restarts;
  * per-server retention prunes to the newest `backup_keep` archives.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import threading
import time

import alerts
import config
import controls
import games
import systemd
from applog import app_log, audit_log
from controls import ConfirmRequired
import paths
from games.base import ActionError
from registry import by_key

BACKUP_ROOT = os.path.expanduser(config.load().get("backups_dir") or paths.DEFAULT_BACKUP_ROOT)
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.tar\.gz$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")   # same shape as a server key
_restore_lock = threading.Lock()                     # one restore at a time (shared staging dir)
MANIFEST = "realmcradle-manifest.json"


def _server(key: str):
    s = by_key().get(key)
    if s is None:
        raise ActionError(f"unknown server: {key}")
    return s


def _dir(key: str) -> str:
    # `key` arrives from requests: it must be a plain server key, never a path
    # (otherwise "../x" would let download/delete reach outside the backup root).
    if not KEY_RE.match(key or ""):
        raise ActionError("bad server key.")
    return os.path.join(BACKUP_ROOT, key)


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")[:40]


def save_paths(s) -> list[dict]:
    game = games.get(s.kind)
    return game.save_paths(s) if game else []


# ---- archive / restore core (testable without the registry) ----------------

def _archive(parts: list[dict], out_path: str, meta: dict) -> list[dict]:
    """`parts` = list of {"path": abs, "role": str}. Each existing path is added
    under item<idx>/ and recorded in the manifest with its role."""
    items: list[dict] = []
    tmp = out_path + ".partial"
    with tarfile.open(tmp, "w:gz") as tf:
        for idx, part in enumerate(parts):
            p = part["path"]
            if not os.path.exists(p):
                continue
            is_dir = os.path.isdir(p)
            arc = f"item{idx}"
            tf.add(p, arcname=arc if is_dir else f"{arc}/{os.path.basename(p)}")
            items.append({"idx": idx, "orig": os.path.abspath(p),
                          "is_dir": is_dir, "name": os.path.basename(p),
                          "role": part.get("role", "save")})
        man = dict(meta)
        man["items"] = items
        data = json.dumps(man, indent=2).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(data)
        info.mtime = int(meta.get("created", time.time()))
        tf.addfile(info, io.BytesIO(data))
    os.replace(tmp, out_path)
    return items


def _read_manifest(arc_path: str) -> dict:
    with tarfile.open(arc_path, "r:gz") as tf:
        try:
            return json.loads(tf.extractfile(MANIFEST).read().decode("utf-8"))
        except (KeyError, AttributeError, ValueError):
            raise ActionError("backup is missing/has a bad manifest.")


def _restore_archive(arc_path: str, exclude_roles: tuple = ()) -> int:
    """Restore each archived item to its original location, skipping any whose
    role is in `exclude_roles`. Returns the number of items restored."""
    man = _read_manifest(arc_path)
    staging = os.path.join(BACKUP_ROOT, ".restore-tmp")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    restored = 0
    try:
        with tarfile.open(arc_path, "r:gz") as tf:
            tf.extractall(staging, filter="data")  # path-traversal safe (py3.12+)
        for it in man.get("items", []):
            if it.get("role", "save") in exclude_roles:
                continue
            restored += 1
            orig = it["orig"]
            arc = os.path.join(staging, f"item{it['idx']}")
            os.makedirs(os.path.dirname(orig) or "/", exist_ok=True)
            if it["is_dir"]:
                bak = orig + ".restoring-old"
                shutil.rmtree(bak, ignore_errors=True)
                if os.path.exists(orig):
                    os.rename(orig, bak)
                try:
                    shutil.move(arc, orig)
                except Exception:
                    if os.path.exists(bak) and not os.path.exists(orig):
                        os.rename(bak, orig)  # roll back
                    raise
                shutil.rmtree(bak, ignore_errors=True)
            else:
                src = os.path.join(arc, it["name"])
                if os.path.exists(src):
                    shutil.move(src, orig)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return restored


# ---- public API -------------------------------------------------------------

def list_backups(key: str) -> list[dict]:
    d = _dir(key)
    out = []
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if not NAME_RE.match(fn):
                continue
            fp = os.path.join(d, fn)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            out.append({"name": fn, "size": st.st_size, "size_h": _human(st.st_size),
                        "mtime": int(st.st_mtime)})
    out.sort(key=lambda b: b["mtime"], reverse=True)
    return out


_CLASSES = ("auto", "pre-restore", "manual")


def _backup_class(name: str) -> str:
    """Classify a backup by its filename label so retention is scoped per kind —
    daily 'auto' backups never prune away 'manual' ones or 'pre-restore' nets."""
    if "_auto" in name:
        return "auto"
    if "_pre-restore" in name:
        return "pre-restore"
    return "manual"


def _prune(key: str, keep: int, cls: str) -> None:
    """Keep only the newest `keep` backups of class `cls` for this server."""
    keep = max(1, int(keep or 1))
    same = [b for b in list_backups(key) if _backup_class(b["name"]) == cls]
    for b in same[keep:]:
        try:
            os.remove(os.path.join(_dir(key), b["name"]))
            audit_log.info("backup PRUNE key=%s file=%s", key, b["name"])
        except OSError:
            pass


def create_backup(key: str, label: str = "", flush: bool = True) -> dict:
    s = _server(key)
    existing = [it for it in save_paths(s) if os.path.exists(it["path"])]
    if not existing:
        raise ActionError(f"No save files found to back up for {s.name}. "
                          f"(For a custom service, set its save folder first.)")
    game = games.get(s.kind)
    if flush and game and game.supports("save") and systemd.is_active(s.unit):
        try:
            game.save(s)
            time.sleep(1.5)  # let the write settle to disk
        except Exception as e:
            app_log.warning("backup: pre-save flush on %s failed: %s", key, e)
    os.makedirs(_dir(key), exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    fname = f"{ts}{('_' + _slug(label)) if label else ''}.tar.gz"
    out = os.path.join(_dir(key), fname)
    _archive(existing, out, {"created": time.time(), "key": key, "kind": s.kind,
                          "server_name": s.name, "label": label})
    _prune(key, s.backup_keep, _backup_class(fname))
    size = os.path.getsize(out)
    audit_log.info("backup CREATE key=%s file=%s size=%d", key, fname, size)
    return {"ok": True, "name": fname, "message": f"Backup created ({_human(size)})."}


def set_keep(key: str, keep) -> dict:
    import store
    _server(key)  # validate it exists
    try:
        keep = max(1, min(int(keep), 100))
    except (TypeError, ValueError):
        raise ActionError("Keep count must be a number.")
    store.update(key, backup_keep=keep)
    for c in _CLASSES:  # apply immediately if lowered (per class)
        _prune(key, keep, c)
    audit_log.info("backup KEEP key=%s keep=%d", key, keep)
    return {"ok": True, "keep": keep, "message": f"Keeping the newest {keep} backup(s)."}


def backup_file(key: str, name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise ActionError("bad backup name.")
    path = os.path.join(_dir(key), name)
    if not os.path.isfile(path):
        raise ActionError("backup not found.")
    return path


def delete_backup(key: str, name: str) -> dict:
    os.remove(backup_file(key, name))
    audit_log.info("backup DELETE key=%s file=%s", key, name)
    return {"ok": True, "message": f"Deleted {name}."}


def _allowed_dirs(s) -> set:
    """Locations a restore for server `s` may write into — strictly its CURRENT
    declared save paths and their immediate parents (the orig of every archived
    item is one of these). Deliberately NOT install_dir's parent / home dir."""
    dirs = set()
    for it in save_paths(s):
        p = it["path"]
        dirs.add(os.path.realpath(p))                      # the save path itself
        dirs.add(os.path.realpath(os.path.dirname(p)))     # where it's placed
    return {d for d in dirs if d and d != os.sep}


def _orig_allowed(orig: str, allowed: set) -> bool:
    rp = os.path.realpath(orig)
    if os.path.dirname(rp) in allowed:
        return True
    return any(rp == d or rp.startswith(d + os.sep) for d in allowed)


def restore_backup(key: str, name: str, confirm: bool = False,
                   include_cluster: bool = True) -> dict:
    s = _server(key)
    path = backup_file(key, name)
    # ARK: optionally skip the shared cluster dir (it's common to ALL maps)
    exclude_roles = () if include_cluster else ("cluster",)
    # hardening: never let a (tampered) manifest write outside this server's own
    # save locations — validate every target before we stop the server.
    allowed = _allowed_dirs(s)
    for it in _read_manifest(path).get("items", []):
        if it.get("role", "save") in exclude_roles:
            continue
        if not _orig_allowed(it["orig"], allowed):
            raise ActionError("Refusing restore: this backup targets a path outside "
                              f"{s.name}'s save locations ({it['orig']}).")
    active = systemd.is_active(s.unit)
    if active and not confirm:
        cnt, names = controls.live_players(s)
        if cnt:  # players online → require explicit confirm
            raise ConfirmRequired(cnt, names)
    if not _restore_lock.acquire(blocking=False):
        raise ActionError("Another restore is already running — wait for it to finish.")
    try:
        # Safety net: snapshot the CURRENT save before overwriting it (always
        # full). If there is a save on disk and we can't snapshot it, stop here —
        # a restore must never be the thing that destroys the only copy.
        has_current = any(os.path.exists(it["path"]) for it in save_paths(s))
        if has_current:
            try:
                create_backup(key, label="pre-restore", flush=active)
            except Exception as e:
                app_log.warning("backup: pre-restore snapshot on %s failed: %s", key, e)
                raise ActionError(f"Restore cancelled: couldn't take the pre-restore safety "
                                  f"snapshot of the current save ({e}). Nothing was changed.")
        if active:
            alerts.suppress(key, 600)
            systemd.run("stop", s.unit, timeout=140)   # whether it stopped is checked just below
            # Never write save files underneath a running server.
            if systemd.is_active(s.unit):
                raise ActionError(f"Restore cancelled: {s.name} did not stop. "
                                  f"Nothing was changed.")
        try:
            n = _restore_archive(path, exclude_roles=exclude_roles)
        finally:
            if active:  # bring it back whether the restore worked or not
                systemd.run("start", s.unit, timeout=140)
    finally:
        _restore_lock.release()
    audit_log.info("backup RESTORE key=%s file=%s items=%d cluster=%s", key, name, n, include_cluster)
    extra = "" if include_cluster else " (map save only — shared cluster left as-is)"
    return {"ok": True, "message": f"Restored {name}.{extra}" + (" Server restarted." if active else "")}


def backup_all() -> dict:
    """Back up every server that has a known save location. Best-effort: a
    failure on one server is logged and the rest continue. Used by the daily
    systemd timer (realmcradle-backup.timer)."""
    results: dict[str, str] = {}
    for s in by_key().values():
        if not save_paths(s):
            continue  # no known save location (e.g. custom service w/o a folder)
        try:
            r = create_backup(s.key, label="auto")
            results[s.key] = r.get("name", "ok")
        except Exception as e:
            results[s.key] = f"FAILED: {e}"
            app_log.warning("backup AUTO failed key=%s: %s", s.key, e)
    audit_log.info("backup AUTO-ALL %d server(s): %s", len(results),
                   ", ".join(f"{k}={v}" for k, v in results.items()))
    failed = {k: v for k, v in results.items() if str(v).startswith("FAILED")}
    if failed:  # a backup that silently stops is worse than none — say so
        names = by_key()
        alerts.notify("⚠️ realmcradle: backup FAILED",
                      "\n".join(f"{names[k].name if k in names else k}: {v[8:]}"
                                 for k, v in failed.items()), "bad")
    return results


STALE_HOURS = 36   # the timer runs daily; anything older means backups have stopped


def newest_age_hours(key: str) -> float | None:
    """Hours since this server's newest backup (None if it has none)."""
    try:
        b = list_backups(key)
    except ActionError:
        return None
    return (time.time() - b[0]["mtime"]) / 3600 if b else None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        for k, v in backup_all().items():
            print(f"{k}: {v}")
    else:
        print("usage: backups.py all   # back up every server (daily timer entry point)")
