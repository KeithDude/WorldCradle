# Development log

A running record of how WorldCradle has developed: what was built, what was found, and what is still
open. Newest entries first. Add an entry whenever something notable changes — a feature, a game, a
bug found and fixed, or a decision and the reason for it.

The list of games and their test status is kept separately in
[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

---

## 2026-10-18 — Fresh-install test on Ubuntu 24.04, and sudo only where you type it

- **Installing no longer asks for a password behind your back.** `get.sh` is retired; installing is
  download, `sudo apt install`, `worldcradle setup`. The package does the jobs that need root when it
  is installed (start with the computer, the firewall, fail2ban); `worldcradle setup` never asks for a
  password. Updating is `sudo worldcradle update` (or by hand, the same way as installing); installing
  from the source is `sudo bash install.sh`. Run as root, WorldCradle writes nothing in the account's
  folders.
- **Fresh Ubuntu 24.04 LTS server**, tested by Claude and then by Keith following the guide: install in
  under a minute, setup with no password prompt, first visit, and Terraria, Minecraft, Eco, Valheim,
  Palworld, V Rising and Abiotic Factor running. **Keith installed Abiotic Factor himself and joined
  it.** `sudo bash install.sh` tested too.
- **Space Engineers on Ubuntu 22.04/24.04 needs 32-bit Wine** for its one-time .NET install (26.04's
  Wine has it built in). The Games panel now says so with the commands to type; whether it then fully
  works on 24.04 is still to be confirmed.
- The six getting-started screenshots retaken under the new name; a finished job's message now shows
  for 10 minutes instead of for good; uninstall messages corrected.

## 2026-10-18 — One standard for every game, a new name, and every game tested on the server side

- **Every game on the shared bases.** All game types now build on `SimpleGame` / `WineGame`, keeping
  only what each game really needs. Keith's own servers (ARK ×4, Palworld, Valheim, Satisfactory,
  Abiotic Factor) were moved onto the standard launch with `provision.adopt()`: same worlds and
  settings, a player check and 1-minute warning before each stop, saves confirmed after each.
- **Renamed to WorldCradle** — "A Cradle for your Worlds" (after GameDash, WorldSeed and
  RealmCradle: the first two were taken). Everything was renamed, including service and folder names;
  Keith's box and the test VM were moved over.
- **Server-side tests of every game** with `tools/test-game.py` on the test VM: install, add, run,
  answer, players, Save/Message buttons, clean stop, remove, uninstall. 41 of 43 pass everything.
  Squad 44 and Icarus run, are listed and stop cleanly, but their game traffic goes through Steam's
  network rather than an ordinary open port — whether players can join needs a real player.
  DST (needs a Klei token) and Dragonwilds (needs an owner ID) were not run.
