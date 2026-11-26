#!/usr/bin/env bash
# Fetch the support files that people sent with Send logs (server/neo/support/send.php stores them)
# and show what is new.
#
#   server/support-fetch.sh          # download every file not fetched yet into server/support/ and
#                                    print who sent it, with the note
#   server/support-fetch.sh --list   # list what the server holds (reference, time, call, version,
#                                    platform, size), and mark what is already here; downloads
#                                    nothing
#
# The server keeps each file as NEO-YYYYmmdd-HHMM-XXXX.zip with NEO-...json beside it (time, call,
# email, version, platform, size, note). They are fetched into server/support/ (not in git), zip and json
# together, and a file already there is never fetched again. A note sent alone (the person took the
# file off) is its json only, which says `"file": false`: no zip is asked for it. The server removes
# a file 30 days after it was sent (at the next upload it accepts): fetch before. To read one: unzip
# it and open summary.txt first.
#
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw); the token is the
# first line of a .secrets file: SECRETS_FILE, else the first one found searching upwards, else
# ../../oh2gba/.secrets.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # server/
REMOTE="${PROJECT_PAGE_REMOTE:-/public_html/neo}/private/support"
LOCAL="$ROOT/support"
list_only=0
case "${1:-}" in
  --list) list_only=1 ;;
  "") ;;
  *) echo "support-fetch.sh: unknown option $1" >&2; exit 2 ;;
esac

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || [ -n "${SECRETS_FILE:-}" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"  # a named file that is missing is never replaced by another one
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
sec() { "$BWS" secret list -o json --color no | python3 -c \
  "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)
# The login goes to curl as a config on stdin, never on its command line.
quote() { local s=${1//\\/\\\\}; printf '%s' "${s//\"/\\\"}"; }
CURL_USER="user = \"$(quote "$FU"):$(quote "$FP")\""
fcurl() { curl -K - "$@" <<<"$CURL_USER"; }

mkdir -p "$LOCAL"
# A file counts once its json is there: the server writes the json last. Only names of exactly that
# form are used, whatever the listing says.
refs=$(fcurl -sS --max-time 60 "sftp://$FH$REMOTE/" | awk '{print $NF}' | grep -E '^NEO-[0-9]{8}-[0-9]{4}-[0-9A-F]{4,8}\.json$' | sed 's/\.json$//' | sort || true)

# Whether the json at $1 says a file came with the note (a note alone has "file": false and no zip).
has_file() { python3 -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1], encoding="utf-8")).get("file", True) else 1)' "$1"; }

# One line for a file from its json: the reference, time, call, the address for a reply when there
# is one, version, platform and size ("no file" for a note alone), and under it the note.
show() {
  python3 -c '
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
note = " ".join(str(m.get("note", "")).split())
size = "%d KB" % (int(m.get("size", 0)) // 1024) if m.get("file", True) else "no file"
email = " ".join(str(m.get("email") or "").split())
who = "%-12s %s " % (m.get("call") or "-", email) if email else "%-12s" % (m.get("call") or "-")
print("  %s  %s  %s %-10s %-14s %s" % (m.get("ref", "?"), m.get("time", "?"), who, m.get("version") or "-", m.get("platform") or "-", size))
if note:
    print("      " + note[:300] + ("..." if len(note) > 300 else ""))
' "$LOCAL/$1.json"
}

new=0
for ref in $refs; do
  if [ -f "$LOCAL/$ref.json" ] && { [ -f "$LOCAL/$ref.zip" ] || ! has_file "$LOCAL/$ref.json"; }; then
    if [ "$list_only" = 1 ]; then echo "here:"; show "$ref"; fi
    continue
  fi
  if [ "$list_only" = 1 ]; then
    fcurl -sS --max-time 60 -o "$LOCAL/$ref.json" "sftp://$FH$REMOTE/$ref.json"
    echo "new:"; show "$ref"; rm -f "$LOCAL/$ref.json"
    continue
  fi
  fcurl -sS --max-time 60 -o "$LOCAL/$ref.json.part" "sftp://$FH$REMOTE/$ref.json"
  if has_file "$LOCAL/$ref.json.part"; then
    fcurl -sS --max-time 300 -o "$LOCAL/$ref.zip.part" "sftp://$FH$REMOTE/$ref.zip"
    mv "$LOCAL/$ref.zip.part" "$LOCAL/$ref.zip"
  fi
  mv "$LOCAL/$ref.json.part" "$LOCAL/$ref.json"
  if [ "$new" = 0 ]; then echo "New support files, in $LOCAL:"; fi
  show "$ref"; new=$((new + 1))
done
if [ "$list_only" = 0 ]; then echo "$new new, $(echo "$refs" | grep -c . || true) on the server in all"; fi
