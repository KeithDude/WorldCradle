# Development log

A running record of how GameDash has developed: what was built, what was found, and what is still
open. Newest entries first. Add an entry whenever something notable changes — a feature, a game, a
bug found and fixed, or a decision and the reason for it.

The list of games and their test status is kept separately in
[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

---

## 2026-10-15 — Ubuntu 24.04: upgrade survival and clean install

- **Upgrade test:** the test VM (GameDash installed) was upgraded 22.04 → 24.04.5 with
  `do-release-upgrade`. Afterwards the dashboard was stuck in a restart loop (`No module named
  'gunicorn'`) and the `gamedash` command crashed: the Python environment was tied to Python 3.10,
  which the upgrade replaced with 3.12. (The same had happened once on the maintainer's server.)
- **Fix — self-repair:** `bin/gamedash-ensure-venv` checks the environment and rebuilds it with the
  current Python (falling back to fetching pip when the venv module is missing). It runs before the
  dashboard starts (`ExecStartPre`, with a 15-minute start allowance) and from the `gamedash`
  command, and setup.sh uses it too. On the upgraded VM, a restart rebuilt the environment and the
  dashboard was answering within 17 s.
- **Clean install on 24.04** (GameDash and every package it installed removed first): 82 s; setup
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
Wine 6.0) all worked, as did the `gamedash` command, the QR code and the CPU/RAM figures.
Problems found and fixed:
- A fresh Ubuntu desktop has **no curl**: the README's `curl … | bash` would fail → the README now
  uses `wget -qO- … | bash` (curl still mentioned), and get.sh says so.
- The installer's **internet check used curl** and so reported "no internet" on such a machine →
  now uses Python, which every Ubuntu has.
- A downloaded copy unpacks to `GameDash-main`, not `gamedash`, and GameDash then runs from wherever
  it was unpacked → the README explains moving it to the home folder, and the installer warns when
  it is run from Downloads or /tmp.
- **Old Wine on 22.04** (6.0; our Windows-only servers were tested with Wine 10) → the installer
  warns; V Rising was confirmed to work with 6.0, so the warning says "some may not work".
- apt printed ~1,900 lines → the installer shows "Downloading and installing…" / "Done" and keeps
  the full output in a log file (shown only if something fails).
- setup.sh repeated an outdated, very long "get a setup code" command right before the installer's
  own final screen → removed when run from the installer; standalone it says `gamedash setup-code`.
  pip's ~35 "Requirement already satisfied" lines → one "Python libraries ready." line.
- **Removing a Windows-only server left its Wine environment** (~1 GB) behind → it is now deleted
  with the server (saves are still left alone).

## 2026-10-15 — `gamedash update`

- Updates GameDash from its repository: lists what's new, asks (or `--yes`), fast-forwards the code,
  installs the Python libraries, checks the new version loads (web app, every game type, pages),
  restarts the dashboard and waits for it to answer. If any step fails it resets to the previous
  version, reinstalls its libraries and restarts it. Refuses when the copy has local edits or
  commits that aren't published. Settings, passwords, servers and saves are never touched (they
  live outside the code).
- Tested in a sandbox (separate install, stand-in repository, throwaway dashboard on a spare port):
  already up to date; a good update; a broken update (rolled back, dashboard kept answering); local
  edits (refused). Not yet tested: a version that loads but then fails to start.

## 2026-10-15 — QR code for phones

- The installer's last screen and the new `gamedash qr` command show a QR code of the dashboard's
  home-network address, so it can be opened on a phone by pointing the camera at it. Uses `segno`
  (BSD). Checked by decoding the code with an independent reader (zxing-cpp).

## 2026-10-15 — Installer checks the computer first

- `install.sh` now checks, before installing anything: operating system (Ubuntu 22.04+ / Debian 12+),
  64-bit Intel/AMD processor and AVX, memory, free disk space, background services (systemd for the
  user), whether port 8443 is free, and internet access. Each result is one plain line (✓ / ⚠ / ✗);
  any ✗ stops the install with the reason (`--force` overrides). Tested here (all ✓) and with
  stand-in tools simulating an ARM processor, a full disk, no systemd and a busy port.
- Roadmap: a *Packaging* plan (a `.deb` on GitHub Releases → a GameDash apt repository → possibly a
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

- **`gamedash` command** (`bin/gamedash`, installed to `~/.local/bin` by setup): status, address,
  reset-password, setup-code, start/stop/restart of the dashboard,
  logs, servers, `server start|stop|restart|logs <server>` (asks first when players are online),
  backup, check, version, help. Reset-password tested end to end on a copy of the settings.
- **Installer:** no questions by default (it installs the optional extras too; `--ask` and
  `--minimal` change that); `get.sh` downloads GameDash and runs the installer in one line.
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
  with a noncommercial licence. GameDash now has its own Source RCON client (`monitor.source_rcon`),
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
