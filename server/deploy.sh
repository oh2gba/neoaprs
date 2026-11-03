#!/usr/bin/env bash
# Upload the version page, and with --site the project page, to the shared hosting account, in one SFTP session each.
#
#   server/deploy.sh          # the version page (version.php, latest.php, log/.htaccess) to both of its places:
#                             #   neo.oh2gba.eu/version.php, which the copies from 0.16 on ask, and oh2gba.eu/neoaprs/version.php, which the copies before ask
#   server/deploy.sh --site   # the same, and the project page (site/ as it is, and server/neo/: the .htaccess and the page-view endpoint) to neo.oh2gba.eu
#   server/deploy.sh --list   # show what would be uploaded, don't touch the network
#
# Only these files: nothing else of either folder is touched, and message.txt and the logs, which live on the server only, are never uploaded or removed.
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw). The machine-account token is the first line of a .secrets file: SECRETS_FILE, else the first one found searching upwards
# from here, else ../../oh2gba/.secrets. Nothing secret is stored in this repository or printed.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # server/
SITE="$(cd "$ROOT/../site" && pwd)"
OLD="${VERSION_PAGE_REMOTE:-/public_html/oh2gba.eu/neoaprs}"
NEO="${PROJECT_PAGE_REMOTE:-/public_html/neo}"
PAGE=(version.php latest.php log/.htaccess)
GONE=(download.php)          # files of earlier versions of the version page, removed from the old folder at each upload (a missing one is no error)

# local path and remote path, tab-separated: the version page twice, and with --site the project page.
manifest() {
  local f
  for f in "${PAGE[@]}"; do printf '%s\t%s/%s\n' "$ROOT/$f" "$OLD" "$f"; printf '%s\t%s/%s\n' "$ROOT/$f" "$NEO" "$f"; done
  if [ "$with_site" = 1 ]; then
    ( cd "$SITE" && find . -type f -printf '%P\n' | sort ) | while read -r f; do printf '%s\t%s/%s\n' "$SITE/$f" "$NEO" "$f"; done
    ( cd "$ROOT/neo" && find . -type f -printf '%P\n' | sort ) | while read -r f; do printf '%s\t%s/%s\n' "$ROOT/neo/$f" "$NEO" "$f"; done
  fi
}

with_site=0
case "${1:-}" in
  --site) with_site=1 ;;
  --list) with_site=1; manifest | awk -F'\t' '{printf "  %s\n", $2}'; exit 0 ;;
  "") ;;
  *) echo "deploy.sh: unknown option $1" >&2; exit 2 ;;
esac

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
_all=""
sec() { [ -n "$_all" ] || _all="$("$BWS" secret list -o json --color no)"; python3 -c "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])" <<<"$_all"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)

ARGS=()
for f in "${GONE[@]}"; do ARGS+=(-Q "*rm $OLD/$f"); done
n=0
while IFS=$'\t' read -r local remote; do ARGS+=(-T "$local" "sftp://$FH$remote"); n=$((n + 1)); done < <(manifest)

echo "$n files in one session -> $OLD and $NEO"
curl -sS --max-time 600 --ftp-create-dirs -u "$FU:$FP" "${ARGS[@]}" >/dev/null
manifest | awk -F'\t' '{printf "  -> %s\n", $2}' | head -12
[ "$n" -le 12 ] || echo "  ... and $((n - 12)) more"
echo "done. Try: curl 'https://neo.oh2gba.eu/version.php?v=0.1.0&os=linux' and curl 'https://oh2gba.eu/neoaprs/version.php?v=0.1.0&os=linux'"
