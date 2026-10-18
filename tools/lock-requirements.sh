#!/usr/bin/env bash
# Regenerate requirements.lock from requirements.txt: exact versions and checksums that work on
# every Python WorldCradle supports (3.10 and newer), for Linux. Run it after changing
# requirements.txt, then run the tests and tools/prepush-check.sh before committing.
#
# Needs uv (https://docs.astral.sh/uv/), e.g.:  venv/bin/pip install uv
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="$(command -v uv || echo "$REPO/venv/bin/uv")"
[ -x "$UV" ] || { echo "uv isn't installed — run: venv/bin/pip install uv"; exit 1; }
tmp="$(mktemp)"
"$UV" pip compile "$REPO/requirements.txt" --universal --python-version 3.10 \
    --generate-hashes --no-header --quiet -o "$tmp"
{
    echo "# Exact versions of every Python library WorldCradle uses, with checksums, so each install gets"
    echo "# exactly the files that were tested (pip refuses anything that does not match)."
    echo "# Generated from requirements.txt by tools/lock-requirements.sh — do not edit by hand."
    cat "$tmp"
} > "$REPO/requirements.lock"
rm -f "$tmp"
echo "requirements.lock updated:"
grep -cE '^[A-Za-z]' "$REPO/requirements.lock" | sed 's/$/ libraries pinned/'
