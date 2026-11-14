#!/usr/bin/env bash
# Fetch the start logs written by version.php and print a summary of how many copies of NeoAPRS asked.
#   usage-report.sh [--ignore FILE] [--local]
# Nothing in the logs identifies anyone: each line is
#   <UTC minute>  <program version>  <platform>  <id>
# where the id is the random number an installation made once for itself (versions that do not send one, and lines
# written before there was one, have - or no fourth column). The report counts the distinct ids per month, and per
# version and platform for the latest month, and says how many requests came without an id.
# The logs are kept in server/logs/ (not in git).
#
# Two kinds of requests are not users' and are left out of every count, each said in one line at the end:
#   - id 0: a run from the source tree, or one that has `neoaprs db set update/not_counted true` (the developers' runs);
#   - the numbers of the ignore list: a plain file of ids, one to a line, with comments after #, blank lines, CRLF line ends and a byte-order mark allowed.
#     It is read when it is there, from --ignore FILE, else `usage-ignore` in the folder of the .secrets file (below). It is
#     the owner's own file, outside the repository: git does not track it and server/deploy.sh never uploads it. It takes out
#     numbers that were sent before id 0 existed (your own machines, the test machines), for every month. The number of an
#     installation is the row update/install_id: on that machine `neoaprs db get update/install_id` prints it.
# --local fetches nothing and needs no .secrets file: it reports on the logs already in server/logs/.
#
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw); the token is the first
# line of a .secrets file: SECRETS_FILE, else the first one found searching upwards from here, else
# ../../oh2gba/.secrets.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

IGNORE=""
LOCAL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --ignore) [ $# -ge 2 ] || { echo "--ignore needs a file" >&2; exit 2; }; IGNORE="$2"; shift 2 ;;
    --local) LOCAL=1; shift ;;
    *) echo "usage: usage-report.sh [--ignore FILE] [--local]" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # server/
REMOTE="${VERSION_PAGE_REMOTE:-/public_html/oh2gba.eu/neoaprs}"

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"
EXPLICIT_IGNORE="$IGNORE"
[ -n "$IGNORE" ] || IGNORE="$(dirname "$ENVFILE")/usage-ignore"
if [ -n "$EXPLICIT_IGNORE" ] && [ ! -f "$IGNORE" ]; then echo "no ignore list at $IGNORE" >&2; exit 1; fi
if [ -z "$LOCAL" ]; then
  [ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
  BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
  export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
  sec() { "$BWS" secret list -o json --color no | python3 -c \
    "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])"; }
  FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)

  mkdir -p "$ROOT/logs"
  # The page writes its log in both of its places (server/deploy.sh): the old folder, which the copies before 0.16 ask, and the project's own name, which the later ones ask. The lines of a month from both are one file here.
  NEO="${PROJECT_PAGE_REMOTE:-/public_html/neo}"
  for place in "$REMOTE" "$NEO"; do
    for f in $(curl -sS --max-time 60 -u "$FU:$FP" "sftp://$FH$place/log/" | awk '{print $NF}' | grep -E '^starts-[0-9]{4}-[0-9]{2}\.log$'); do
      curl -sS --max-time 120 -u "$FU:$FP" -o "$ROOT/logs/$f.part" "sftp://$FH$place/log/$f"
      cat "$ROOT/logs/$f.part" >> "$ROOT/logs/$f.new" && rm -f "$ROOT/logs/$f.part"
    done
  done
  for f in "$ROOT"/logs/*.new; do [ -f "$f" ] && sort -u "$f" > "${f%.new}" && rm -f "$f"; done
fi

compgen -G "$ROOT/logs/starts-*.log" > /dev/null || { echo "no start logs in $ROOT/logs" >&2; exit 1; }

# The ignore list (when there is one) goes to awk by name; `left_out` says whether a request is not a user's, and counts it.
NOTE=""
[ -f "$IGNORE" ] || { NOTE="(no ignore list at $IGNORE)"; IGNORE=""; }
PRELUDE='
  BEGIN { if (ignore != "") { while ((getline line < ignore) > 0) { sub(/#.*/, "", line); if (split(line, w, " ") > 0) { x = tolower(w[1]); gsub(/[^0-9a-f]/, "", x); if (x != "") listed[x] = 1 } } close(ignore) } }
  function left_out(id) {
    if (id == "0") { dev++; return 1 }
    if (id in listed) { ign++; seen[id] = 1; return 1 }
    return 0
  }'

cat "$ROOT"/logs/starts-*.log 2>/dev/null | awk -F'\t' -v ignore="$IGNORE" "$PRELUDE"'
  { if (left_out($4)) next; day=substr($1,1,10); days[day]++; ver[$2]++; os[$3]++; n++ }
  END {
    printf "%d starts in total\n\nPer day:\n", n
    for (d in days) printf "  %s  %d\n", d, days[d] | "sort"
    close("sort")
    printf "\nPer version:\n"; for (v in ver) printf "  %-12s %d\n", v, ver[v] | "sort"
    close("sort")
    printf "\nPer platform:\n"; for (o in os) printf "  %-16s %d\n", o, os[o] | "sort"
  }'

cat "$ROOT"/logs/starts-*.log 2>/dev/null | awk -F'\t' -v ignore="$IGNORE" "$PRELUDE"'
  { if (left_out($4)) next; n++; m = substr($1,1,7); if (m > last) last = m
    if ($4 ~ /^[0-9a-f]+$/) { id[m SUBSEP $4] = 1; ver[m SUBSEP $2 SUBSEP $4] = 1; plat[m SUBSEP $3 SUBSEP $4] = 1 } else none++ }
  END {
    for (k in id) { split(k, a, SUBSEP); months[a[1]]++ }
    printf "\nInstallations (distinct ids) per month:\n"
    for (m in months) printf "  %s  %d\n", m, months[m] | "sort"
    close("sort")
    for (k in ver) { split(k, a, SUBSEP); if (a[1] == last) v[a[2]]++ }
    for (k in plat) { split(k, a, SUBSEP); if (a[1] == last) p[a[2]]++ }
    printf "\nInstallations in %s, per version:\n", last; for (x in v) printf "  %-12s %d\n", x, v[x] | "sort"
    close("sort")
    printf "\nInstallations in %s, per platform:\n", last; for (x in p) printf "  %-16s %d\n", x, p[x] | "sort"
    close("sort")
    printf "\n%d of %d requests came without an id (older versions)\n", none, n
    printf "%d requests came from developers\047 runs (id 0)\n", dev
    if (ignore != "") { for (k in seen) kept++; printf "%d requests came from %d number%s of the ignore list\n", ign, kept, (kept == 1 ? "" : "s") }
  }'
[ -n "$NOTE" ] && echo "$NOTE"
exit 0
