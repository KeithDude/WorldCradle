"""Rules every game type must follow, and the parsers that read player lists."""
import pytest

import games
import provision
from games.base import ActionError

ALL = [g for g in games.all_types() if g.kind != "custom"]


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_control_ports_are_never_forwarded(g):
    for p in g.port_layout:
        if p.get("klass") == "rcon":
            assert not p.get("forward"), f"{g.kind}: {p['name']} would be listed for forwarding"


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_form_and_ports_build(g):
    names = [f["name"] for f in list(g.extra_fields) + g.port_fields()]
    assert len(names) == len(set(names)), f"{g.kind}: duplicate form field"


@pytest.mark.parametrize("g", [g for g in ALL if g.eula and g.eula.get("required")], ids=lambda g: g.kind)
def test_required_eula_blocks_server_creation(g):
    with pytest.raises(ActionError, match="tick the box"):
        provision.create({"kind": g.kind, "key": "eula-test", "name": "x"})


def test_terraria_is_never_probed_by_connecting():
    assert games.get("terraria").survives_connect_test is False


def test_minecraft_player_list():
    count, limit, names = games.get("minecraft").parse_list(
        "There are 2 of a max of 20 players online: Alex, Steve")
    assert (count, limit, names) == (2, 20, ["Alex", "Steve"])


def test_ark_player_list():
    import monitor
    text = "0. Rex Rider, 76561198000000001\n1. Dodo, 76561198000000002\n"
    assert monitor.parse_ark_players(text) == [
        {"name": "Rex Rider", "id": "76561198000000001"}, {"name": "Dodo", "id": "76561198000000002"}]
    assert monitor.parse_ark_players("No Players Connected") == []


def test_squad_player_list_ignores_recently_disconnected():
    text = ("----- Active Players -----\n"
            "ID: 0 | Online IDs: EOS: a steam: 1 | Name: [CLAN] Keith | Team ID: 1 | Squad ID: N/A\n"
            "----- Recently Disconnected Players [Max of 15] -----\n"
            "ID: 9 | Online IDs: EOS: b steam: 2 | Since Disconnect: 01m.02s | Name: Gone")
    assert games.get("squad").parse_players(text) == ["[CLAN] Keith"]


def test_7dtd_commented_setting_becomes_live():
    """The shipped serverconfig.xml has UserDataFolder inside a comment; editing the comment does
    nothing (worlds were saved outside the backed-up folder)."""
    xml = ('<ServerSettings>\n\t<!-- <property name="UserDataFolder"\t\tvalue="absolute_path"/> -->\n'
           '</ServerSettings>')
    out = games.get("sdtd")._set(xml, "UserDataFolder", "/srv/data")
    assert '<property name="UserDataFolder" value="/srv/data"/>' in out
    assert "<!--" not in out
