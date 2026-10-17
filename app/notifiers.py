"""notifiers.py — the services RealmCradle can send alerts to.

Each service has a plain-language form (SERVICES[...]["fields"]) and a sender. A sender raises
NotifyError with a message the owner can act on when delivery fails; otherwise the message
was accepted by the service. Destinations are stored in config as a list of
{"type": <service>, <field>: <value>, ...}.

Fields marked secret (tokens, passwords, webhook addresses, which work like passwords) are never
sent back to the browser in full: the Settings page gets "saved" and keeps the stored value unless
the owner types a new one.

Each sender follows its service's own documentation; the links are next to each one.
"""
from __future__ import annotations

import base64
import re
import smtplib
import ssl
import time
import urllib.parse
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import NamedTuple

import requests

SEND_TIMEOUT = 10.0
TELEGRAM_API = "https://api.telegram.org"      # overridable for tests
PUSHOVER_API = "https://api.pushover.net"
SECRET_PLACEHOLDER = "__saved__"
# A service that says "too many messages, wait N seconds" gets one retry if N is this short;
# alerts are sent from a background thread, so a short wait holds nothing up.
MAX_RETRY_WAIT = 5.0


class NotifyError(Exception):
    pass


def _service_reason(r: requests.Response) -> str:
    """The reason a service gave for refusing a message, from the fields each one documents:
    Telegram "description", Matrix "error", Pushover "errors", Slack's plain-text body."""
    try:
        body = r.json()
    except ValueError:
        return r.text.strip()[:150]
    if not isinstance(body, dict):
        return ""
    errors = body.get("errors")
    if isinstance(errors, list):
        return ", ".join(str(e) for e in errors)[:150]
    return str(body.get("description") or body.get("error") or body.get("message") or "")[:150]


def _retry_after(r: requests.Response) -> float | None:
    try:
        return float(r.headers.get("Retry-After") or r.json().get("retry_after")
                     or r.json().get("parameters", {}).get("retry_after"))
    except (TypeError, ValueError, AttributeError):
        return None


def _http(method: str, url: str, check_status: bool = True, **kw) -> requests.Response:
    """Send one request. Problems become a NotifyError the owner can act on; with
    check_status=False an error answer is returned for the sender to read itself."""
    for attempt in (1, 2):
        try:
            r = requests.request(method, url, timeout=SEND_TIMEOUT, **kw)
        except requests.exceptions.SSLError:
            raise NotifyError("the service's security certificate wasn't accepted")
        except requests.exceptions.ConnectionError:
            raise NotifyError("couldn't reach the service — check the address and the internet connection")
        except requests.exceptions.Timeout:
            raise NotifyError("the service didn't answer in time")
        if r.status_code == 429:
            wait = _retry_after(r)
            if attempt == 1 and wait is not None and wait <= MAX_RETRY_WAIT:
                time.sleep(wait)
                continue
            raise NotifyError("the service says too many messages were sent — it will work again shortly")
        break
    if r.status_code < 400 or not check_status:
        return r
    reason = _service_reason(r)
    because = f": {reason}" if reason else ""
    if r.status_code == 401:
        raise NotifyError(f"the service refused it (401) — check the token / password{because}")
    if r.status_code == 403:   # Telegram, Matrix and Slack also use this for "not allowed in that chat/room"
        raise NotifyError(f"the service refused it (403){because or ' — check the token / password'}")
    if r.status_code == 404:
        raise NotifyError("the service says that address doesn't exist (404) — check it was copied in full")
    raise NotifyError(f"the service answered with an error ({r.status_code}){because}")


# ---- senders --------------------------------------------------------------------------

def _discord(d, title, message, level):
    # https://discord.com/developers/docs/resources/webhook#execute-webhook
    # content: up to 2000 characters. allowed_mentions stops a server or player name containing
    # "@everyone" from pinging the whole Discord server.
    _http("POST", d["url"], json={"content": f"**{title}**\n{message}"[:2000],
                                  "allowed_mentions": {"parse": []}})


