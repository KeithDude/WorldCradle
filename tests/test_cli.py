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
    servers = {k: SimpleNamespace(key=k, name=k.title(), unit=f"worldcradle-{k}.service", kind="custom")
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
    assert "worldcradle-idle.service" in stopped and "worldcradle-busy.service" not in stopped


def test_uninstall_finishes_even_if_deleting_stops_part_way(tmp_path, monkeypatch):
    import config
    import games
    import installs
    game = games.get("necesse")
    folder = tmp_path / "necesseserver"
    (folder / "deep").mkdir(parents=True)
    (folder / game.install_marker).write_text("")
    monkeypatch.setattr(config, "install_dir", lambda kind: str(folder))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    real = installs.shutil.rmtree
    calls = []
    def flaky(path, *a, **kw):          # the first delete stops part-way, like a full file table
        calls.append(path)
        if len(calls) == 1:
            raise OSError(24, "Too many open files")
        return real(path, *a, **kw)
    monkeypatch.setattr(installs.shutil, "rmtree", flaky)
    r = installs.uninstall("necesse")
    assert r["ok"] and "next time" in r["message"]
    assert not installs.is_installed(game)                     # gone from WorldCradle already
    assert installs._clear_leftovers(str(folder))             # and the rest clears next time
    assert not list(tmp_path.iterdir())


def test_updating_the_package_needs_the_sudo_typed_by_the_person(monkeypatch, capsys):
    monkeypatch.setattr(cli, "PACKAGED", True)
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    assert cli.cmd_update([]) != 0
    out = capsys.readouterr()
    assert "sudo worldcradle update" in out.err + out.out


def test_a_git_copy_is_never_updated_as_root(monkeypatch, capsys):
    monkeypatch.setattr(cli, "PACKAGED", False)
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    assert cli.cmd_update([]) != 0
    out = capsys.readouterr()
    assert "without sudo" in out.err + out.out
