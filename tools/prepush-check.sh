#!/usr/bin/env bash
# WorldCradle pre-push checks. Run by .git/hooks/pre-push (see tools/install-hooks.sh) and
# can be run by hand: tools/prepush-check.sh
# Any failure stops the push. Nothing here changes files or touches running servers.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/venv/bin/python"
fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=1; }
echo "WorldCradle pre-push checks"

# 1. Everything is committed (what is pushed is what was tested)
if [ -z "$(git -C "$REPO" status --porcelain)" ]; then ok "working tree clean"; else bad "uncommitted changes:"; git -C "$REPO" status --short | sed 's/^/         /'; fi

# 2. Python compiles, with nothing unused left behind
if "$PY" -m compileall -q "$REPO/app" >/dev/null; then ok "Python compiles"; else bad "Python compile errors"; fi
if "$PY" -c "import pyflakes" 2>/dev/null; then
  if out=$("$PY" -m pyflakes "$REPO/app" "$REPO/tests" 2>&1); then ok "no unused imports or variables (pyflakes)"
  else bad "pyflakes found problems:"; printf '%s\n' "$out" | sed 's/^/         /'; fi
else
  bad "pyflakes isn't installed — run: venv/bin/pip install -r requirements-dev.txt"
fi

# 3. App, game types, templates load
if (cd "$REPO/app" && "$PY" - <<'T' 2>&1 | grep -v Warning
import sys; sys.path.insert(0, ".")
import app as A, games, installs
ts = games.all_types()
for g in ts:
    if g.kind != "custom":
        g.port_fields(); list(g.extra_fields); g.provision_hint; g.eula
        for p in g.port_layout:
            if p.get("klass") == "rcon" and p.get("forward"):
                raise SystemExit(f"control port marked for forwarding: {g.kind}/{p['name']}")
for t in ("admin.html", "public.html", "base.html", "settings.html", "backups.html", "login.html", "setup.html"):
    A.app.jinja_env.get_template(t)
installs.catalog()
print(f"{len(ts)} game types")
T
); then ok "app, game types and templates load; no control port marked for forwarding"; else bad "app / game types / templates failed to load"; fi

# 3b. Automated tests (tests/; needs: venv/bin/pip install -r requirements-dev.txt)
if "$PY" -c "import pytest" 2>/dev/null; then
  # with umask 022, as on GitHub's machines, so a test that only passes with this computer's
  # settings is caught here rather than after the push
  out=$(cd "$REPO" && umask 022 && "$PY" -m pytest -q tests 2>&1 | tail -1)
  case "$out" in *failed*|*error*) bad "tests: $out" ;; *passed*) ok "tests: $out" ;; *) bad "tests didn't run: $out" ;; esac
else
  bad "pytest isn't installed — run: venv/bin/pip install -r requirements-dev.txt"
fi

# 4. The page's JavaScript modules parse, and every import names something its module exports
#    (needs gjs or node)
js_fail=""
for f in "$REPO"/app/static/js/*.js; do
  if command -v gjs >/dev/null; then
    out=$(cd "$(dirname "$f")" && gjs -m "$f" 2>&1 | grep -E "Error" | head -1)
  elif command -v node >/dev/null; then
    tmp=$(mktemp -d); cp "$REPO"/app/static/js/*.js "$tmp"/
    for m in "$tmp"/*.js; do mv "$m" "${m%.js}.mjs"; done
    sed -i 's/\.js";$/.mjs";/' "$tmp"/*.mjs
    out=$(node --check "$tmp/$(basename "${f%.js}").mjs" 2>&1 | head -1); rm -rf "$tmp"
  else
    out="no JavaScript checker (install nodejs or gjs)"
  fi
  [ -n "$out" ] && js_fail="$js_fail ${f##*/}: $out;"
done
[ -z "$js_fail" ] && ok "JavaScript modules parse" || bad "JavaScript:$js_fail"

