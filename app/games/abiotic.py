"""Abiotic Factor game type. The dedicated server is Windows-only and runs
under Wine. No RCON — who is online is read from the server log (Steam's
query always reports 0 players for this game). Options follow the official dedicated-server wiki
(launch parameters + SandboxSettings.ini)."""
from __future__ import annotations

import os
import re

import monitor
import registry
from games.base import ActionError, empty_probe, opt_choice, opt_float
from games.winegames import WineGame

EXE = "AbioticFactorServer-Win64-Shipping.exe"

# Every SandboxSettings.ini key with the game's default. A world's sandbox file
# is written in full (defaults + whatever the Add form changed) so nothing
# depends on how the game treats a partial file.
SANDBOX_DEFAULTS = {
    "GameDifficulty": "1", "HardcoreMode": "False", "LootRespawnEnabled": "False",
    "PowerSocketsOffAtNight": "True", "DayNightCycleState": "0",
    "DayNightCycleSpeedMultiplier": "1.0", "WeatherFrequency": "3", "SinkRefillRate": "1.0",
    "FoodSpoilSpeedMultiplier": "1.0", "RefrigerationEffectivenessMultiplier": "1.0",
    "EnemySpawnRate": "1.0", "EnemyHealthMultiplier": "1.0",
    "EnemyPlayerDamageMultiplier": "1.0", "EnemyDeployableDamageMultiplier": "1.0",
    "DamageToAlliesMultiplier": "0.5", "HungerSpeedMultiplier": "1.0",
    "ThirstSpeedMultiplier": "1.0", "FatigueSpeedMultiplier": "1.0",
    "ContinenceSpeedMultiplier": "1.0", "DetectionSpeedMultiplier": "1.0",
    "BonusPerkPoints": "0", "PlayerXPGainMultiplier": "1.0", "ItemStackSizeMultiplier": "1.0",
    "ItemWeightMultiplier": "1.0", "ItemDurabilityMultiplier": "1.0",
    "DurabilityLossOnDeathMultiplier": "0.1", "ShowDeathMessages": "True",
    "AllowRecipeSharing": "True", "AllowPagers": "True", "AllowTransmog": "True",
    "DisableResearchMinigame": "False", "DeathPenalties": "1", "FirstTimeStartingWeapon": "0",
    "HostAccessPlayerCorpses": "True", "StorageByTag": "True", "StructuralSupportLimit": "5",
    "AllowCharacterReset": "True", "BridgeSupports": "2", "HomeWorlds": "True",
    "InvisibleRadiation": "False", "BaseInventorySize": "12", "TaintedSinkWater": "False",
    "RadiationDealsDamage": "False", "PlayerFurnitureDestruction": "False",
    "AllowIronMode": "True", "EnemyAccuracy": "2", "ApocalypticAbilities": "False",
    "MaximizeEnemySpawns": "False",
}
DIFFICULTIES = [["1", "Normal"], ["2", "Hard"], ["3", "Apocalyptic"]]
DAY_NIGHT = [["0", "Normal cycle"], ["1", "Always day"], ["2", "Always night"]]
DEATH_PENALTIES = [["0", "Keep all items"], ["1", "Keep equipped items & hotbar"],
                   ["2", "Keep hotbar only"], ["3", "Keep equipped items only"],
                   ["4", "Lose all items including hotbar"], ["5", "All items are destroyed"]]
PLATFORMS = [["", "Crossplay (all platforms)"], ["PC", "Steam / PC only"],
             ["Playstation", "PlayStation only"], ["Xbox", "Xbox / Windows Store only"]]
# Add-form field -> (sandbox key, min, max, label) for the multiplier options
_MULTIPLIERS = {
    "xp_rate": ("PlayerXPGainMultiplier", 0.0, 3.0, "XP gain"),
    "friendly_fire": ("DamageToAlliesMultiplier", 0.0, 3.0, "Friendly-fire damage"),
    "enemy_health": ("EnemyHealthMultiplier", 0.75, 3.0, "Enemy health"),
    "enemy_damage": ("EnemyPlayerDamageMultiplier", 0.25, 3.0, "Enemy damage"),
    "enemy_spawn": ("EnemySpawnRate", 0.5, 3.0, "Enemy respawn rate"),
}

