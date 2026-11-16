# The first start

## Starting NeoAPRS

- **Windows with the installer:** open **NeoAPRS** in the Start menu. The [desktop app](desktop.md) opens a window and starts the daemon.
- **Linux AppImage:** run the file with no arguments.
- **A service** (the .deb with `neoaprs service install`): it is already running. `neoaprs open` opens the page in your browser, starting NeoAPRS first if it is not running.
- **By hand:** `neoaprs` runs the daemon until you press Ctrl+C. Open <http://127.0.0.1:7303/>.

If the port says *permission denied* on Linux, add yourself to the group that owns serial devices: `sudo usermod -aG dialout $USER` (`uucp` on Arch), then log out and in. `neoaprs doctor` says what else keeps the radio from working ([commands.md](commands.md#neoaprs-doctor)).

## The setup guide

On a fresh install the page opens a guide in four steps. It opens by itself once, when NeoAPRS has no call. The lime **no call set** button in the header and **Run the setup guide again** in the Settings tab open it again, and what you typed is still there.

1. **Call.** Your call sign in the field, and beside it the **SSID** to choose: none for your main station, -9 for a car and so on ([beacon.md](beacon.md#the-call-and-its-ssid)). Pasting `OH2GBA-9` into the field works too.
2. **Position.** Press **Choose on map** and click where you are, or drag the pin. Or type latitude and longitude in decimal degrees in the fields under it: north and east positive, south and west negative (Sydney is -33.87, 151.21). A Maidenhead locator works too. It is the same row as the Location of the My station tab ([beacon.md](beacon.md#the-location)), with the fields open the whole time.
3. **Symbol.** The twelve usual ones are on top; the symbol in force is shown under them, and **More symbols…** beside it opens the picker with every symbol.
4. **Radio.** The boxes of Settings → Radio ([radio.md](radio.md#the-radio-group)), and each change is saved at once, as in the Settings tab. A new installation has no radio: the step is one box, **New radio**, with **Add radio**. Choose the type of your radio, of any kind (FM, Mercury, LoRa), and press **Add**. The radio's box then takes its place: fill in what the type asks for (a port, an address). **Add radio** under it adds another.
   - **Finish**, on this step, needs one radio on with no field in error. On Windows and macOS a radio on a serial line needs its **Port** chosen (or found with **Find my radio**).

The map under the guide is the world, from the first second. When you press **Next** on the Position step, NeoAPRS saves the place and starts downloading the streets and names 150 km round your station (the radius of Settings → Map), unless the detailed map it has covers the place already, so that it is there soon after the guide. A quiet line in the guide says "Downloading the map of your area…", and a **Map** mark at the top of the page shows the percent until it is done.

The radius (150 km unless you change it) and the **Download map** button are in Settings → Map ([page.md](page.md#the-base-map)).

The Radio step shows each radio's status line, so you see at once whether it is connected, and has the helpers of its box:

- **Find my radio**, for a radio on a serial line, tries the ports and, when it finds the radio, fills in the type, the port and the speed (Linux, Windows, macOS).
- **Terminal**, closed until you open it, shows what the TNC saw and did.
- A Mercury radio's **Sound card** and **Keying** are chosen for you, with **Test** beside the keying and the **Suggested frequencies**. Tune, the Transmit level and the Spectrum are in the Settings tab only, and so is **RX only**.
- The type **Dummy FM radio** needs no port and no speed: pick it to try NeoAPRS without a radio ([radio.md](radio.md#the-dummy-radios)).

A radio you change or add in the guide stays when the guide is closed. **Finish** saves the call, the place and the symbol. On a station that has no call and no beacon yet, it also sets the beacon to every 30 minutes (the My station tab shows and changes it). Run again on a station that already has a call, the guide leaves the beacon alone.

**Nothing is transmitted until a call is set.** While the call is empty, `N0CALL`, `NOCALL`, `MYCALL` or not an amateur call (3 to 6 letters and digits, with at least one of each), NeoAPRS only listens: no beacon, status, message, ack, object, bulletin or answer to a query. A message is refused with "set your call first", and the header says "no call set". The commands that put the TNC in KISS are not transmissions and go on.

## After an update

An update keeps everything you have: the settings, the messages, the packets, the stations, the map. At its first start the new NeoAPRS brings your database up to date. It first puts a copy of it into `backup/`, as the version before left it, and the version before can open that copy. The database of any earlier release is brought up to date this way, back to the first one.

- **Your radios** become radios of their own: the radio you had, and the Mercury radio if you ever switched it on. Their settings, their messages and what they heard stay theirs.
- **A large database** takes a while, minutes on a slow card. The desktop app and `neoaprs open` wait for it, `neoaprs doctor` says that it is being brought up to date, and a second NeoAPRS started meanwhile waits too.
- **A start that was cut short** (a power cut) goes on from the same copy the next time: there is still one copy, and the disk does not fill.

**If it does not start**, `neoaprs support` makes the file to send ([support.md](support.md)). To go back to the version before, stop NeoAPRS, install that version again and put its copy back with `neoaprs db restore` ([below](#the-data-folder)).

## The data folder

Everything NeoAPRS keeps is in one folder, one daemon to a folder. A second daemon on the same folder ends at once with exit code 2.

| where | folder |
|---|---|
| Linux | `~/.local/share/neoaprs` (`$XDG_DATA_HOME/neoaprs`) |
| Windows | `%LOCALAPPDATA%\NeoAPRS` |
| macOS | `~/Library/Application Support/NeoAPRS` |

`--data DIR` chooses another folder, and `NEOAPRS_DATA_DIR` sets the default (the table "Environment variables" of [`CONVENTIONS.md`](../../CONVENTIONS.md) lists every variable).

- `neoaprs.sqlite` is everything NeoAPRS keeps: the settings, every packet heard or sent, the messages, the message board, your own objects, items and bulletins, the weather of the weather stations, and the stations (a cache the daemon rebuilds from the packets). It is private to your user and is migrated at the start; a copy of it is made into `backup/` before a migration changes it.
- `backup/` is also the way back. An older NeoAPRS refuses a file made by a newer one and leaves it alone; its message names the newest copy in `backup/` that it can open and the command that puts it back.

  With NeoAPRS stopped, `neoaprs db restore` lists the copies (date, version, size) and `neoaprs db restore NAME` puts one in the place of the database. The file that was there is kept beside it as `neoaprs-set-aside-DATE-TIME.sqlite`, never deleted, so a newer NeoAPRS can have it back.

  `backup/` holds one copy NeoAPRS made: your database as the version before the latest update left it, which that version opens. It is the way back from the last release, not from several. Copies you put there yourself stay.
- Packets, weather observations and stations older than 7 days are removed once a day; packets that came from the internet (the Internet stations) are kept 2 days, since they are most of what the database holds. The weather graphs reach back 7 days. Messages and bulletins stay until you delete them.
- `neoaprs.log` is the log, rotated (20 MB, five files), with every packet as the TNC2 line and what it is. Warnings and errors, and the lines of a database migration (what an upgrade changed), also go to stderr, which `systemctl status` and the journal show.
- `basemap.pmtiles` is the detailed base map of your area (the world map ships with NeoAPRS and is not in this folder, unless an earlier version made `basemap-world.pmtiles` here); an earlier version fetched a `pmtiles` tool into `bin/`, which is not used any more and can be deleted; `tls/` holds the certificates of the secure connection.
- `message.key` is your private key for [encrypted messages](messages.md#encrypted-messages), made the first time it is needed (the daemon has to be started with `--encryption`). It is private to your user; keep it out of any copy you share.
- `neoaprs.lock` shows that a daemon holds the folder. `neoaprs.migrate.lock` is held while the database is brought up to date, while `neoaprs db set` writes it and while `neoaprs db restore` puts a copy back. The desktop app keeps `neoaprs-app.log`, `neoaprs-app.json`, `neoaprs-app.lock`, `neoaprs-app.port` and `webview/` there too.

## How settings apply

The Settings tab and the My station tab have no Save button and no Revert. A setting is put in force as you change it, as on a phone.

- A tickbox, a choice from a list, the port list, the symbol and **Choose on map** apply at once.
- A field you type in (the call, the comment, the position, the path) applies when you press Enter or leave the field, never while you type, so a half-typed call or position is never beaconed. Esc puts back the value in force.
- The page checks the value first and says what is wrong under the field. Nothing is sent until it is right.
- Fields that belong together are sent as one change: the latitude and the longitude, and the Address and the Port of a radio on the network (the radio restarts once, not twice).
- Nothing is shown beside a field when a change applies, so nothing on the page moves. The toast that floats over the page, and a screen reader's "Saved", are the confirmation.
- When the daemon refuses a change, the reason is under the field, what you typed stays in it and the old value stays in force.
- After a change a small toast, such as "Beacon interval changed · Undo", stays for ten seconds. **Undo** puts the old values back in one step. With several quick changes the toast is for the latest and the earlier ones stay applied.
- Only a change that could cut you off asks first: turning off **Allow access from the network** on a page opened from another device.
- The changes go to the daemon one at a time, in the order they were made. **Beacon now** and **Send status now** wait while a change is being saved.

Choosing the radio as the status source fills in the usual rigctld address, `127.0.0.1:4532`, so the choice is valid at once. A comment too long for the power you set says "Shorten the comment to 36 first" on the power.

The forms carry no sentences under the fields: a label, a placeholder with the default, a unit, and a tooltip at the most. A field that a non-developer may not understand has a small **(i)** that opens a few plain sentences; Esc, a click outside or moving on closes it. What each setting does is in [settings.md](settings.md).

`neoaprs db list` shows the settings and `neoaprs db set KEY VALUE` changes one. The value is checked like the daemon checks it, and the daemon takes it at its next start. While a NeoAPRS is running with this folder and the database is not up to date yet, `neoaprs db set` changes nothing: try again in a minute, or, if it is the version before, stop it, and the new one brings the database up to date at its start. A change made on the page is put in force at once.

## Without the radio

`neoaprs replay` plays a capture as a KISS TNC on a TCP port of this computer, so NeoAPRS runs without a radio on any system.

```bash
neoaprs replay                                                  # the sample capture of the package; prints socket://127.0.0.1:PORT
neoaprs db --data data radios add kiss                          # once, in another terminal: a new data folder has no radio yet
neoaprs run --data data --port socket://127.0.0.1:PORT          # then, in that terminal
neoaprs db --data data stations                                 # and in a third
neoaprs db --data data packets
```

With no file it plays the sample capture inside the package, three minutes of a TH-D7. `neoaprs capture` records a capture from your radio. Nothing is sent while nobody is connected, and the frames go on from where they were when the daemon connects again. `--port` is radio 1's for this run only; its own port is not changed.

The type **Dummy FM radio** needs no capture and no second program: the daemon makes the traffic itself, around your position, and nothing goes on the air ([radio.md](radio.md#the-dummy-fm-radio)).

A moving station can be tried without a car in the same way: `neoaprs gps-replay` plays a drive as a gpsd, and the My station tab's **A GPS via gpsd** reads it ([beacon.md](beacon.md#mobile-operation)).

## Stopping NeoAPRS

- Ctrl+C or a termination signal ends the daemon cleanly: it finishes what the database was asked, closes it and exits with code 0. On Windows Ctrl+C, Ctrl+Break and the termination signal do the same.
- `neoaprs stop` ends the daemon that holds the data folder, on every system, and waits until it has ended. It exits 0 when it ended or none was running, and 1 after 30 seconds. A service manager that restarts the daemon starts it again; use `systemctl --user stop neoaprs` there.
- Exit code 2 means the database cannot be used (a newer NeoAPRS made it, or it is not a database) or another NeoAPRS runs on the same data folder.
