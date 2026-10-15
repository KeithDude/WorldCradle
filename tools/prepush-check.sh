#!/usr/bin/env bash
# GameDash pre-push checks. Run by .git/hooks/pre-push (see tools/install-hooks.sh) and
# can be run by hand: tools/prepush-check.sh
# Any failure stops the push. Nothing here changes files or touches running servers.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/venv/bin/python"
fail=0
ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=1; }
echo "GameDash pre-push checks"

# 1. Everything is committed (what is pushed is what was tested)
if [ -z "$(git -C "$REPO" status --porcelain)" ]; then ok "working tree clean"; else bad "uncommitted changes:"; git -C "$REPO" status --short | sed 's/^/         /'; fi

# 2. Python compiles
if "$PY" -m compileall -q "$REPO/app" >/dev/null; then ok "Python compiles"; else bad "Python compile errors"; fi

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

# 4. JavaScript syntax (needs gjs or node)
JS="$REPO/app/static/app.js"
if command -v node >/dev/null; then node --check "$JS" && ok "app.js syntax" || bad "app.js syntax"
elif command -v gjs >/dev/null; then
  out=$(gjs -c "const [o,b]=imports.gi.GLib.file_get_contents('$JS'); try{new Function(new TextDecoder().decode(b)); print('ok')}catch(e){print('ERR '+e.message+' line '+e.lineNumber)}" 2>&1)
  [ "$out" = "ok" ] && ok "app.js syntax" || bad "app.js syntax: $out"
else bad "no JavaScript checker (install nodejs or gjs)"; fi

# 5. Shell scripts parse
for f in "$REPO"/*.sh "$REPO"/tools/*.sh "$REPO"/deploy/maintenance/*.sh; do
  [ -f "$f" ] && { bash -n "$f" 2>/dev/null || bad "shell syntax: ${f#$REPO/}"; }
done; [ $fail = 0 ] && ok "shell scripts parse"

# 6. No secrets or personal data in tracked files
files=$(git -C "$REPO" ls-files)
SECRETS="${GAMEDASH_HOME:-$HOME/.config/gamedash}/secrets.conf"
[ -f "$SECRETS" ] || SECRETS="$(grep -ho '^\. [^ ]*secrets[^ ]*' "$REPO"/../*server/gamedash-*-run.sh 2>/dev/null | head -1 | cut -c3-)"
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

# 7. Dependencies: nothing GPL (the project licence is PolyForm Noncommercial)
gpl=$("$PY" - "$REPO/requirements.txt" <<'T' 2>/dev/null
import re, sys
from importlib.metadata import metadata, PackageNotFoundError
for line in open(sys.argv[1]):
    name = re.split(r"[<>=!~\[ ;#]", line.strip())[0]
    if not name: continue
    try:
        m = metadata(name)
        lic = " ".join([m.get("License-Expression") or "", (m.get("License") or "")[:200]] + (m.get_all("Classifier") or []))
        if re.search(r"\bA?GPL|General Public License", lic) and not re.search(r"LGPL|Lesser", lic):
            print(name)
    except PackageNotFoundError:
        print(name + " (not installed — licence unchecked)")
T
)
[ -z "$gpl" ] && ok "dependencies: no GPL licences" || bad "dependency licence problem: $gpl"

# 8. The running dashboard still answers (when it runs here)
if systemctl --user is-active -q gamedash 2>/dev/null; then
  code=$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/ || true)
  [ "$code" = 200 ] && ok "running dashboard answers" || bad "running dashboard returned HTTP $code"
fi

echo
if [ $fail = 0 ]; then echo "All checks passed."; else echo "Checks FAILED — not pushing. Fix the items above first."; fi
exit $fail
