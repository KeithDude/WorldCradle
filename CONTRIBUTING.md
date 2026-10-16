# Contributing to GameDash

Thanks for helping. The most useful thing right now is **testing games** — most supported games are
marked *Not Tested* until someone confirms that players can actually join and play.

## Testing a game

1. Pick a game marked *Not Tested* in [docs/SUPPORTED_GAMES.md](docs/SUPPORTED_GAMES.md).
2. Follow "How to help test" at the bottom of that page.
3. Open an issue with the **Game test report** form (Issues → New issue). It asks what you checked
   and what happened.

**Never paste passwords** — the dashboard password, the join password or the admin password — into
an issue, a log or a screenshot. Logs from the dashboard hide them, but check before posting.

## Reporting a bug

Use the **Bug report** form. Include what you did, what you expected, what happened, and the output
of `gamedash version` and `gamedash logs` (passwords removed).

**Security problems** go through [SECURITY.md](SECURITY.md) instead — please don't open a public
issue for them.

## Asking for a game

Use the **Game request** form. A link to the game's official dedicated-server instructions helps a
lot, and so does being able to test it.

## Changing the code

- Small fixes are welcome as pull requests. For anything bigger, open an issue first so we can agree
  on the approach.
- GameDash is for people with little technical knowledge: plain words in the interface, nothing
  that needs editing files or typing commands to use a normal feature.
- It's expected to be reachable from the internet: never forward or expose an admin console (RCON)
  or other control port, validate everything that comes from the browser, and keep secrets out of
  logs.
- Before sending a change, install the test tools once (`venv/bin/pip install -r requirements-dev.txt`),
  run `tools/prepush-check.sh` (the same checks the maintainer runs before every push — it includes
  the automated tests in `tests/`), and say what you tested — on a real server if the change touches
  one. A bug fix should come with a test that fails without the fix.
- Don't add dependencies with a GPL or AGPL licence (they can't be combined with GameDash's licence).

## Licence of contributions

GameDash is released under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). By sending a
contribution you agree that it may be distributed under that licence, and that the maintainer may
also offer GameDash, including your contribution, under other terms (for example to a company that
asks permission for commercial use). If you can't agree to that, please say so in your pull request
before it is merged.
