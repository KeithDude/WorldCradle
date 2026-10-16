# Changelog

What changed in each version of GameDash, written for the people who run it. The detailed history
of how it was built is in [docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md).

Version numbers: `MAJOR.MINOR.PATCH`. Until 1.0, a new MINOR version can change how things work;
these notes say what you need to do when it does. The version you have: `gamedash version`, or the
footer of the dashboard when signed in.

## 0.2.0 — Public preview (not released yet)

### New
- **45 games** you can install and run from the dashboard (Windows-only servers run through Wine),
  plus any other server as a custom service. Which ones have been tried with real players:
  [docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md).
- **One-step install** that asks no questions (only your computer's password) and checks first that
  the computer can run GameDash. Shows a QR code to open the dashboard on a phone, and the password
  your friends need to join.
- **The `gamedash` command** for everyday jobs: `status`, `passwords`, `reset-password`, `restart`,
  `logs`, `servers`, `server start|stop|restart <server>`, `backup`, `backup list|restore`, `unban`,
  `update`, `uninstall`, `check`, `qr`. Type `gamedash help` for the list.
- **Safe updates:** `gamedash update` installs the new version and puts the old one back by itself if
  the new one doesn't start.
- **Repairs itself after an Ubuntu upgrade** that changes the Python version.
- **Licence terms:** where a game's publisher requires it, you accept its EULA when adding a server.
- **Total CPU usage, RAM and storage** at the top; each server's own share of the computer on its
  card.

- **Alerts to the services you use:** Discord, Telegram, email, Slack, Microsoft Teams, Pushover,
  ntfy, Gotify, Matrix or a webhook — several at once, each with a Test button that tells you whether
  it worked and, if not, why. Also `gamedash test-alert`.

### Safer
- New installs pick **random game passwords** instead of well-known placeholders.
- **Admin consoles are never forwarded**: they're marked "keep closed" everywhere, and *Can friends
  connect?* lists them under "Never forward these".
- The dashboard can no longer be **locked up by connections that never finish**.
- Several game setups fixed after checking them against the publishers' own documentation —
  including two that could lose a world (Space Engineers reloaded its starting world on every
  restart; 7 Days to Die saved outside the backed-up folder) and one that left a server open to
  takeover (StarRupture).
- **Terraria servers no longer crash every few minutes** — GameDash's "is it answering?" check used
  to connect to the game in a way Terraria's server can't handle. It now asks the computer instead.
- The dashboard works properly on phones (the top menu used to run off the screen).
- When you're signed out while the dashboard is open, it now goes to the login page instead of
  quietly showing old information.
- `gamedash uninstall` now leaves a server running if you say so, and also offers to remove a
  backup folder you moved elsewhere.
- Don't Starve Together servers now pick up a changed join password when they start.
- Alerts follow each service's own documentation: new Matrix rooms can be used, email over "SSL"
  uses the right port, and when a service refuses a message you're told its actual reason.
- A server that **keeps crashing** now says so on its card (and sends an alert), instead of looking
  "running" between crashes.

### Good to know
- Requires Ubuntu 22.04 or newer (24.04+ recommended for Windows-only game servers), or Debian 12+.
- Licensed under PolyForm Noncommercial 1.0.0 — free for noncommercial use.

## 0.1.0 — Private alpha (2026-06 to 2026-09)

First working version on the maintainer's own machine: monitoring and control of ARK: Survival
Evolved, Palworld, Valheim and Satisfactory servers, backups and restore, alerts, update checks.
