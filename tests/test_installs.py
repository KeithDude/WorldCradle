"""What a game needs before it can be installed, and the commands to add it."""
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
