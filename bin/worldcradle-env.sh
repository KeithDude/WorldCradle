# Where WorldCradle's files are. Sourced by the other scripts in bin/ and by setup.sh (POSIX sh).
#
#   WORLDCRADLE_CODE  the program (this repository, or /usr/lib/worldcradle from the package)
#   WORLDCRADLE_VENV  its Python libraries. In a copy you can write to (a git checkout) they live
#                  beside the code in venv/; the package's program folder belongs to the system,
#                  so there they live in your home folder instead.
#   WORLDCRADLE_HOME  settings, passwords, server list, certificate, logs (see app/paths.py)
#   WORLDCRADLE_PORT  the dashboard's web address port
#
# The caller sets WORLDCRADLE_CODE before sourcing this.
: "${WORLDCRADLE_CODE:?set WORLDCRADLE_CODE before sourcing worldcradle-env.sh}"
if [ -z "${WORLDCRADLE_VENV:-}" ]; then
    if [ -w "$WORLDCRADLE_CODE" ]; then
        WORLDCRADLE_VENV="$WORLDCRADLE_CODE/venv"
    else
        WORLDCRADLE_VENV="${XDG_DATA_HOME:-$HOME/.local/share}/worldcradle/venv"
    fi
fi
: "${WORLDCRADLE_HOME:=$HOME/.config/worldcradle}"
: "${WORLDCRADLE_PORT:=8443}"
export WORLDCRADLE_CODE WORLDCRADLE_VENV WORLDCRADLE_HOME WORLDCRADLE_PORT