- **Bugs found by the tests and fixed:** Steam's 64-bit client library was never set up on a fresh
  computer (Eco couldn't start); Stop / Restart / updates gave up after 130 s on games that take
  minutes to save (Soulmask); ARK's stop never waited for the process (a `?` in its pattern);
  Satisfactory didn't save on stop, needed claiming in-game before the dashboard could see it, and
  its API moved port when restarted quickly; Windrose's and ARK Ascended's cards promised rows they
  could never fill; removing a server left its scripts behind; a blank ARK map or Valheim world name
  was refused.
- **The package, re-tested with apt** under the new name: install, update, a broken update rolled
  back (now in 30 s instead of 10 minutes), uninstall and reinstall keeping the settings.
- **GitHub Actions** failed only because the setup tests depended on the machine's umask; fixed, and
  the pre-push check now uses GitHub's.
- **Decided:** install stays the one-line `get.sh` (or the `.deb`) for the first release; our own apt
  repository is wanted for a later update (see ROADMAP).

## 2026-10-17 — Code clean-up, part 2

All checked in a browser or on real servers on the test VM, and by a new safety net.

- **The dashboard page:**
  - **Windows:** one helper replaces six hand-built ones. Each now closes on Escape, a click
    outside or ✕.
  - **Players-online question:** one shared step replaces five copies.
  - **Card buttons:** they live in one table.
  - **Game knowledge moved out of the page:** each game declares its own "How to join" steps and
    its in-game buttons. This gave Terraria and other console-driven games the Save and Message
    buttons they were missing.
  - **Split into modules:** the 1,290-line `app.js` became eight modules
    (`app/static/js/`), each page loading only its own, with no build step.
  - **No inline styles:** the security policy no longer allows `'unsafe-inline'` styles.
- **Safety net for game setup:** `tests/provision_snapshots.py` records, for all 45 games, what
  creating a server writes:
  - launch scripts, settings files and their permissions;
  - the server record;
  - each settings file after its password-sync step runs with a changed password.
  
  The recording is identical on every computer, because paths, the Python, random values and the
  LAN address become placeholders. Every step below was checked against it.
- **Game setup reworked:**
  - **Password sync:** one way to put the passwords into a game's settings at start
    (`common.password_sync` / `json_password_sync`), replacing ~20 snippets.
  - **Form limits** are written once, in the form field (`GameType.option`), replacing 139 copies.
  - **Shared helpers:** `common.write_private` (21 copies) and `empty_probe()` (33 copies).
  - **One file per game:** `more.py` and `winegames.py` split.
  - **Result:** every game writes the same files as before, with one exception — a found bug, below.
- **Found and fixed:** Squad and Squad 44 kept their admin-console password (Squad 44 also the
  join password) in settings files other accounts could read.
- **Plumbing:**
  - `systemd.py` is now the one way to run `systemctl`, replacing six. Stop, start, restart and
    force stop were tested on the VM, with start-at-boot following each.
  - `jobs.Job` is the one helper for background tasks, replacing four.
- **Still to do** (roadmap):
  - the smaller shared helpers (player lists, admin commands, downloads);
  - moving the older game types onto the shared bases. That changes their launch scripts, so each
    one needs a real server test.

## 2026-10-16 — A real package; one setup for every way of installing

The owner made the package and the install/update process the priority before going public.

- **`.deb` package** (`tools/build-deb.sh`). The program goes in `/usr/lib/worldcradle`. Each account's
  Python libraries live in its home folder (`~/.local/share/worldcradle/venv`), not in the package:
  the package stays `all`-architecture and small (~200 KB), and Python upgrades are handled by the
  existing self-repair.
  - System packages are listed once, in `deploy/packages.conf`. The package Depends only on what
    WorldCradle itself needs; game libraries and extras are Recommends, so it still installs where a
    game library is missing.
  - postinst restarts every account's running dashboard after an upgrade. prerm stops them on
    removal; settings, servers and saves are always kept.
- **Pinned libraries:** `requirements.lock` (generated with `uv pip compile --universal
  --generate-hashes` for Python 3.10+, `tools/lock-requirements.sh`) installed with
  `--require-hashes`. The environment remembers which list it was built from, so a new version
  that needs different libraries gets them on its first start.
  - The pre-push check now checks the licence of every pinned library (it used to check only the
    direct ones) and that the lock matches `requirements.txt`.
- **One setup:** `setup.sh` now does everything account-level, including the computer checks (now
  `bin/worldcradle-preflight`, shared with `install.sh`), linger, the firewall, fail2ban and the
  final screen (now `worldcradle welcome`).
  - `install.sh` is just: checks, system packages, setup.
  - `worldcradle setup` runs the same setup after installing the package.
  - The dashboard's port is set in one place for the scripts (`bin/worldcradle-env.sh`).
- **Updates:** `worldcradle update` on a package install finds the newest GitHub release, checks the
  download against its published SHA-256 checksum, installs it with apt, and reinstalls the
  previous release if the new one doesn't answer. `get.sh` installs the newest release's package
  (checksum-checked) and falls back to the source while none is published.
- **Smaller fixes:**
  - The OS-maintenance script now backs up through the dashboard's own backup service instead
    of a hard-coded program path.
  - `worldcradle version` no longer crashes without git.
- Tested on the VM: the source install re-run (libraries moved to the pinned versions), and the
  package's files run as a package install would (libraries built in the home folder in 13 s;
  dashboard, backup service, `status`, `version`, `update`). `install.sh --check` too.
  Later the same day, **tested with apt for real** on the VM:
  - install, then setup;
  - an update to a newer package;
  - a deliberately broken update, which rolled back to the previous version by itself;
  - removal, with settings and the game server kept;
  - a reinstall that picked up the same settings and servers.
  
  All steps passed.
