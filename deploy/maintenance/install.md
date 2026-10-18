# Unattended OS maintenance for the game-server box

Weekly, player-aware OS patching. Backs up saves, gracefully stops the fleet,
applies updates, and reboots only when the kernel/libs actually require it.

## Why a root systemd timer and not a sudoers rule

The obvious approach — a `NOPASSWD` sudoers entry so a user timer can call
`sudo apt upgrade` — would be a **root escalation on this box**. The rule has to
name a script, and any script the game user can write is a script the game user
(or anything running as them, including the internet-facing dashboard's launch-script
editor) can turn into `chmod +s /bin/sh`.

A root-owned system timer gets the same unattended result with no standing
`NOPASSWD` grant. That is why the script installs to `/usr/local/sbin`
(root-owned, not writable by the game user) rather than running from `~/worldcradle`.

**The files in this directory are a staging copy and ARE user-writable.** They are
not what runs. Only the installed copy at `/usr/local/sbin/worldcradle-os-maintenance.sh`
executes, and re-installing from here is a privileged action — re-read the script
before you do it.

## Install (one time, as root)

```bash
# run as the account that runs WorldCradle (not root), from the WorldCradle folder
cd ~/worldcradle/deploy/maintenance

# 1. the script — filled in with your account, root-owned, not writable by the game user
sed -e "s/__GAME_USER__/$(id -un)/" -e "s/__GAME_UID__/$(id -u)/" worldcradle-os-maintenance.sh \
    | sudo install -o root -g root -m 0755 /dev/stdin /usr/local/sbin/worldcradle-os-maintenance.sh

# 2. the units
sudo install -o root -g root -m 0644 \
    worldcradle-os-maintenance.service worldcradle-os-maintenance.timer \
    /etc/systemd/system/

# 3. activate the weekly timer
sudo systemctl daemon-reload
sudo systemctl enable --now worldcradle-os-maintenance.timer

# 4. confirm
systemctl status worldcradle-os-maintenance.timer
systemctl list-timers worldcradle-os-maintenance.timer
```

## Preview without changing anything

`--dry-run` performs the real player check and refreshes the package lists (both
non-destructive), then logs what it *would* do instead of stopping servers,
installing anything, or rebooting:

```bash
sudo /usr/local/sbin/worldcradle-os-maintenance.sh --dry-run
```

## Run the window now instead of waiting

```bash
sudo systemctl start worldcradle-os-maintenance.service
journalctl -u worldcradle-os-maintenance.service -f
```

## Schedule

`Wed *-*-* 10:00:00` local, plus up to 15 min jitter. Mid-morning is deliberate:
observed play on this box is late-night (~01:00–04:00), so this sits as far from
it as a daytime slot gets.

Not `Persistent=true` — if the box is off at 10:00 we do **not** want the fleet
stopped and rebooted at whatever random time it next boots. A missed week just
waits for the next one.

To change the day/time: `sudo systemctl edit worldcradle-os-maintenance.timer`.

## Safety behaviour

| Situation | What happens |
|---|---|
| Any player online | Defers to the next window. Nothing is touched. |
| Dashboard unreachable (player count unknown) | **Aborts.** Unknown is not treated as zero. |
| Nothing to install, no reboot pending | Exits early; the fleet is never stopped. |
| Save backup fails | **Aborts** before patching. |
| A server won't stop within 5 min | Aborts and restarts the fleet rather than patching mid-save. |
| Reboot required | Reboots; enabled units auto-start on boot. |
| No reboot required | Restarts exactly the servers it stopped. |

Servers are discovered at runtime from `systemctl --user`, so servers added or
removed via the dashboard are picked up automatically. `worldcradle.service` (the
dashboard itself) is not a `worldcradle-*` unit and is never stopped.

Servers you stopped in the dashboard are not set to start with the computer, so they stay
stopped after a reboot — on purpose. Servers that were running come back.

## Log

`/var/log/worldcradle-os-maintenance.log`, plus the systemd journal:

```bash
journalctl -u worldcradle-os-maintenance.service --since "1 month ago"
```
