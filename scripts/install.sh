#!/usr/bin/env bash
# Installs neoaprs from this git clone as a user service that starts at boot and survives logout: a thin wrapper that calls `neoaprs service install` of this clone's venv with this clone's data
# folder (the command writes the systemd unit, ~/.config/systemd/user/neoaprs.service, enables and starts it, and enables lingering; docs/manual/install.md and systemd/README.md say how).
#   scripts/install.sh            write the unit, reload systemd, enable the service and start it (run it again after a git pull)
#   scripts/install.sh --remove   stop and disable the service and delete the unit it wrote
# A user who installed NeoAPRS with `uv tool install` runs `neoaprs service install` himself: this script is for a clone.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHON=.venv/bin/python
[ -x "$PYTHON" ] || { echo "no .venv: uv sync --frozen"; exit 1; }
case "${1:-}" in
    --remove) exec "$ROOT/$PYTHON" -m neoaprs service remove --data "$ROOT/data" --clone "$ROOT" ;;
    "") exec "$ROOT/$PYTHON" -m neoaprs service install --data "$ROOT/data" --clone "$ROOT" --linger ;;
    *) echo "install.sh: unknown argument $1 (--remove, --help)" >&2; exit 2 ;;
esac