- Found on the way: another product called "WorldCradle" exists — a commercial game-server control
  panel. The owner was told before going public.

## 2026-10-16 — Alerts checked against each service's documentation; code clean-up

Every alert service was compared with its own developer documentation, and the whole codebase was
reviewed for dead code, duplication and comments that no longer matched the code. Fixed:

- **Alerts, per the services' documentation:**
  - Matrix: new rooms couldn't be saved. Their IDs have no `:server` part since room version 12.
  - Email: "SSL" with the port left empty connected on 587 instead of 465. Messages also lacked the
    Date and Message-ID headers.
  - Telegram: "bot was kicked" and "chat not found" were reported as a bad token; the message now
    says what Telegram said. A group upgraded to a supergroup gives its new chat ID.
  - Discord: alerts can no longer ping @everyone.
  - Slack: `&`, `<` and `>` are escaped.
  - Teams: the card's `contentUrl`, the current template name, and a note that Teams accepts a
    message before posting it.
  - Pushover: keys are exactly 30 characters.
  - ntfy: titles with accents or emoji survive.
  - All services: a "too many messages" answer is retried once if the wait is short. Matrix,
    Pushover and Slack now show the service's own reason when they refuse something.
- **Real bugs found by the review:**
  - The Getting-started "alerts" step could never be ticked.
  - A signed-out dashboard froze on stale data instead of returning to the login page.
  - `worldcradle uninstall` stopped a server the owner had chosen to leave running, and ignored a
    custom backup folder.
  - Don't Starve Together never picked up a changed join password.
  - The lenient RCON client could hang on a malformed reply.
  - The update checker's thread could die silently.
  - The pre-push check's "shell scripts parse" line depended on earlier failures, and
    `install.sh --help` printed a line of code.
  - The OS-maintenance dry run waited 5 minutes for servers it hadn't stopped.
  - Clone-install games all ran Palworld's folder clean-up.
  - Barotrauma servers share one campaign-save folder. It isn't fixed yet, but the Add form now says so.
- **Clean-up (no change in behaviour):**
  - One CSRF check and one error handler instead of about 17 copies each in `app.py`.
  - One request helper in `app.js` instead of about 30 hand-written ones.
  - One LAN-address lookup instead of three.
  - Game types share the default save location (21 copies removed) and the "never forward the
    admin console" text (10 copies).
  - Dead code removed: unused helpers, constants and imports, and a field that was never filled in.
  - Outdated docstrings and comments corrected.
  - `pyflakes` added to the pre-push check so unused code can't creep back.
- Tested: 176 automated tests (new: every admin route refuses a missing or wrong CSRF token and a
  signed-out caller; the alert fixes; uninstall; DST password sync; RCON garbage). The dashboard
  was clicked through in a real browser on the test VM. **Alerts are still not tested with real
  accounts.**
- **Still to do (roadmap, *Code clean-up, part 2*):** the larger restructuring the review proposed.
  It touches how servers are launched, so each step needs testing on real servers.

## 2026-10-16 — Alerts: ten services, several destinations, an honest Test button

- **Bug: the "send test" button always reported success.** Delivery errors were swallowed and an
  error answer from the service (e.g. a mistyped Discord address) still counted as sent, so the
  alerts — which the maintainer had never tried — couldn't be trusted. Each send now reports what
  happened, in plain words ("the service refused it — check the token", "that address doesn't
  exist", "couldn't reach the service"…).
- **`app/notifiers.py`:** Discord, Telegram, email (SMTP with STARTTLS/SSL), Slack, Microsoft Teams
  (Workflows / Adaptive Card), Pushover, ntfy, Gotify, Matrix and a generic webhook. Each has a form
  with plain help on where to find the token or address, and checks that values look right before
  saving. Tokens, passwords and webhook addresses are never sent back to the browser (shown as
  "saved"; kept unless replaced).
- **Several destinations at once** (up to 10), each with its own Test button; "Save & test all";
  `worldcradle test-alert`. Older single-destination settings are read as one destination.
- Tested: every service against stand-in servers on this machine (HTTP and a small SMTP server),
  including the failure messages (122 tests); the Settings page in a real browser on the test VM
  (webhook test reached a local receiver; a wrong Discord address was refused; secrets stayed hidden
  after a reload). **Not yet tested with real accounts** — on the roadmap.
- Found while checking: the maintainer's dashboard had no alert destination set, so no alert had
  ever been sent.

## 2026-10-16 — Automated tests

- `tests/` (pytest, a development-only dependency in `requirements-dev.txt`): 113 tests in half a
  second — port allocation, WorldCradle's RCON client against a fake RCON server (multi-packet replies,
  wrong password, nothing listening), `port_listening` never connecting to the game, the
  never-forward rule and form for all 45 game types, EULA enforcement for every game that requires
  it, player-list parsers (Minecraft, ARK, Squad), the 7 Days to Die commented-setting fix, Terraria's
  no-connect rule, command names. Tests run against a throwaway data folder.
