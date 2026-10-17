"""jobs.py — long tasks that run in the background, one at a time of each kind: installing a game,
copying an install for a new server, updating a game.

The page polls a job's status(): {"state": "idle" | "running" | "done" | "failed", ...} plus
whatever the task records as it goes (its step, a percentage, the final message).
"""
from __future__ import annotations

import threading
import time

from applog import app_log
from games.base import ActionError


class Job:
    def __init__(self, name: str):
        self.name = name                  # for the log: "update", "install", …
        self._lock = threading.Lock()
        self._info: dict = {"state": "idle"}

    def status(self) -> dict:
        with self._lock:
            return dict(self._info)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._info.get("state") == "running"

    def get(self, key: str, default=None):
        with self._lock:
            return self._info.get(key, default)

    def begin(self, busy: str, **info) -> None:
        """Mark the job running with `info`, or raise ActionError(busy) if one already is."""
        with self._lock:
            if self._info.get("state") == "running":
                raise ActionError(busy)
            self._info = {"state": "running", "started_ts": time.time(), **info}

    def update(self, **info) -> None:
        with self._lock:
            self._info.update(info)

    def step(self, text: str, log: bool = True) -> None:
        """What it is doing now (shown on the page; also logged unless it's a progress tick)."""
        self.update(step=text)
        if log:
            app_log.info("%s: %s", self.name, text)

    def finish(self, ok: bool, message: str, **info) -> None:
        self.update(state="done" if ok else "failed", ok=ok, finished_ts=time.time(), message=message, **info)
