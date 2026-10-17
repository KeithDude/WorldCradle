# Where RealmCradle's files are. Sourced by the other scripts in bin/ and by setup.sh (POSIX sh).
#
#   REALMCRADLE_CODE  the program (this repository, or /usr/lib/realmcradle from the package)
#   REALMCRADLE_VENV  its Python libraries. In a copy you can write to (a git checkout) they live
#                  beside the code in venv/; the package's program folder belongs to the system,
#                  so there they live in your home folder instead.
#   REALMCRADLE_HOME  settings, passwords, server list, certificate, logs (see app/paths.py)
#   REALMCRADLE_PORT  the dashboard's web address port
#
# The caller sets REALMCRADLE_CODE before sourcing this.
: "${REALMCRADLE_CODE:?set REALMCRADLE_CODE before sourcing realmcradle-env.sh}"
if [ -z "${REALMCRADLE_VENV:-}" ]; then
    if [ -w "$REALMCRADLE_CODE" ]; then
        REALMCRADLE_VENV="$REALMCRADLE_CODE/venv"
    else
        REALMCRADLE_VENV="${XDG_DATA_HOME:-$HOME/.local/share}/realmcradle/venv"
    fi
fi
: "${REALMCRADLE_HOME:=$HOME/.config/realmcradle}"
: "${REALMCRADLE_PORT:=8443}"
export REALMCRADLE_CODE REALMCRADLE_VENV REALMCRADLE_HOME REALMCRADLE_PORT