- Checked that they catch real bugs: with the 7 Days to Die and Terraria fixes undone in a scratch
  copy, exactly those two tests failed.
- `tools/prepush-check.sh` now runs the tests; CONTRIBUTING asks for a test with every bug fix.

## 2026-10-16 — "Keeps crashing" warning

- systemd restarts a crashed server by itself, so a crash-looping server showed "running" most of
  the time (19 restarts went unnoticed in testing). The poller now watches each server's automatic
  restart counter (`NRestarts`): two or more automatic restarts within 15 minutes, or a server waiting
  to be restarted, puts a red "Keeps crashing — … Open Logs to see why." on its card and sends one
  alert through the configured channel. A normal restart by the owner resets it. Tested on the VM by
  killing a Terraria server twice: no warning after one crash, warning after the second, cleared by
  a normal restart. ARK's crash on a requested stop is not an automatic restart, so it doesn't count.

## 2026-10-16 — Getting started guide; WorldCradle was crashing Terraria servers

- **`docs/GETTING_STARTED.md`** with six screenshots taken on the test VM's WorldCradle (public page,
  dashboard, Games, Add a server, Can friends connect?, phone). The VM was given a placeholder public
  address first so no real address appears.
- **Bug found while taking them: WorldCradle crashed Terraria servers.** The dashboard's "answering?"
  check opened a TCP connection to the game and closed it straight away; Terraria's server dies on
  that (`ObjectDisposedException` in `Netplay.UpdateConnectedClients`), so a WorldCradle-managed
  Terraria server crashed and restarted every minute or two (19 times in the test). The short tests
  done earlier ended before it showed. Fix: local checks now ask the operating system whether the
  port is listening (`monitor.port_listening`, no contact with the game) — used for Terraria,
  Minecraft Java, Bedrock and Windrose; *Can friends connect?* no longer tests Terraria by connecting
  (`survives_connect_test = False`). Verified: 5 minutes of polling plus a *Can friends connect?*
  check, no crash. The card had said "running" throughout — recorded in the roadmap.
- **Phone layout:** the top menu ran off the right edge (Settings and Log out unreachable without
  sideways scrolling) — it now wraps onto a second line.
- "Ark: Survival Evolved" → "ARK: Survival Evolved".
- **Testing from outside the home, made concrete:** "try from a phone on mobile data" didn't say how to
  test a game. *Can friends connect?*, the Getting started guide, the testing steps and the test-report
  form now say: turn on the phone's **Mobile Hotspot**, connect the computer you play on to it (not
  to the home Wi-Fi), and join with the public address — exactly how a friend outside connects.

## 2026-10-16 — Version number and release notes

- `VERSION` (0.2.0-dev) read by `app/version.py`; `worldcradle version` shows it with the git build,
  and the dashboard footer shows it to signed-in admins only — the public page doesn't reveal the
  version, so it can't be used to look up known problems.
- `CHANGELOG.md`: user-facing release notes (0.2.0 not yet released; 0.1.0 = private alpha), kept
  separate from this log.

## 2026-10-16 — Contributor files, backups and unban from the terminal

- GitHub issue forms (`.github/ISSUE_TEMPLATE/`): a **game test report** that asks exactly what was
  checked, a bug report, a game request; blank issues allowed; a link sends security reports to
  GitHub's private reporting. `CONTRIBUTING.md` (testing first, plain-language and internet-facing
  rules for code, no GPL dependencies, licence of contributions) and `SECURITY.md`.
