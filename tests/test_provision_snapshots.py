"""What each game writes when a server is created must not change by accident.

If a difference is intended, re-record with:  venv/bin/python tests/provision_snapshots.py --update
and read the changed files in the diff before committing."""
import difflib
import json
import os

import pytest

import provision_snapshots as ps

RECORDED = {f[:-5]: os.path.join(ps.SNAPSHOTS, f) for f in os.listdir(ps.SNAPSHOTS) if f.endswith(".json")}


@pytest.fixture(scope="module")
def now():
    return ps.record_all()


def test_every_game_is_recorded(now):
    assert set(now) == set(RECORDED), "games added or removed: re-record the snapshots"


@pytest.mark.parametrize("kind", sorted(RECORDED))
def test_setup_writes_what_was_recorded(now, kind):
    with open(RECORDED[kind]) as f:
        before = json.load(f)
    after = json.loads(json.dumps(now[kind]))
    if before != after:
        diff = difflib.unified_diff(json.dumps(before, indent=1, sort_keys=True).splitlines(),
                                    json.dumps(after, indent=1, sort_keys=True).splitlines(),
                                    "recorded", "now", lineterm="", n=1)
        pytest.fail(f"{kind} now sets servers up differently:\n" + "\n".join(list(diff)[:60]))
