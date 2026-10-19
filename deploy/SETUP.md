# Installing WorldCradle — the details

Most people only need the four lines in [docs/GETTING_STARTED.md](../docs/GETTING_STARTED.md). This
page explains what installing does, the other ways to install, updating, removing, and the
manual route for systems the installer doesn't cover.

## Ways to install

**1. The package** (Ubuntu 22.04+ / Debian 12+; Debian not yet tested):
```
wget -O /tmp/worldcradle.deb https://github.com/KeithDude/WorldCradle/releases/latest/download/worldcradle.deb
sudo apt update
sudo apt install /tmp/worldcradle.deb
worldcradle setup                     # as your normal user, not with sudo
```
The address always gives the newest release. To check the download first, compare it with the
release's `worldcradle.deb.sha256` (`sha256sum /tmp/worldcradle.deb`). Only the `sudo apt` step needs
administrator rights: apt installs WorldCradle and the system packages the games need. Add
`--no-install-recommends` to it to leave out the optional extras (Java, Wine, fail2ban). Each release
also has the same package under its versioned name, `worldcradle_<version>_all.deb`.

**2. From the source** (for development, or before a release exists): clone or download the
repository into your home folder, then `sudo bash install.sh` in it, from your own account. As root it
installs the same system packages the package would and does the same system jobs (below); then it
runs the same setup as you.

Both end the same way: the dashboard running at `https://<this computer>:8443/`, a one-time
setup code for choosing your password in the browser, and the password friends need to join.

## What gets installed where

| What | Package install | Source install |
|---|---|---|
| The program | `/usr/lib/worldcradle` (the `worldcradle` command in `/usr/bin`) | the folder you put it in |
| Its Python libraries | `~/.local/share/worldcradle/venv` | `venv/` in that folder |
| Settings, server list, certificate, logs | `~/.config/worldcradle` | same |
| The two game passwords | `~/.config/worldcradle/secrets.conf` (private to your account) | same |
| Save backups | `~/.local/share/worldcradle/backups` | same |
| Games | `~/worldcradle-games`, one folder per game named after it, e.g. `~/worldcradle-games/Valheim`, `~/worldcradle-games/ARK-Survival-Evolved`, `~/worldcradle-games/Garrys-Mod` | same |
| Extra copies for games that need one per server (Palworld, Eco, Squad and a few others) | next to the game's folder, named after the server: `~/worldcradle-games/Palworld-<server>` | same |
| Wine environments (Windows-only servers) | `~/.wine-wc-<game>-<server>`, one per server | same |
| Background services | `worldcradle.service`, `worldcradle-backup.timer`, and one `worldcradle-<server>.service` per game server (your account's systemd, `~/.config/systemd/user`) | same |

Each server's world is kept where its game normally keeps it — usually inside the game's folder,
for a few games in your home folder (Valheim: `~/.config/unity3d/IronGate/Valheim`). Backups know
where each one is; **Backups** in the dashboard lists them by server.

**Updating from 0.1.0:** games installed by 0.1.0 live in `~/<game>server` (for example
`~/valheimserver`). They stay there and keep working: WorldCradle records each one's folder the
first time the new version starts, and **Settings → General** shows it. Nothing is moved for you.
Games you install from now on go into `~/worldcradle-games`.

The Python libraries are exact versions with checksums (`requirements.lock`); pip refuses
anything that doesn't match. If an operating-system upgrade changes the Python version, WorldCradle
rebuilds its libraries by itself the next time it starts.

**System packages** — listed once in [packages.conf](packages.conf): WorldCradle itself needs Python
(with `venv`), openssl and curl. Game servers need a few libraries (32-bit support for Steam's
downloader, plus some that particular games load). Optional extras: Java (Minecraft), Wine
(Windows-only servers), winetricks + cabextract (Space Engineers), fail2ban. The package lists the
optional ones as "recommended", which apt installs unless you add `--no-install-recommends`.

**What installing does as root** (the `sudo apt install` step, or `sudo bash install.sh`): lets
WorldCradle keep running after you log out and start with the computer (linger), lets the dashboard
through the `ufw` firewall if it's on, and sets up fail2ban, if it's installed, to block addresses that
keep getting the dashboard password wrong. Run it again with `sudo dpkg-reconfigure worldcradle`.

**What setup does** (`worldcradle setup`, or the last step of `install.sh`; runs as you, never asks for a
password; safe to repeat): checks the computer, builds the Python libraries, creates the settings folder
with random game passwords and a self-signed certificate, and starts the dashboard and the daily 05:00
backup. If one of the root jobs above is missing, it says which command to run. It never overwrites
existing settings, passwords, certificate or servers. Option: `--force` (carry on despite failed checks).

## Updating

It's a good idea to bring the computer up to date first — `sudo apt update`, then `sudo apt upgrade`
— before installing or updating WorldCradle. (Not required: WorldCradle refreshes the package lists
itself.)

**Package install:** `sudo worldcradle update`. It needs `sudo` because it replaces a system package.
It shows what's new, downloads the newest release's package, checks its checksum, installs it with apt,
checks the new version answers, and puts the previous version back by itself if it doesn't. Game
servers keep running throughout.

**Or by hand**, the same way as the first install — no automatic check or roll-back:
```
wget -O /tmp/worldcradle.deb https://github.com/KeithDude/WorldCradle/releases/latest/download/worldcradle.deb
sudo apt update
sudo apt install /tmp/worldcradle.deb
```

**Source install:** `worldcradle update`, without sudo — it fetches the newest code with git, as you.

Your settings, servers and saves are never touched by an update.

## Removing

`worldcradle uninstall` stops and removes your game servers' background services (asking first if
players are online), the dashboard, and the daily backup, and asks before deleting settings or
backups. Game installs and their saves are never deleted (`~/worldcradle-games` and the worlds stay
where they are). For a package install, finish with
`sudo apt remove worldcradle`.

