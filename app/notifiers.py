"""notifiers.py — the services GameDash can send alerts to.

Each service has a plain-language form (SERVICES[...]["fields"]) and a sender. A sender raises
NotifyError with a message the owner can act on when delivery fails; otherwise the message
was accepted by the service. Destinations are stored in config as a list of
{"type": <service>, <field>: <value>, ...}.

Fields marked secret (tokens, passwords, webhook addresses, which work like passwords) are never
sent back to the browser in full: the Settings page gets "saved" and keeps the stored value unless
the owner types a new one.
"""
from __future__ import annotations

import re
import smtplib
import ssl
import time
import urllib.parse
from email.message import EmailMessage

import requests

SEND_TIMEOUT = 10.0
TELEGRAM_API = "https://api.telegram.org"      # overridable for tests
PUSHOVER_API = "https://api.pushover.net"
SECRET_PLACEHOLDER = "__saved__"


class NotifyError(Exception):
    pass


def _http(method: str, url: str, **kw) -> requests.Response:
    try:
        r = requests.request(method, url, timeout=SEND_TIMEOUT, **kw)
    except requests.exceptions.SSLError:
        raise NotifyError("the service's security certificate wasn't accepted")
    except requests.exceptions.ConnectionError:
        raise NotifyError("couldn't reach the service — check the address and the internet connection")
    except requests.exceptions.Timeout:
        raise NotifyError("the service didn't answer in time")
    if r.status_code in (401, 403):
        raise NotifyError(f"the service refused it ({r.status_code}) — check the token / password")
    if r.status_code == 404:
        raise NotifyError("the service says that address doesn't exist (404) — check it was copied in full")
    if r.status_code >= 400:
        raise NotifyError(f"the service answered with an error ({r.status_code}): {r.text[:150]}")
    return r


def _level_emoji(level: str) -> str:
    return {"bad": "🔴", "good": "🟢", "warn": "🟠"}.get(level, "🎮")


# ---- senders --------------------------------------------------------------------------

def _discord(d, title, message, level):
    _http("POST", d["url"], json={"content": f"**{title}**\n{message}"[:1990]})


def _telegram(d, title, message, level):
    r = _http("POST", f"{TELEGRAM_API}/bot{d['bot_token']}/sendMessage",
              json={"chat_id": d["chat_id"], "text": f"{title}\n{message}"[:4000]})
    if not r.json().get("ok", False):
        raise NotifyError(f"Telegram refused it: {r.json().get('description', 'unknown reason')}")


def _slack(d, title, message, level):
    _http("POST", d["url"], json={"text": f"*{title}*\n{message}"})


