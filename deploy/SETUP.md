# GameDash — setup & third-party prerequisites

## The short version

On Ubuntu or Debian, from the GameDash folder:

```bash
bash install.sh
```

It installs what GameDash needs, starts it, and prints the address to open in
your browser together with a one-time setup code. Everything after that —
choosing passwords, installing games, adding servers, checking that friends can
connect — happens in the dashboard, guided by its "Getting started" checklist.

The rest of this document is the manual route and background detail.

GameDash manages **game dedicated servers you have already installed** on a
Linux host: it doesn't install the games for you (yet), it monitors and controls
them. This guide covers everything you need around GameDash, provider-neutral,
with examples. Commands assume Debian/Ubuntu `apt`; translate to your distro's
package manager as needed.

> TL;DR: install steamcmd + your game servers → run `./setup.sh` → open the
> dashboard → add each server pointing at its install dir → forward ports.

---

## 1. Host & system packages (required)

A 64-bit Linux box with **systemd** and a normal user account (GameDash runs as a
user service — no root needed for day-to-day operation).

```
sudo apt update
sudo apt install -y python3 python3-venv openssl curl
```

- **python3 / python3-venv** — GameDash is Python + Flask in a virtualenv.
  If your distro splits out `ensurepip`, also `sudo apt install -y python3-pip`.
  (setup.sh will bootstrap pip via `get-pip.py` if the venv has none.)
- **openssl** — generates the self-signed TLS certificate.
- **curl** — used by setup.sh and by some game launch helpers.

## 2. steamcmd (required to install/update game servers)

steamcmd is Valve's CLI for installing Steam dedicated servers, and GameDash's
"Update now" buttons call it. It needs 32-bit libraries.

```
sudo dpkg --add-architecture i386 && sudo apt update
sudo apt install -y lib32gcc-s1 ca-certificates
# Option A — distro package:
sudo apt install -y steamcmd
# Option B — manual (if no package):
mkdir -p ~/steamcmd && cd ~/steamcmd
curl -sqL https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz | tar zxvf -
# then run ./steamcmd.sh
```

## 3. Game dedicated servers (required — you install these)

Install each game's dedicated server with steamcmd, then point GameDash at the
install directory. Example pattern (anonymous login works for most):

```
steamcmd +force_install_dir ~/arkserver +login anonymous +app_update <APPID> validate +quit
```

| Game | steamcmd app id | Notes |
|------|-----------------|-------|
| ARK: Survival Evolved | 376030 | one install hosts many maps (cluster) |
| Palworld | 2394010 | one server per install (no save-dir override) |
| Valheim | 896660 | one install hosts many worlds |
| Satisfactory | 1690800 | one install hosts many instances (per-port) |

GameDash also supports a **Custom service** (any launch command) for games not
listed above.

After installing, open the dashboard → **Add a server**, pick the game template,
and set the install dir (or set defaults in **Settings → Install directories**).

## 4. Install GameDash

```
cd gamedash
./setup.sh            # venv, data root, cert, systemd units, linger
# add --fail2ban to also install the login-ban jail (needs sudo)
```

`setup.sh` creates the **data root** (default `~/.config/gamedash`, override with
`GAMEDASH_HOME`) holding `config.json`, `servers.json`, `secrets.conf`, `certs/`,
`logs/`; backups go to `~/.local/share/gamedash/backups` (override
`GAMEDASH_BACKUPS`). It generates a self-signed cert, prompts for the dashboard
admin password, installs the user units + daily-backup timer, and enables linger.

Open **https://<host>:8443/** and accept the self-signed cert.

### Linger (boot auto-start)
So the dashboard + servers start on boot without you logging in:
```
sudo loginctl enable-linger "$USER"      # setup.sh attempts this
```

## 5. Game-server passwords

The two shared passwords live in the secrets file (`secrets.conf` in the data
root, 0600). Set them in **Settings → Game-server passwords** (recommended) or
edit the file directly:
- `GAME_SERVER_PASSWORD` — shared join/server password (ARK/Palworld/Valheim).
- `GAME_ADMIN_PASSWORD` — admin / RCON password.
Restart a server after changing its password. Satisfactory's admin password is
set in its own in-game Server Manager (then matched in Settings if you want the
dashboard's player count / Save button).

## 6. Router port-forwarding (required for internet play)

You don't need to work out the ports yourself. On each server's card press
**“Can friends connect?”**: it lists exactly which ports your router has to pass on
to this computer, with the type (UDP/TCP) of each, and step-by-step instructions.
Forward those and nothing else.

> 🔒 **Never forward an admin console (RCON) or any other control port.**
> These ports let GameDash control a server: see the players, send messages, save,
> kick, ban, shut it down. Their passwords travel unencrypted and they are not built to
> face the internet, so if one were reachable from outside your home, a stranger could
> try passwords until one works and take the server over. GameDash only ever uses them
> from inside this computer.
>
> You will see them marked **“🔒 keep closed, never forward”** on the Add-a-server form,
> and listed under **“Never forward these”** in “Can friends connect?”. Leave them out
> of your router — always, even when a guide on the internet tells you to add them.

### Which games are tested?

See [docs/SUPPORTED_GAMES.md](../docs/SUPPORTED_GAMES.md) for the full list, marked Tested / Not Tested.

## 7. TLS certificate

setup.sh creates a self-signed cert (10-year, SANs for the hostname + localhost).
Browsers warn once — that's expected for self-signed. To use a browser-trusted
cert later, drop a `cert.pem`/`key.pem` from your CA (e.g. Let's Encrypt via
DNS-01) into `<data root>/certs/` and restart `gamedash`.

---

## Optional / recommended

### fail2ban (recommended — bans brute-force dashboard logins)
Bans IPs that repeatedly fail the dashboard login, at the firewall, on port 8443
only. `./setup.sh --fail2ban` installs it, or do it manually — see
`deploy/fail2ban/INSTALL.md`. Add your own LAN/VPN range to `ignoreip` so you
can't lock yourself out.

### Alerts (optional — Discord / ntfy / webhook)
**Settings → Alerts.** Get a target URL from your provider, paste it in:
- **Discord:** Server Settings → Integrations → Webhooks → New Webhook → Copy URL.
- **ntfy:** pick a topic, e.g. `https://ntfy.sh/your-unique-topic` (free phone push).
- **Generic webhook:** any URL that accepts a JSON POST.
Alerts fire on DOWN, RECOVERED, and running-but-unreachable.

### Dynamic DNS (optional — stable public hostname)
If your home IP changes, a DDNS provider gives you a stable name
(`yourname.example-ddns.net`) that follows your IP. Set it as **Settings →
Public host** so the "How to join" instructions show a stable address. Update
your router/DDNS client per your provider's docs.

### Valheim mods (optional — BepInEx)
For a modded Valheim world, install **BepInEx** into the Valheim install
(from Thunderstore or the BepInEx releases), add plugins under
`BepInEx/plugins/`, and choose the **"modded"** launch profile when adding the
world (or edit its launch script via the card's **Edit script** button).

---

## Updating GameDash

Pull/replace the code in the repo and restart — your data in the data root is
untouched:
```
git pull            # or replace the files
~/gamedash/venv/bin/pip install -r requirements.txt   # if deps changed
systemctl --user restart gamedash
```
