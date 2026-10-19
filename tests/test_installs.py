"""What a game needs before it can be installed, and the commands to add it."""
import os
import installs
import games
from games import common


def test_space_engineers_asks_for_32bit_wine_only_where_wine_lacks_it(monkeypatch):
    se = games.get("spaceengineers")
    monkeypatch.setattr(installs.shutil, "which", lambda p: "/usr/bin/" + p)   # every program is there
    monkeypatch.setattr(common, "wine_runs_32bit", lambda: False)              # Ubuntu 22.04 / 24.04
    assert installs._missing(se) == [installs.WINE32]
    monkeypatch.setattr(common, "wine_runs_32bit", lambda: True)               # Ubuntu 26.04
    assert installs._missing(se) == []
    assert installs.WINE32 not in installs._missing(games.get("vrising"))      # other Wine games don't need it


def test_the_fix_is_commands_the_person_types():
    assert installs.fix_commands([installs.WINE32]) == [
        "sudo dpkg --add-architecture i386", "sudo apt update", "sudo apt install wine32:i386"]
    assert installs.fix_commands(["winetricks", "xvfb-run"]) == ["sudo apt install winetricks xvfb"]
    assert installs.fix_commands([]) == []


def test_each_game_installs_in_a_folder_named_after_it(monkeypatch):
    import os
    import config
    monkeypatch.setattr(config, "load", lambda: {"install_dirs": {}})
    home = os.path.expanduser("~/worldcradle-games/")
    assert config.install_dir("ark") == home + "ARK-Survival-Evolved"
    assert config.install_dir("gmod") == home + "Garrys-Mod"
    assert config.install_dir("sdtd") == home + "7-Days-to-Die"
    assert config.install_dir("scpsl") == home + "SCP-Secret-Laboratory"
    names = [config.install_dir(g.kind) for g in installs._installable()]
    assert len(set(names)) == len(names)                                     # no two games share one
    monkeypatch.setattr(config, "load", lambda: {"install_dirs": {"ark": "~/arkserver"}})
    assert config.install_dir("ark") == os.path.expanduser("~/arkserver")    # a folder set by hand


def test_a_game_in_its_old_folder_keeps_that_folder(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(installs.os.path, "expanduser", lambda p: str(tmp_path) + p[1:] if p.startswith("~") else p)
    monkeypatch.setattr(config.os.path, "expanduser", installs.os.path.expanduser)
    cfg = {"install_dirs": {"valheim": "~/my-valheim"}}
    monkeypatch.setattr(config, "load", lambda: cfg)
    monkeypatch.setattr(config, "update", lambda change: change(cfg) or cfg)
    pal = games.get("palworld")
    os.makedirs(tmp_path / "palworldserver" / os.path.dirname(pal.install_marker), exist_ok=True)
    (tmp_path / "palworldserver" / pal.install_marker).touch()
    vh = games.get("valheim")                                  # already set: left alone
    os.makedirs(tmp_path / "valheimserver" / os.path.dirname(vh.install_marker), exist_ok=True)
    (tmp_path / "valheimserver" / vh.install_marker).touch()
    assert installs.keep_old_folders() == ["palworld"]
    assert cfg["install_dirs"] == {"valheim": "~/my-valheim", "palworld": "~/palworldserver"}
    assert installs.keep_old_folders() == []                   # only once
