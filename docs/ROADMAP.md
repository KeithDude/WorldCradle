# Roadmap

Where GameDash is heading. This is a living document: update it whenever priorities change,
something is finished (move it to **Done** with the date, and record the details in
[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)), or a new idea comes up. Game-by-game test status is
tracked in [SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

Last updated: 2026-10-15

---

## Now — before making the repository public

- [ ] **Community testing call.** Most games are *Not Tested* with players. Publish the "How to help
      test" steps from SUPPORTED_GAMES.md and add a GitHub issue template for test reports
      (game, what worked, what didn't, log excerpt — no passwords).
- [ ] **Confirm the fixes that need a player.** Changes made from the documentation audit that could
      not be checked without joining: Squad 44 join password, Factorio admins, Terraria ban list,
      Don't Starve Together Caves saving, Bedrock joins from outside the home network, SCUM's join
      port, Arma Reforger progress after a restart, StarRupture loading its save after a restart.
- [ ] **Fresh-machine install test.** Run `install.sh` on a clean Ubuntu machine (not this one) and
      follow the Getting started checklist as a non-technical user would; fix anything confusing.
- [ ] **Public-release files:** `CONTRIBUTING.md` (how to report tests and send changes, what the
      licence means for contributors), `SECURITY.md` (how to report a vulnerability privately),
      screenshots for the README.
- [ ] **Automated tests.** There is no test suite yet; add unit tests for the parts that are easy to
      break (port allocation, settings-file editing, player-list parsing, the RCON client) and run
      them in the pre-push check.

## Next

- [ ] **ARK maps report "failed" on every stop.** The ARK server crashes on exit (SIGABRT) right
      after saving, so systemd marks the stop as failed even though the world was saved. Teach the
      unit to treat that exit as normal, once confirmed it never hides a real failure.
- [ ] **Clean shutdown for more games.** V Rising (`shutdown` over its admin console), Space
      Engineers (documented `taskkill` does not work under Wine), Soulmask, HumanitZ, Conan Exiles.
- [ ] **Unturned has no autosave** — add a periodic save from the dashboard.
- [ ] **Palworld's admin console (RCON) is marked deprecated** by the developer — move player lists
      and controls to its REST API before RCON is removed. Note: removing Palworld's
      `-useperfthreads -NoAsyncLoadingThread -UseMultithreadForDS` broke world loading on a live
      server; keep them unless re-tested.
- [ ] **Library checks for fresh machines.** Declare the system libraries some servers need
      (32-bit libraries for Garry's Mod / Left 4 Dead 2, libcurl-gnutls for Don't Starve Together,
      libatomic/libpulse for Valheim, glibc 2.40+ for Stationeers) so the Games panel says what is
      missing before an install fails.
- [ ] **Left 4 Dead 2:** full campaign list, survival-only maps, and check whether "max players"
      does anything.
- [ ] **Killing Floor 2:** declare its Steam port; either switch on web admin or drop the port.

## Open problems (need research or outside help)

- [ ] **RuneScape: Dragonwilds admin password** — the developer calls it mandatory but the server
      deletes the obvious setting; the real setting name is unknown.
- [ ] **Astroneer under Wine** — community reports say players can only join with Wine 10.6 or newer
      (the game's connection encryption); Ubuntu currently ships 10.0.
- [ ] **StarRupture passwords** — stored in an encrypted form only the game client (or a third-party
      website) can produce, so GameDash cannot apply the shared password.
- [ ] **s&box** — the server cannot start its Steam session; not added yet.
- [ ] **ARK: Survival Ascended** stop takes about 2½ minutes under Wine (the world is saved first).

## Later / ideas

- [ ] More games from the researched list: Vintage Story (Linux, plain download), Hytale (needs its
      own downloader and account), FiveM (needs a free licence key), Path of Titans (needs a token).
- [ ] Games that need a Steam account that owns them (Arma 3, DayZ): would need a safe
      "sign in with Steam" step — a security question in its own right.
- [ ] Euro Truck Simulator 2 / American Truck Simulator: an upload step for the files the game client
      exports.
- [ ] Automatic mod downloads for ARK done the documented way (Game.ini `[ModInstaller]`).

## Not planned (decided)

- **Restricting the dashboard to the home network or a VPN** — GameDash is built to be safe when
  reachable from the internet; owners who want it private simply don't forward its port.
- **Automatic stop-when-empty / start-on-join** — investigated and deliberately not built.

## Done

- 2026-10-15 — Licensed under PolyForm Noncommercial 1.0.0; GPL dependency replaced by GameDash's own
  RCON client; pre-push checks; this roadmap.
- 2026-10-14 — Supported-games list and development log; never-forward rule for control ports in the
  form, the connection panel and the setup guide; RAM / storage figures in binary units.
- 2026-10-13 — Documentation audit of every game (three data-loss / security bugs fixed); EULA
  handling; Windows-only games through Wine.
- 2026-10-12 — 30+ games added; ease-of-use work for non-technical owners; security review.
