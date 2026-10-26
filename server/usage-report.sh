#!/usr/bin/env bash
# Fetch the start logs written by version.php and print a summary of how many copies of NeoAPRS asked.
# Nothing in the logs identifies anyone: each line is
#   <UTC minute>  <program version>  <platform>  <id>
# where the id is the random number an installation made once for itself (versions that do not send one, and lines
# written before there was one, have - or no fourth column). The report counts the distinct ids per month, and per
# version and platform for the latest month, and says how many requests came without an id.
# The logs are kept in server/logs/ (not in git).
#
# Credentials come from Bitwarden Secrets Manager (ftp_server/ftp_login/ftp_pw); the token is the first
# line of a .secrets file: SECRETS_FILE, else the first one found searching upwards from here, else
# ../../oh2gba/.secrets.
case "${1:-}" in -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;; esac
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # server/
REMOTE="${VERSION_PAGE_REMOTE:-/public_html/oh2gba.eu/neoaprs}"

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"
[ -f "$ENVFILE" ] || { echo "no .secrets file (set SECRETS_FILE)" >&2; exit 1; }
BWS="${BWS:-$(command -v bws || echo "$HOME/.local/bin/bws")}"
export BWS_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-$(grep -v '^#' "$ENVFILE" | head -1 | tr -d '\r\n')}"
sec() { "$BWS" secret list -o json --color no | python3 -c \
  "import json,sys;print([s['value'] for s in json.load(sys.stdin) if s['key']=='$1'][0])"; }
FH=$(sec ftp_server); FU=$(sec ftp_login); FP=$(sec ftp_pw)

mkdir -p "$ROOT/logs"
for f in $(curl -sS --max-time 60 -u "$FU:$FP" "sftp://$FH$REMOTE/log/" | awk '{print $NF}' | grep -E '^starts-[0-9]{4}-[0-9]{2}\.log$'); do
  curl -sS --max-time 120 -u "$FU:$FP" -o "$ROOT/logs/$f" "sftp://$FH$REMOTE/log/$f"
done

cat "$ROOT"/logs/starts-*.log 2>/dev/null | awk -F'\t' '
  { day=substr($1,1,10); days[day]++; ver[$2]++; os[$3]++; n++ }
  END {
    printf "%d starts in total\n\nPer day:\n", n
    for (d in days) printf "  %s  %d\n", d, days[d] | "sort"
    close("sort")
    printf "\nPer version:\n"; for (v in ver) printf "  %-12s %d\n", v, ver[v] | "sort"
    close("sort")
    printf "\nPer platform:\n"; for (o in os) printf "  %-16s %d\n", o, os[o] | "sort"
  }'

cat "$ROOT"/logs/starts-*.log 2>/dev/null | awk -F'\t' '
  { n++; m = substr($1,1,7); if (m > last) last = m
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
  }'