def _telegram(d, title, message, level):
    # https://core.telegram.org/bots/api#sendmessage — text: 1-4096 characters. Every answer,
    # error or not, is {"ok": ..., "description": ...}, which says what went wrong better than
    # the status code (403 is used for "the bot isn't in that chat" as well as a bad token).
    r = _http("POST", f"{TELEGRAM_API}/bot{d['bot_token']}/sendMessage", check_status=False,
              json={"chat_id": d["chat_id"], "text": f"{title}\n{message}"[:4096]})
    try:
        body = r.json()
    except ValueError:
        body = {}
    if body.get("ok") is True:
        return
    new_id = (body.get("parameters") or {}).get("migrate_to_chat_id")
    if new_id:   # https://core.telegram.org/bots/api#responseparameters
        raise NotifyError(f"this Telegram group was upgraded and has a new chat ID: {new_id} — "
                          "put that in the Chat ID box")
    if r.status_code == 401 or r.status_code == 404:   # Telegram answers 404 for a token it doesn't know
        raise NotifyError("Telegram doesn't recognise that bot token — copy it again from @BotFather")
    raise NotifyError(f"Telegram refused it: {body.get('description') or f'error {r.status_code}'}")


def _slack_escape(text: str) -> str:
    # https://docs.slack.dev/messaging/formatting-message-text — &, < and > are control characters
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slack(d, title, message, level):
    # https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks
    _http("POST", d["url"], json={"text": f"*{_slack_escape(title)}*\n{_slack_escape(message)}"})


