# Security

GameDash is built to be reachable from the internet, so security reports are taken seriously.

## Reporting a problem

Please report security problems **privately**, not in a public issue:

- On GitHub: the repository's **Security** tab → **Report a vulnerability**
  (https://github.com/KeithDude/GameDash/security/advisories/new).

Include what you found, how to reproduce it, and what someone could do with it. You'll get a reply as
soon as possible; please give a reasonable time for a fix before telling anyone else.

## What counts

Anything that could let someone who isn't the owner:

- sign in to the dashboard, or get around the sign-in;
- control a game server, read its settings or passwords, or run commands on the computer;
- make the dashboard unusable for its owner (for example by tying up its connections);
- read files they shouldn't, or trick the owner's browser into doing something (cross-site
  scripting, cross-site request forgery).

Problems inside the game servers themselves belong to their publishers — but if GameDash sets a
game up in an unsafe way (for example exposes its admin console), that is in scope.

## Supported versions

Fixes go into the latest version. Update with `gamedash update`.

## Good practice for owners

- Choose a strong dashboard password (`gamedash reset-password`).
- Forward only the ports listed under *Can friends connect?* — **never** an admin console (RCON) or
  other control port.
- Install fail2ban when the installer offers it (it does by default) to block password guessing.
- Keep GameDash and the computer updated.
