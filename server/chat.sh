#!/usr/bin/env bash
# Moderate the chat of the HF tests tab on neo.oh2gba.eu over SFTP, since the host has no shell.
# server/neo/api/v1/chat.php keeps the lines in private/chat/lines.json and writes the chat to
# chat.json in the site root.
#
#   server/chat.sh --list           every kept line: the id, when, the call, the first 8 digits of
#                                   its token's hash (the lines of one installation share them) and
#                                   the text
#   server/chat.sh rm ID...         take these lines out (removed.txt), then write the chat again
#   server/chat.sh close            refuse every line (the file `closed`); the chat says
#                                   "closed": true and the program says so
#   server/chat.sh open             take lines again
#   server/chat.sh blocked          the blocked calls: the sked board's list, which the chat shares
#   server/chat.sh block CALL       refuse the lines of a call (every SSID of it, when CALL has
#                                   none) and take its lines out, as `server/skeds.sh block` does for
#                                   the board, then write both again
#   server/chat.sh unblock CALL     take them again
#   server/chat.sh refresh          write the chat again (a POST of {"action": "refresh"})
#
# Every change ends with a refresh, so the chat says it at once. A line is never edited here. Refused
# before anything is asked: an id that is not a whole number, a call that is not letters and digits
# with an SSID. Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw); the
# token is the first line of a .secrets file: SECRETS_FILE, else the first one found searching
# upwards, else ../../oh2gba/.secrets.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # server/
REMOTE="${PROJECT_PAGE_REMOTE:-/public_html/neo}/private/chat"
ENDPOINT="https://neo.oh2gba.eu/api/v1/chat.php"
ID_FORM='^[1-9][0-9]{0,15}$'
CALL_FORM='^[A-Za-z0-9]{1,6}(-[0-9]{1,2})?$'

usage() { echo "chat.sh: $1 (see --help)" >&2; exit 2; }

command="${1:-}"
[ $# -gt 0 ] && shift
ids=()
case "$command" in
  --list|close|open|blocked|refresh) [ $# -eq 0 ] || usage "$command takes nothing more" ;;
  rm)
    [ $# -gt 0 ] || usage "rm needs an id"
    for id in "$@"; do [[ "$id" =~ $ID_FORM ]] || usage "not an id: $id"; ids+=("$id"); done ;;
  block|unblock)
    [ $# -eq 1 ] && [[ "$1" =~ $CALL_FORM ]] || usage "$command needs one call" ;;
  "") usage "nothing to do" ;;
  *) usage "unknown command $command" ;;
esac

# The chat written again by the endpoint; prints how many lines it holds and whether it is closed.
refresh() {
  curl -sS --max-time 30 -X POST -H 'Content-Type: application/json' --data '{"action": "refresh"}' "$ENDPOINT" | python3 -c '
import json, sys
answer = json.load(sys.stdin)
if not answer.get("ok"):
    sys.exit("the chat was not written again: %s" % answer.get("reason"))
chat = answer["chat"]
print("the chat: %d lines%s" % (len(chat["lines"]), ", closed" if chat.get("closed") else ""))
'
}

case "$command" in
  blocked) exec "$ROOT/skeds.sh" blocked ;;
  block|unblock) "$ROOT/skeds.sh" "$command" "$1"; refresh; exit 0 ;;
esac

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || [ -n "${SECRETS_FILE:-}" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"  # a named file that is missing is never replaced by another one
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
_all=""
sec() { [ -n "$_all" ] || _all="$("$BWS" secret list -o json --color no)"; python3 -c "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])" <<<"$_all"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)
# The login goes to curl as a config on stdin, never on its command line.
quote() { local s=${1//\\/\\\\}; printf '%s' "${s//\"/\\\"}"; }
CURL_USER="user = \"$(quote "$FU"):$(quote "$FP")\""
fcurl() { curl -K - "$@" <<<"$CURL_USER"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# A file of the folder into $WORK: empty when the server has none (curl's exit 78), a stop on any
# other failure.
fetch() {
  local code=0
  fcurl -sS --max-time 60 -o "$WORK/$1" "sftp://$FH$REMOTE/$1" 2>/dev/null || code=$?
  if [ "$code" -eq 78 ]; then
    : > "$WORK/$1"
  elif [ "$code" -ne 0 ]; then
    echo "chat.sh: $1 could not be read (curl exit $code); nothing was changed" >&2
    exit 1
  fi
}
upload() { fcurl -sS --max-time 60 --ftp-create-dirs -T "$1" "sftp://$FH$REMOTE/$2" >/dev/null; }

case "$command" in
  --list)
    fetch lines.json
    python3 -c '
import json, sys
try:
    kept = json.loads(open(sys.argv[1], encoding="utf-8").read() or "{}")
except ValueError:
    sys.exit("lines.json is not JSON")
lines = kept.get("lines", []) if isinstance(kept, dict) else []
for r in lines:
    print("  %6s  %s  %-10s %s  %s" % (r.get("id"), r.get("at"), r.get("call"), str(r.get("token", ""))[:8], " ".join(str(r.get("text", "")).split())))
print("%d kept, next id %s" % (len(lines), kept.get("next") if isinstance(kept, dict) else "?"))
' "$WORK/lines.json" ;;
  rm)
    fetch removed.txt
    printf '%s\n' "${ids[@]}" >> "$WORK/removed.txt"
    upload "$WORK/removed.txt" removed.txt
    echo "taken out: ${ids[*]}"
    refresh ;;
  close)
    : > "$WORK/closed"
    upload "$WORK/closed" closed
    echo "closed: every line is refused"
    refresh ;;
  open)
    fcurl -sS --max-time 60 -Q "*rm $REMOTE/closed" "sftp://$FH$REMOTE/" >/dev/null
    echo "open: lines are taken"
    refresh ;;
  refresh)
    refresh ;;
esac
