# Changelog

What changed in each version of WorldCradle, written for the people who run it. The detailed history
of how it was built is in [docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md).

Version numbers: `MAJOR.MINOR.PATCH`. Until 1.0, a new MINOR version can change how things work;
these notes say what you need to do when it does. The version you have: `worldcradle version`, or the
footer of the dashboard when signed in.

## 0.2.0 — Public preview (not released yet)

### New
- **45 games** you can install and run from the dashboard (Windows-only servers run through Wine),
  plus any other server as a custom service. Which ones have been tried with real players:
  [docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md).
- **Simple install:** download the package, install it with `sudo apt`, then run `worldcradle setup`,
  which asks no questions, checks first that the computer can run WorldCradle, and shows a QR code to
  open the dashboard on a phone and the password your friends need to join.
- **A WorldCradle package** (`.deb`) for Ubuntu and Debian: download it, `sudo apt install` it, then
  `worldcradle setup` — the only `sudo` is the one you type; setup itself never asks for a password.
  `sudo worldcradle update` installs new versions of it (and puts the old one back if the new one
  doesn't start).
- WorldCradle's Python libraries are **exact, checksum-verified versions**, so every install gets
  exactly what was tested.
- **The `worldcradle` command** for everyday jobs: `status`, `passwords`, `reset-password`, `restart`,
  `logs`, `servers`, `server start|stop|restart <server>`, `backup`, `backup list|restore`, `unban`,
  `update`, `uninstall`, `check`, `qr`. Type `worldcradle help` for the list.
- **Safe updates:** `sudo worldcradle update` installs the new version and puts the old one back by itself if
  the new one doesn't start.
- **Repairs itself after an Ubuntu upgrade** that changes the Python version.
- **Licence terms:** where a game's publisher requires it, you accept its EULA when adding a server.
- **Total CPU usage, RAM and storage** at the top; each server's own share of the computer on its
  card.

- **Alerts to the services you use:** Discord, Telegram, email, Slack, Microsoft Teams, Pushover,
  ntfy, Gotify, Matrix or a webhook — several at once, each with a Test button that tells you whether
  it worked and, if not, why. Also `worldcradle test-alert`.

### Safer
- New installs pick **random game passwords** instead of well-known placeholders.
- **Admin consoles are never forwarded**: they're marked "keep closed" everywhere, and *Can friends
  connect?* lists them under "Never forward these".
- The dashboard can no longer be **locked up by connections that never finish**.
- Several game setups fixed after checking them against the publishers' own documentation —
  including two that could lose a world (Space Engineers reloaded its starting world on every
  restart; 7 Days to Die saved outside the backed-up folder) and one that left a server open to
  takeover (StarRupture).
- **Terraria servers no longer crash every few minutes** — WorldCradle's "is it answering?" check used
  to connect to the game in a way Terraria's server can't handle. It now asks the computer instead.
- The dashboard works properly on phones (the top menu used to run off the screen).
- When you're signed out while the dashboard is open, it now goes to the login page instead of
  quietly showing old information.
- `worldcradle uninstall` now leaves a server running if you say so, and also offers to remove a
  backup folder you moved elsewhere.
- Don't Starve Together servers now pick up a changed join password when they start.
- **Servers can share ports and take turns:** type any ports when adding a server — even ones
  another server uses. Pressing Start checks the ports first and, if they're in use, says which
  server (or that another program) has them. No more "parked" servers or extra questions.
- Every server's card offers the in-game buttons its game supports (e.g. **Save** and **Message**
  for Terraria, which were missing).
- **Stop means stopped:** a server you stop stays stopped when the computer restarts, and one you
  start comes back by itself. (Before, a stopped server started again after a reboot.)
- Alerts follow each service's own documentation: new Matrix rooms can be used, email over "SSL"
  uses the right port, and when a service refuses a message you're told its actual reason.
- A server that **keeps crashing** now says so on its card (and sends an alert), instead of looking
  "running" between crashes.
- **Satisfactory:** a new server is claimed for you with your passwords and its name (no claiming it
  in the game first), and every stop **saves the world first** (the game itself doesn't). Its admin
  connection no longer goes missing after a quick restart.
- **Stop, Restart and updates wait for slow games** (some take minutes to save, like Soulmask) instead
  of reporting a failure while the server is still saving.
- **Steam games start on a fresh computer:** Steam's own library is set up for them (Eco, among
  others, couldn't start without it).
- **A broken update is undone in seconds**, not after a 10-minute wait.
- Removing a server also removes its launch files (its world is still kept).
- Each server's card shows only what its game can actually report.

### Good to know
- Requires Ubuntu 22.04 or newer (24.04+ recommended for Windows-only game servers), or Debian 12+.
- Licensed under PolyForm Noncommercial 1.0.0 — free for noncommercial use.
- Games install in `~/worldcradle-games`, each in a folder named after the game (for example
  `~/worldcradle-games/Valheim`). Games installed by 0.1.0 in `~/<game>server` stay where they are.

## 0.1.0 — Private alpha (2026-06 to 2026-09)

First working version on the maintainer's own machine: monitoring and control of ARK: Survival
Evolved, Palworld, Valheim and Satisfactory servers, backups and restore, alerts, update checks.
