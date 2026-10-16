import os

import cli


def test_command_names_are_forgiving():
    for spelling in ("reset-password", "reset_password", "resetpassword", "RESET-PASSWORD"):
        key = spelling.lstrip("-").replace("-", "").replace("_", "").lower()
        assert cli.COMMANDS[key] is cli.cmd_reset_password


def test_every_documented_command_exists():
    for line in cli.__doc__.splitlines():
        word = line.strip().split(" ")[0]
        if word and word.isalpha() and line.startswith("  ") and word not in ("Server", "Usage"):
            assert word.replace("-", "") in cli.COMMANDS or word in ("start",), f"'{word}' is in the help but not a command"


def test_uninstall_leaves_a_busy_server_alone_when_asked(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import builtins
    import controls
    import registry
    servers = {k: SimpleNamespace(key=k, name=k.title(), unit=f"gamedash-{k}.service", kind="custom")
               for k in ("busy", "idle")}
    calls = []
    monkeypatch.setattr(registry, "by_key", lambda: servers)
    monkeypatch.setattr(cli, "_active", lambda unit: True)
    monkeypatch.setattr(cli, "_systemctl", lambda *a: calls.append(a))
    monkeypatch.setattr(controls, "live_players", lambda s: (2, ["a", "b"]) if s.key == "busy" else (0, []))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    # "uninstall", stop the servers: yes, stop Busy anyway: no, keep settings + backups
    answers = iter(["uninstall", "y", "n", "n", "n"])
    monkeypatch.setattr(builtins, "input", lambda *a: next(answers, "n"))
    assert cli.cmd_uninstall([]) == 0
    stopped = [a[-1] for a in calls if a[:2] == ("disable", "--now")]
    assert "gamedash-idle.service" in stopped and "gamedash-busy.service" not in stopped
