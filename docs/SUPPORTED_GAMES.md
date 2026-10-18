# Supported games

WorldCradle can install, create and run servers for the 45 games below, plus any other server
through **Custom service**.

**Tested** means real players have joined and played on a server run by WorldCradle.
**Not Tested** means the server has been tested on the server side only: it installs, starts, takes
its settings from the Add-a-server form and stops cleanly, but nobody has joined it from the game yet.
The maintainer doesn't own all of these games, so help is welcome (see *How to help test* below).

This list is maintained by hand. When a game is confirmed, update its row here and add an entry to
[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md).

| Game | Status | Server type | Download from | Still to confirm |
|---|---|---|---|---|
| 7 Days to Die | Not Tested | Linux native | Steam app 294420 | Joining; Saves landing in the server's own folder after play |
| Abiotic Factor | **Tested** | Windows server via Wine | Steam app 2857200 | — |
| ARK: Survival Ascended | Not Tested | Windows server via Wine | Steam app 2430930 · EULA tick required | Joining; Crossplay off really keeps consoles out; Stopping takes about 2½ minutes under Wine (the world is saved first, then it is closed) |
| ARK: Survival Evolved | **Tested** | Linux native | Steam app 376030 | Crossplay with Epic players (new servers now pass the public address); Automatic mod downloads |
| Arma Reforger | Not Tested | Linux native | Steam app 1874900 · EULA tick required | Joining; Progress kept after a restart; Xbox crossplay |
| Astroneer | Not Tested | Windows server via Wine | Steam app 728470 | Joining at all — may need a newer Wine (10.6+) for the game's encryption |
| Barotrauma | Not Tested | Linux native | Steam app 1026340 | Joining; Who can start rounds |
| Conan Exiles | Not Tested | Windows server via Wine | Steam app 443030 | Joining |
| Core Keeper | Not Tested | Linux native | Steam app 1963720 | Joining with the Game ID; Player list |
| Counter-Strike 2 | Not Tested | Linux native | Steam app 730 | Joining; Every mode with every map |
| Don't Starve Together | Not Tested | Linux native | Steam app 343050 · EULA tick required | Joining; Caves saving on stop; Home-network-only mode |
| Eco | Not Tested | Linux native | Steam app 739590 | Joining |
| Enshrouded | Not Tested | Windows server via Wine | Steam app 2278520 | Joining |
| Factorio | Not Tested | Linux native | factorio.com | Joining; In-game admins |
| Garry's Mod | Not Tested | Linux native | Steam app 4020 | Joining |
| HumanitZ | Not Tested | Linux native | Steam app 2728330 | Joining; Ping showing in the server browser |
| Icarus | Not Tested | Windows server via Wine | Steam app 2089300 | Joining; Server staying up for hours with nobody on |
| Insurgency: Sandstorm | Not Tested | Linux native | Steam app 581330 | Joining |
| Killing Floor 2 | Not Tested | Linux native | Steam app 232130 | Joining |
| Left 4 Dead 2 | Not Tested | Linux native | Steam app 222860 | Joining; Game mode taking effect; Max players |
| Minecraft: Bedrock Edition | Not Tested | Linux native | minecraft.net · EULA tick required | Joining from outside your home network; Two Bedrock servers at once; Player list |
| Minecraft: Java Edition | Not Tested | Linux native | mojang.com · EULA tick required | Joining; Whitelist keeps strangers out |
| Necesse | Not Tested | Linux native | Steam app 1169370 | Joining; Player list |
| Palworld | **Tested** | Linux native | Steam app 2394010 | New servers' save-and-shutdown on stop; PvP (all three settings) |
| Project Zomboid | Not Tested | Linux native | Steam app 380870 | Joining |
| RuneScape: Dragonwilds | Not Tested | Linux native | Steam app 4019830 | Joining; Admin password (the setting's real name is unknown) |
| Rust | Not Tested | Linux native | Steam app 258550 | Joining |
| Satisfactory | **Tested** | Linux native | Steam app 1690800 | — |
| SCP: Secret Laboratory | Not Tested | Linux native | Steam app 996560 · EULA tick required | Joining; Player names |
| SCUM | Not Tested | Windows server via Wine | Steam app 3792580 | Joining, and which port to type; Public listing |
| Sons of the Forest | Not Tested | Windows server via Wine | Steam app 2465200 | Joining |
| Soulmask | Not Tested | Linux native | Steam app 3017300 | Joining; Save-and-quit on stop |
| Space Engineers | Not Tested | Windows server via Wine | Steam app 298740 · EULA tick required | Joining; World kept after a restart with real builds |
| Squad | Not Tested | Linux native | Steam app 403240 · EULA tick required | Joining; Join password; Player list |
| Squad 44 | Not Tested | Linux native | Steam app 746200 | Joining; Join password |
| StarRupture | Not Tested | Windows server via Wine | Steam app 3809400 · EULA tick required | Joining; Loading the saved session after a restart |
| Stationeers | Not Tested | Linux native | Steam app 600760 | Joining; Progress kept after a restart |
| Team Fortress 2 | Not Tested | Linux native | Steam app 232250 | Joining |
| Terraria | Not Tested | Linux native | terraria.org | Joining; Per-server ban list |
| Unturned | Not Tested | Linux native | Steam app 1110390 | Joining with the Server Code |
| V Rising | Not Tested | Windows server via Wine | Steam app 1829350 | Joining |
| Valheim | **Tested** | Linux native | Steam app 896660 | — |
| VEIN | Not Tested | Linux native | Steam app 2131400 | Joining |
| Voyagers of Nera | Not Tested | Windows server via Wine | Steam app 3937860 | Joining (browser or join code); Join password |
| Windrose | Not Tested | Windows server via Wine | Steam app 4129620 | Joining with the invite code |

## How to help test

1. Install the game in WorldCradle (Games → Install) and add a server with the default settings.
2. Join it from the game — ideally once from your own home network and once from outside it.
   To test "outside" yourself: turn on your phone's **Mobile Hotspot**, connect the computer you
   play on to that hotspot (not to your home Wi-Fi), and join using the server's public address
   (shown under *Can friends connect?*). Or ask a friend to join from their home.
3. Check the points listed for that game above, plus these for every game:
   - you can join with the join password, and a wrong password is refused;
   - the server card shows you as a player (where the game supports a player list);
   - after building or changing something, **Stop** then **Start** the server and check it is still there;
   - the dashboard's Save / Message buttons (where shown) work.
4. Report what happened: the game, what worked, what didn't, and the server's log (card → Logs) if
   something failed. **Never include passwords.**

Never forward a server's admin console (RCON) or other control port, even for a test — see
[SETUP.md, section 6](../deploy/SETUP.md).
