"""Every alert service, sent to stand-in servers on this machine (nothing leaves the computer)."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import notifiers
from notifiers import NotifyError


class _Capture(BaseHTTPRequestHandler):
    status, reply, got = 200, b"{}", []

    def _handle(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).got.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).reply)

    do_POST = do_PUT = _handle

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    _Capture.status, _Capture.reply, _Capture.got = 200, b"{}", []
    srv = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", _Capture
    srv.shutdown()


def _json(cap):
    return json.loads(cap.got[-1]["body"])


def test_discord(server):
    base, cap = server
    notifiers.send({"type": "discord", "url": base + "/api/webhooks/1/abc"}, "🔴 Valheim is DOWN", "went offline", "bad")
    assert "Valheim is DOWN" in _json(cap)["content"]


def test_slack_teams_webhook(server):
    base, cap = server
    notifiers.send({"type": "slack", "url": base + "/s"}, "T", "M")
    assert _json(cap)["text"] == "*T*\nM"
    notifiers.send({"type": "teams", "url": base + "/t"}, "T", "M")
    card = _json(cap)["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and card["body"][1]["text"] == "M"
    notifiers.send({"type": "webhook", "url": base + "/w"}, "T", "M", "good")
    assert _json(cap) == {"title": "T", "message": "M", "level": "good"}


def test_telegram(server, monkeypatch):
    base, cap = server
    monkeypatch.setattr(notifiers, "TELEGRAM_API", base)
    cap.reply = b'{"ok": true}'
    notifiers.send({"type": "telegram", "bot_token": "123:abc", "chat_id": "-100200"}, "T", "M")
    assert cap.got[-1]["path"] == "/bot123:abc/sendMessage" and _json(cap)["chat_id"] == "-100200"
    cap.reply = b'{"ok": false, "description": "chat not found"}'
    with pytest.raises(NotifyError, match="chat not found"):
        notifiers.send({"type": "telegram", "bot_token": "123:abc", "chat_id": "1"}, "T", "M")


def test_pushover(server, monkeypatch):
    base, cap = server
    monkeypatch.setattr(notifiers, "PUSHOVER_API", base)
    cap.reply = b'{"status": 1}'
    notifiers.send({"type": "pushover", "user_key": "u" * 30, "app_token": "a" * 30}, "T", "M", "bad")
    assert b"priority=1" in cap.got[-1]["body"]


def test_ntfy_gotify_matrix(server):
    base, cap = server
    notifiers.send({"type": "ntfy", "url": base + "/topic", "token": "tk"}, "🟢 Back up", "fine", "good")
    h = cap.got[-1]["headers"]
    assert h["Title"] == "Back up" and h["Authorization"] == "Bearer tk" and cap.got[-1]["body"] == b"fine"
    notifiers.send({"type": "gotify", "server": base + "/", "app_token": "gt"}, "T", "M")
    assert cap.got[-1]["path"] == "/message" and cap.got[-1]["headers"]["X-Gotify-Key"] == "gt"
    notifiers.send({"type": "matrix", "homeserver": base, "access_token": "mt", "room_id": "!abc:example.org"}, "T", "M")
    last = cap.got[-1]
    assert last["method"] == "PUT" and "/rooms/%21abc%3Aexample.org/send/m.room.message/" in last["path"]
    assert last["headers"]["Authorization"] == "Bearer mt"


def test_errors_are_plain(server):
    base, cap = server
    cap.status = 401
    with pytest.raises(NotifyError, match="token / password"):
        notifiers.send({"type": "slack", "url": base + "/s"}, "T", "M")
    cap.status = 404
    with pytest.raises(NotifyError, match="doesn't exist"):
        notifiers.send({"type": "discord", "url": base + "/x"}, "T", "M")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); dead = s.getsockname()[1]; s.close()
    with pytest.raises(NotifyError, match="couldn't reach"):
        notifiers.send({"type": "webhook", "url": f"http://127.0.0.1:{dead}/"}, "T", "M")


def _smtp_server(received):
    """A minimal SMTP server: enough of the protocol to accept one message."""
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(1)

    def run():
        conn, _ = sock.accept()
        f = conn.makefile("rwb")
        f.write(b"220 test\r\n"); f.flush()
        data = False
        for raw in f:
            line = raw.decode().rstrip("\r\n")
            if data:
                if line == ".":
                    data = False; f.write(b"250 ok\r\n")
                else:
                    received.append(line)
            elif line.upper().startswith("EHLO"):
                f.write(b"250 test\r\n")
            elif line.upper().startswith("DATA"):
                data = True; f.write(b"354 go\r\n")
            elif line.upper().startswith("QUIT"):
                f.write(b"221 bye\r\n"); f.flush(); break
            else:
                f.write(b"250 ok\r\n")
            f.flush()
        conn.close(); sock.close()
    threading.Thread(target=run, daemon=True).start()
    return sock.getsockname()[1]


def test_email():
    received = []
    port = _smtp_server(received)
    notifiers.send({"type": "email", "to_addr": "owner@example.org", "smtp_host": "127.0.0.1",
                    "smtp_port": str(port), "security": "none", "from_addr": "gd@example.org"},
                   "🔴 Valheim is DOWN", "went offline", "bad")
    text = "\n".join(received)
    assert "To: owner@example.org" in text and "went offline" in text


def test_secrets_never_go_back_to_the_browser_and_are_kept_on_save():
    stored = {"type": "telegram", "bot_token": "123456:" + "x" * 35, "chat_id": "42"}
    view = notifiers.public_view(stored)
    assert view["bot_token"] == notifiers.SECRET_PLACEHOLDER and view["chat_id"] == "42"
    again = notifiers.clean(view, previous=stored)
    assert again["bot_token"] == stored["bot_token"]


def test_clean_rejects_wrong_or_missing_values():
    with pytest.raises(ValueError, match="doesn't look right"):
        notifiers.clean({"type": "discord", "url": "https://example.com/not-a-discord-webhook"})
    with pytest.raises(ValueError, match="fill in"):
        notifiers.clean({"type": "telegram", "chat_id": "42"})
    with pytest.raises(ValueError):
        notifiers.clean({"type": "no-such-service"})
    ok = notifiers.clean({"type": "email", "to_addr": "a@b.org", "smtp_host": "smtp.b.org",
                          "username": "a@b.org", "password": "pw"})
    assert ok["smtp_port"] == "587" and ok["security"] == "starttls"
