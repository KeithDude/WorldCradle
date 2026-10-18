# Roadmap

Where WorldCradle is heading. This is a living document: update it whenever priorities change,
something is finished (tick it, move it to **Done** with the date, and record the details in
[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)), or a new idea comes up. Game-by-game test status is
tracked in [SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

Last updated: 2026-10-15

---

## What WorldCradle is for

- **Anyone can run it.** Someone with almost no technical knowledge should be able to install it,
  add a game server and have friends playing — without editing files or typing commands, unless
  they want to.
- **Safe on the open internet.** The dashboard is expected to be reachable from anywhere, so it has to
  hold up to that. Control ports are never forwarded.
- **Honest.** A game is only called *Tested* once real players have played on it; known problems
  are written down, not hidden.
- **Nothing is pushed or released unverified.**

## Milestones

| Milestone | Goal | State |
|---|---|---|
| **0.1 — Private alpha** | Works on the maintainer's own machine with real players on a few games | ✅ reached |
| **0.2 — Public preview** | The repository is public; anyone can install it with one command; testers can report results | in progress |
| **0.3 — Community-tested** | Most popular games confirmed *Tested* by players; automated tests; easy updates | planned |
| **1.0 — Stable** | Clean installs on supported Linux versions, no known data-loss issues, documented upgrade path | planned |

---

## Now — for 0.2 (public preview)

### Installing should be as simple as possible
- [x] One-step installer that asks **no questions** by default (only the computer's password); `--ask`
      to choose extras, `--minimal` to skip them. *(2026-10-15)*
- [x] One-line "get and install": `curl -fsSL …/get.sh | bash` downloads WorldCradle and runs the
      installer. *(2026-10-15 — works once the repository is public)*
- [x] **Fresh-machine test, Ubuntu 22.04 desktop** — full install in 1 min 45 s, first-visit setup,
      sign-in, installing / running / removing a Linux game (Terraria) and a Windows-only one
      (V Rising, under 22.04's Wine 6.0) all worked. Seven problems found and fixed (see the
      development log). *(2026-10-15)*
- [x] **Ubuntu 24.04:** upgrading 22.04 → 24.04 with WorldCradle installed broke it (Python 3.10 → 3.12)
      → WorldCradle now repairs its Python environment by itself; then a clean install on 24.04 passed
      the same tests as 22.04. *(2026-10-15)*
- [x] **Ubuntu 26.04:** upgrading 24.04 → 26.04 (Python 3.12 → 3.14) — WorldCradle repaired itself on
      the first boot with no help; V Rising (Wine 10) and Terraria ran; clean install passed.
      *(2026-10-16)*
- [ ] A Debian 12 / 13 run.
- [ ] Repeat the fresh-machine test with the one-line installer once the repository is public.
- [x] Installer checks before it starts: operating system, 64-bit Intel/AMD processor (and AVX),
      memory, disk space, background services (systemd), the dashboard's port, internet — each
      explained in plain words; serious problems stop the install (`--force` to go ahead anyway).
      *(2026-10-15)*
- [x] The installer's last screen: the address to open, the setup code, and a QR code for opening it
      on a phone (also `worldcradle qr`). *(2026-10-15)*
- [x] **Getting started** guide with screenshots: `docs/GETTING_STARTED.md`. *(2026-10-16)*

### Command line (`worldcradle …`)
- [x] `worldcradle` command installed for the owner: `status`, `address`, `reset-password`,
      `setup-code`, `start` / `stop` / `restart`, `logs`, `servers`,
      `server start|stop|restart|logs <server>` (asks first when players are online),
      `backup <server|all>`, `check`, `version`, `help`. *(2026-10-15)*
- [x] `worldcradle update` — update WorldCradle itself safely: shows what's new, downloads it, installs
      libraries, checks the new version loads, restarts, and puts the old version back if anything
      fails. *(2026-10-15)*
- [x] `worldcradle backup list|restore <server> <backup>` from the terminal. *(2026-10-16)*
- [x] `worldcradle unban <address>` — lifts a fail2ban block (asks for the admin password) and the
      dashboard's own short lock-out. *(2026-10-16)*
- [x] `worldcradle uninstall` — removes WorldCradle step by step; stops and unregisters the game servers
      after asking (checking for players), asks separately about settings and backups, never
      deletes games or saves, and lists what's left. *(2026-10-16)*
- [x] The installer's last screen shows the (random) join password; `worldcradle passwords` shows both
      game passwords any time. *(2026-10-16)*
- [ ] Tab completion for commands and server names.

### Public-release preparation
- [x] GitHub issue forms: game test report, bug report, game request; security reports routed to
      private reporting. *(2026-10-16)*
- [x] `CONTRIBUTING.md` and `SECURITY.md`. *(2026-10-16)*
- [x] GitHub's *private vulnerability reporting* turned on, so the link in SECURITY.md works.
      *(2026-10-16)*
- [ ] **Community testing call** once the repository is public.
- [ ] Screenshots in the README.
- [x] **Support the developer (Patreon):** link in the dashboard footer, a "Support the project"
      section in the README, and a GitHub *Sponsor* button (`.github/FUNDING.yml`). *(2026-10-15)*
- [x] Version number (`VERSION`, now 0.2.0-dev) shown by `worldcradle version` and in the dashboard
      footer for signed-in admins (hidden from the public page); release notes in `CHANGELOG.md`.
      *(2026-10-16)*
- [ ] **Before the public release: remove the update test switch** (`WORLDCRADLE_RELEASES_URL` in
      `app/release.py` and `tools/test-releases.py`), used only to test updates before anything is
      published. The release workflow refuses to build while it's still there.
- [ ] When 0.2.0 is released: set `VERSION` to 0.2.0, date the CHANGELOG entry, commit, then
      `git tag v0.2.0 && git push origin v0.2.0` — the release workflow builds and publishes the
      package. Then check the one-line installer and `worldcradle update` against the real release.

### Confirm the fixes that need a player
Changes from the documentation audit that could not be checked without joining a game: Squad 44
join password, Factorio admins, Terraria ban list, Don't Starve Together Caves saving, Bedrock joins
from outside the home network, SCUM's join port, Arma Reforger progress after a restart, StarRupture
loading its save after a restart.

---

## Next — for 0.3

### Quality and testing
- [x] **Automated tests** (`tests/`, 113 so far): port allocation, the RCON client against a fake
      server, the never-forward rule and form for every game, EULA enforcement, player-list parsers,
      the 7 Days to Die settings fix, Terraria's no-connect rule, command names. Run by the pre-push
      check. *(2026-10-16)*
- [ ] More tests: settings-file writers for each game, backup/restore, the update rollback, the
      dashboard's pages and sign-in.
- [ ] A test run that installs, starts and stops every supported game on a spare machine, reporting
      what changed since the last run (games update and break things).
- [ ] Watch for game updates that change a server's settings or launch options.

### Code clean-up, part 2
Part 1 (dead code, duplicated checks, outdated comments, bugs found on the way) is done — see the
development log, 2026-10-16. Part 2 is checked by **recordings of what every game writes when a
server is created** (`tests/provision_snapshots.py`): launch scripts, settings files, their
permissions, and the settings after a password change. A step that leaves them identical changes
nothing for any game; a step that changes them needs trying on real servers.
- [x] **Safety net:** the recordings above, run by the tests. *(2026-10-17)*
- [x] One way to put the shared passwords into a game's settings at start
      (`common.password_sync` / `common.json_password_sync`) instead of ~20 hand-written snippets
      and three half-shared helpers — every game's settings come out the same. *(2026-10-17)*
- [x] Game form limits written once, in the form field (`GameType.option`), instead of being
      repeated in the check and the settings writer (139 copies). *(2026-10-17)*
- [x] One helper for private settings files (`common.write_private`, 21 copies) — which also made
      Squad's and Squad 44's password files private; one `empty_probe()` (33 copies). *(2026-10-17)*
- [x] One game per file: `more.py` (12 games) and `winegames.py` (5) split; `winegames.py` keeps only
      the shared Wine base; the game registry lists one game per line. *(2026-10-17)*
- [ ] Smaller shared helpers still to do: player lists, "send an admin command or say why not",
      downloads (Terraria, Factorio, Bedrock, Minecraft each have their own); Palworld's two
      settings rewriters become one.
- [ ] Move the older game types onto the shared `SimpleGame` / `WineGame` bases where they fit.
      This **changes their launch scripts** (stop timing, folders), so each one needs a real
      create-start-join-stop test — do it game by game, alongside testing those games.
- [x] One `systemd` module (`run`, `check`, `is_active`, `is_enabled`, `show`) instead of six
      ways of calling `systemctl`, each with its own timeouts and error handling. *(2026-10-17)*
- [x] One background-job helper (`jobs.Job`) instead of four copies (game installs, copying an install
      for a new server, game updates, the certificate request). *(2026-10-17)*
- [x] `app.js`: one window helper instead of six hand-built ones (every window now closes on
      Escape, a click outside or ✕, and is announced as a dialog), one "players are online —
      continue?" step instead of five, the card buttons in one table. *(2026-10-17)*
- [x] Each game declares its own "How to join" steps and its in-game buttons (Save, Message, Chat)
      come from what the game supports, instead of game names written into `app.js` — which also
      gave Terraria and other console games the Save / Message buttons they were missing.
      *(2026-10-17)*
- [x] The page's code split into modules by job (`app/static/js/`: core, servers, public, admin,
      server-actions, games-panel, settings, backups); each page loads only its own, with no build
      step. The pre-push check parses every module and checks every import. *(2026-10-17)*
- [x] No inline styles: all moved into the stylesheet, so the security policy no longer allows
      `'unsafe-inline'` styles (a test keeps it that way). *(2026-10-17)*

### Dashboard
- [x] Total CPU usage at the top; each server's CPU as its share of the whole computer, and RAM, for
      all of its processes together; storage used; binary units throughout. *(2026-10-14/15)*
- [ ] Small history graphs per server: players, CPU and RAM over the last day.
- [ ] A clear "this server needs attention" banner (crashed, not answering, backups stale, update
      waiting) with one button to fix the common cases.
- [x] **"Keeps crashing" warning** on a server's card (and one alert) when it restarts itself twice
      within 15 minutes — a crash-looping server used to show plain "running". *(2026-10-16)*
- [x] Phone layout check: the top menu ran off the screen — now wraps. *(2026-10-16)*
- [ ] Optional second dashboard account with limited rights (start/stop only, no settings).

### Servers and games
- [ ] **ARK maps report "failed" on every stop.** The ARK server crashes on exit (SIGABRT) right
      after saving, so the stop looks like a failure even though the world was saved. Treat that
      exit as normal, once confirmed it never hides a real failure.
- [ ] **Clean shutdown for more games:** V Rising (its `shutdown` console command), Space Engineers
      (the documented `taskkill` doesn't work under Wine), Soulmask, HumanitZ, Conan Exiles.
- [ ] **Unturned has no autosave** — save it on a timer from the dashboard.
- [ ] **Palworld's admin console (RCON) is deprecated** by its developer — move player lists and
      controls to its REST API before RCON is removed. (Removing Palworld's
      `-useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS` broke world loading on a live
      server; keep them unless re-tested.)
- [ ] **Library checks:** declare the system libraries some servers need (32-bit libraries for
      Garry's Mod / Left 4 Dead 2, libcurl-gnutls for Don't Starve Together, libatomic/libpulse for
      Valheim, glibc 2.40+ for Stationeers) so the Games panel says what's missing before an install
      fails.
- [ ] Left 4 Dead 2: full campaign list, survival-only maps, check whether "max players" works.
- [ ] Killing Floor 2: declare its Steam port; switch on web admin or drop that port.
- [ ] Scheduled restarts per server (several games recommend a daily restart), skipped while
      players are online.
- [ ] Mod support beyond Valheim and ARK where games have an official mod system.

### Alerts and notifications
- [x] **Each alert service checked against its own documentation** and fixed where it differed
      (Matrix room IDs, email SSL port and headers, Telegram/Matrix/Slack error reasons, Discord
      mentions, Slack escaping, Teams card, ntfy titles, retry on "too many"). *(2026-10-16)*
- [x] **ntfy and Gotify tested against the real servers** (their official releases, run privately on
      the test VM): test / down / recovered messages arrive with the right titles (accents and emoji
      kept), priorities and tags; a protected ntfy topic refuses a missing or wrong token, Gotify a
      wrong token, each with a plain message. *(2026-10-17)*
- [ ] **Test the alerts end to end with real accounts.** Each service is tested against stand-in
      servers, and the Settings page was tried in a browser against a local receiver — but no message
      has yet reached a real Discord / Telegram / email / Slack / Teams / Pushover / ntfy / Gotify /
      Matrix account. For each: the Test button, a server going down and recovering, a server that
      keeps crashing, a failed backup. Confirm each message arrives, reads clearly, and isn't sent
      twice. *(Needs the owner's accounts.)*
- [x] **Popular notification services**, each with a simple form and plain help: Discord, Telegram,
      email, Slack, Microsoft Teams, Pushover, ntfy, Gotify, Matrix, generic webhook. *(2026-10-16)*
- [x] Several destinations at once, each with its own **Test** button showing sent / the reason it
      failed. *(2026-10-16)*
- [x] `worldcradle test-alert`. *(2026-10-16)*

### Security
- [x] Idle or slow connections can no longer lock everyone out of the dashboard (event-based web
      worker). *(2026-10-15)*
- [ ] Limit how many connections a single address may hold open, and show repeated offenders in
      the dashboard (the event worker absorbs them, but a cap is a second line of defence).
- [ ] Optional two-factor sign-in (authenticator app) for the dashboard.
- [ ] Automatic HTTPS certificate renewal check in `worldcradle check` and on the dashboard.
- [ ] Periodic review against the "safe on the open internet" principle, with the findings logged.

---

## Packaging — making WorldCradle a "real" package

Goal: install and update WorldCradle like any other program, with no scripts to download.
**Priority for going public** (2026-10-16): the package and the install/update process must be
right before the repository is made public.

1. [x] **`.deb` package** — `tools/build-deb.sh` → `worldcradle_<version>_all.deb` + `.sha256`.
       Program in `/usr/lib/worldcradle`, `worldcradle` command in `/usr/bin`; system packages declared
       from `deploy/packages.conf` (WorldCradle's own needs as Depends, game libraries and extras as
       Recommends); each account's Python libraries built by `worldcradle setup` from
       `requirements.lock` (pinned, checksum-verified) in `~/.local/share/worldcradle/venv`; an upgrade
       restarts every account's dashboard; removal stops them and keeps all data. *(2026-10-16)*
   - [x] `worldcradle setup` (same setup as `install.sh`), `worldcradle update` installs the newest
         release's package after checking its checksum and rolls back to the previous release if
         the new one doesn't answer; `worldcradle uninstall` and `worldcradle version` know about the
         package; `get.sh` installs the package when a release exists. *(2026-10-16)*
   - [x] Tested on the VM: the package's files run as a package install would (libraries built in
         the home folder, dashboard and backup services, every command). *(2026-10-16)*
   - [x] **Tested with apt for real** on the Ubuntu 26.04 VM: `apt install`, `worldcradle setup`
         (libraries in the home folder), `worldcradle update` to a newer package (dashboard restarted
         by the package), a broken update rolled back to the previous version by itself,
         `apt remove` (dashboard stopped, settings and game server kept), reinstall + setup picked
         up the same settings and servers. *(2026-10-16)*
   - [x] GitHub Actions: tests, unused-code check and a package build on every push
         (`.github/workflows/tests.yml`); pushing a tag `v<version>` checks VERSION and CHANGELOG
         agree, builds the package and creates the release with it, its checksum and the
         CHANGELOG notes (`release.yml`). The tests workflow passes on GitHub (first run
         2026-10-17); the release workflow runs for the first time with the first tag. *(2026-10-16)*
   - [ ] **Sign releases** (beyond the checksum, which only proves the download is complete): sign
         the package / checksum file so `worldcradle update` and `get.sh` can tell it came from the
         maintainer even if GitHub were compromised.
   - [ ] A desktop shortcut ("WorldCradle") that opens the dashboard, and running `worldcradle setup` for
         you when the package is installed from the Ubuntu App Center (no terminal at all).
2. [ ] **WorldCradle apt repository** (signed, hosted on GitHub Pages or similar) — then installing is
       `apt install worldcradle` after adding the repository once, and updates arrive with the
       computer's normal system updates (`apt upgrade`).
3. [ ] **Launchpad PPA** (`sudo add-apt-repository ppa:…/worldcradle`) — the most familiar route for
       Ubuntu users; Launchpad builds from source, which takes more packaging work.

Things a package has to get right: WorldCradle runs as a *user* service (not as root), its data lives in
the user's home folder and must survive upgrades and removal, the `worldcradle update` command and the
package manager must not fight over updates, and the noncommercial licence must be shown.
Not a good fit: Snap and Flatpak (sandboxed apps can't manage background services and game servers
the way WorldCradle needs). A Docker image is possible later for people who prefer containers, but game
servers in containers add networking and storage steps that work against the "easy for anyone" goal.

## Open problems (need research or outside help)

- [ ] **RuneScape: Dragonwilds admin password** — the developer calls it mandatory, but the server
      deletes the obvious setting; the real setting name is unknown.
- [ ] **Astroneer under Wine** — community reports say players can only join with Wine 10.6 or
      newer (the game's connection encryption); Ubuntu currently ships 10.0.
- [ ] **StarRupture passwords** — stored in an encrypted form only the game client (or a third-party
      website) can produce, so WorldCradle cannot apply the shared password.
- [ ] **s&box** — the server can't start its Steam session; not added yet.
- [ ] **ARK: Survival Ascended** — stopping takes about 2½ minutes under Wine (the world is saved
      first).

## Later / ideas

- [ ] More games: Vintage Story (Linux, plain download), Hytale (own downloader and account), FiveM
      (free licence key), Path of Titans (token).
- [ ] Games that need a Steam account that owns them (Arma 3, DayZ): a safe "sign in with Steam"
      step — a security question in its own right.
- [ ] Euro Truck Simulator 2 / American Truck Simulator: an upload step for the files the game client
      exports.
- [ ] ARK automatic mod downloads done the documented way (Game.ini `[ModInstaller]`).
- [ ] **A real package** — see *Packaging* below.
- [ ] Several machines in one dashboard (one WorldCradle, servers on more than one computer).
- [ ] Translations of the dashboard.

## Considered

- **Rewriting parts in C++** (2026-10-15): not worthwhile at this stage. WorldCradle spends almost all of
  its time waiting — on game servers, the network and the disk — not computing; the game servers
  themselves are what use the processor (the dashboard uses well under 1% of it). Python keeps the
  code short, safe from memory bugs on an internet-facing service, and easy for contributors to
  change. Revisit only if a measured bottleneck appears, and then only for that one piece.

## Not planned (decided)

- **Restricting the dashboard to the home network or a VPN** — WorldCradle is built to be safe when
  reachable from the internet; owners who want it private simply don't forward its port.
- **Automatic stop-when-empty / start-on-join** — investigated and deliberately not built.
- **Showing test status inside the dashboard** — test status is project documentation
  (SUPPORTED_GAMES.md), not part of the product.

## Done

- 2026-10-15 — `worldcradle` command line; installer with no questions by default and a one-line
  get-and-install script; per-server CPU/RAM measured for all of a server's processes; licensed
  under PolyForm Noncommercial 1.0.0 (GPL dependency replaced by WorldCradle's own RCON client);
  pre-push checks; this roadmap.
- 2026-10-14 — Supported-games list and development log; never-forward rule for control ports in the
  form, the connection panel and the setup guide; RAM / storage figures in binary units.
- 2026-10-13 — Documentation audit of every game (three data-loss / security bugs fixed); EULA
  handling; Windows-only games through Wine.
- 2026-10-12 — 30+ games added; ease-of-use work for non-technical owners; security review.