- `worldcradle backup list <server>` and `worldcradle backup restore <server> <number>`: on the test VM a
  Terraria world was deliberately damaged (7 bytes), then restored byte-for-byte (same checksum);
  a safety copy of the damaged state was made first and the server restarted.
- `worldcradle unban <address>`: on the VM a test address was blocked in fail2ban and the command
  lifted it after one password prompt; it also clears the dashboard's own short lock-out.
- The `worldcradle` command no longer prints internal log lines on screen (they still go to the log
  files).

## 2026-10-16 — Ubuntu 26.04, uninstall, passwords on screen

- **Upgrade 24.04 → 26.04** on the test VM with WorldCradle installed (Python 3.12 → 3.14): on the
  first boot the dashboard rebuilt its Python environment by itself and came back — no help needed
  this time. V Rising (Wine 10) and Terraria ran; a clean install on 26.04 passed too.
- **`worldcradle uninstall`:** confirms, offers to stop and unregister the game servers (asking per
  server when players are online), removes the dashboard service, backup timer, certificate-renewal
  timer and the command, asks separately before deleting settings and backups, and never deletes
  games or saves; ends with a list of what's left and how to remove it. A bug on the first try
  (the closing summary read the settings after they had been deleted) was fixed and the test
  repeated: the game and both world files were kept, everything else was gone.
- **`worldcradle passwords`**, and the installer's last screen now shows the join password (new
  installs pick a random one).
- **Self-repair without internet** stops after a few seconds with a message naming both possible
  causes (no internet, or the python3-venv package missing).
- **Keep-alive 5 s → 30 s:** a client reusing an idle connection at the exact moment the server
  closed it got a dropped request (browsers retry, scripts may not). With the gevent worker idle
  connections are cheap; re-checked that 50 held connections still don't slow the dashboard.
- A Terraria card briefly shows "not answering" while the world is being generated — expected; it
  switches by itself once the port opens.

## 2026-10-15 — Ubuntu 24.04: upgrade survival and clean install

- **Upgrade test:** the test VM (WorldCradle installed) was upgraded 22.04 → 24.04.5 with
  `do-release-upgrade`. Afterwards the dashboard was stuck in a restart loop (`No module named
  'gunicorn'`) and the `worldcradle` command crashed: the Python environment was tied to Python 3.10,
  which the upgrade replaced with 3.12. (The same had happened once on the maintainer's server.)
- **Fix — self-repair:** `bin/worldcradle-ensure-venv` checks the environment and rebuilds it with the
  current Python (falling back to fetching pip when the venv module is missing). It runs before the
  dashboard starts (`ExecStartPre`, with a 15-minute start allowance) and from the `worldcradle`
  command, and setup.sh uses it too. On the upgraded VM, a restart rebuilt the environment and the
  dashboard was answering within 17 s.
- **Clean install on 24.04** (WorldCradle and every package it installed removed first): 82 s; setup
  code, sign-in, Terraria and V Rising (Wine 9) installed, run, removed, uninstalled; no Wine
  environment left behind.
- **Random game passwords:** a new install used to start with the example file's placeholder
  passwords — known to anyone who reads the repository. setup.sh now picks random ones (10-character
  join password, 20-character admin password, letters and digits only so every game accepts them).
- Quieter install: no certificate-generation noise; first-install wording for the environment step.
- The maintainer's own dashboard service got the same self-repair step.

## 2026-10-15 — First fresh-machine test (Ubuntu 22.04 desktop VM)

Installed from a downloaded copy on a clean Ubuntu 22.04.5 desktop VM (8 cores, 16 GB, 40 GB disk).
The install took 1 min 45 s; first-visit setup with the code, sign-in, the dashboard, installing,
running, messaging, saving, stopping and removing Terraria (Linux) and V Rising (Windows-only, under
Wine 6.0) all worked, as did the `worldcradle` command, the QR code and the CPU/RAM figures.
Problems found and fixed:
- A fresh Ubuntu desktop has **no curl**: the README's `curl … | bash` would fail → the README now
  uses `wget -qO- … | bash` (curl still mentioned), and get.sh says so.
- The installer's **internet check used curl** and so reported "no internet" on such a machine →
  now uses Python, which every Ubuntu has.
- A downloaded copy unpacks to `WorldCradle-main`, not `worldcradle`, and WorldCradle then runs from wherever
  it was unpacked → the README explains moving it to the home folder, and the installer warns when
  it is run from Downloads or /tmp.
- **Old Wine on 22.04** (6.0; our Windows-only servers were tested with Wine 10) → the installer
  warns; V Rising was confirmed to work with 6.0, so the warning says "some may not work".
- apt printed ~1,900 lines → the installer shows "Downloading and installing…" / "Done" and keeps
  the full output in a log file (shown only if something fails).
- setup.sh repeated an outdated, very long "get a setup code" command right before the installer's
  own final screen → removed when run from the installer; standalone it says `worldcradle setup-code`.
  pip's ~35 "Requirement already satisfied" lines → one "Python libraries ready." line.
- **Removing a Windows-only server left its Wine environment** (~1 GB) behind → it is now deleted
  with the server (saves are still left alone).

## 2026-10-15 — `worldcradle update`

- Updates WorldCradle from its repository: lists what's new, asks (or `--yes`), fast-forwards the code,
  installs the Python libraries, checks the new version loads (web app, every game type, pages),
  restarts the dashboard and waits for it to answer. If any step fails it resets to the previous
  version, reinstalls its libraries and restarts it. Refuses when the copy has local edits or
  commits that aren't published. Settings, passwords, servers and saves are never touched (they
  live outside the code).
