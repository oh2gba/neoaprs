# Settings

The settings are rows of the database, read at the start. Most are on the page, in the Beacon tab and the Settings tab, and apply as you change them ([start.md](start.md#how-settings-apply)). The rest are changed with the command line:

- `neoaprs db list` shows every setting.
- `neoaprs db get KEY` shows one.
- `neoaprs db set KEY VALUE` changes one. The value is checked as the daemon checks it, and the daemon takes it at its next start.

The daemon may be running while you use them. A key that is not a setting is refused.

The settings the page does not show (`map/maxzoom`, `map/source`, `update/url`, `serial/pattern`, `serial/skip`, `web/port`, `web/allowed_hosts`) are for the command line only. The first five went back to their defaults once, when this version first started on a database; each reset is a line in the log with the old value, and a value you set afterwards with `neoaprs db set` stays. `web/port` and `web/allowed_hosts` were never reset.

What an earlier version stored for a setting that no longer exists (the number of attempts, the keep-alive, the log's days, the update check's switch, the map's timeout, the destination call, the compressed form, the DAO) was deleted then, and is ignored.

The table below is made from the program, so it lists every setting there is, with its default, and cannot drift. The column "where" says where on the page the setting is.

<!-- doc-settings:settings -->
| key | default | where | what it is |
| --- | --- | --- | --- |
| `station/call` | empty | Beacon tab, Station | your call, with an SSID if any. **While it is empty, `N0CALL`, `NOCALL`, `MYCALL` or not an amateur call (3 to 6 letters and digits with at least one of each), nothing at all is transmitted** ([start.md](start.md#the-setup-guide)) |
| `station/lat` | empty | Beacon tab, Location | where you are, decimal degrees, north positive (−90 to 90). The map opens here and distances are measured from here. Empty with the longitude: no position, no beacon, no station of your own, and the map opens on the world |
| `station/lon` | empty | Beacon tab, Location | decimal degrees, east positive (−180 to 180) |
| `station/symbol_table` | `/` | Beacon tab, Station (the symbol) | `/` is the primary table, `\` the alternate one, `0`-`9` and `A`-`Z` an overlay on the alternate table |
| `station/symbol_code` | `-` | Beacon tab, Station (the symbol) | one printable character (`-` is a house, `>` a car) |
| `station/comment` | `NeoAPRS` | Beacon tab, Beacon | the comment of your position: printable ASCII without `\|` and `~`, at most 43 characters, 36 when the PHG extension is sent. A save that breaks it is refused with the reason |
| `station/status` | empty | Beacon tab, Status | the text of a status of your own when the status source is the text: printable ASCII without `\|` and `~`, at most 55 characters (the report always carries a time). Empty sends none ([beacon.md](beacon.md#the-status)) |
| `beacon/interval_min` | `0` | Beacon tab, Beacon | minutes between your position packets: 0 is off, else 20 to 1440. The page offers Off and every 30 min, 60 min and 3 hours. A stored value below 20 is raised to 20, with a line in the log (a stored 20 or 45 is shown as one more choice). The default is off so that an upgrade never starts to transmit |
| `beacon/path` | empty | Beacon tab, Beacon, Advanced | the digipeaters of your beacon: up to 8 calls separated by commas, each a call with an optional SSID. Empty is the recommended path of your station's type, which the symbol decides: `WIDE1-1,WIDE2-1` for a mobile symbol (a car, a bike, a boat, an aircraft ...), `WIDE2-1` for any other. `DIRECT` is no digipeaters at all |
| `beacon/power_w` | empty | Beacon tab, Beacon, Antenna | the transmitter's power in watts (0 to 9999) for the PHG extension of the beacon. Empty sends no PHG ([beacon.md](beacon.md#power-height-and-gain-phg)) |
| `beacon/antenna_height_m` | `0` | Beacon tab, Beacon, Antenna | the antenna's height above average terrain in metres (0 to 9999), for PHG |
| `beacon/antenna_gain_db` | `0` | Beacon tab, Beacon, Antenna | its gain in dBi (0 to 9), for PHG |
| `beacon/antenna_direction` | `omni` | Beacon tab, Beacon, Antenna | `omni` or the point of the compass it favours (`NE` `E` `SE` `S` `SW` `W` `NW` `N`), for PHG |
| `status/source` | empty | Beacon tab, Status | where the status comes from: `off`, `text` (`station/status`) or `rig` (the frequency and mode of the radio, from `status/rigctld` and `status/template`). Empty follows the other settings: `rig` while `status/rigctld` is set, else `text` while `station/status` is not empty, else `off`. A save of `rig` without `status/rigctld` is refused |
| `status/rigctld` | empty | Beacon tab, Status | `host:port` of a Hamlib rigctld (its default is `127.0.0.1:4532`) whose frequency and mode make the status. Ignored for `text` and `off` |
| `status/interval_min` | `30` | Beacon tab, Status | a status report goes out at most this often, whatever made it (15 to 1440). The page offers 30 min, 60 min and 2 hours. A stored value below 15 is raised to 15, with a line in the log |
| `status/template` | `QRV {freq} {mode}` | Beacon tab, Status | the text of a status made from the radio. `{freq}` is `14.074 MHz` (megahertz with three decimals), `{mode}` is the mode as rigctld names it (`USB`, `LSB`, `CW`, `FM` ...). No other field in braces, printable ASCII without `\|` and `~`, and at most 55 characters with the widest values (`1296.000 MHz`, `PKTUSB`) |
| `tnc/profile` | `kiss` | Settings tab, TNC (Radio type) | what kind of TNC the radio is: `kenwood-tnc2`, `kenwood-d710`, `kantronics`, `kiss`, `kiss-tcp`. It decides what is written to the TNC to put it in KISS, whether the TNC is asked if it is there, and how it is reached ([radio.md](radio.md#the-tnc-type)). A TCP type is refused, with the reason, while `serial/port` names a serial device |
| `serial/port` | empty | Settings tab, TNC (Port) | the radio's port: a serial port such as `/dev/ttyUSB0` or `COM3`, `socket://host:port` (KISS over TCP, with every type) or `bt://AA:BB:CC:DD:EE:FF` (Linux, a paired Bluetooth device). Empty means: open `serial/last_port` if there is one, else on Linux listen to the ports of `serial/pattern` for the radio ([radio.md](radio.md#the-port)) |
| `serial/baud` | empty | Settings tab, TNC (Speed) | the speed of the serial line, 8N1 (300 to 921600). Empty is the type's own, 9600 for every serial type. A TCP or Bluetooth port has none |
| `tcp/host` | `127.0.0.1` | Settings tab, TNC | where the `kiss-tcp` type connects when `serial/port` is empty. The serial types ignore it |
| `tcp/port` | `8001` | Settings tab, TNC | the KISS port of that program (1 to 65535): Direwolf 8001, UZ7HO SoundModem and QtSoundModem 8100 |
| `serial/last_port` | empty | the daemon's own memory | the port the search found last time, tried first while `serial/port` is empty. Written by the daemon; the page shows it as `found: PORT` beside an automatic Port |
| `serial/pattern` | `/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*` | `neoaprs db set` only | the device files the search listens to (Linux only): shell globs (`*`, `?`, `[0-3]`), each an absolute path, separated by spaces. A device that several globs match keeps the name of the earliest glob, so a stable `by-id` name comes first. A change restarts the search, and **Find my radio** tries the same ports ([radio.md](radio.md#finding-the-radio)) |
| `serial/skip` | empty | `neoaprs db set` only | ports the search never opens, nor does **Find my radio**, separated by commas (`/dev/brainbox_2`, a rotator's adapter, say) |
| `web/network` | `false` | Settings tab, Web page | `true` lets other devices on the network open the page: it then listens on every interface, and a device other than this computer logs in with `web/key` first. It counts at once, with no restart ([network.md](network.md)) |
| `web/key` | empty | Settings tab, Web page | the access key a device on the network types to log in: three groups of four lowercase letters and digits without `0 1 i l o` (`k7m2-x9pq-4hrt`). Made by the daemon when `web/network` is first on; a key of your own is accepted in the same form. A new one logs every device out |
| `web/https` | `false` | Settings tab, Web page | `true` (with `web/network`) also serves the page over https, on the port after `web/port`, with a certificate NeoAPRS makes itself ([network.md](network.md#the-secure-connection-https)) |
| `web/port` | `7303` | `neoaprs db set` only | the port of the page, read at the daemon's start. A port that is in use moves the page to the first free one of the ten after it. 0 takes a free one at once |
| `web/allowed_hosts` | empty | `neoaprs db set` only | names besides an IP address, `localhost` and the machine's own name (and `name.local`) that the page answers to, separated by commas |
| `messages/alert` | `true` | Settings tab, Notifications (Alert) | whether a message to you runs `messages/alert_command` ([notifications.md](notifications.md)) |
| `messages/alert_command` | a notification and a sound | Settings tab, Notifications (Command) | the shell line that is run (at most 1000 characters; empty runs nothing). The default shows a notification and plays a sound, in a form that suits the system |
| `map/radius_km` | `150` | Settings tab, Map (Radius) | the detailed base map covers a square this far from your position in every direction (10 to 1000 km). Read when the map is made ([page.md](page.md#the-base-map)) |
| `map/maxzoom` | `12` | `neoaprs db set` only | the deepest zoom the detailed map has tiles for (6 to 15): 10 shows towns, 12 streets, 14 houses. The page's Download map uses the stored value |
| `map/source` | empty | `neoaprs db set` only | where the map is cut from: empty is the latest daily build of build.protomaps.com; or a web address (`https://...`) or the path of a PMTiles file, such as a planet file of your own |
| `update/url` | `https://oh2gba.eu/neoaprs/version.php` | `neoaprs db set` only | the address of the version page that the daily update check asks (`http` or `https`; [install.md](install.md#the-update-check)) |
| `digi/enabled` | `false` | Settings tab, Digipeater | `true` switches the fill-in digipeater on ([beacon.md](beacon.md#the-fill-in-digipeater)) |
<!-- /doc-settings -->

## Values the program decides

These are not settings. They are fixed by design, and no field or `neoaprs db set` changes them.

<!-- doc-settings:fixed -->
- Packets, weather observations and stations are kept 7 days and cleaned up once a day. Messages and bulletins are kept until you delete them.
- A station leaves the map 180 minutes (3 hours) after its last position.
- The keep-alive asks a TNC that can be asked after 10 minutes of silence on the line (and a random minute or two more).
- A message to a station is sent 4 times, and one to the email gateway 2 times, before it has failed or is unconfirmed.
- Your own frames go out at least 10 seconds apart, except acks, answers to queries and digipeated packets.
- The first beacon goes out 30 seconds after the daemon starts.
- Every frame you send has the tocall `APZNEO`. The beacon is always the plain uncompressed position.
- At most 50 objects and items, and 36 bulletins, of your own at once. A bulletin is sent for 4 hours and an announcement for 72 hours.
- The update check asks the version page every 24 hours.
<!-- /doc-settings -->

## State the daemon keeps

These rows are written by the daemon so that a restart goes on where it stopped. They are not settings and are not listed above: `beacon/last_sent_at`, `status/last_sent_at` and `status/last_text`.

## Rows that mean another setting

A database made by an older NeoAPRS may hold two rows that are read as a setting while that setting has no row of its own. The first save writes the setting itself, and from then on the old row is not looked at.

- `tnc/enter_kiss` set to `true`, with no `tnc/profile`, is read as `tnc/profile` `kenwood-tnc2`.
- `web/bind` naming anything but the loopback, with no `web/network`, is read as `web/network` `true`.

A value in the database that is wrong falls back to its default and is logged with its key.