def _teams(d, title, message, level):
    # Teams "Workflows" webhooks take an Adaptive Card.
    card = {"type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                     {"type": "TextBlock", "text": message, "wrap": True}]}
    _http("POST", d["url"], json={"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]})


def _pushover(d, title, message, level):
    r = _http("POST", f"{PUSHOVER_API}/1/messages.json",
              data={"token": d["app_token"], "user": d["user_key"], "title": title[:250],
                    "message": message[:1000], "priority": 1 if level == "bad" else 0})
    if r.json().get("status") != 1:
        raise NotifyError(f"Pushover refused it: {', '.join(r.json().get('errors', [])) or 'unknown reason'}")


def _ntfy(d, title, message, level):
    tag = {"bad": "rotating_light", "good": "white_check_mark", "warn": "warning"}.get(level, "video_game")
    prio = {"bad": "high", "warn": "high"}.get(level, "default")
    headers = {"Title": title.encode("ascii", "ignore").decode().strip() or "GameDash",
               "Priority": prio, "Tags": tag}
    if d.get("token"):
        headers["Authorization"] = f"Bearer {d['token']}"
    _http("POST", d["url"], data=message.encode("utf-8"), headers=headers)


def _gotify(d, title, message, level):
    _http("POST", d["server"].rstrip("/") + "/message", headers={"X-Gotify-Key": d["app_token"]},
          json={"title": title, "message": message, "priority": 8 if level == "bad" else 5})


def _matrix(d, title, message, level):
    room = urllib.parse.quote(d["room_id"], safe="")
    txn = f"gamedash-{time.time_ns()}"
    _http("PUT", f"{d['homeserver'].rstrip('/')}/_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}",
          headers={"Authorization": f"Bearer {d['access_token']}"},
          json={"msgtype": "m.text", "body": f"{title}\n{message}"})


def _email(d, title, message, level):
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = d.get("from_addr") or d.get("username") or d["to_addr"]
    msg["To"] = d["to_addr"]
    msg.set_content(message + "\n\n— sent by GameDash")
    host, port, security = d["smtp_host"], int(d.get("smtp_port") or 587), d.get("security", "starttls")
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=SEND_TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=SEND_TIMEOUT)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if d.get("username"):
                server.login(d["username"], d.get("password", ""))
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise NotifyError("the mail server refused the user name / password (many providers need an "
                          "\"app password\" here, not your normal one)")
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"couldn't send the email: {e}")


def _webhook(d, title, message, level):
    _http("POST", d["url"], json={"title": title, "message": message, "level": level})


# ---- the form for each service ----------------------------------------------------------
# field: (name, label, help, kind) — kind: "url" | "text" | "secret" | "number" | "choice:<a|b|c>"

_HTTPS = r"^https://[^\s]{1,2000}$"
_HTTP_ANY = r"^https?://[^\s]{1,2000}$"

SERVICES: dict[str, dict] = {
    "discord": {"label": "Discord", "send": _discord, "fields": [
        ("url", "Webhook address", "In the Discord channel: Edit Channel → Integrations → Webhooks → "
         "New Webhook → Copy Webhook URL.", "secret", r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\S+$")]},
    "telegram": {"label": "Telegram", "send": _telegram, "fields": [
        ("bot_token", "Bot token", "In Telegram, talk to @BotFather, send /newbot and copy the token it gives you.",
         "secret", r"^\d{5,}:[A-Za-z0-9_-]{30,}$"),
        ("chat_id", "Chat ID", "Send your new bot a message, then talk to @userinfobot to get your ID "
         "(for a group: add the bot to the group; group IDs start with -).", "text", r"^(-?\d{1,20}|@[A-Za-z0-9_]{4,})$")]},
    "email": {"label": "Email", "send": _email, "fields": [
        ("to_addr", "Send to (email address)", "Where the alerts should arrive.", "text", r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
        ("smtp_host", "Mail server", "Your email provider's outgoing (SMTP) server, e.g. smtp.gmail.com.",
         "text", r"^[A-Za-z0-9.-]{3,253}$"),
        ("smtp_port", "Port", "Usually 587 (or 465 for \"SSL\").", "number", r"^\d{2,5}$"),
        ("security", "Security", "STARTTLS for port 587, SSL for port 465.", "choice:starttls|ssl|none", None),
        ("username", "User name", "Usually your full email address.", "text", r"^\S{1,254}$"),
        ("password", "Password", "Gmail, Outlook and others need an \"app password\" created in your account's "
         "security settings, not your normal password.", "secret", r"^.{1,500}$"),
        ("from_addr", "Send from (optional)", "Leave empty to use the user name.", "text", r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$")]},
    "slack": {"label": "Slack", "send": _slack, "fields": [
        ("url", "Webhook address", "In Slack: create an app with an \"Incoming Webhook\" for your channel and "
         "copy its address (starts with https://hooks.slack.com/).", "secret", r"^https://hooks\.slack\.com/\S+$")]},
    "teams": {"label": "Microsoft Teams", "send": _teams, "fields": [
        ("url", "Workflow address", "In the Teams channel: ⋯ → Workflows → \"Post to a channel when a webhook "
         "request is received\", then copy the address it gives you.", "secret", _HTTPS)]},
    "pushover": {"label": "Pushover (phone push)", "send": _pushover, "fields": [
        ("user_key", "Your user key", "Shown on your pushover.net dashboard after you sign in.", "secret", r"^[A-Za-z0-9]{20,40}$"),
        ("app_token", "App token", "On pushover.net: Create an Application, then copy its API token.", "secret", r"^[A-Za-z0-9]{20,40}$")]},
    "ntfy": {"label": "ntfy (free phone push)", "send": _ntfy, "fields": [
        ("url", "Topic address", "Install the ntfy app, subscribe to a topic with a hard-to-guess name, and enter "
         "its address here, e.g. https://ntfy.sh/gamedash-x7k2p9.", "secret", _HTTP_ANY),
        ("token", "Access token (optional)", "Only needed for a protected topic or your own ntfy server.", "secret", r"^(\S{1,500})?$")]},
    "gotify": {"label": "Gotify (self-hosted push)", "send": _gotify, "fields": [
        ("server", "Server address", "Your Gotify server, e.g. https://gotify.example.com.", "url", _HTTP_ANY),
        ("app_token", "App token", "In Gotify: Apps → Create Application, then copy its token.", "secret", r"^\S{5,200}$")]},
    "matrix": {"label": "Matrix / Element", "send": _matrix, "fields": [
        ("homeserver", "Homeserver address", "e.g. https://matrix.org or your own server.", "url", _HTTP_ANY),
        ("access_token", "Access token", "In Element: Settings → Help & About → Access Token (use a separate bot "
         "account if you can).", "secret", r"^\S{10,500}$"),
        ("room_id", "Room ID", "Room settings → Advanced → Internal room ID (starts with !). Invite the account "
         "into the room first.", "text", r"^![^\s:]+:\S+$")]},
    "webhook": {"label": "Another service (webhook)", "send": _webhook, "fields": [
        ("url", "Webhook address", "GameDash sends a JSON message with title, message and level to this address.",
         "secret", _HTTP_ANY)]},
}


def describe() -> list[dict]:
    """The services and their forms, for the Settings page."""
    return [{"type": k, "label": v["label"],
             "fields": [{"name": f[0], "label": f[1], "help": f[2], "kind": f[3]} for f in v["fields"]]}
            for k, v in SERVICES.items()]


def secret_fields(kind: str) -> set[str]:
    return {f[0] for f in SERVICES.get(kind, {}).get("fields", []) if f[3] == "secret"}


def public_view(dest: dict) -> dict:
    """A destination as the browser may see it: secret values replaced by a placeholder."""
    secrets = secret_fields(dest.get("type", ""))
    return {k: (SECRET_PLACEHOLDER if k in secrets and v else v) for k, v in dest.items()}


def clean(dest: dict, previous: dict | None = None) -> dict:
    """Check one destination from the Settings page; secret fields left as the placeholder keep
    their stored value. Raises ValueError with a plain message."""
    kind = dest.get("type")
    if kind not in SERVICES:
        raise ValueError("Unknown alert service.")
    label = SERVICES[kind]["label"]
    out = {"type": kind}
    for name, flabel, _help, fkind, pattern in SERVICES[kind]["fields"]:
        value = str(dest.get(name, "") or "").strip()
        if value == SECRET_PLACEHOLDER and previous and previous.get("type") == kind:
            value = previous.get(name, "")
        if fkind.startswith("choice:"):
            choices = fkind[7:].split("|")
            value = value if value in choices else choices[0]
        optional = "optional" in flabel.lower()
        if not value and not optional:
            if name == "smtp_port":
                value = "587"
            else:
                raise ValueError(f"{label}: please fill in “{flabel}”.")
        if value and pattern and not re.match(pattern, value):
            raise ValueError(f"{label}: “{flabel}” doesn't look right — check it was copied in full.")
        out[name] = value
    return out


def send(dest: dict, title: str, message: str, level: str = "warn") -> None:
    """Deliver to one destination; raises NotifyError (plain message) when it didn't work."""
    service = SERVICES.get(dest.get("type"))
    if service is None:
        raise NotifyError("unknown alert service")
    service["send"](dest, title, message, level)