class AbioticGame(WineGame):
    join_steps = [
        "In Abiotic Factor: <b>Join a Game</b>, search the server list for <b>{server}</b>.",
        "Or connect directly by IP: <code>{address}</code>",
        "{password} Type it in the game's own password prompt — it can re-send a password "
        "remembered from another server.",
    ]
    kind = "abiotic"
    label = "Abiotic Factor"
    exe = "AbioticFactor/Binaries/Win64/" + EXE
    run_dir = "AbioticFactor/Binaries/Win64"
    install_gb = 3
    # its worlds live by name in the shared install's save folder (several servers, one install)
    own_folder = False
    ram_note = "about 2-4 GB of memory"
    about = "Co-op survival in a research facility. The server is Windows-only, so it runs through Wine."
    steam_app = 2857200
    update_script = "UpdateAbioticFactorServer.sh"
    # no admin console: no in-app controls
    extra_fields = [
        {"name": "world", "label": "World save name (blank = the key)", "placeholder": "Cascade",
         "help": "Letters/digits/underscores. An existing world of this name is loaded as-is."},
        {"name": "maxplayers", "label": "Max players (1-24; over 6 warns players on join)",
         "type": "number", "min": 1, "max": 24, "default": 6},
        {"name": "platform", "label": "Who can join", "type": "select", "options": PLATFORMS,
         "help": "Anything but crossplay launches with -PlatformLimited."},
        {"name": "lanonly", "label": "LAN only (not listed on the internet)", "type": "checkbox",
         "default": False,
         "help": "Launches with -LANOnly. The server then doesn't answer Steam queries, so "
                 "the dashboard can't show its player count."},
        {"name": "difficulty", "label": "Difficulty", "type": "select", "options": DIFFICULTIES,
         "default": "1"},
        {"name": "hardcore", "label": "Hardcore (one life; forces Apocalyptic)", "type": "checkbox",
         "default": False},
        {"name": "death_penalties", "label": "Death penalty", "type": "select",
         "options": DEATH_PENALTIES, "default": "1"},
        {"name": "daynight", "label": "Day / night", "type": "select", "options": DAY_NIGHT,
         "default": "0"},
        {"name": "loot_respawn", "label": "Loot respawns around the Facility", "type": "checkbox",
         "default": False},
        {"name": "power_off_night", "label": "Power sockets shut off at night", "type": "checkbox",
         "default": True},
    ] + [
        {"name": f, "label": f"{label} multiplier ({lo:g}-{hi:g}, blank = "
                             f"{SANDBOX_DEFAULTS[skey]})",
         "type": "number", "min": lo, "max": hi, "step": 0.05,
         "placeholder": SANDBOX_DEFAULTS[skey]}
        for f, (skey, lo, hi, label) in _MULTIPLIERS.items()
    ]
    provision_hint = ("Abiotic Factor — another world from the shared install (Windows server "
                      "under Wine), with its own ports, save folder and sandbox settings. The "
                      "join/admin passwords are the shared ones. The gameplay options here are "
                      "written to the world's sandbox settings file, which holds the rest of the "
                      "game's sandbox options too. First boot takes a minute longer while its "
                      "Wine environment (~1 GB) is created.")

    port_layout = [
        {"name": "game", "klass": "game", "start": 7784, "proto": "UDP", "forward": True, "label": "Game port (UDP)",
         "help": "The port players connect to. Forward it."},
        {"name": "query", "klass": "query", "start": 27030, "proto": "UDP", "forward": True, "label": "Steam query port (UDP)",
         "help": "Lists the server in the browser. Forward it."},
    ]

    @staticmethod
    def _world(spec) -> str:
        world = (spec.get("world") or "").strip() or spec["key"].replace("-", "_")
        if not re.match(r"^[A-Za-z0-9_]{1,30}$", world):
            raise ActionError("World save name must be 1-30 letters, digits or underscores.")
        return world

    @staticmethod
    def _saved(install) -> str:
        return os.path.join(install, "AbioticFactor", "Saved")

    @staticmethod
    def _sandbox_rel(key) -> str:
        return f"Config/WindowsServer/gamedash-{key}-Sandbox.ini"   # relative to Saved/

    def command(self, spec, ports, name, server_dir, install):
        key, world = spec["key"], self._world(spec)
        for s in registry.load_servers():
            if s.kind == self.kind and s.key != key and (s.world or "Cascade").lower() == world.lower():
                raise ActionError(f"World '{world}' is already used by {s.name} — two servers "
                                  f"writing one world would corrupt it.")
        platform = opt_choice(spec, "platform", [v for v, _ in PLATFORMS], "", "Who can join")
        flags = (f" -PlatformLimited={platform}" if platform else "") + \
                (" -LANOnly" if self.option(spec, "lanonly") else "")
        return (f"wine {EXE} \\\n"
                f"    -log -LOG=gamedash-{key}.log -useperfthreads -NoAsyncLoadingThread \\\n"
                f"    -MaxServerPlayers={self.option(spec, 'maxplayers')} -PORT={ports['game']} -QueryPort={ports['query']} \\\n"
                f'    -ServerPassword="$GAME_SERVER_PASSWORD" \\\n'
                f'    -AdminPassword="$GAME_ADMIN_PASSWORD" \\\n'
                f'    -SteamServerName="{name}" \\\n'
                f"    -WorldSaveName={world} -SandboxIniPath={self._sandbox_rel(key)}{flags} -tcp")

    def write_files(self, spec, ports, name, server_dir, install):
        sandbox = dict(SANDBOX_DEFAULTS)
        sandbox["GameDifficulty"] = self.option(spec, "difficulty")
        sandbox["HardcoreMode"] = str(self.option(spec, "hardcore"))
        sandbox["DeathPenalties"] = self.option(spec, "death_penalties")
        sandbox["DayNightCycleState"] = self.option(spec, "daynight")
        sandbox["LootRespawnEnabled"] = str(self.option(spec, "loot_respawn"))
        sandbox["PowerSocketsOffAtNight"] = str(self.option(spec, "power_off_night"))
        for field, (skey, lo, hi, label) in _MULTIPLIERS.items():
            n = opt_float(spec, field, None, lo, hi, label)
            if n is not None:
                sandbox[skey] = f"{n:g}" if "." in f"{n:g}" else f"{n:.1f}"
        path = os.path.join(self._saved(install), self._sandbox_rel(spec["key"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("[SandboxSettings]\n" + "".join(f"{k}={v}\n" for k, v in sandbox.items()))

    def log_file(self, server_dir, install):
        return os.path.join(self._saved(install), "Logs", f"gamedash-{os.path.basename(server_dir)}.log")

    def proc_pattern(self, spec, ports, server_dir):
        return f"-PORT={ports['game']} "

    def provision(self, spec: dict, ports: dict) -> dict:
        out = super().provision(spec, ports)
        world = self._world(spec)
        out.update(world=world,
                   save_root=os.path.join(self._saved(out["install_dir"]), "SaveGames", "Server", "Worlds", world))
        return out

    def probe(self, s) -> dict:
        out = empty_probe()
        # Steam A2S answers for reachability and the player limit, but its
        # player count stays 0 for this game — the roster comes from the log.
        info = monitor.a2s_info(s.query_port) if s.query_port else None
        if info is not None:
            out["reachable"] = True
            out["max_players"] = info["max_players"]
            out["players"] = info["players"]
        names = monitor.abiotic_players_from_log(s.log_path) if s.log_path else None
        if names is not None:
            out["players"] = max(len(names), out["players"] or 0)
            out["player_names"] = names
            out["player_detail"] = [{"name": n, "id": ""} for n in names]
        return out