- Tested in a sandbox (separate install, stand-in repository, throwaway dashboard on a spare port):
  already up to date; a good update; a broken update (rolled back, dashboard kept answering); local
  edits (refused). Not yet tested: a version that loads but then fails to start.

## 2026-10-15 — QR code for phones

- The installer's last screen and the new `worldcradle qr` command show a QR code of the dashboard's
  home-network address, so it can be opened on a phone by pointing the camera at it. Uses `segno`
  (BSD). Checked by decoding the code with an independent reader (zxing-cpp).

## 2026-10-15 — Installer checks the computer first

- `install.sh` now checks, before installing anything: operating system (Ubuntu 22.04+ / Debian 12+),
  64-bit Intel/AMD processor and AVX, memory, free disk space, background services (systemd for the
  user), whether port 8443 is free, and internet access. Each result is one plain line (✓ / ⚠ / ✗);
  any ✗ stops the install with the reason (`--force` overrides). Tested here (all ✓) and with
  stand-in tools simulating an ARM processor, a full disk, no systemd and a busy port.
- Roadmap: a *Packaging* plan (a `.deb` on GitHub Releases → a WorldCradle apt repository → possibly a
  Launchpad PPA).

## 2026-10-15 — Patreon support link

- The "Support the developer on Patreon" link (https://www.patreon.com/KeithDude) is switched on in
  the dashboard footer; the README gains a "Support the project" section and GitHub a *Sponsor*
  button via `.github/FUNDING.yml`.

## 2026-10-15 — Dashboard outage: connection exhaustion fixed

- **What happened:** the live dashboard stopped answering while its service still showed "running".
  A single internet address (most likely a scanner) held 8 connections open without sending a
  request. The web server ran 8 threads, one connection each, with no time limit for a silent
  client, so nobody else could get in. Reproduced locally: 8 connections that complete the TLS
  handshake and then go quiet, or send a request very slowly, lock everyone out.
- **Fix:** gunicorn now uses the event-based **gevent** worker (`--worker-class gevent
  --worker-connections 1000 --keep-alive 5`), so idle and slow clients cost almost nothing.
  Verified with 300 silent and 300 slow connections held open: normal requests still answered in
  about 0.01 s. The whole app (sign-in, every admin page, background polling of the real servers,
  CPU/RAM figures) was exercised on a test copy before switching the live service.
- New dependencies: `gevent` (MIT) and `packaging` (Apache-2.0 / BSD).

## 2026-10-15 — Command line, simpler install, accurate CPU figures

- **`worldcradle` command** (`bin/worldcradle`, installed to `~/.local/bin` by setup): status, address,
  reset-password, setup-code, start/stop/restart of the dashboard,
  logs, servers, `server start|stop|restart|logs <server>` (asks first when players are online),
  backup, check, version, help. Reset-password tested end to end on a copy of the settings.
- **Installer:** no questions by default (it installs the optional extras too; `--ask` and
  `--minimal` change that); `get.sh` downloads WorldCradle and runs the installer in one line.
- **CPU figures:** the top bar says *Total CPU usage* (the whole computer). Each server's CPU is now
  its share of the whole computer, and its RAM is the total of all its processes, measured from the
  server's systemd control group (game servers are often several processes, e.g. under Wine). On the
  live machine the six servers' figures added up to about 6% against 8% total CPU usage.
- **Footer:** a link to the project, and an optional "Support the developer on Patreon" link that
  appears once `SUPPORT_URL` is set in `app/project.py` (only plain https addresses are accepted).
- Roadmap expanded (principles, milestones, install, command line, testing, dashboard, security);
  a C++ rewrite was considered and judged not worthwhile (see the roadmap).

## 2026-10-15 — Licence

- Licensed under the **PolyForm Noncommercial License 1.0.0** (`LICENSE.md`): free for any
  noncommercial use; commercial use needs the author's permission.
- Removed the only GPL-licensed dependency (the `rcon` package), whose licence could not be combined
  with a noncommercial licence. WorldCradle now has its own Source RCON client (`monitor.source_rcon`),
  used by the player lists, controls, the ARK stop helper and generated stop scripts. Checked on live
  ARK servers (player list, world save) and on Minecraft (player list, save, messages, long
  multi-part replies, graceful stop) with identical results to the old library.
- Remaining dependencies are BSD, MIT or Apache licensed.
- **Pre-push checks** (`tools/prepush-check.sh`, run automatically before every push): clean tree,
  code and pages load, no control port marked for forwarding, script syntax, no passwords or personal
  data in the repository, no GPL dependencies, dashboard answers. Anything not verified on a running
  server is raised with the maintainer before pushing.
- Verified the ARK stop path through the new RCON client with a real restart: the world saved and the
  map came back. ARK still exits with a crash (SIGABRT) right after saving, as it did before this
  change — recorded in the roadmap.
- Added [ROADMAP.md](ROADMAP.md), a living plan.

## 2026-10-14 — Documentation, port safety, clearer figures

- **Supported-games list moved into the documentation.** Each game is marked *Tested* (real players
  have played on it) or *Not Tested* (server-side testing only) in `docs/SUPPORTED_GAMES.md`, kept by
  hand. A short-lived in-dashboard badge was removed again: test status is project documentation, not
  part of the product, and it is not updated automatically from anyone's testing.
- **Control ports are never forwarded.** Every admin console (RCON) and other control port is marked
  "keep closed, never forward" on the Add-a-server form, listed under "Never forward these" in *Can
  friends connect?*, and explained in plain words in `deploy/SETUP.md`. None is ever included in the
  ports-to-forward list.
- **System figures:** memory is labelled *RAM*, sizes use binary units (1 GB = 1024³ bytes), the top
  bar gains *Storage used*, and the load figure is explained.
- **Palworld launch flags:** Palworld's documentation for v1.0 suggests dropping
  `-useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS`. Tried on a live server: it then never
  finished loading its world (admin console never came up). The flags stay.
- Prepared for publishing: README rewritten, development log and supported-games list added, the
  OS-maintenance helper no longer contains a hard-coded user name.

## 2026-10-13 — Documentation audit of every game

Every game setup was compared with the publisher's own dedicated-server documentation (several
official sites refuse automated reading, so some findings came from community wikis and were treated
as leads to test). Confirmed problems, fixed and re-tested on real installs:

