# The first start

## Starting NeoAPRS

- **Windows with the installer:** open **NeoAPRS** in the Start menu. The [desktop app](desktop.md) opens a window and starts the daemon.
- **Linux AppImage:** run the file with no arguments.
- **A service** (the .deb, the install line or `neoaprs service install`): it is already running. `neoaprs open` opens the page in your browser, starting NeoAPRS first if it is not running.
- **By hand:** `neoaprs` runs the daemon until you press Ctrl+C. Open <http://127.0.0.1:7303/>.

If the port says *permission denied* on Linux, add yourself to the group that owns serial devices: `sudo usermod -aG dialout $USER` (`uucp` on Arch), then log out and in. `neoaprs doctor` says what else keeps the radio from working ([commands.md](commands.md#neoaprs-doctor)).

## The setup guide

On a fresh install the page opens a guide in five steps. It opens by itself once, when NeoAPRS has no call. The amber **no call set** button in the header and **Run the setup guide again** in the Settings tab open it again, and what you typed is still there.

1. **Call.** Your call sign, with an SSID if you use one.
2. **Position.** Press **Choose on map** and click where you are, or drag the pin. Or click the place beside the button ("Not set" at first, which opens by itself) and type latitude and longitude in decimal degrees: north and east positive, south and west negative (Sydney is -33.87, 151.21). A Maidenhead locator works too. It is the same row as the Location of the Beacon tab ([beacon.md](beacon.md#the-location)).
3. **Symbol.** The twelve usual ones are on top; a click on the symbol under them opens the picker with every symbol.
4. **Radio.** The type of TNC, and for a serial one the port and speed, for a TCP one the host and port ([radio.md](radio.md)).
5. **Map.** The radius of the detailed map, which is already being downloaded, with its progress; at the right end of the row the plain **Download map** button makes it again for another radius ([page.md](page.md#the-base-map)).

The map under the guide is the world, from the first second. When you press **Next** on the Position step, NeoAPRS saves the place and starts making the detailed map of your area, so that it is there at the end of the guide; a quiet line says "Downloading the map of your area…" ([page.md](page.md#the-base-map)).

**Finish** saves what you set. On a station that has no call and no beacon yet, it also sets the beacon to every 30 minutes, and the last step says "Beacon every 30 min". Run again on a station that already has a call, the guide leaves the beacon alone.

**Nothing is transmitted until a call is set.** While the call is empty, `N0CALL`, `NOCALL`, `MYCALL` or not an amateur call (3 to 6 letters and digits, with at least one of each), NeoAPRS only listens: no beacon, status, message, ack, object, bulletin or answer to a query. A message is refused with "set your call first", and the header says "no call set". The commands that put the TNC in KISS are not transmissions and go on.

## The data folder

Everything NeoAPRS keeps is in one folder, one daemon to a folder. A second daemon on the same folder ends at once with exit code 2.

| where | folder |
|---|---|
| Linux | `~/.local/share/neoaprs` (`$XDG_DATA_HOME/neoaprs`) |
| Windows | `%LOCALAPPDATA%\NeoAPRS` |
| macOS | `~/Library/Application Support/NeoAPRS` |

`--data DIR` chooses another folder, and `NEOAPRS_DATA_DIR` sets the default (the table "Environment variables" of [`CONVENTIONS.md`](../../CONVENTIONS.md) lists every variable).

- `neoaprs.sqlite` is everything NeoAPRS keeps: the settings, every packet heard or sent, the messages, the message board, your own objects, items and bulletins, the weather of the weather stations, and the stations (a cache the daemon rebuilds from the packets). It is private to your user and is migrated at the start; a copy of it is made into `backup/` before a migration changes it.
- Packets, weather observations and stations older than 7 days are removed once a day. The weather graphs reach back 7 days. Messages and bulletins stay until you delete them.
- `neoaprs.log` is the log, rotated (20 MB, five files), with every packet as the TNC2 line and what it is. Warnings and errors, and the lines of a database migration (what an upgrade changed), also go to stderr, which `systemctl status` and the journal show.
- `basemap.pmtiles` is the detailed base map of your area (the world map ships with NeoAPRS and is not in this folder, unless an earlier version made `basemap-world.pmtiles` here); `bin/` holds the `pmtiles` tool; `tls/` holds the certificates of the secure connection.
- `neoaprs.lock` shows that a daemon holds the folder. The desktop app keeps `neoaprs-app.log`, `neoaprs-app.json`, `neoaprs-app.lock`, `neoaprs-app.port` and `webview/` there too.

## How settings apply

The Settings tab and the Beacon tab have no Save button and no Revert. A setting is put in force as you change it, as on a phone.

- A tickbox, a choice from a list, the port list, the symbol and **Choose on map** apply at once.
- A field you type in (the call, the comment, the position, the path) applies when you press Enter or leave the field, never while you type, so a half-typed call or position is never beaconed. Esc puts back the value in force.
- The page checks the value first and says what is wrong under the field. Nothing is sent until it is right.
- Fields that belong together are sent as one change: the latitude and the longitude, and the TCP host and port (the TNC restarts once, not twice).
- Nothing is shown beside a field when a change applies, so nothing on the page moves. The toast that floats over the page, and a screen reader's "Saved", are the confirmation.
- When the daemon refuses a change, the reason is under the field, what you typed stays in it and the old value stays in force.
- After a change a small toast, such as "Beacon interval changed · Undo", stays for ten seconds. **Undo** puts the old values back in one step. With several quick changes the toast is for the latest and the earlier ones stay applied.
- Only a change that could cut you off asks first: turning off **Allow access from the network** on a page opened from another device.
- The changes go to the daemon one at a time, in the order they were made. **Beacon now** and **Send status now** wait while a change is being saved.

Choosing the radio as the status source fills in the usual rigctld address, `127.0.0.1:4532`, so the choice is valid at once. A comment too long for the power you set says "Shorten the comment to 36 first" on the power.

The forms carry no sentences under the fields: a label, a placeholder with the default, a unit, and a tooltip at the most. A field that a non-developer may not understand has a small **(i)** that opens a few plain sentences; Esc, a click outside or moving on closes it. What each setting does is in [settings.md](settings.md).

`neoaprs db list` shows the settings and `neoaprs db set KEY VALUE` changes one. The value is checked like the daemon checks it, and the daemon takes it at its next start. A change made on the page is put in force at once.

## Without the radio

`neoaprs replay` plays a capture as a KISS TNC on a TCP port of this computer, so NeoAPRS runs without a radio on any system.

```bash
neoaprs replay                                                  # the sample capture of the package; prints socket://127.0.0.1:PORT
neoaprs run --data data --port socket://127.0.0.1:PORT          # in another terminal
neoaprs db --data data stations                                 # and in a third
neoaprs db --data data packets
```

With no file it plays the sample capture inside the package, three minutes of a TH-D7. `neoaprs capture` records a capture from your radio. Nothing is sent while nobody is connected, and the frames go on from where they were when the daemon connects again. `--port` is for this run only; the setting `serial/port` is not changed.

A moving station can be tried without a car in the same way: `neoaprs gps-replay` plays a drive as a gpsd, and the Beacon tab's **A GPS via gpsd** reads it ([beacon.md](beacon.md#mobile-operation)).

## Stopping NeoAPRS

- Ctrl+C or a termination signal ends the daemon cleanly: it finishes what the database was asked, closes it and exits with code 0. On Windows Ctrl+C, Ctrl+Break and the termination signal do the same.
- `neoaprs stop` ends the daemon that holds the data folder, on every system, and waits until it has ended. It exits 0 when it ended or none was running, and 1 after 30 seconds. A service manager that restarts the daemon starts it again; use `systemctl --user stop neoaprs` there.
- Exit code 2 means the database cannot be used (a newer NeoAPRS made it, or it is not a database) or another NeoAPRS runs on the same data folder.
