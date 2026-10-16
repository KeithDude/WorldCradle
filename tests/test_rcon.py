"""GameDash's own Source RCON client against a small fake server."""
import socket
import struct
import threading

import monitor

PASSWORD = "right-password"


def _packet(pid, ptype, body):
    payload = struct.pack("<ii", pid, ptype) + body.encode() + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def _read(conn):
    n = struct.unpack("<i", conn.recv(4))[0]
    data = b""
    while len(data) < n:
        data += conn.recv(n - len(data))
    pid, ptype = struct.unpack("<ii", data[:8])
    return pid, ptype, data[8:-2].decode()


def _serve(sock, reply_parts):
    conn, _ = sock.accept()
    with conn:
        pid, _, pw = _read(conn)
        conn.sendall(_packet(pid, 0, ""))                      # some servers send an empty reply first
        conn.sendall(_packet(pid if pw == PASSWORD else -1, 2, ""))
        if pw != PASSWORD:
            return
        pid, _, cmd = _read(conn)
        for part in reply_parts:                                # a long answer in several packets
            conn.sendall(_packet(pid, 0, part))


def _fake_server(reply_parts):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    threading.Thread(target=_serve, args=(sock, reply_parts), daemon=True).start()
    return sock.getsockname()[1]


def test_reply_in_several_packets_is_joined():
    port = _fake_server(["first part, ", "second part"])
    assert monitor.source_rcon(port, PASSWORD, "ListPlayers") == "first part, second part"


def test_wrong_password_gives_none():
    port = _fake_server(["never sent"])
    assert monitor.source_rcon(port, "wrong", "ListPlayers") is None


def test_nothing_listening_gives_none():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    assert monitor.source_rcon(port, PASSWORD, "x", timeout=2) is None


def test_port_listening_never_connects():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); port = s.getsockname()[1]
    try:
        assert monitor.port_listening(port) is True
        s.settimeout(0.2)
        try:
            s.accept()
            raise AssertionError("port_listening opened a connection to the game")
        except socket.timeout:
            pass
    finally:
        s.close()
    assert monitor.port_listening(port) is False


def _serve_raw(sock, raw):
    conn, _ = sock.accept()
    with conn:
        _read(conn)
        conn.sendall(_packet(1, 2, ""))
        _read(conn)
        conn.sendall(raw)


def test_lenient_client_reads_replies_and_survives_garbage():
    for raw, want in ((_packet(2, 0, "3 players"), "3 players"),
                      (struct.pack("<i", -4) + b"\x00" * 12, "")):     # a nonsense length must not hang
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(1)
        threading.Thread(target=_serve_raw, args=(sock, raw), daemon=True).start()
        assert monitor.palworld_rcon(sock.getsockname()[1], PASSWORD, "ShowPlayers", timeout=3) == want