- **Space Engineers** — every restart reloaded the blank starting world, discarding the saved one
  (`-ignorelastsession`). Removed; restarts now continue the saved world.
- **7 Days to Die** — the save-folder setting sits inside a comment in the shipped config file, so it
  never took effect and worlds were saved outside the server's folder (backups were empty). Commented
  settings are now replaced with live ones.
- **StarRupture** — the engine's remote-control web interface answered on the game port with no
  login. It is now switched off, only UDP is forwarded, and the session starts from `DSSettings.txt`
  automatically. Its passwords use an encrypted format only the game can write, so the shared join
  password cannot be applied (stated in the Add form).
- **Minecraft Java** — PvP and command blocks are game rules since 1.21.9, no longer
  `server.properties` settings; they are now set through the admin console on first start.
- **Eco** — stopped with SIGTERM (the documented save-and-exit) instead of SIGINT; admin console bound
  to this computer only.
- **VEIN** — Steam library link added (its connection to Steam never started without it); several
  admins now use the documented `+` syntax; settings verified through the server's own status.
- **ARK: Survival Ascended** — admin password moved to the last launch option as documented;
  "crossplay off" now means PC only. Stopping saves the world but takes about 2½ minutes under Wine.

Changed to match the documentation but not yet confirmed with a player: Factorio admin list file,
per-server Terraria ban list, Squad / Squad 44 ports and Squad 44's password setting, Don't Starve
Together Caves shutdown and home-network port range, Palworld clean stop for new servers, ARK: Survival
Evolved crossplay address, Stationeers player limit, plus many corrections to form wording and limits.

