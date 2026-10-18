"""The one way WorldCradle runs systemctl: problems come back as results or plain messages."""
import subprocess

import pytest

import systemd
from games.base import ActionError


def test_a_timeout_is_a_failed_result_not_a_crash(monkeypatch):
    def slow(*a, **kw):
        raise subprocess.TimeoutExpired(a[0], kw.get("timeout"))
    monkeypatch.setattr(systemd.subprocess, "run", slow)
    r = systemd.run("stop", "x.service", timeout=3)
    assert r.returncode == -1 and "longer than 3 seconds" in r.stderr
    assert systemd.is_active("x.service") is False


def test_check_explains_a_failure(monkeypatch):
    monkeypatch.setattr(systemd.subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(a[0], 5, "", "Unit x.service not found."))
    with pytest.raises(ActionError, match="Couldn't start the server: Unit x.service not found."):
        systemd.check("start", "x.service", failed="Couldn't start the server")


def test_show_reads_properties(monkeypatch):
    monkeypatch.setattr(systemd.subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, "NRestarts=2\nSubState=running\n", ""))
    assert systemd.show("x.service", "NRestarts", "SubState") == {"NRestarts": "2", "SubState": "running"}


def test_stop_limit_reads_systemds_time_spans(monkeypatch):
    for text, seconds in (("4min 20s", 260), ("2min 10s", 130), ("1min", 60), ("90s", 90),
                          ("infinity", systemd.CHANGE), ("", systemd.CHANGE)):
        monkeypatch.setattr(systemd, "show", lambda unit, *p, t=text: {"TimeoutStopUSec": t})
        assert systemd.stop_limit("x.service") == seconds
