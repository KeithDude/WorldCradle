"""ports.py — port allocation for provisioning new realmcradle instances.

Each game template has a conventional start port per port class (game / query /
rcon). A `port_pool` range in config.json is only used when the caller asks for
it (the Add form's "use port pool" box): allocation then draws from that range. What's already
taken is computed live by `provision.used_ports()` (configured servers +
listening sockets + reserved), so there's no separate allocation ledger to
drift out of sync — the pool only *bounds* where we hunt for a free port.

A range is an inclusive [low, high] pair in config.json:

    "port_pool": {
      "game":  [7800, 7899],
      "query": [27030, 27089],
      "rcon":  [27090, 27099]
    }

Any class may be omitted; omitted classes fall back to template defaults.
Existing/migrated servers keep whatever ports they already have — the pool
governs *new* allocations only.
"""
from __future__ import annotations

import config

CLASSES = ("game", "query", "rcon")


def configured() -> dict[str, tuple[int, int]]:
    """Validated pool ranges from config (malformed/missing entries dropped)."""
    raw = config.load().get("port_pool") or {}
    out: dict[str, tuple[int, int]] = {}
    if not isinstance(raw, dict):
        return out
    for k in CLASSES:
        rng = raw.get(k)
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            try:
                lo, hi = int(rng[0]), int(rng[1])
            except (ValueError, TypeError):
                continue
            if 1 <= lo <= hi <= 65535:
                out[k] = (lo, hi)
    return out


def alloc(klass: str, fallback_start: int, used: set[int], span: int = 1,
          use_pool: bool = False) -> int:
    """Reserve `span` consecutive free ports for `klass`; return the first.

    The pool is opt-in: only when `use_pool` is true AND a range is configured
    for `klass` do we allocate from that range. Otherwise (the default) we hunt
    upward from `fallback_start` — the game template's conventional ports, which
    is how every server is provisioned unless the operator opts into the pool.
    Reserved ports are added to `used` so subsequent allocations don't collide.
    """
    from games.base import ActionError  # lazy: avoid import cycle at module load
    rng = configured().get(klass) if use_pool else None
    lo = rng[0] if rng else fallback_start
    hi = rng[1] if rng else 65535
    p = lo
    while p + span - 1 <= hi:
        if not any((p + i) in used for i in range(span)):
            for i in range(span):
                used.add(p + i)
            return p
        p += 1
    block = f"a block of {span} ports" if span > 1 else "a port"
    where = f"the '{klass}' pool ({lo}-{hi})" if rng else f"ports from {fallback_start}"
    raise ActionError(f"Couldn't allocate {block} in {where} — it's full.")


def claim(port, used: set[int], span: int = 1, label: str = "Port") -> int:
    """Reserve a port the operator asked for by number (plus the `span - 1`
    ports above it). Refuses anything privileged, reserved or already taken,
    naming the server that holds it when we know."""
    from games.base import ActionError  # lazy: avoid import cycle at module load
    try:
        p = int(str(port).strip())
    except (TypeError, ValueError):
        raise ActionError(f"{label}: enter a port number.")
    if not 1024 <= p <= 65535 - (span - 1):
        raise ActionError(f"{label}: must be between 1024 and {65535 - (span - 1)}.")
    for q in range(p, p + span):
        if q in used:
            raise ActionError(f"{label}: port {q} is already in use{_owner(q)} — pick another, "
                              f"or leave the box blank to have one chosen.")
    for q in range(p, p + span):
        used.add(q)
    return p


def _owner(port: int) -> str:
    """' by <server name>' when a configured server holds this port, else ''."""
    try:
        import registry
        for s in registry.load_servers():
            if port in s.all_ports():
                return f" by {s.name}"
    except Exception:
        pass
    return ""