Removing the package alone stops the dashboard but leaves your settings and your game servers
running; installing WorldCradle again picks up where you left off.

## Letting friends in: router port forwarding

You don't need to work out the ports yourself. On each server's card press
**“Can friends connect?”**: it lists exactly which ports your router has to pass on
to this computer, with the type (UDP/TCP) of each, and step-by-step instructions.
Forward those and nothing else.

> 🔒 **Never forward an admin console (RCON) or any other control port.**
> These ports let WorldCradle control a server: see the players, send messages, save,
> kick, ban, shut it down. Their passwords travel unencrypted and they are not built to
> face the internet, so if one were reachable from outside your home, a stranger could
> try passwords until one works and take the server over. WorldCradle only ever uses them
> from inside this computer.
>
> You will see them marked **“🔒 keep closed, never forward”** on the Add-a-server form,
> and listed under **“Never forward these”** in “Can friends connect?”. Leave them out
> of your router — always, even when a guide on the internet tells you to add them.

Which games have been tried with real players: [docs/SUPPORTED_GAMES.md](../docs/SUPPORTED_GAMES.md).

## Passwords

- **Dashboard password** — chosen in the browser on first visit; forgot it? `worldcradle reset-password`.
- **Game passwords** — one that friends type to join, one private admin password. Random ones are
  picked at setup; see them with `worldcradle passwords`, change them in **Settings → Game-server passwords**
  (restart the servers afterwards).

## Certificate

The dashboard starts with its own self-signed certificate, so browsers warn once — expected. For a
certificate browsers trust, use **Settings → Trusted certificate** (free, from Let's Encrypt; needs a name
that points at your home, see *Dynamic DNS*). It renews itself.

## Optional

### Dynamic DNS (a stable name for your home)
If your home's internet address changes, a dynamic-DNS provider gives you a name
(`yourname.example-ddns.net`) that follows it. Put it in **Settings → General → Your public address** so
"How to join" shows it.

### Valheim mods (BepInEx)
For a modded Valheim world, install **BepInEx** into the Valheim install (from Thunderstore or the
BepInEx releases), add plugins under `BepInEx/plugins/`, and choose the **"modded"** launch profile
when adding the world (or edit its launch script with the card's **Launch script** button).

### Weekly operating-system updates
[maintenance/install.md](maintenance/install.md): patches the computer once a week, only when no one
is playing, after backing up every save.

## Other Linux systems

The installer and package are for Ubuntu and Debian. Elsewhere: install the equivalents of the
packages in [packages.conf](packages.conf) with your package manager, download the source into your
home folder and run `./setup.sh` in it. WorldCradle needs systemd user services.

## Building the package

`tools/build-deb.sh` builds `dist/worldcradle_<version>_all.deb` (and its `.sha256`) from the
committed code; `--worktree` builds from the files as they are now, for testing. A release
attaches both files to a GitHub release tagged `v<version>`.