def _teams(d, title, message, level):
    # Teams Workflows ("Send webhook alerts to a channel") take an Adaptive Card:
    # https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook
    # The workflow accepts the request first and posts it afterwards, so a broken workflow
    # can't be detected from here.
    card = {"type": "AdaptiveCard", "version": "1.4",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": [{"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                     {"type": "TextBlock", "text": message, "wrap": True}]}
    _http("POST", d["url"], json={"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]})


def _pushover(d, title, message, level):
    # https://pushover.net/api — title up to 250 characters, message up to 1024.
    # Priority 1 ("high") is kept for servers going down.
    r = _http("POST", f"{PUSHOVER_API}/1/messages.json",
              data={"token": d["app_token"], "user": d["user_key"], "title": title[:250],
                    "message": message[:1024], "priority": 1 if level == "bad" else 0})
    if r.json().get("status") != 1:
        raise NotifyError(f"Pushover refused it: {_service_reason(r) or 'unknown reason'}")


def _header_text(text: str) -> str:
    """A header value that survives HTTP: plain ASCII as is, anything else as RFC 2047
    (which ntfy documents for titles with accents or emoji)."""
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        return "=?UTF-8?B?" + base64.b64encode(text.encode("utf-8")).decode() + "?="


def _ntfy(d, title, message, level):
    # https://docs.ntfy.sh/publish/ — the body is the message (up to 4,096 bytes); the title and
    # priority go in headers; tags that name an emoji are shown as that emoji.
    tag = {"bad": "rotating_light", "good": "white_check_mark", "warn": "warning"}.get(level, "video_game")
    prio = {"bad": "high", "warn": "high"}.get(level, "default")
    clean_title = title.lstrip("🔴🟢🟠🎮 ").strip() or "RealmCradle"   # the tag already shows the emoji
    headers = {"Title": _header_text(clean_title[:250]), "Priority": prio, "Tags": tag}
    if d.get("token"):
        headers["Authorization"] = f"Bearer {d['token']}"
    body = message.encode("utf-8")[:4096].decode("utf-8", "ignore").encode("utf-8")
    _http("POST", d["url"], data=body, headers=headers)


def _gotify(d, title, message, level):
    # https://gotify.net/docs/pushmsg — priority 8 and up makes Android show it as a pop-up.
    _http("POST", d["server"].rstrip("/") + "/message", headers={"X-Gotify-Key": d["app_token"]},
          json={"title": title, "message": message, "priority": 8 if level == "bad" else 5})


def _matrix(d, title, message, level):
    # https://spec.matrix.org/latest/client-server-api/#put_matrixclientv3roomsroomidsendeventtypetxnid
    room = urllib.parse.quote(d["room_id"], safe="")
    txn = f"realmcradle-{time.time_ns()}"   # must be unique for each message sent with this token
    _http("PUT", f"{d['homeserver'].rstrip('/')}/_matrix/client/v3/rooms/{room}/send/m.room.message/{txn}",
          headers={"Authorization": f"Bearer {d['access_token']}"},
          json={"msgtype": "m.text", "body": f"{title}\n{message}"})


_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
SMTP_DEFAULT_PORT = {"starttls": "587", "ssl": "465", "none": "25"}


def _email(d, title, message, level):
    # https://docs.python.org/3/library/smtplib.html — STARTTLS upgrades a plain connection
    # (usually port 587); "SSL" is encrypted from the start (usually port 465).
    security = d.get("security", "starttls")
    username = d.get("username", "")
    sender = d.get("from_addr") or (username if re.match(_EMAIL_RE, username) else d["to_addr"])
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = sender
    msg["To"] = d["to_addr"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    msg.set_content(message + "\n\n— sent by RealmCradle")
    host = d["smtp_host"]
    port = int(d.get("smtp_port") or SMTP_DEFAULT_PORT.get(security, "587"))
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=SEND_TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=SEND_TIMEOUT)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if username:
                server.login(username, d.get("password", ""))
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise NotifyError("the mail server refused the user name / password (many providers need an "
                          "\"app password\" here, not your normal one)")
    except (smtplib.SMTPException, OSError) as e:
        raise NotifyError(f"couldn't send the email: {e}")


def _webhook(d, title, message, level):
    # RealmCradle's own format, described to the owner in the form's help.
    _http("POST", d["url"], json={"title": title, "message": message, "level": level})


# ---- the form for each service ----------------------------------------------------------

class Field(NamedTuple):
    name: str
    label: str
    help: str
    kind: str                   # "url" | "text" | "secret" | "number" | "choice:<a|b|c>"
    pattern: str | None         # what a valid value looks like (None: anything)
    optional: bool = False


_HTTPS = r"^https://[^\s]{1,2000}$"
_HTTP_ANY = r"^https?://[^\s]{1,2000}$"

SERVICES: dict[str, dict] = {
    "discord": {"label": "Discord", "send": _discord, "fields": [
        Field("url", "Webhook address", "In the Discord channel: Edit Channel → Integrations → Webhooks → "
              "New Webhook → Copy Webhook URL (you need the Manage Webhooks permission).", "secret",
              r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\S+$")]},
    "telegram": {"label": "Telegram", "send": _telegram, "fields": [
        Field("bot_token", "Bot token", "In Telegram, talk to @BotFather, send /newbot and copy the token it "
              "gives you.", "secret", r"^\d{5,}:[A-Za-z0-9_-]{30,}$"),
        Field("chat_id", "Chat ID", "Send your new bot a message first. Your own ID: ask a bot such as "
              "@userinfobot. A public channel: its @name (add the bot as an admin of the channel). "
              "A group: add the bot to it; group IDs start with -.", "text",
              r"^(-?\d{1,20}|@[A-Za-z0-9_]{4,})$")]},
    "email": {"label": "Email", "send": _email, "fields": [
        Field("to_addr", "Send to (email address)", "Where the alerts should arrive.", "text", _EMAIL_RE),
        Field("smtp_host", "Mail server", "Your email provider's outgoing (SMTP) server, e.g. smtp.gmail.com.",
              "text", r"^[A-Za-z0-9.-]{3,253}$"),
        Field("smtp_port", "Port", "Leave empty for the usual one: 587 for STARTTLS, 465 for SSL.", "number",
              r"^\d{2,5}$", optional=True),
        Field("security", "Security", "STARTTLS for port 587, SSL for port 465.", "choice:starttls|ssl|none", None),
        Field("username", "User name", "Usually your full email address.", "text", r"^\S{1,254}$"),
        Field("password", "Password", "Gmail, Outlook and others need an \"app password\" created in your "
              "account's security settings, not your normal password.", "secret", r"^.{1,500}$"),
        Field("from_addr", "Send from (optional)", "Leave empty to send from the user name. Most providers "
              "only accept your own address here.", "text", r"^([^@\s]+@[^@\s]+\.[^@\s]+)?$", optional=True)]},
    "slack": {"label": "Slack", "send": _slack, "fields": [
        Field("url", "Webhook address", "In Slack: create an app with an \"Incoming Webhook\" for your channel "
              "and copy its address (starts with https://hooks.slack.com/).", "secret",
              r"^https://hooks\.slack\.com/\S+$")]},
    "teams": {"label": "Microsoft Teams", "send": _teams, "fields": [
        Field("url", "Workflow address", "In the Teams channel: ⋯ → Workflows → \"Send webhook alerts to a "
              "channel\" → pick the team and channel → Save, then copy the address it gives you. "
              "Teams accepts the message before posting it, so if a test says it worked but nothing "
              "appears, check the workflow in the Workflows app.", "secret", _HTTPS)]},
    "pushover": {"label": "Pushover (phone push)", "send": _pushover, "fields": [
        Field("user_key", "Your user key", "Shown on your pushover.net dashboard after you sign in.", "secret",
              r"^[A-Za-z0-9]{30}$"),
        Field("app_token", "App token", "On pushover.net: Create an Application, then copy its API token.",
              "secret", r"^[A-Za-z0-9]{30}$")]},
    "ntfy": {"label": "ntfy (free phone push)", "send": _ntfy, "fields": [
        Field("url", "Topic address", "Install the ntfy app, subscribe to a topic with a hard-to-guess name, "
              "and enter its address here, e.g. https://ntfy.sh/realmcradle-x7k2p9.", "secret", _HTTP_ANY),
        Field("token", "Access token (optional)", "Only needed for a protected topic or your own ntfy server.",
              "secret", r"^(\S{1,500})?$", optional=True)]},
    "gotify": {"label": "Gotify (self-hosted push)", "send": _gotify, "fields": [
        Field("server", "Server address", "Your Gotify server, e.g. https://gotify.example.com.", "url", _HTTP_ANY),
        Field("app_token", "App token", "In Gotify: Apps → Create Application, then copy its token straight "
              "away (newer versions show it only once). Use an App token, not a Client one.", "secret",
              r"^\S{5,200}$")]},
    "matrix": {"label": "Matrix / Element", "send": _matrix, "fields": [
        Field("homeserver", "Homeserver address", "e.g. https://matrix.org or your own server.", "url", _HTTP_ANY),
        Field("access_token", "Access token", "Best: a separate account just for alerts. Sign in to it in "
              "Element, then Settings → Help & About → Access Token, and don't sign that session out "
              "(that ends the token).", "secret", r"^\S{10,500}$"),
        # Newer room versions have IDs with no ":server" part, so only the "!" is required.
        Field("room_id", "Room ID", "Room settings → Advanced → Internal room ID (starts with !). Invite the "
              "account into the room first.", "text", r"^!\S{1,255}$")]},
    "webhook": {"label": "Another service (webhook)", "send": _webhook, "fields": [
        Field("url", "Webhook address", "RealmCradle sends a JSON message with title, message and level to this "
              "address.", "secret", _HTTP_ANY)]},
}


def describe() -> list[dict]:
    """The services and their forms, for the Settings page."""
    return [{"type": k, "label": v["label"],
             "fields": [{"name": f.name, "label": f.label, "help": f.help, "kind": f.kind}
                        for f in v["fields"]]}
            for k, v in SERVICES.items()]


def secret_fields(kind: str) -> set[str]:
    return {f.name for f in SERVICES.get(kind, {}).get("fields", []) if f.kind == "secret"}


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
    for f in SERVICES[kind]["fields"]:
        value = str(dest.get(f.name, "") or "").strip()
        if value == SECRET_PLACEHOLDER and previous and previous.get("type") == kind:
            value = previous.get(f.name, "")
        if f.kind.startswith("choice:"):
            choices = f.kind[len("choice:"):].split("|")
            value = value if value in choices else choices[0]
        if not value and not f.optional:
            raise ValueError(f"{label}: please fill in “{f.label}”.")
        if value and f.pattern and not re.match(f.pattern, value):
            raise ValueError(f"{label}: “{f.label}” doesn't look right — check it was copied in full.")
        out[f.name] = value
    return out


def send(dest: dict, title: str, message: str, level: str = "warn") -> None:
    """Deliver to one destination; raises NotifyError (plain message) when it didn't work."""
    service = SERVICES.get(dest.get("type"))
    if service is None:
        raise NotifyError("unknown alert service")
    service["send"](dest, title, message, level)
