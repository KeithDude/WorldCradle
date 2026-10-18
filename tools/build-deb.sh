#!/usr/bin/env bash
# Build the WorldCradle .deb package:  tools/build-deb.sh [--worktree]
#
# Packs the committed version (HEAD) — or, with --worktree, the files as they are now (for testing
# before a commit) — into dist/worldcradle_<version>_all.deb plus a .sha256 checksum file.
#
# The package puts the program in /usr/lib/worldcradle and the `worldcradle` command in /usr/bin. It
# needs no compiling: each account's Python libraries are installed (pinned, checksum-verified, from
# requirements.lock) when that account runs "worldcradle setup". System packages come from
# deploy/packages.conf: WorldCradle's own needs are "Depends", the rest "Recommends" (apt installs
# those by default; --no-install-recommends gives a minimal install).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME=worldcradle
WORKTREE=0; [ "${1:-}" = --worktree ] && WORKTREE=1

# --- version: 0.2.0 for a release; 0.2.0~dev+<date>.<commit> while VERSION says 0.2.0-dev ----
upstream="$(tr -d '[:space:]' < "$REPO/VERSION")"
commit="$(git -C "$REPO" rev-parse --short=7 HEAD)"
case "$upstream" in
    *-dev) version="${upstream%-dev}~dev+$(git -C "$REPO" log -1 --format=%cd --date=format:%Y%m%d).$commit" ;;
    *)     version="$upstream" ;;
esac
[ "$WORKTREE" = 1 ] && [ -n "$(git -C "$REPO" status --porcelain)" ] && version="$version.local"
deb_version="$version-1"

# --- the files -------------------------------------------------------------------------
build="$(mktemp -d)"; trap 'rm -rf "$build"' EXIT
src="$build/src"; root="$build/root"; mkdir -p "$src" "$root"
if [ "$WORKTREE" = 1 ]; then
    (cd "$REPO" && { git ls-files; git ls-files --others --exclude-standard; } | sort -u \
        | while read -r f; do [ -e "$f" ] && printf '%s\0' "$f"; done | tar --null -cf - -T -) | tar -xf - -C "$src"
else
    git -C "$REPO" archive HEAD | tar -xf - -C "$src"
fi
lib="$root/usr/lib/$NAME"; doc="$root/usr/share/doc/$NAME"
mkdir -p "$lib/deploy" "$root/usr/bin" "$doc"
cp -r "$src/app" "$src/bin" "$lib/"
cp -r "$src/deploy/systemd" "$src/deploy/fail2ban" "$src/deploy/examples" "$src/deploy/packages.conf" "$lib/deploy/"
cp "$src/setup.sh" "$src/VERSION" "$src/requirements.txt" "$src/requirements.lock" "$lib/"
find "$lib" -name __pycache__ -type d -prune -exec rm -rf {} +
ln -s "../lib/$NAME/bin/worldcradle" "$root/usr/bin/worldcradle"
cp "$src/README.md" "$src/docs/GETTING_STARTED.md" "$doc/"
gzip -9n -c "$src/CHANGELOG.md" > "$doc/changelog.gz"
{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: WorldCradle"
    echo "Source: https://github.com/KeithDude/WorldCradle"
    echo
    echo "Files: *"
    sed -n 's/^Required Notice: /Copyright: /p' "$src/LICENSE.md"
    echo "License: PolyForm-Noncommercial-1.0.0"
    echo " Free for noncommercial use. The full licence follows."
    echo " ."
    sed -e 's/^$/./' -e 's/^/ /' "$src/LICENSE.md"
} > "$doc/copyright"

# permissions: everything readable, only the programs executable
find "$root" -type d -exec chmod 755 {} +
find "$root" -type f -exec chmod 644 {} +
chmod 755 "$lib/setup.sh" "$lib"/bin/worldcradle "$lib"/bin/worldcradle-ensure-venv "$lib"/bin/worldcradle-preflight

# --- package information -------------------------------------------------------------
group() { sed -n "s/^$1:[[:space:]]*//p" "$src/deploy/packages.conf"; }
commas() { tr -s ' ' '\n' | sed '/^$/d; /^|$/d' | paste -sd, | sed 's/,/, /g'; }
depends="$(group required | commas | sed "s/^python3,/python3 (>= 3.10),/"), systemd (>= 249)"
# a "a | b" group stays one alternative; plain groups are one package each
recommends="$( { group games | commas; group java; group wine | commas; group wine-extras | commas; group fail2ban | commas; } | paste -sd, | sed 's/,\([^ ]\)/, \1/g')"
mkdir -p "$root/DEBIAN"
cat > "$root/DEBIAN/control" <<CONTROL
Package: $NAME
Version: $deb_version
Architecture: all
Maintainer: Keith <6182573+KeithDude@users.noreply.github.com>
Installed-Size: $(du -sk "$root/usr" | cut -f1)
Depends: $depends
Recommends: $recommends
Section: games
Priority: optional
Homepage: https://github.com/KeithDude/WorldCradle
Description: run and watch your own game servers from a web browser
 WorldCradle installs, runs and monitors dedicated game servers (Valheim, Palworld,
 Minecraft, ARK, Terraria and many more) on your own computer, with a web
 dashboard made for people who aren't technical: who is playing, start and stop,
 backups, alerts, and step-by-step help letting friends connect.
 .
 After installing, run "worldcradle setup" as your normal user.
 .
 Licence: PolyForm Noncommercial 1.0.0 — free for noncommercial use.
CONTROL
install -m 755 "$src/deploy/debian/postinst" "$src/deploy/debian/prerm" "$root/DEBIAN/"

mkdir -p "$REPO/dist"
out="$REPO/dist/${NAME}_${deb_version}_all.deb"
dpkg-deb --root-owner-group -Zxz --build "$root" "$out" >/dev/null
(cd "$REPO/dist" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
echo "Built: dist/$(basename "$out")"
echo "       $(du -h "$out" | cut -f1), checksum in dist/$(basename "$out").sha256"
