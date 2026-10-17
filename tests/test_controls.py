"""Start and Stop also decide whether a server starts with the computer."""
import subprocess
from types import SimpleNamespace

import pytest

import controls


@pytest.fixture
def fleet(monkeypatch):
    servers = {k: SimpleNamespace(key=k, name=k.title(), unit=f"gamedash-{k}.service", kind="custom",
                                  slot_group=group, rcon_port=None, rcon_password=None)
               for k, group in (("island", "ark-7782"), ("extinction", "ark-7782"), ("valheim", ""))}
    running = {"valheim"}
    calls = []

    def fake_run(args, **kw):
        calls.append(tuple(args[2:]))           # drop "systemctl --user"
        if args[2] in ("start", "restart"):
            running.add(args[3].removeprefix("gamedash-").removesuffix(".service"))
        if args[2] == "stop":
            running.discard(args[3].removeprefix("gamedash-").removesuffix(".service"))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(controls, "by_key", lambda: servers)
    monkeypatch.setattr(controls.monitor, "unit_active",
                        lambda unit: unit.removeprefix("gamedash-").removesuffix(".service") in running)
    monkeypatch.setattr(controls, "live_players", lambda s: (0, []))
    monkeypatch.setattr(controls.subprocess, "run", fake_run)
    monkeypatch.setattr(controls.alerts, "suppress", lambda *a: None)
    return calls


def test_stop_means_stopped_through_a_reboot(fleet):
    controls.perform("valheim", "stop")
    assert ("disable", "gamedash-valheim.service") in fleet


def test_start_comes_back_after_a_reboot_and_parks_its_port_partner(fleet):
    controls.perform("island", "start")
    assert ("enable", "gamedash-island.service") in fleet
    assert ("disable", "gamedash-extinction.service") in fleet


def test_restart_keeps_it_starting_with_the_computer(fleet):
    controls.perform("valheim", "restart")
    assert ("enable", "gamedash-valheim.service") in fleet