# 5. Shell scripts parse
sh_fail=0
for f in "$REPO"/*.sh "$REPO"/tools/*.sh "$REPO"/deploy/maintenance/*.sh "$REPO"/bin/*; do
  [ -f "$f" ] && { bash -n "$f" 2>/dev/null || { bad "shell syntax: ${f#$REPO/}"; sh_fail=1; }; }
done; [ $sh_fail = 0 ] && ok "shell scripts parse"

# 6. No secrets or personal data in tracked files
files=$(git -C "$REPO" ls-files)
SECRETS="${WORLDCRADLE_HOME:-$HOME/.config/worldcradle}/secrets.conf"
[ -f "$SECRETS" ] || SECRETS="$(grep -ho '^\. [^ ]*secrets[^ ]*' "$REPO"/../*server/worldcradle-*-run.sh 2>/dev/null | head -1 | cut -c3-)"
leak=0
if [ -n "$SECRETS" ] && [ -f "$SECRETS" ]; then
  while IFS='=' read -r k v; do
    v="${v%\"}"; v="${v#\"}"
    case "$k" in GAME_*PASSWORD*) [ ${#v} -ge 4 ] && (cd "$REPO" && echo "$files" | xargs /usr/bin/grep -lF -e "$v" 2>/dev/null) && leak=1 ;; esac
  done < "$SECRETS"
fi
[ $leak = 0 ] && ok "no game passwords in tracked files" || bad "a game password appears in the files listed above"
# whole words only: a host called "GameServer" must not match "ShooterGameServer"
pat="\\b($(id -un)|$(hostname)|$(hostname -I 2>/dev/null | awk '{print $1}' | sed 's/\./\\./g'))\\b"
hits=$(cd "$REPO" && echo "$files" | xargs /usr/bin/grep -nIE -e "$pat" -e 'BEGIN [A-Z ]*PRIVATE KEY' -e 'gh[pousr]_[A-Za-z0-9]{30,}' 2>/dev/null | grep -v '^tools/prepush-check.sh')
[ -z "$hits" ] && ok "no user name, host name, LAN address, private key or token in tracked files" || { bad "personal data / secrets found:"; echo "$hits" | cut -c1-150 | sed 's/^/         /'; }

# 7. Dependencies: requirements.lock matches requirements.txt, and nothing in it is GPL (the
#    project licence is PolyForm Noncommercial) — every library, including the ones pulled in
deps=$("$PY" - "$REPO/requirements.txt" "$REPO/requirements.lock" <<'T' 2>/dev/null
import re, sys
from importlib.metadata import metadata, PackageNotFoundError
from packaging.markers import Marker
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()
top = {norm(re.split(r"[<>=!~\[ ;#]", l.strip())[0]) for l in open(sys.argv[1]) if l.strip() and not l.startswith("#")}
locked = {}
for line in open(sys.argv[2]):
    m = re.match(r"^([A-Za-z0-9_.-]+)==\S+(?:\s*;\s*([^\\]+))?", line)
    if m:
        locked[norm(m[1])] = m[2]
for name in sorted(top - set(locked)):
    print(f"{name} is in requirements.txt but not requirements.lock (run tools/lock-requirements.sh)")
for name, marker in sorted(locked.items()):
    if marker and not Marker(marker.strip()).evaluate():
        continue   # not used on this system (e.g. Windows-only)
    try:
        m = metadata(name)
    except PackageNotFoundError:
        print(f"{name} (not installed here — licence unchecked)")
        continue
    lic = " ".join([m.get("License-Expression") or "", (m.get("License") or "")[:200]] + (m.get_all("Classifier") or []))
    if re.search(r"\bA?GPL|General Public License", lic) and not re.search(r"LGPL|Lesser", lic):
        print(f"{name} has a GPL licence")
T
)
[ -z "$deps" ] && ok "dependencies: lock file up to date, no GPL licences" || { bad "dependency problems:"; echo "$deps" | sed 's/^/         /'; }

# 7b. The .deb package builds and holds what it must
if command -v dpkg-deb >/dev/null 2>&1; then
  if out=$(bash "$REPO/tools/build-deb.sh" 2>&1); then
    deb=$(ls -t "$REPO"/dist/*.deb | head -1)
    missing=""; listing=$(dpkg-deb -c "$deb")
    for f in ./usr/bin/worldcradle ./usr/lib/worldcradle/setup.sh ./usr/lib/worldcradle/requirements.lock \
             ./usr/lib/worldcradle/bin/worldcradle-ensure-venv ./usr/lib/worldcradle/app/app.py ./usr/share/doc/worldcradle/copyright; do
      grep -q " $f\( \|$\)" <<< "$listing" || missing="$missing $f"
    done
    [ -z "$missing" ] && ok "package builds: dist/$(basename "$deb")" || bad "package is missing:$missing"
  else
    bad "package doesn't build:"; echo "$out" | tail -5 | sed 's/^/         /'
  fi
fi

# 8. The running dashboard still answers (when it runs here)
if systemctl --user is-active -q worldcradle 2>/dev/null; then
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/ || true)
  [ "$code" = 200 ] && ok "running dashboard answers" || bad "running dashboard returned HTTP $code"
fi

echo
if [ $fail = 0 ]; then echo "All checks passed."; else echo "Checks FAILED — not pushing. Fix the items above first."; fi
exit $fail
