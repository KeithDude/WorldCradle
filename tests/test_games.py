"""Rules every game type must follow, and the parsers that read player lists."""
import os

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


def test_dst_picks_up_a_changed_join_password_at_start(tmp_path, monkeypatch):
    import os
    import stat
    import subprocess
    import config
    from games import dst
    install = tmp_path / "dst"
    (install / "bin64").mkdir(parents=True)
    exe = install / "bin64" / dst.EXE
    exe.write_text("#!/bin/sh\nexit 0\n")                      # stands in for the real server
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    secrets = tmp_path / "secrets.conf"
    secrets.write_text('GAME_SERVER_PASSWORD="first-pw"\n')
    monkeypatch.setattr(config, "install_dir", lambda kind: str(install))
    monkeypatch.setattr(config, "secrets_path", lambda: str(secrets))
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    g = dst.DstGame()
    ports = {"game": 10999, "caves": 11000, "steam_master": 27050, "auth_master": 8770,
             "steam_caves": 27051, "auth_caves": 8771, "shard": 10888}
    fields = g.provision({"key": "dsttest", "name": "Test", "cluster_token": "pds-g^KU_test^" + "x" * 30,
                          "caves": False}, ports)
    ini = os.path.join(fields["save_root"], "cluster.ini")
    secrets.write_text('GAME_SERVER_PASSWORD="changed-pw"\n')   # changed in Settings after creation
    subprocess.run(["sh", fields["exec_start"]], check=True, timeout=30)
    assert "cluster_password = changed-pw\n" in open(ini).read()


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_card_rows_depend_on_the_game_not_on_running(g):
    """A server card's rows come from the game (and its ports), so starting or stopping a server
    never changes the card's layout."""
    from registry import Server
    s = Server(key="t", name="T", kind=g.kind, unit="worldcradle-t.service", game_port=7000, query_port=7001)
    rows = g.card_rows(s)
    assert set(rows) == {"players", "answering", "server_stats"}
    assert all(isinstance(v, bool) for v in rows.values())


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_join_steps_only_use_known_placeholders(g):
    import re
    known = {"address", "host", "port", "server", "password"}
    for step in g.join_steps:
        assert set(re.findall(r"\{(\w+)\}", step)) <= known, f"{g.kind}: {step}"


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_form_fields_check_their_own_limits(g):
    """Each number, list and checkbox field is read and checked from its own definition
    (GameType.option), so a value outside the form's limits is refused."""
    for f in g.extra_fields:
        kind = f.get("type", "text")
        if kind not in ("number", "select", "checkbox"):
            continue
        assert g.option({}, f["name"]) == f.get("default", False if kind == "checkbox" else None)
        if kind == "number":
            with pytest.raises(ActionError):
                g.option({f["name"]: f["max"] + 1000}, f["name"])
        if kind == "select":
            with pytest.raises(ActionError):
                g.option({f["name"]: "not-a-choice"}, f["name"])


@pytest.mark.parametrize("g", ALL, ids=lambda g: g.kind)
def test_status_check_of_a_stopped_server_is_a_plain_result(g, tmp_path, monkeypatch):
    """Every game's probe runs (nothing listening, no log yet) and returns the standard fields."""
    import socket
    import monitor
    from registry import Server
    for name in ("A2S_TIMEOUT", "RCON_TIMEOUT"):     # nothing will answer: don't wait long
        monkeypatch.setattr(monitor, name, 0.2)
    s0 = socket.socket(); s0.bind(("127.0.0.1", 0)); free = s0.getsockname()[1]; s0.close()
    s = Server(key="t", name="T", kind=g.kind, unit="worldcradle-t.service", game_port=free, query_port=free,
               rcon_port=free, rcon_password="pw", log_path=str(tmp_path / "none.log"),
               save_root=str(tmp_path), install_dir=str(tmp_path))
    out = g.probe(s)
    assert {"players", "player_names", "player_detail", "max_players", "reachable"} <= set(out)


def test_a_server_can_be_added_without_typing_a_name(monkeypatch):
    import types
    import provision
    import registry
    import store
    taken = [types.SimpleNamespace(key="valheim-server", name="Valheim · Valheim Server")]
    monkeypatch.setattr(registry, "load_servers", lambda: taken)
    monkeypatch.setattr(store, "load", lambda: [])
    vh = games.get("valheim")
    assert vh.default_name({}) == "Valheim Server" and not vh.named_after
    assert provision.unique_name("Valheim Server") == "Valheim Server 2"     # the next free one
    assert provision.unique_key("Valheim Server 2", "valheim") == "valheim-server-2"
    assert provision.unique_name("Terraria Server") == "Terraria Server"
    assert provision.unique_key("!!", "terraria") == "terraria"              # nothing usable in the name
    assert provision.KEY_RE.match(provision.unique_key("x" * 60, "x"))      # long names still fit
    assert games.get("ark").named_after == "the map"                        # ARK: named after its map
    assert games.get("ark").default_name({"map": "ScorchedEarth_P"}) == "Scorched Earth"   # its proper name
    assert games.get("asa").default_name({"map": "Aberration_WP"}) == "Aberration"
    assert games.get("ark").default_name({"map_custom": "MyModMap"}) == "MyModMap"     # mod maps: the code


def test_every_game_sets_up_with_the_form_as_it_opens(monkeypatch, tmp_path):
    """Nothing typed, every option at its default: only the games that need a value from the
    person's own game account (a Klei token, a Dragonwilds player ID) ask for anything."""
    import config
    from provision_snapshots import FIXTURES
    home = str(tmp_path / "home")
    monkeypatch.setattr(os.path, "expanduser", lambda p: home + p[1:] if p.startswith("~") else p)
    secrets_file = tmp_path / "secrets.conf"
    secrets_file.write_text('GAME_SERVER_PASSWORD="joinpw"\nGAME_ADMIN_PASSWORD="adminpw"\n')
    monkeypatch.setattr(config, "secrets_path", lambda: str(secrets_file))
    refused = set()
    for g in games.all_types():
        if not g.provisionable or g.kind == "custom":
            continue
        install = tmp_path / "installs" / g.kind
        for rel, text in {**({g.install_marker: ""} if g.install_marker else {}),
                          **FIXTURES.get(g.kind, {}).get("files", {})}.items():
            (install / rel).parent.mkdir(parents=True, exist_ok=True)
            (install / rel).write_text(text)
        install.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, "install_dir", lambda kind, install=install: str(install))
        spec = {"key": "test", "name": g.default_name({}) if not g.named_after else "",
                "install_dir": str(install), "eula": True}
        spec.update({f["name"]: f["default"] for f in g.extra_fields if f.get("default") is not None})
        try:
            g.provision(spec, g.provision_ports(set(), False, {}))
        except ActionError:
            refused.add(g.kind)
    assert refused == {"dst", "dragonwilds"}
