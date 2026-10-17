"""Starting and stopping servers: Stop means stopped (through reboots too), and a server can only
start when its ports are free — servers may be set up on the same ports and take turns."""
import subprocess
from types import SimpleNamespace

import pytest

import controls
from games.base import ActionError


def _server(key, *ports):
    return SimpleNamespace(key=key, name=key.title(), unit=f"gamedash-{key}.service", kind="custom",
                           rcon_port=None, rcon_password=None, all_ports=lambda: set(ports))


@pytest.fixture
def fleet(monkeypatch):
    servers = {"island": _server("island", 7782, 7783, 27030),
               "extinction": _server("extinction", 7782, 7783, 27031),
               "valheim": _server("valheim", 2456, 2457)}
    running = {"valheim"}
    listening = set()
    calls = []

    def fake_run(args, **kw):
        calls.append(tuple(args[2:]))           # drop "systemctl --user"
        key = args[-1].removeprefix("gamedash-").removesuffix(".service")
        if args[2] in ("start", "restart"):
            running.add(key)
        if args[2] == "stop":
            running.discard(key)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(controls, "by_key", lambda: servers)
    monkeypatch.setattr(controls.monitor, "unit_active",
                        lambda unit: unit.removeprefix("gamedash-").removesuffix(".service") in running)
    monkeypatch.setattr(controls.monitor, "ports_in_use", lambda: set(listening))
    monkeypatch.setattr(controls, "live_players", lambda s: (0, []))
    monkeypatch.setattr(controls.subprocess, "run", fake_run)
    monkeypatch.setattr(controls.alerts, "suppress", lambda *a: None)
    return SimpleNamespace(calls=calls, running=running, listening=listening)


def test_stop_means_stopped_through_a_reboot(fleet):
    controls.perform("valheim", "stop")
    assert ("disable", "gamedash-valheim.service") in fleet.calls


def test_start_comes_back_after_a_reboot(fleet):
    controls.perform("island", "start")
    assert ("start", "gamedash-island.service") in fleet.calls
    assert ("enable", "gamedash-island.service") in fleet.calls


def test_restart_keeps_it_starting_with_the_computer(fleet):
    controls.perform("valheim", "restart")
    assert ("enable", "gamedash-valheim.service") in fleet.calls


def test_a_server_on_the_same_ports_as_a_running_one_does_not_start(fleet):
    controls.perform("island", "start")
    with pytest.raises(ActionError, match="ports are in use — Island is running on the same ports"):
        controls.perform("extinction", "start")
    assert ("start", "gamedash-extinction.service") not in fleet.calls
    controls.perform("island", "stop")
    controls.perform("extinction", "start")          # free again: takes its turn
    assert "extinction" in fleet.running


def test_a_port_another_program_uses_blocks_the_start(fleet):
    fleet.listening.add(27030)
    with pytest.raises(ActionError, match="port 27030 is being used by another program"):
        controls.perform("island", "start")
