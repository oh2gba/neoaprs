# The command line and troubleshooting

NeoAPRS is a Python package with one command, `neoaprs`. `neoaprsw` is the same without a console window, which is how Windows starts the daemon, and `neoaprs-app` is the [desktop app](desktop.md). `python -m neoaprs` is the same command.

`neoaprs` with no command, or `neoaprs run`, is the daemon. The rest is the tools around it, each with `--help`. `--data DIR` is the data folder everywhere (the default is in [start.md](start.md#the-data-folder), and `NEOAPRS_DATA_DIR` sets it).

## The daemon

| flag | what it does |
|---|---|
| `--data DIR` | the data folder |
| `--port PATH` | the radio's port for this run only. The setting `serial/port` is not changed or stored; a replay's address, for instance. The kinds of port are in [radio.md](radio.md#the-port) |
| `--web-port N` | the page's port for this run only; 0 takes a free one |
| `--debug` | logs more |
| `--version` | says the version |

## The tools

| command | what it does |
|---|---|
| `neoaprs [run] [--data DIR] [--port PATH] [--web-port N] [--debug] [--version]` | the daemon, until it is told to stop (Ctrl+C, SIGTERM) |
| `neoaprs service install\|remove\|status\|logs` | start NeoAPRS at login, the way the system does it ([install.md](install.md#start-at-login)); `--linger` on Linux, `-n N` for `logs` |
| `neoaprs map [--radius KM] [--maxzoom Z] [--source SRC] [--lat DEG --lon DEG] [--dry-run]` | makes the base map as the page's Download button does ([page.md](page.md#the-base-map)): the map of `map/radius_km` round the station down to `map/maxzoom` into `basemap.pmtiles` (the world map ships with NeoAPRS). It fetches the `pmtiles` tool when it is missing. The flags go over the settings, and `--dry-run` says the size and changes nothing |
| `neoaprs db list\|get KEY\|set KEY VALUE\|stations\|packets -n N` | looks at and changes the database: the settings (`set` is checked like the daemon checks it), the stations the daemon knows, the latest packets. The daemon may be running |
| `neoaprs open [--data DIR] [--no-browser] [--timeout SEC]` | opens the page in the default browser. When no daemon holds the data folder it starts one first, detached (on Windows `neoaprsw.exe run` with no console window, elsewhere a child whose output goes to `neoaprs.log`). It waits for the page to answer, so the port can be any of the ten from `web/port`, and prints the address. `--no-browser` only starts and prints. On failure it says why and exits 1. The Start menu's NeoAPRS on Windows runs it |
| `neoaprs stop [--data DIR] [--timeout SEC]` | ends the daemon that holds the data folder, cleanly, on every system, and waits until it has ended. Exit 0 when it ended or none was running, 1 after `--timeout` (30 s). It needs no port and no key: whoever can write to the data folder (private to you) could end the process as well. The Start menu's Stop NeoAPRS and the uninstaller run it |
| `neoaprs replay [FILE] [--interval S] [--loop] [--port P]` | plays a capture as a KISS TNC on a TCP port of this computer and prints `socket://127.0.0.1:PORT` ([start.md](start.md#without-the-radio)). With no FILE it plays the sample capture inside the package. `--pty` plays on a pseudo-terminal instead (Linux, macOS) |
| `neoaprs gps-replay [--at LAT,LON] [--kmh N] [--port P] [--interval S]` | plays a made-up drive as a gpsd on `127.0.0.1:2948` (the first line it prints), so that NeoAPRS can be tried as a moving station with no car and no GPS: choose **A GPS via gpsd** on the Beacon tab and give `127.0.0.1:2948` as the gpsd address ([beacon.md](beacon.md#mobile-operation)). The car sets off, goes round a rectangle of streets at `--kmh` (50 by default), slows for the corners and stops for a while, lap after lap, from `--at` (60.43,24.145 by default) |
| `neoaprs capture OUT [--port PORT] [--seconds N] [--baud N] [--force]` | records the radio's serial port into a file byte for byte and shows its KISS frames, to make test files or to find the radio's port. Without `--port` it probes the usual USB serial names on Linux |
| `neoaprs app [--data DIR] [--tray] [--quit] [--timeout SEC]` | the [desktop app](desktop.md); needs `neoaprs[app]`. `--tray` starts with the window hidden, `--quit` ends the app that is running |
| `neoaprs support [--data DIR] [--out FOLDER] [--show] [--pause]` | makes the file to send when something does not work ([support.md](support.md)): the logs, the settings without the access key, the checks of `neoaprs doctor` and the latest packets, in one zip on your Desktop (your home folder when there is none; `--out` names another folder). It needs no daemon, works when the daemon will not start, and changes nothing. It prints the path of the file and who to send it to. `--show` shows the file in the file manager, and `--pause` waits for Enter before the window closes (when it runs in a console). The Start menu's NeoAPRS support logs on Windows runs it |
| `neoaprs doctor` | the checklist below |

The table "Environment variables" of [`CONVENTIONS.md`](../../CONVENTIONS.md) lists every `NEOAPRS_*` variable the program reads.

## neoaprs doctor

`neoaprs doctor` prints one line for each thing NeoAPRS needs, marked `ok`, `warn` or `FAIL`, and under each line that is not ok the command or step that cures it. It changes nothing: the database is opened for reading and the ports are listed and not opened. The exit code is 1 when something failed and 0 otherwise; a warning is not a failure.

It checks:

- **Python**: 3.13 or newer.
- **The data folder**: made yet, writable.
- **The database**: readable, and its version against the one this NeoAPRS uses. A file of a newer NeoAPRS fails; an older one is migrated at the next start.
- **The call**: `station/call`. It says "set your call on the page" while it is empty or cannot transmit.
- **The serial ports** the system lists, with the description and the USB `VID:PID` of each. That is also what to paste into a bug report.
- **On Linux**, whether you are in the group that owns the serial devices (`dialout`, `uucp` on Arch), and whether **brltty** or **ModemManager** are installed. They take USB serial adapters: brltty makes a CH340, CP210x or FTDI port vanish as it is plugged in, and ModemManager probes new ports as modems. It gives the way to remove or stop them.
- **On Linux with KDE**, whether Firefox is a Flatpak whose pop-ups can go missing. It prints the two `flatpak override` commands and never runs them ([notifications.md](notifications.md#pop-ups-do-not-appear)).
- Whether a daemon holds the data folder, where its page is, and whether it answers.
- The base map files and their sizes.
- Whether the service is set up.

## When something does not work

Start with `neoaprs doctor`, then look at the radio status at the top of the Radio group in the Settings tab, and at the log.

- **The log** is `neoaprs.log` in the data folder (`neoaprs service logs` prints its end; `--debug` logs more). It names the port, what was sent to the TNC and what came back. The footer under the panel says "Radio: ..." whenever the radio is not ok ([page.md](page.md#the-header-and-the-footer)).
- **"Permission denied" on the port** (Linux): join the group that owns serial devices, `sudo usermod -aG dialout $USER`, then log out and in.
- **The port vanishes a moment after plugging in:** brltty. **The port is held:** ModemManager. `doctor` says how to remove or stop them; so does [`docs/RADIOS.md`](../RADIOS.md#permissions-on-linux).
- **The radio is silent:** the line is open and the radio does not answer. Check the cable, the speed and that the radio is on. A radio switched on again is found within a minute ([radio.md](radio.md#is-the-radio-there)).
- **Nothing is transmitted:** the call must be set, and not `N0CALL`, `NOCALL` or `MYCALL` ([start.md](start.md#the-setup-guide)). The radio must be usable. A beacon that is due waits for it. The Beacon choice must not be Off for an automatic beacon ([beacon.md](beacon.md#beacon-off)), and `station/transmit` must not be `false` ([beacon.md](beacon.md#rx-only)).
- **Garbage or nothing on a serial port:** the wrong speed or port. The radio guide lists the speed of each radio ([`docs/RADIOS.md`](../RADIOS.md#not-working)).
- **The search finds the wrong device, or skips yours:** [radio.md](radio.md#finding-the-radio).
- **A moving station sends nothing:** it has no fresh fix, or the Beacon choice is Off. The beacon status at the top of the Beacon tab says which, and why there is no fix ([beacon.md](beacon.md#mobile-operation)).
- **No detailed map:** the world is there from the start; the detailed map of your area is made when you first set a place, and again in the Settings tab, Map ([page.md](page.md#the-base-map)). It needs the internet once. "No base map" or "The map file cannot be read" means the file that ships with NeoAPRS is damaged: install again.
- **The page does not open from another device:** the setting **Allow access from the network** is off, the name you used is not one of the computer's (`web/allowed_hosts`), or the firewall blocks the port ([network.md](network.md)).
- **The daemon ends at once with exit code 2:** another NeoAPRS is running on the same data folder, or the database was made by a newer NeoAPRS or is not a database.
- **An AppImage that does not start:** no FUSE. Use `--appimage-extract-and-run` ([install.md](install.md#linux-appimage)).
- **A message you sent shows a cross:** it failed after its attempts, or the station rejected it ([messages.md](messages.md#attempts)). The Packets tab shows what was sent and heard.

When you report a bug, say the version (`neoaprs --version`), the system and the `doctor` output, and attach the end of `neoaprs.log`. Issues go to <https://github.com/oh2gba/neoaprs/issues>.
