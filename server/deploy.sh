#!/usr/bin/env bash
# Upload the version page, and with --site the project page, to the shared hosting account, in one SFTP session each.
#
#   server/deploy.sh          # the version page (version.php, latest.php, log/.htaccess) to both of its places:
#                             #   neo.oh2gba.eu/version.php, which the copies from 0.16 on ask, and oh2gba.eu/neoaprs/version.php, which the copies before ask
#   server/deploy.sh --site   # the same, and the project page (site/ as it is, and server/neo/ as it is: the .htaccess, the page-view endpoint, the Send logs endpoint support/send.php with its .user.ini, the sked board's endpoint api/v1/skeds.php, and private/.htaccess) to neo.oh2gba.eu
#   server/deploy.sh --list   # show what would be uploaded, don't touch the network
#
# Only these files, and of the folders only what git tracks (`git ls-files`): a file that is not tracked or is ignored is never uploaded, and the ones skipped are named. Nothing else of either folder is touched,
# and message.txt, the logs, the stored support files and skeds, and the sked board skeds.json, which live on the server only, are never uploaded or removed (a skeds.json in site/ would be uploaded over the
# live board, so the upload refuses to start while there is one).
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
    tracked "$SITE" | while IFS= read -r f; do printf '%s\t%s/%s\n' "$SITE/$f" "$NEO" "$f"; done
    tracked "$ROOT/neo" | while IFS= read -r f; do printf '%s\t%s/%s\n' "$ROOT/neo/$f" "$NEO" "$f"; done
  fi
}

# The files of a folder that git tracks and that exist, relative to it, sorted. One that git does not track (new, or ignored) is not among them, and neither is a link or a submodule: only a regular file (mode 100644 or 100755).
tracked() { git -C "$1" ls-files -s -z | while IFS= read -r -d '' e; do if [[ $e == 100644\ * || $e == 100755\ * ]] && [ -f "$1/${e#*$'\t'}" ]; then printf '%s\n' "${e#*$'\t'}"; fi; done; }

# Stops (exit 2) when git tracks, under the two folders, a link or a submodule (curl would send what it points at) or a name with a control character (a line end or a tab would make it two paths in the manifest).
refuse_odd() {
  local d e mode f
  for d in "$SITE" "$ROOT/neo"; do
    while IFS= read -r -d '' e; do
      mode="${e%% *}"; f="${e#*$'\t'}"
      case "$mode" in 100644|100755) ;; *) echo "deploy.sh: $d/$f is tracked as a link or a submodule, not a file: nothing is uploaded" >&2; exit 2 ;; esac
      if [[ $f == *[[:cntrl:]]* ]]; then echo "deploy.sh: a tracked name under $d has a control character: nothing is uploaded" >&2; exit 2; fi
    done < <(git -C "$d" ls-files -s -z)
  done
}

# Says on stderr which files of the two folders are left out because git does not track them.
say_skipped() {
  local d f
  for d in "$SITE" "$ROOT/neo"; do
    git -C "$d" ls-files -z --others | sort -z | while IFS= read -r -d '' f; do printf 'skipped, not tracked by git: %s/%s\n' "$d" "$f" >&2; done
  done
}

git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "deploy.sh: $ROOT is no git checkout: only tracked files are uploaded" >&2; exit 2; }
for f in "${PAGE[@]}"; do
  git -C "$ROOT" ls-files --error-unmatch -- "$f" >/dev/null 2>&1 || { echo "deploy.sh: $ROOT/$f is not tracked by git" >&2; exit 2; }
done

with_site=0
case "${1:-}" in
  --site) with_site=1; refuse_odd; say_skipped ;;
  --list) with_site=1; refuse_odd; say_skipped; manifest | awk -F'\t' '{printf "  %s\n", $2}'; exit 0 ;;
  "") ;;
  *) echo "deploy.sh: unknown option $1" >&2; exit 2 ;;
esac
[ ! -e "$SITE/skeds.json" ] || { echo "deploy.sh: site/skeds.json would be uploaded over the live sked board; remove it" >&2; exit 1; }

ENVFILE="${SECRETS_FILE:-$(d="$ROOT"; until [ -f "$d/.secrets" ] || [ "$d" = / ]; do d="$(dirname "$d")"; done; echo "${d%/}/.secrets")}"
[ -f "$ENVFILE" ] || [ -n "${SECRETS_FILE:-}" ] || ENVFILE="$ROOT/../../oh2gba/.secrets"   # a file that was named and is not there is never replaced by another one
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
