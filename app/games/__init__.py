"""games — registry of supported game types.

Dispatch with `games.get(kind)` instead of `if kind == ...` branches.
"""
from __future__ import annotations

from games.abiotic import AbioticGame
from games.ark import ArkGame
from games.base import ActionError, GameType
from games.custom import CustomGame
from games.dst import DstGame
from games.minecraft import MinecraftGame
from games.palworld import PalworldGame
from games.satisfactory import SatisfactoryGame
from games.valheim import ValheimGame
from games.more import (ArmaReforgerGame, EcoGame, HumanitzGame, InsurgencyGame, Kf2Game,
                        ScpslGame, SoulmaskGame, Squad44Game, SquadGame, StationeersGame, VeinGame, DragonwildsGame)
from games.barotrauma import BarotraumaGame
from games.necesse import NecesseGame
from games.spaceengineers import SpaceEngineersGame
from games.icarus import IcarusGame
from games.winegames import AstroneerGame, NeraGame, ScumGame, StarRuptureGame, WindroseGame
from games.asa import AsaGame
from games.sotf import SotfGame
from games.conan import ConanGame
from games.vrising import VRisingGame
from games.enshrouded import EnshroudedGame
from games.bedrock import BedrockGame
from games.corekeeper import CoreKeeperGame
from games.unturned import UnturnedGame
from games.source import Cs2Game, GmodGame, L4d2Game, Tf2Game
from games.factorio import FactorioGame
from games.rust import RustGame
from games.zomboid import ZomboidGame
from games.sdtd import SdtdGame
from games.terraria import TerrariaGame

_TYPES: list[GameType] = [ArkGame(), PalworldGame(), ValheimGame(),
                          SatisfactoryGame(), AbioticGame(), DstGame(), MinecraftGame(), TerrariaGame(),
                          SdtdGame(),
                          ZomboidGame(),
                          RustGame(),
                          FactorioGame(),
                          Cs2Game(), GmodGame(), L4d2Game(), Tf2Game(),
                          UnturnedGame(),
                          CoreKeeperGame(),
                          BedrockGame(),
                          EnshroudedGame(),
                          VRisingGame(),
                          ConanGame(),
                          SotfGame(),
                          AsaGame(),
                          IcarusGame(),
                          SpaceEngineersGame(),
                          NecesseGame(),
                          BarotraumaGame(),
                          InsurgencyGame(), Kf2Game(), ArmaReforgerGame(), EcoGame(), HumanitzGame(), SoulmaskGame(), VeinGame(), DragonwildsGame(), StationeersGame(), SquadGame(), Squad44Game(), ScpslGame(), ScumGame(), AstroneerGame(), NeraGame(), WindroseGame(), StarRuptureGame(), 
                          CustomGame()]
BY_KIND: dict[str, GameType] = {g.kind: g for g in _TYPES}


def get(kind: str) -> GameType | None:
    return BY_KIND.get(kind)


def all_types() -> list[GameType]:
    return list(_TYPES)


def titles() -> dict[str, str]:
    """{card label: full game title} for section headings (pages + JSON feeds)."""
    return {g.label: g.title for g in _TYPES if g.title and g.title != g.label}


def join_steps() -> dict[str, list[str]]:
    """{game kind: "How to join" steps} for the pages (see GameType.join_steps)."""
    return {g.kind: list(g.join_steps) for g in _TYPES}


__all__ = ["get", "all_types", "titles", "join_steps", "GameType", "ActionError", "BY_KIND"]