Still unresolved: Dragonwilds' mandatory admin password (the server strips the obvious setting);
Astroneer may need Wine 10.6+ for players to join; s&box cannot start its Steam session (not added).

## 2026-10-13 — EULAs and Windows-only games

- **Licence terms:** a game's EULA is a property of its game type. Where the terms cover the server
  itself, the Add-a-server form requires a tick (with a link) and the acceptance is written to the
  audit log; where the publisher only has terms for the game, a link is shown. The Games panel notes
  that Steam downloads fall under the Steam Subscriber Agreement.
- **Windows-only servers through Wine:** SCUM, Astroneer, Voyagers of Nera, Windrose and StarRupture
  added (shared `winegames.py` base). Windrose and s&box first failed with "illegal instruction"; the
  cause was a virtual CPU without AVX — setting the VM's CPU type to *host* fixed Windrose.
- Minecraft Java and SCP: Secret Laboratory finished and tested once their EULAs were accepted.

## 2026-10-12 — Many more games, ease of use, security review

- **Add-a-server form matches each game's real options** (typed fields: checkboxes, lists, number
  ranges), and every game has its own port boxes (blank = automatic).
- **Shared ports with a clear warning:** a server may reuse another's ports on purpose (only one can run
  at a time); the form explains this before allowing it.
- **Security review** for an internet-facing dashboard: content-security policy with per-response
  nonces, secure cookies, CSRF on every change, sessions tied to the password, atomic config writes,
  safe backup restore, fail2ban support.
- **Ease of use for non-technical owners:** one-step `install.sh`, first-run setup code, a Getting
  started checklist, game installs from the dashboard, *Can friends connect?* with router instructions,
  and an optional free HTTPS certificate.
- **Games added** (one at a time, each installed, started on spare ports, stopped and uninstalled):
  Don't Starve Together, Minecraft (Java and Bedrock), Terraria, 7 Days to Die, Project Zomboid, Rust,
  Factorio, Counter-Strike 2, Garry's Mod, Left 4 Dead 2, Unturned, Core Keeper, Enshrouded, V Rising,
  Conan Exiles, Sons of the Forest, ARK: Survival Ascended, Space Engineers, Icarus; then Team
  Fortress 2, Necesse, Barotrauma, Insurgency: Sandstorm, Killing Floor 2, Arma Reforger, HumanitZ,
  Soulmask, RuneScape: Dragonwilds, Stationeers, Squad, Squad 44, Eco, VEIN.
- **Not added, with reasons:** Arma 3 and DayZ (need a Steam account that owns the game), The Isle
  (needs Epic credentials), Romestead (needs .NET 8, risk of save corruption), Euro Truck Simulator 2 /
  American Truck Simulator (need files exported from the game client), Farming Simulator 25 (needs a
  second paid licence).
- **Abiotic Factor** added (Windows server under Wine) including a player list read from its log.

## Earlier (2026-06 to 2026-09)

- First versions: monitoring and control of ARK, Palworld, Valheim and Satisfactory servers — status,
  players, start/stop/restart, backups and restore with automatic pre-restore snapshots, daily backups,
  alerts (Discord / ntfy / webhook), Steam update checks, launch-script editor, port pool.
- Weekly, player-aware OS maintenance via a root systemd timer (no sudoers rule), see
  `deploy/maintenance/install.md`.
