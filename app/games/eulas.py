"""eulas.py — the licence terms each game's publisher attaches to it.

One entry per game type: {"name", "url", "required"}.

  required=True   the server itself is covered by terms that whoever runs it
                  must accept: either the server refuses to start without it
                  (Minecraft, SCP: Secret Laboratory) or Steam lists a EULA on
                  the dedicated-server download itself. The Add-a-server form
                  shows a tick box, and no server is created without it.
  required=False  the publisher has terms for the game (listed on its Steam
                  page) but nothing specific to the server. The form and the
                  Games list show the link, for information.

The Steam entries are the "eulas" records Steam publishes for each app
(`steamcmd +app_info_print <app>`); the number in the link is the app they
are attached to. Games with no entry publish no terms there. Every Steam
download is also covered by the Steam Subscriber Agreement (STEAM_TERMS).
"""
from __future__ import annotations

STEAM_TERMS = "https://store.steampowered.com/subscriber_agreement/"


def _steam(name: str, doc: str, required: bool = False) -> dict:
    return {"name": name, "url": f"https://store.steampowered.com/eula/{doc}", "required": required}


_MINECRAFT = {"name": "Minecraft End User Licence Agreement", "url": "https://aka.ms/MinecraftEULA",
              "required": True}

EULAS: dict[str, dict] = {
    # -- the server itself is covered: a tick box is required -----------------
    "minecraft": _MINECRAFT,
    "bedrock": _MINECRAFT,
    "scpsl": {"name": "SCP: Secret Laboratory EULA", "url": "https://link.scpslgame.com/eula",
              "required": True},
    "armareforger": _steam("Arma Reforger Server EULA", "1874900_eula_1", True),
    "asa": _steam("ARK: Survival Ascended Dedicated Server EULA", "2430930_eula_0", True),
    "dst": _steam("Don't Starve Together Dedicated Server EULA", "343050_eula_0", True),
    "spaceengineers": _steam("Space Engineers Dedicated Server EULA", "298740_eula_0", True),
    "squad": _steam("Squad Dedicated Server EULA", "403240_eula_0", True),
    "starrupture": _steam("StarRupture Dedicated Server EULA", "3809400_eula_0", True),
    # -- the publisher's terms for the game: shown as a link -------------------
    "astroneer": _steam("ASTRONEER EULA", "361420_eula_0"),
    "conan": _steam("Conan Exiles EULA", "440900_eula_0"),
    "dragonwilds": _steam("RuneScape: Dragonwilds EULA", "1374490_eula_0"),
    "eco": _steam("Eco EULA", "382310_eula_1"),
    "enshrouded": _steam("Enshrouded EULA", "1203620_eula_0"),
    "gmod": _steam("Facepunch Terms of Service", "4000_eula_0"),
    "insurgency": _steam("Insurgency: Sandstorm EULA", "581320_eula_0"),
    "kf2": _steam("Killing Floor 2 EULA", "232090_eula_0"),
    "palworld": _steam("Palworld EULA", "1623730_eula_1"),
    "rust": _steam("Rust EULA", "252490_eula_0"),
    "sdtd": _steam("7 Days to Die EULA", "251570_eula_0"),
    "soulmask": _steam("Soulmask EULA", "2646460_eula_1"),
    "unturned": _steam("Unturned EULA", "304930_eula_1"),
    "vein": _steam("VEIN EULA", "1857950_eula_0"),
    "vrising": _steam("V Rising EULA", "1604030_eula_1"),
    "zomboid": _steam("Project Zomboid EULA", "108600_eula_1"),
    "factorio": {"name": "Factorio Terms of Service", "url": "https://www.factorio.com/terms-of-service",
                 "required": False},
}
