# GameDash

A self-hosted **web panel for running game dedicated servers** on a Linux machine —
install a game, create servers, see who's online, start/stop, back up and restore,
all from one page. Built to be usable by people with little technical knowledge.
Python + Flask, runs as a systemd **user** service and serves HTTPS directly.

**45 games** are supported out of the box (Minecraft, Valheim, ARK, Palworld,
Satisfactory, Rust, Terraria, Factorio, Counter-Strike 2, Project Zomboid, 7 Days to
Die and many more — Windows-only servers run through Wine), plus any other server as
a **custom** service. See **[docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md)** for the
full list and which games have been tested with real players.

> **Status:** early. Most games are *Not Tested* with players yet — help is welcome.

## Features
- **Live dashboard** — per-server online/offline, player counts + names, CPU/RAM,
  reachability, ports; host load. Public page shows only status + counts.
- **Controls** — start / stop / restart / **kill (no-save)** / save / broadcast,
  per-player kick/ban (RCON games), ARK live chat. Disruptive actions re-check
  live players and confirm first.
- **Games** — install any supported game's server from the dashboard; licence
  terms are linked and, where required, must be accepted.
- **Provisioning** — add servers with each game's real options and its own ports
  (blank = automatic); an optional **port pool**; a **launch-script editor**.
- **Can friends connect?** — exactly which router ports to forward (and which must
  never be forwarded), plus a reachability check.
- **Backups** — per-server save backup/restore/download/delete with per-server
  retention, an automatic **pre-restore snapshot**, and a **daily auto-backup**
  timer. ARK backups include the shared cluster (toggle on restore).
- **Settings page** — all system-wide settings in one place, including changing
  the two game-server passwords.
- **Alerts** — Discord / ntfy / webhook on down / recovered / unreachable.
- **Update checks** — installed vs latest Steam build, with one-click apply.
- **Security** — bcrypt login, per-IP rate-limit, CSRF, hardened headers, optional
  fail2ban; the launch-script editor is content-validated.

## Quick start
One line in a terminal (once the repository is public):
```
wget -qO- https://raw.githubusercontent.com/KeithDude/GameDash/main/get.sh | bash
```
This puts GameDash in `~/gamedash` and installs it. (`curl -fsSL … | bash` works too where curl is
installed; a fresh Ubuntu desktop only has wget.)

Or from a downloaded copy (GitHub → Code → Download ZIP): unpack it, move the folder to your home
folder, open a terminal in it and run
```
bash install.sh       # no questions; it only asks for your computer's password
```
It prints the address to open and a one-time setup code. Open
**https://<host>:8443/**, accept the self-signed certificate, enter the code and choose
your password, then follow the *Getting started* checklist. Details and
prerequisites: **[deploy/SETUP.md](deploy/SETUP.md)**.

## Layout
```
gamedash/
├── app/          all application code (Flask app, games/, templates/, static/)
├── deploy/       systemd unit templates, fail2ban, OS maintenance, examples, SETUP.md
├── docs/         SUPPORTED_GAMES.md, ROADMAP.md, DEVELOPMENT_LOG.md
├── get.sh        one-line download + install
├── install.sh    one-step installer (calls setup.sh)
├── bin/gamedash  the `gamedash` command
├── setup.sh      GameDash-only setup
└── requirements.txt
```
Runtime data lives **outside the code** in the data root (so updating the code
never touches your data):
```
$GAMEDASH_HOME            (default ~/.config/gamedash)
├── config.json  servers.json  secrets.conf  certs/  logs/
~/.local/share/gamedash/backups/     (override with $GAMEDASH_BACKUPS)
```

## Running it
The `gamedash` command covers the everyday jobs (`gamedash help` lists them all):
```
gamedash status             is it running, where to open it, and each server's state
gamedash reset-password     choose a new dashboard password
gamedash restart            restart the dashboard
gamedash logs               the dashboard's recent log
gamedash servers            list the game servers
gamedash server restart <server>
gamedash backup all
gamedash update             update GameDash itself (rolls back if the new version fails)
gamedash qr                 a QR code to open the dashboard on a phone
gamedash check              quick health check
```
- Logs also live in `logs/` in the data root: `access.log`, `audit.log`, `gamedash.log`.
- Daily backups: `gamedash-backup.timer` (05:00). Run on demand from
  Settings/Backups → "Back up all servers now".

## Access tiers
- **Public (no login):** each server's online/offline + player count + the in-game
  name and how-to-join address. No player names, ports, resources, or host info.
- **Admin (login):** full detail + all controls.

## Player counts
Each game uses what it offers: the Steam server query, its admin console (RCON or a
plain-text console), its log file, or its own web API. Some games offer none of these;
the dashboard then shows the server as running without a player count.

## Notes
- HTTPS is terminated directly by gunicorn with a self-signed cert; browsers warn
  once. Swap in a CA-issued cert in `<data root>/certs/` anytime.
- Game-server passwords are stored only in the secrets file (0600), never in the
  code. The dashboard login password is a bcrypt hash in `config.json`.
- **Never forward an admin console (RCON) or other control port** on your router —
  see [deploy/SETUP.md](deploy/SETUP.md), section 6.
- Where it's heading: **[docs/ROADMAP.md](docs/ROADMAP.md)**. Development history: **[docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md)**.

## Support the project

GameDash is free for noncommercial use. If it's useful to you, you can support its development on
**[Patreon](https://www.patreon.com/KeithDude)**. The dashboard shows the same link at the bottom of
each page; it only opens the Patreon page and nothing in GameDash depends on it.

## License

GameDash is released under the **[PolyForm Noncommercial License 1.0.0](LICENSE.md)**.
You may use, change and share it for any noncommercial purpose — running servers for
yourself, your friends or your community, testing, learning. Commercial use (for
example a hosting company offering it to paying customers) needs the author's
permission. The game servers themselves belong to their publishers and are
downloaded by each user under the publishers' own terms.
