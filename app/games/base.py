"""games/base.py — the game-type interface.

Each supported game is a GameType subclass that encapsulates everything
game-specific: how to read players/reachability, which control actions it
supports and how to run them, its Steam app id / update script, and how to
provision a new instance. The rest of the app dispatches through
`games.get(kind)` instead of `if kind == ...` branches.

Methods take a `server` object (the registry Server dataclass) for its ports,
passwords, paths, etc. Low-level probing/clients live in `monitor.py`; game
types orchestrate them.
"""
from __future__ import annotations


class ActionError(Exception):
    """User-facing error from a control action (bad target, no RCON, etc.)."""


def safe_name(text: str, maxlen: int = 60) -> str:
    """Sanitise a user-supplied display/session name for safe embedding in a
    generated shell script or ARK option string. Drops shell-dangerous chars
    (`" ` $ \\ ?`) and control chars, collapses whitespace, caps length — so a
    name can never break out of its quoting or inject a command."""
    bad = set('"`$\\?')
    out = "".join(c for c in (text or "")
                  if c not in bad and 32 <= ord(c) != 127)
    return " ".join(out.split())[:maxlen]


# ---- typed readers for the Add-form options (extra_fields) -----------------
# The form posts strings (text/number/select) or booleans (checkbox). These
# validate one option out of the posted spec and raise a user-facing error.

def opt_bool(spec: dict, name: str, default: bool = False) -> bool:
    v = spec.get(name)
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def opt_int(spec: dict, name: str, default: int | None, lo: int, hi: int,
            label: str) -> int | None:
    v = spec.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ActionError(f"{label} must be a whole number.")
    if not lo <= n <= hi:
        raise ActionError(f"{label} must be between {lo} and {hi}.")
    return n


