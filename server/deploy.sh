#!/usr/bin/env bash
# Upload the version page (version.php and log/.htaccess) to oh2gba.eu/neoaprs/ on the shared hosting
# account, in one SFTP session. Only these files: nothing else of the site is touched, and message.txt
# and the logs, which live on the server only, are never uploaded or removed.
#
#   server/deploy.sh          # upload
#   server/deploy.sh --list   # show what would be uploaded, don't touch the network
#
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw). The machine-account
# token is the first line of a .secrets file: SECRETS_FILE, else the first one found searching upwards
# from here, else ../../oh2gba/.secrets. Nothing secret is stored in this repository or printed.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # server/
REMOTE="${VERSION_PAGE_REMOTE:-/public_html/oh2gba.eu/neoaprs}"
FILES=(version.php log/.htaccess)

if [ "${1:-}" = "--list" ]; then
  printf '  %s -> %s/%s\n' $(for f in "${FILES[@]}"; do echo "$f" "$REMOTE" "$f"; done)
  exit 0
fi

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
sec() { "$BWS" secret list -o json --color no | python3 -c \
  "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)

ARGS=()
for f in "${FILES[@]}"; do ARGS+=(-T "$ROOT/$f" "sftp://$FH$REMOTE/$f"); done

echo "version page: ${#FILES[@]} files in one session -> $REMOTE"
curl -sS --max-time 120 --ftp-create-dirs -u "$FU:$FP" "${ARGS[@]}" >/dev/null
printf '  -> %s\n' "${FILES[@]}"
echo "done. Try: curl 'https://oh2gba.eu/neoaprs/version.php?v=0.1.0&os=linux'"
