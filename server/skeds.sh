#!/usr/bin/env bash
# Moderate the sked board of neo.oh2gba.eu over SFTP, since the host has no shell. server/neo/api/v1/skeds.php keeps each sked as ID.json in private/skeds/ and writes the board, skeds.json in the root of the site.
#
#   server/skeds.sh --list             every stored sked: the id, when it was posted, the call, from, to, the dial, the first 8 digits of its token's hash (the skeds of one installation share them) and the note
#   server/skeds.sh rm ID...           remove these skeds, then make the board again
#   server/skeds.sh rm --since TIME    remove every sked posted at TIME or later (UTC, 2026-11-13T17:00Z), then make the board again
#   server/skeds.sh close              refuse every add (the file `closed`); the board says "closed": true and the program shows it without the form
#   server/skeds.sh open               take adds again
#   server/skeds.sh blocked            the blocked calls (blocked.txt)
#   server/skeds.sh block CALL         refuse the adds of a call (every SSID of it, when CALL has none) and remove its skeds
#   server/skeds.sh unblock CALL       take them again
#   server/skeds.sh refresh            make the board again (a POST of {"action": "refresh"}, which the rate limit does not count, so a flood cannot hold it up)
#
# Every change ends with a refresh, so the board says it at once. A sked is never edited here: removed, or left to end by itself. What is refused before anything is asked: an id that is not 12 hex digits,
# a call that is not letters and digits with an SSID, a time not of the form above.
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw); the token is the first line of a .secrets file: SECRETS_FILE, else the first one found searching upwards from here, else
# ../../oh2gba/.secrets (the same as deploy.sh and support-fetch.sh).
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # server/
REMOTE="${PROJECT_PAGE_REMOTE:-/public_html/neo}/private/skeds"
ENDPOINT="https://neo.oh2gba.eu/api/v1/skeds.php"
ID_FORM='^[0-9a-f]{12}$'
CALL_FORM='^[A-Za-z0-9]{1,6}(-[0-9]{1,2})?$'
TIME_FORM='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?Z$'

usage() { echo "skeds.sh: $1 (see --help)" >&2; exit 2; }

command="${1:-}"
[ $# -gt 0 ] && shift
ids=() since="" call=""
case "$command" in
  --list|close|open|blocked|refresh) [ $# -eq 0 ] || usage "$command takes nothing more" ;;
  rm)
    [ $# -gt 0 ] || usage "rm needs an id or --since TIME"
    if [ "$1" = --since ]; then
      [ $# -eq 2 ] && [[ "$2" =~ $TIME_FORM ]] || usage "rm --since needs a time such as 2026-11-13T17:00Z"
      since="$2"
    else
      for id in "$@"; do [[ "$id" =~ $ID_FORM ]] || usage "not an id: $id"; ids+=("$id"); done
    fi ;;
  block|unblock)
    [ $# -eq 1 ] && [[ "$1" =~ $CALL_FORM ]] || usage "$command needs one call"
    call="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" ;;
  "") usage "nothing to do" ;;
  *) usage "unknown command $command" ;;
esac

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
_all=""
sec() { [ -n "$_all" ] || _all="$("$BWS" secret list -o json --color no)"; python3 -c "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])" <<<"$_all"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The stored skeds' names, only those of exactly the endpoint's form, whatever the listing says.
names() { curl -sS --max-time 60 -u "$FU:$FP" "sftp://$FH$REMOTE/" | awk '{print $NF}' | grep -E '^[0-9a-f]{12}\.json$' | sort || true; }

# Every stored sked into $WORK/skeds/, in one session.
fetch_all() {
  mkdir -p "$WORK/skeds"
  local args=() f
  for f in $(names); do args+=(-o "$WORK/skeds/$f" "sftp://$FH$REMOTE/$f"); done
  [ ${#args[@]} -eq 0 ] || curl -sS --max-time 300 -u "$FU:$FP" "${args[@]}"
}

# The board made again by the endpoint; prints how many skeds it holds and whether it is closed.
refresh() {
  curl -sS --max-time 30 -X POST -H 'Content-Type: application/json' --data '{"action": "refresh"}' "$ENDPOINT" | python3 -c '
import json, sys
answer = json.load(sys.stdin)
if not answer.get("ok"):
    sys.exit("the board was not made again: %s" % answer.get("reason"))
board = answer["board"]
print("the board: %d skeds%s" % (len(board["skeds"]), ", closed" if board.get("closed") else ""))
'
}

# Removes the named files of the folder in one session (a file that is gone already is no error), then makes the board again.
remove() {
  local args=() f
  for f in "$@"; do args+=(-Q "*rm $REMOTE/$f"); done
  curl -sS --max-time 60 -u "$FU:$FP" "${args[@]}" "sftp://$FH$REMOTE/" >/dev/null
  echo "removed: $*"
  refresh
}

# blocked.txt into $WORK/blocked.txt (empty when the server has none).
fetch_blocked() { curl -sS --max-time 60 -u "$FU:$FP" -o "$WORK/blocked.txt" "sftp://$FH$REMOTE/blocked.txt" 2>/dev/null || : > "$WORK/blocked.txt"; }
upload() { curl -sS --max-time 60 -u "$FU:$FP" -T "$1" "sftp://$FH$REMOTE/$2" >/dev/null; }

case "$command" in
  --list)
    fetch_all
    python3 -c '
import json, pathlib, sys
rows = []
for path in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    try:
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    except ValueError:
        print("  %s  (not a sked)" % path.stem)
for r in sorted(rows, key=lambda r: str(r.get("from"))):
    print("  %s  posted %s  %-10s %s to %s  %-16s %s" % (r.get("id"), r.get("posted"), r.get("call"), r.get("from"), r.get("to"), r.get("dial"), str(r.get("token", ""))[:8]))
    if r.get("note"):
        print("      " + " ".join(str(r["note"]).split()))
print("%d stored" % len(rows))
' "$WORK/skeds" ;;
  rm)
    if [ -n "$since" ]; then
      fetch_all
      mapfile -t ids < <(python3 -c '
import datetime, json, pathlib, sys
def instant(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
since = instant(sys.argv[2])
for path in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        if instant(str(row["posted"])) >= since:
            print(path.stem)
    except (ValueError, KeyError):
        pass
' "$WORK/skeds" "$since")
      [ ${#ids[@]} -gt 0 ] || { echo "nothing posted since $since"; exit 0; }
    fi
    files=()
    for id in "${ids[@]}"; do [[ "$id" =~ $ID_FORM ]] && files+=("$id.json"); done
    remove "${files[@]}" ;;
  close)
    : > "$WORK/closed"
    upload "$WORK/closed" closed
    echo "closed: every add is refused"
    refresh ;;
  open)
    curl -sS --max-time 60 -u "$FU:$FP" -Q "*rm $REMOTE/closed" "sftp://$FH$REMOTE/" >/dev/null
    echo "open: adds are taken"
    refresh ;;
  blocked)
    fetch_blocked
    grep -v '^#' "$WORK/blocked.txt" | grep . || echo "no call is blocked" ;;
  block|unblock)
    fetch_blocked
    grep -vxF "$call" "$WORK/blocked.txt" > "$WORK/kept.txt" || true
    [ "$command" = unblock ] || echo "$call" >> "$WORK/kept.txt"
    upload "$WORK/kept.txt" blocked.txt
    echo "${command}ed: $call"
    refresh ;;
  refresh)
    refresh ;;
esac
