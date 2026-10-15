# Roadmap

Where GameDash is heading. This is a living document: update it whenever priorities change,
something is finished (tick it, move it to **Done** with the date, and record the details in
[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)), or a new idea comes up. Game-by-game test status is
tracked in [SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

Last updated: 2026-10-15

---

## What GameDash is for

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
- [x] One-line "get and install": `curl -fsSL …/get.sh | bash` downloads GameDash and runs the
      installer. *(2026-10-15 — works once the repository is public)*
- [ ] **Fresh-machine test** on a clean Ubuntu 24.04 and 26.04 (not the maintainer's machine),
      following only the README, timed, with every confusing moment written down and fixed.
- [ ] Installer checks before it starts: supported Linux version, enough disk space, enough memory,
      a 64-bit x86 processor with AVX (some servers need it), and explains anything missing in
      plain words.
- [ ] The installer's last screen: the address to open, the setup code, and a QR code for opening it
      on a phone.
- [ ] A short **Getting started** guide with screenshots (install → first server → friends join).

### Command line (`gamedash …`)
- [x] `gamedash` command installed for the owner: `status`, `address`, `reset-password`,
      `setup-code`, `start` / `stop` / `restart`, `logs`, `servers`,
      `server start|stop|restart|logs <server>` (asks first when players are online),
      `backup <server|all>`, `check`, `version`, `help`. *(2026-10-15)*
- [ ] `gamedash update` — update GameDash itself safely (download, run the checks, restart; roll
      back if the new version doesn't start).
- [ ] `gamedash backup list|restore <server> <backup>` from the terminal.
- [ ] `gamedash unban <address>` — lift a fail2ban block after someone mistypes the password
      (needs the admin password, like any system change).
- [ ] `gamedash uninstall` — remove GameDash cleanly, asking before touching any game or save.
- [ ] Tab completion for commands and server names.

### Public-release preparation
- [ ] **Community testing call:** publish the "How to help test" steps from SUPPORTED_GAMES.md and add
      GitHub issue templates (test report, bug report, game request).
- [ ] `CONTRIBUTING.md` (how to report tests and send changes, what the licence means for
      contributors), `SECURITY.md` (how to report a vulnerability privately).
- [ ] Screenshots in the README.
- [ ] **Support the developer (Patreon).** The dashboard footer link is built and stays hidden until
      the Patreon address is set in `app/project.py` (`SUPPORT_URL`). Still to do once the address is
      known: a "Support the project" section in the README and a GitHub *Sponsor* button
      (`.github/FUNDING.yml`). The link only ever opens the Patreon page — no tracking, nothing in
      the dashboard depends on it.
- [ ] Version numbers and release notes (a git tag per release; the dashboard and `gamedash version`
      show it).

### Confirm the fixes that need a player
Changes from the documentation audit that could not be checked without joining a game: Squad 44
join password, Factorio admins, Terraria ban list, Don't Starve Together Caves saving, Bedrock joins
from outside the home network, SCUM's join port, Arma Reforger progress after a restart, StarRupture
loading its save after a restart.

---

## Next — for 0.3

### Quality and testing
- [ ] **Automated tests** (there are none yet): port allocation, settings-file editing, player-list
      parsing, the RCON client, EULA enforcement, the never-forward rule. Run them in the pre-push
      check.
- [ ] A test run that installs, starts and stops every supported game on a spare machine, reporting
      what changed since the last run (games update and break things).
- [ ] Watch for game updates that change a server's settings or launch options.

### Dashboard
- [x] Total CPU usage at the top; each server's CPU as its share of the whole computer, and RAM, for
      all of its processes together; storage used; binary units throughout. *(2026-10-14/15)*
- [ ] Small history graphs per server: players, CPU and RAM over the last day.
- [ ] A clear "this server needs attention" banner (crashed, not answering, backups stale, update
      waiting) with one button to fix the common cases.
- [ ] Phone-friendly layout check on small screens.
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

### Security
- [x] Idle or slow connections can no longer lock everyone out of the dashboard (event-based web
      worker). *(2026-10-15)*
- [ ] Limit how many connections a single address may hold open, and show repeated offenders in
      the dashboard (the event worker absorbs them, but a cap is a second line of defence).
- [ ] Optional two-factor sign-in (authenticator app) for the dashboard.
- [ ] Automatic HTTPS certificate renewal check in `gamedash check` and on the dashboard.
- [ ] Periodic review against the "safe on the open internet" principle, with the findings logged.

---

## Open problems (need research or outside help)

- [ ] **RuneScape: Dragonwilds admin password** — the developer calls it mandatory, but the server
      deletes the obvious setting; the real setting name is unknown.
- [ ] **Astroneer under Wine** — community reports say players can only join with Wine 10.6 or
      newer (the game's connection encryption); Ubuntu currently ships 10.0.
- [ ] **StarRupture passwords** — stored in an encrypted form only the game client (or a third-party
      website) can produce, so GameDash cannot apply the shared password.
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
- [ ] A Debian/Ubuntu package (`apt install gamedash`) once installs are stable.
- [ ] Several machines in one dashboard (one GameDash, servers on more than one computer).
- [ ] Translations of the dashboard.

## Considered

- **Rewriting parts in C++** (2026-10-15): not worthwhile at this stage. GameDash spends almost all of
  its time waiting — on game servers, the network and the disk — not computing; the game servers
  themselves are what use the processor (the dashboard uses well under 1% of it). Python keeps the
  code short, safe from memory bugs on an internet-facing service, and easy for contributors to
  change. Revisit only if a measured bottleneck appears, and then only for that one piece.

## Not planned (decided)

- **Restricting the dashboard to the home network or a VPN** — GameDash is built to be safe when
  reachable from the internet; owners who want it private simply don't forward its port.
- **Automatic stop-when-empty / start-on-join** — investigated and deliberately not built.
- **Showing test status inside the dashboard** — test status is project documentation
  (SUPPORTED_GAMES.md), not part of the product.

## Done

- 2026-10-15 — `gamedash` command line; installer with no questions by default and a one-line
  get-and-install script; per-server CPU/RAM measured for all of a server's processes; licensed
  under PolyForm Noncommercial 1.0.0 (GPL dependency replaced by GameDash's own RCON client);
  pre-push checks; this roadmap.
- 2026-10-14 — Supported-games list and development log; never-forward rule for control ports in the
  form, the connection panel and the setup guide; RAM / storage figures in binary units.
- 2026-10-13 — Documentation audit of every game (three data-loss / security bugs fixed); EULA
  handling; Windows-only games through Wine.
- 2026-10-12 — 30+ games added; ease-of-use work for non-technical owners; security review.
