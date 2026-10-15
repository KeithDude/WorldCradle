#!/usr/bin/env bash
# Make git run tools/prepush-check.sh before every push from this clone.
set -eu
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
printf '#!/bin/sh\nexec "%s/tools/prepush-check.sh"\n' "$REPO" > "$REPO/.git/hooks/pre-push"
chmod +x "$REPO/.git/hooks/pre-push"
echo "pre-push hook installed"
