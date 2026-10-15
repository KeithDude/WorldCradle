# Development log

A running record of how GameDash has developed: what was built, what was found, and what is still
open. Newest entries first. Add an entry whenever something notable changes — a feature, a game, a
bug found and fixed, or a decision and the reason for it.

The list of games and their test status is kept separately in
[SUPPORTED_GAMES.md](SUPPORTED_GAMES.md).

---

## 2026-10-15 — Licence

- Licensed under the **PolyForm Noncommercial License 1.0.0** (`LICENSE.md`): free for any
  noncommercial use; commercial use needs the author's permission.
- Removed the only GPL-licensed dependency (the `rcon` package), whose licence could not be combined
  with a noncommercial licence. GameDash now has its own Source RCON client (`monitor.source_rcon`),
  used by the player lists, controls, the ARK stop helper and generated stop scripts. Checked on live
  ARK servers (player list, world save) and on Minecraft (player list, save, messages, long
  multi-part replies, graceful stop) with identical results to the old library.
- Remaining dependencies are BSD, MIT or Apache licensed.

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