def opt_float(spec: dict, name: str, default: float | None, lo: float, hi: float,
              label: str) -> float | None:
    v = spec.get(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        n = float(str(v).strip())
    except ValueError:
        raise ActionError(f"{label} must be a number.")
    if not lo <= n <= hi:
        raise ActionError(f"{label} must be between {lo:g} and {hi:g}.")
    return n


def opt_choice(spec: dict, name: str, choices, default: str, label: str) -> str:
    v = str(spec.get(name) if spec.get(name) is not None else "").strip()
    if v == "":
        return default
    if v not in choices:
        raise ActionError(f"{label}: '{v}' isn't one of the allowed values.")
    return v


class GameType:
    kind: str = ""
    label: str = ""                 # display name, e.g. "ARK"
    title: str = ""                 # full title for section headings ("" → label)
    steam_app: int | None = None    # Steam dedicated-server app id
    update_script: str | None = None  # optional ~/Scripts/<script> override for update-apply
    # ---- installing the dedicated server from the dashboard ---------------
    install_marker: str = ""        # file (relative to the install dir) that proves it's installed
    install_gb: float = 0           # approximate installed size, for the disk check
    steam_platform: str | None = None  # "windows" → fetch the Windows build (run under Wine)
    steam_beta: str | None = None      # Steam branch to install, when the Linux build lives on one
    requires: list[str] = []        # programs the server needs on this computer (e.g. "wine")
    requires_libs: list[str] = []   # system libraries it needs, by short name (e.g. "gdiplus")
    ram_note: str = ""              # plain-language memory guidance
    about: str = ""                 # one line for the Games list
    actions: set[str] = set()       # supported controls: save/broadcast/kick/ban/chat

    @property
    def eula(self) -> dict | None:
        """The publisher's licence terms for this game ({name, url, required}),
        or None. When `required`, the Add form asks for agreement and
        provisioning refuses without it. See games/eulas.py."""
        from games.eulas import EULAS
        return EULAS.get(self.kind)

    # ---- provisioning -----------------------------------------------------
    provisionable: bool = False     # can the dashboard auto-create an instance?
    # extra Add-form fields. Each is {name, label} plus, optionally:
    #   type: "text" (default) | "number" | "select" | "checkbox"
    #   placeholder, default, help (tooltip); number: min/max/step;
    #   select: options = [[value, label], ...]
    # Every field must map to something the game's server really accepts.
    extra_fields: list[dict] = []
    provision_hint: str = ""        # one-paragraph description shown under the form
    # Games that can't run multiple instances from one install (install-local
    # saves/config, no save-dir override) need their own install dir per
    # instance — provisioning clones the base install (with a disk pre-flight).
    needs_install_clone: bool = False
    # Folders inside such a copy to empty so the new server starts fresh (a world, crash dumps
    # or logs left in the base install by an earlier run).
    clone_clear_dirs: tuple[str, ...] = ()
    provision_note: str = ""        # caveat shown in the Add form for this game
    # False for servers that crash when a client connects and hangs up straight away (Terraria):
    # GameDash then never tests them by connecting.
    survives_connect_test: bool = True
    # launch profiles offered at provision time (e.g. vanilla vs modded). The
    # first is the default. Empty/one entry → no profile picker shown.
    mod_profiles: list[str] = []

    # The ports this game's server uses, in allocation order. Each entry:
    #   name  — key in the ports dict handed to provision() ("game"/"query"/"rcon")
    #   klass — port-pool class it draws from when auto-allocated
    #   start — where auto-allocation starts hunting (the game's convention)
    #   span  — consecutive ports it occupies (ARK/Valheim also use port+1)
    #   label, help — shown on the Add form, where each gets a box (blank = auto)
    #   form  — False for internal ports nobody forwards (always auto-allocated)
    #   forward, proto — True + "UDP"/"TCP"/"UDP and TCP" for ports the router
    #           must forward so players can connect (drives the reachability helper)
    port_layout: list[dict] = [
        {"name": "game", "klass": "game", "start": 7100, "label": "Game port"},
    ]

    def port_fields(self) -> list[dict]:
        """Add-form inputs for this game's ports (posted as port_<name>)."""
        def label(p):   # control ports say so where it can't be missed, not only in the tooltip
            closed = " — 🔒 keep closed, never forward" if p.get("klass") == "rcon" and not p.get("forward") else ""
            return f"{p['label']}{closed} — blank = automatic"
        return [{"name": f"port_{p['name']}", "label": label(p),
                 "type": "number", "min": 1024, "max": 65535,
                 "placeholder": f"auto (from {p['start']})", "help": p.get("help", "")}
                for p in self.port_layout if p.get("form", True)]

    def provision_ports(self, used: set[int], use_pool: bool = False,
                        wanted: dict | None = None) -> dict:
        """Settle this game's ports, avoiding `used` (mutated). A port the
        operator typed on the form (`wanted[name]`) is used as typed — it may be
        another server's too (Start refuses while it's in use); the rest are allocated — from the config port pool when `use_pool`,
        else upward from each port's conventional start."""
        import ports
        wanted = wanted or {}
        out = {}
        for p in self.port_layout:
            span = p.get("span", 1)
            if wanted.get(p["name"]):
                out[p["name"]] = ports.claim(wanted[p["name"]], used, span, p["label"])
            else:
                out[p["name"]] = ports.alloc(p["klass"], p["start"], used, span=span,
                                             use_pool=use_pool)
        return out

    def provision(self, spec: dict, ports: dict) -> dict:
        """Write any config/launch files for a new instance and return the
        unit/store fields: exec_start, working_dir, game_port, query_port,
        rcon_port, a2s, proc_match, server_name, join_port, log_path,
        install_dir, steam_app (and optionally rcon_password_ref)."""
        raise ActionError("Auto-provisioning isn't available for this game type yet.")

    def install(self, install_dir: str, on_progress=None) -> tuple[bool, str]:
        """Download this game's server into `install_dir`. Default: steamcmd."""
        import steam
        return steam.app_update(self.steam_app, install_dir, self.steam_platform, on_progress,
                                beta=self.steam_beta)

    def valid_target(self, target: str) -> bool:
        """Is `target` an acceptable player id for kick/ban? Steam ids by default."""
        return target.isdigit()

    def supports(self, action: str) -> bool:
        return action in self.actions

    # ---- backups ----------------------------------------------------------
    def save_paths(self, s) -> list[dict]:
        """The save components for this server, each a dict
        ``{"path": <abs path, dir or file>, "role": <"save"|"cluster"|...>}``.
        Backups archive these; restore puts them back (and can filter by role —
        e.g. restore the map save but not the shared ARK cluster). Empty → no
        known save location (e.g. a custom service with no save folder set).
        Default: the server's save folder, recorded when it was created."""
        return [{"path": s.save_root, "role": "save"}] if s.save_root else []

    # ---- monitoring -------------------------------------------------------
    # What a server card shows for this game. The rows depend only on the game, never on
    # whether the server is running (a stopped server shows "—" in them).
    reports_players: bool = True     # its probe can tell how many players are on
    reports_answering: bool = True   # its probe can tell whether it answers on its port
    server_stats: bool = False       # extra live stats (Satisfactory: tick rate, progress, game time)

    def card_rows(self, s) -> dict:
        return {"players": self.reports_players, "answering": self.reports_answering,
                "server_stats": self.server_stats}

    def probe(self, s) -> dict:
        """Return a partial snapshot dict: any of players, player_names,
        player_detail, max_players, reachable, sf. Called only when the server
        is online."""
        return {}

    # ---- controls (override the ones in `actions`) ------------------------
    def save(self, s) -> str:
        raise ActionError(f"{s.name} doesn't support a save command.")

    def broadcast(self, s, message: str) -> str:
        raise ActionError(f"{s.name} doesn't support broadcast.")

    def kick(self, s, target: str) -> str:
        raise ActionError(f"{s.name} doesn't support kick.")

    def ban(self, s, target: str) -> str:
        raise ActionError(f"{s.name} doesn't support ban.")

    def chat(self, s) -> str:
        raise ActionError(f"{s.name} has no live chat feed.")
