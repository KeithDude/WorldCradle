# Where GameDash's files are. Sourced by the other scripts in bin/ and by setup.sh (POSIX sh).
#
#   GAMEDASH_CODE  the program (this repository, or /usr/lib/gamedash from the package)
#   GAMEDASH_VENV  its Python libraries. In a copy you can write to (a git checkout) they live
#                  beside the code in venv/; the package's program folder belongs to the system,
#                  so there they live in your home folder instead.
#   GAMEDASH_HOME  settings, passwords, server list, certificate, logs (see app/paths.py)
#   GAMEDASH_PORT  the dashboard's web address port
#
# The caller sets GAMEDASH_CODE before sourcing this.
: "${GAMEDASH_CODE:?set GAMEDASH_CODE before sourcing gamedash-env.sh}"
if [ -z "${GAMEDASH_VENV:-}" ]; then
    if [ -w "$GAMEDASH_CODE" ]; then
        GAMEDASH_VENV="$GAMEDASH_CODE/venv"
    else
        GAMEDASH_VENV="${XDG_DATA_HOME:-$HOME/.local/share}/gamedash/venv"
    fi
fi
: "${GAMEDASH_HOME:=$HOME/.config/gamedash}"
: "${GAMEDASH_PORT:=8443}"
export GAMEDASH_CODE GAMEDASH_VENV GAMEDASH_HOME GAMEDASH_PORT
