# Development log

*How WorldCradle grew, one feature (and the occasional burn) at a time. Newest first.*

I started WorldCradle so my friends and I could play together on our own private servers. It began
as a few scripts on my home server and grew, feature by feature, into something anyone can install.
What's in each release is in [CHANGELOG.md](../CHANGELOG.md); which games have been played on is in
[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

— Keith

---

## 2026-10-19 — 0.2.0: out in the wild

- **First public release**, and the repository went public.
- Installing is four lines, each with a one-sentence description.
- The welcome screen's link and QR code take you straight to the setup page.
- My own servers now run the same release everyone else gets. New versions are tried on a test
  machine first.

## 2026-10-18 — A new name, and every game on the same footing

- **Renamed to WorldCradle** — *A Cradle for your Worlds*. The first names I picked were taken.
- Every game rebuilt on the same foundations, then each one installed, started, stopped and removed
  on a test machine. 41 of 43 passed everything.
- Installing is download, `sudo apt install`, `worldcradle setup` — the only `sudo` is one you type,
  and setup itself never asks for a password.
- `sudo worldcradle update` puts the previous version back within 30 seconds if the new one doesn't
  start.
- Games install into `~/worldcradle-games`, each in a folder named after the game.
- Every game comes with a server name and settings filled in, so you can add a server without typing
  anything.
- Satisfactory saves its world when stopped (the game itself doesn't), and slow savers like Soulmask
  get the minutes they need.
- Tested a fresh install start to finish, then installed a game and joined it myself.

## 2026-10-17 — A big clean-up under the hood

- No new buttons, but the code got much simpler, which made adding and fixing games easier.
- Terraria and other console-driven games got the Save and Message buttons they were missing.
- Fixed: Squad's and Squad 44's password files could be read by other accounts on the computer.

## 2026-10-16 — A real package, and alerts that actually alert

- **A proper package** for Ubuntu and Debian, with exact, checksum-verified libraries.
- **Alerts to ten services** — Discord, Telegram, email, Slack, Teams, Pushover, ntfy, Gotify, Matrix
  or a webhook — several at once, each with a Test button that tells the truth.
  **Burned by:** the old Test button said "sent" every single time. Then I found out I'd never set an
  alert up, so not one had ever been sent.
- **"Keeps crashing" warning** on a server's card, plus an alert.
  **Burned by:** WorldCradle's own "are you alive?" check was crashing Terraria servers every couple
  of minutes — 19 times in one test — and the card said "running" the whole time. The check now asks
  the computer instead of poking the game.
- Servers simply start and stop: a stopped server stays stopped after a reboot, and servers can share
  ports and take turns.
- The Getting started guide, with screenshots. The dashboard works on phones.
- From the terminal: `uninstall`, `passwords`, `backup list` / `restore`, `unban`, `version`.
- Automated tests, a version number, release notes, and forms for bug reports and game test reports.
- Survives an upgrade to Ubuntu 26.04 without help.

## 2026-10-15 — The `worldcradle` command, and a bot that held me hostage

- **The `worldcradle` command** for everyday jobs: status, passwords, restart, logs, backups, start
  and stop servers.
- **`worldcradle update`** checks the new version works and puts the old one back if it doesn't.
- The installer checks the computer first, ends with a QR code for your phone, and picks random game
  passwords.
- **Repairs itself after an Ubuntu upgrade.**
  **Burned by:** the September upgrade swapped Python out from under the dashboard. It crash-looped,
  and took the nightly backup and ARK's clean shutdown down with it.
- **Copes with thousands of idle connections.**
  **Burned by:** something on the internet opened 8 connections and just… sat there. Nobody could get
  in, and the dashboard swore it was "running" the whole time.
- Licensed under PolyForm Noncommercial, with my own admin-console client replacing a GPL library.
- Accurate CPU and RAM figures per server; a Patreon link; the roadmap.

## 2026-10-14 — Honest about testing; control ports stay closed

- The supported-games list, with every game marked *Tested* (real players have played on it) or
  *Not Tested*.
- Admin consoles and other control ports are marked "keep closed, never forward" everywhere.
- Clearer figures: RAM, storage, binary gigabytes.

## 2026-10-13 — Every game checked against its own documentation

- Compared every game's setup with its publisher's instructions. The worst finds: Space Engineers
  reloaded its starting world on every restart, 7 Days to Die saved its world where backups couldn't
  see it, and StarRupture left a remote-control page open with no login. All fixed.
- Games whose licence requires it ask you to accept it before a server is created.
- More Windows-only servers running through Wine: SCUM, Astroneer, Voyagers of Nera, Windrose,
  StarRupture.

## 2026-10-12 — From my servers to anyone's

- **Goal: someone with almost no technical knowledge can set this up and use it.**
- Install games from the dashboard; a one-time setup code on first visit; a Getting started
  checklist; **Can friends connect?** with router steps; a free trusted certificate from Let's
  Encrypt.
- **30+ games added**, one at a time, each installed, run and removed: Minecraft, Terraria, Rust,
  Factorio, Counter-Strike 2, 7 Days to Die, Project Zomboid, V Rising, Enshrouded and many more.
  Rule from here on: if Steam has a Linux dedicated server for it, WorldCradle supports it.

## 2026-10-10 — Who's actually online

- Abiotic Factor's player list is read from the server's own log.
  **Burned by:** the card said nobody was online while three of us were playing.
- Every game has its own port boxes again (blank = automatic).

## 2026-10-08 — Locked down for the open internet

- **Decided:** the dashboard is built to be reachable from anywhere, so security has to hold up to
  that. Restricting it to the home network isn't the answer — if you don't want it open, don't open
  the port.
- A security review: a safety copy before every restore, alerts when a backup fails, a strict
  content-security policy, no game passwords in the log viewer, and changing the password signs
  everyone else out.
  **Burned by:** Valheim's backups had been failing silently for ten days after a game update changed
  how worlds are saved.
- The Add-a-server form shows each game's real options: lists, tick boxes, numbers with limits.
- Windows-only servers run with no window popping up.
  **Burned by:** a Windows console window kept appearing on my desktop every time Abiotic Factor
  started.

## 2026-10-06 — Windows-only servers, through Wine

- First Windows-only server, Abiotic Factor, running under Wine instead of Docker — one way of
  running servers, not two.

## 2026-07-20 — Patching the computer without kicking anyone off

- An OS-updates tile: how many updates are waiting, how many are security fixes, whether a restart is
  needed.
- Weekly operating-system patching that backs up every save first and only runs when nobody is
  playing — and gives up if it can't tell.

## 2026-06-25 — Installable by someone other than me

- Settings, passwords and servers moved out of the code, so updating can never touch them.
- A setup script and an install guide; personal details became settings.
- Change the game passwords from the dashboard.

## 2026-06-19 — The dashboard runs everything

- Every server runs as a dashboard-managed service with a generated launch, instead of my
  hand-made ones.

## 2026-06-18 — From a status page to a control panel

- One join password friends share and one private admin password, instead of a copy per server.
- **Add a server** from the dashboard, one module per game.
- **Update checks** against Steam's latest build.
  **Burned by:** friends couldn't join ARK. My update script had its options in the wrong order and
  had quietly done nothing for over a year, so the game refused the out-of-date server.
- Logs, and fail2ban blocking anyone who keeps guessing the password.

## 2026-06-17 — The first dashboard

- A web page showing which servers are up and who's playing, with start, stop and restart.
- Two levels from day one: a public page friends can see, and a signed-in admin page with everything
  else.
- Over the following weeks: backups and restore, daily automatic backups, alerts, a launch-script
  editor and a port pool.

## 2026-06-14 — The day I froze my friend in ARK

- **WorldCradle checks who's online before it stops, restarts or updates anything, and warns them
  first.**
  **Burned by:** trying to pause an "empty" ARK server to save power. It wasn't empty. My friend and I
  were stuck in a frozen world until a restart rolled us back.

## Before 2026 — Scripts on my home server

- Hand-written scripts to back up ARK, update my servers with steamcmd, and talk to ARK's admin
  console. That's where the first dashboard commands came from.
