#!/bin/bash
# Tests a rendered install.sh against a wheel that is not on the release yet: a fresh HOME, a PATH without uv (so the script has to install it with Astral's installer), a systemctl that only writes down
# how it was called (a CI runner has no systemd user session), the wheel served from a port of the loopback through NEOAPRS_WHEEL_URL. The script is run twice, the second time as an update.
#   packaging/test-install.sh INSTALL_SH WHEEL
# Needs the network (uv's installer, Python 3.13, the dependencies). Exit code 0: the script ended well both times and `neoaprs --version` says the wheel's version.
set -euo pipefail
script="$(realpath "$1")"
wheel="$(realpath "$2")"
version="$(basename "$wheel" | cut -d- -f2)"

work="$(mktemp -d)"
trap 'kill "${server:-0}" 2>/dev/null || true; rm -rf "$work"' EXIT
mkdir -p "$work/home" "$work/fakebin" "$work/serve"
cp "$wheel" "$work/serve/"

cat > "$work/fakebin/systemctl" <<'FAKE'
#!/bin/sh
echo "systemctl $*" >> "$FAKE_LOG"
case "$*" in *is-active*) echo active ;; *is-enabled*) echo enabled ;; esac
exit 0
FAKE
cp "$work/fakebin/systemctl" "$work/fakebin/loginctl"
sed -i 's/^echo "systemctl/echo "loginctl/' "$work/fakebin/loginctl"
chmod +x "$work/fakebin/systemctl" "$work/fakebin/loginctl"

port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$work/serve" >/dev/null 2>&1 &
server=$!
sleep 1

wheel_name="$(basename "$wheel")"
export HOME="$work/home" FAKE_LOG="$work/systemctl.log" NEOAPRS_WHEEL_URL="http://127.0.0.1:$port/$wheel_name"
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_BIN_HOME UV_INSTALL_DIR UV_FROZEN UV_CACHE_DIR NEOAPRS_DATA_DIR VIRTUAL_ENV
export PATH="$work/fakebin:/usr/bin:/bin"
command -v uv >/dev/null && { echo "test-install: uv is on the test PATH ($(command -v uv)); the script would not install it" >&2; exit 1; }

echo "=== first run: nothing is installed"
sh "$script"
test -x "$HOME/.local/bin/uv" || { echo "test-install: the script did not install uv" >&2; exit 1; }
out="$("$HOME/.local/bin/neoaprs" --version)"
test "$out" = "NeoAPRS $version" || { echo "test-install: neoaprs --version says '$out', not 'NeoAPRS $version'" >&2; exit 1; }
unit="$HOME/.config/systemd/user/neoaprs.service"
test -f "$unit" || { echo "test-install: no unit file at $unit" >&2; exit 1; }
grep -q "enable --now" "$FAKE_LOG" || { echo "test-install: the unit was not enabled; systemctl was called:"; cat "$FAKE_LOG"; exit 1; }
! grep -q try-restart "$FAKE_LOG" || { echo "test-install: a first install restarted the service" >&2; exit 1; }

echo "=== second run: an update"
: > "$FAKE_LOG"
sh "$script"
out="$("$HOME/.local/bin/neoaprs" --version)"
test "$out" = "NeoAPRS $version" || { echo "test-install: after the update neoaprs --version says '$out'" >&2; exit 1; }
grep -q "try-restart" "$FAKE_LOG" || { echo "test-install: the update did not restart the service; systemctl was called:"; cat "$FAKE_LOG"; exit 1; }
echo "test-install: ok ($out; unit at $unit)"
