# Settings

The settings are rows of the database, read at the start. Most are on the page, in the My station tab and the Settings tab, and apply as you change them ([start.md](start.md#how-settings-apply)). The rest are changed with the command line:

- `neoaprs db list` shows every setting.
- `neoaprs db get KEY` shows one.
- `neoaprs db set KEY VALUE` changes one. The value is checked as the daemon checks it, and the daemon takes it at its next start.

The daemon may be running while you use them. `db set` refuses a key that is not a setting, except `update/not_counted`; `db get` also shows a row of the state below, such as `update/install_id`, the number of this installation.

The settings the page does not show (`map/maxzoom`, `map/source`, `update/url`, `serial/pattern`, `serial/skip`, `web/port`, `web/allowed_hosts`, `igate/server`, `igate/password`) are for the command line only. The first five went back to their defaults once, when this version first started on a database; each reset is a line in the log with the old value, and a value you set afterwards with `neoaprs db set` stays. `web/port` and `web/allowed_hosts` were never reset.

What an earlier version stored for a setting that no longer exists (the number of attempts, the keep-alive, the log's days, the update check's switch, the map's timeout, the destination call, the compressed form, the DAO) was deleted then, and is ignored.

The table below is made from the program, so it lists every setting there is, with its default, and cannot drift. The column "where" says where on the page the setting is.

<!-- doc-settings:settings -->
| key | default | where | what it is |
| --- | --- | --- | --- |
| `station/call` | empty | My station tab, Station | your call, with an SSID if any, as one text such as `OH2GBA-9` (the page has the call in its field and the SSID in a dropdown beside it, [beacon.md](beacon.md#the-call-and-its-ssid)). **While it is empty, `N0CALL`, `NOCALL`, `MYCALL` or not an amateur call (3 to 6 letters and digits with at least one of each), nothing at all is transmitted** ([start.md](start.md#the-setup-guide)) |
| `station/transmit` | `true` | Top right of the page, on every tab | `false` is RX only (the switch at the top right reads RX only): nothing at all is transmitted (beacon, status, messages, acks, answers to queries, objects, bulletins, the digipeater) and every button that sends is off; messages being sent wait, with no attempt used up. One press switches RX only on; switching it off takes a second press. It takes effect at once on every open page ([beacon.md](beacon.md#rx-only)). A beacon that is off is not this |
| `email/radio` | empty | Email tab, the list beside Check email (while several radios that can send are on) | the radio email goes out on, by its id as `neoaprs db radios` lists it: any radio that can send. Empty, or a radio that is off: the topmost radio that can send, by the order of the boxes. A radio that comes on beside the one a mail went on while none was chosen stores that one, so that the mail stays there; a radio removed takes its choice with it. With one radio that can send it is that one, whatever is stored ([email.md](email.md#which-radio)) |
| `station/lat` | empty | My station tab, Location (Position: Fixed) | where you are, decimal degrees, north positive (−90 to 90). The map opens here and distances are measured from here. The page shows it for a fixed station only; with a GPS chosen it stays stored and is used until the first fix. Empty with the longitude: no position, no beacon, no station of your own, and the map opens on the world |
| `station/lon` | empty | My station tab, Location (Position: Fixed) | decimal degrees, east positive (−180 to 180) |
| `station/symbol_table` | `/` | My station tab, Station (the symbol) | `/` is the primary table, `\` the alternate one, `0`-`9` and `A`-`Z` an overlay on the alternate table |
| `station/symbol_code` | `-` | My station tab, Station (the symbol) | one printable character (`-` is a house, `>` a car) |
| `station/comment` | `NeoAPRS` | My station tab, Beacon | the comment of your position: printable ASCII without `\|` and `~`, at most 43 characters, 36 when the PHG extension is sent. A save that breaks it is refused with the reason |
| `station/status` | empty | My station tab, Status | the text of a status of your own when the status source is the text: printable ASCII without `\|` and `~`, at most 55 characters (the report always carries a time). Empty sends none ([beacon.md](beacon.md#the-status)) |
| `beacon/interval_min` | `0` | My station tab, Beacon | minutes between your position packets: 0 is off, else 20 to 1440. 0 switches the beacon off ([beacon.md](beacon.md#beacon-off)): no beacon and no status report, while messages, answers, objects, bulletins and the digipeater go on. The page offers Off and every 30 min, 60 min and 3 hours; a moving station (a GPS is chosen) is offered Off and On (SmartBeaconing), where any value but 0 is On and the value is not used, and On stores 30. A stored value below 20 is raised to 20, with a line in the log (a stored 20 or 45 is shown as one more choice). On a Mercury radio an interval below 30 is raised to 30, with a line in the log; the FM radio keeps the interval set: a frame on a channel that distant stations share is not sent often. The default is off so that an upgrade never starts to transmit |
| `beacon/power_w` | empty | My station tab, Beacon, Antenna | the transmitter's power in watts (0 to 9999) for the PHG extension of the beacon. Empty sends no PHG ([beacon.md](beacon.md#power-height-and-gain-phg)) |
| `beacon/antenna_height_m` | `0` | My station tab, Beacon, Antenna | the antenna's height above average terrain in metres (0 to 9999), for PHG |
| `beacon/antenna_gain_db` | `0` | My station tab, Beacon, Antenna | its gain in dBi (0 to 9), for PHG |
| `beacon/antenna_direction` | `omni` | My station tab, Beacon, Antenna | `omni` or the point of the compass it favours (`NE` `E` `SE` `S` `SW` `W` `NW` `N`), for PHG |
| `status/source` | empty | My station tab, Status | where the status comes from: `off`, `text` (`station/status`) or `rig` (the frequency and mode of the radio, from `status/rigctld` and `status/template`). Empty follows the other settings: `rig` while `status/rigctld` is set, else `text` while `station/status` is not empty, else `off`. A save of `rig` without `status/rigctld` is refused |
| `status/rigctld` | empty | My station tab, Status | `host:port` of a Hamlib rigctld (its default is `127.0.0.1:4532`) whose frequency and mode make the status. Ignored for `text` and `off` |
| `status/interval_min` | `30` | My station tab, Status | a status report goes out at most this often, whatever made it (15 to 1440). The page offers 30 min, 60 min and 2 hours. A stored value below 15 is raised to 15, with a line in the log |
| `status/template` | `QRV {freq} {mode}` | My station tab, Status | the text of a status made from the radio. `{freq}` is `14.074 MHz` (megahertz with three decimals), `{mode}` is the mode as rigctld names it (`USB`, `LSB`, `CW`, `FM` ...). No other field in braces, printable ASCII without `\|` and `~`, and at most 55 characters with the widest values (`1296.000 MHz`, `PKTUSB`) |
| `serial/last_port` | empty | the daemon's own memory | the port the search found last time, tried first while radio 1's own port (`radio/1/port`) is empty. Written by the daemon, in radio 1's own row `radio/1/last_port`; the page shows it as `found: PORT` beside an automatic Port |
| `serial/pattern` | `/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*` | `neoaprs db set` only | the device files the search listens to (Linux only): shell globs (`*`, `?`, `[0-3]`), each an absolute path, separated by spaces. A device that several globs match keeps the name of the earliest glob, so a stable `by-id` name comes first. A change restarts the search, and **Find my radio** tries the same ports ([radio.md](radio.md#finding-the-radio)) |
| `serial/skip` | empty | `neoaprs db set` only | ports the search never opens, nor does **Find my radio**, separated by commas (`/dev/brainbox_2`, a rotator's adapter, say) |
| `web/network` | `false` | Settings tab, Web page | `true` lets other devices on the network open the page: it then listens on every interface, and a device other than this computer logs in with `web/key` first. It counts at once, with no restart ([network.md](network.md)) |
| `web/key` | empty | Settings tab, Web page | the access key a device on the network types to log in: three groups of four lowercase letters and digits without `0 1 i l o` (`k7m2-x9pq-4hrt`). Made by the daemon when `web/network` is first on; a key of your own is accepted in the same form. A new one logs every device out |
| `web/https` | `false` | Settings tab, Web page | `true` (with `web/network`) also serves the page over https, on the port after `web/port`, with a certificate NeoAPRS makes itself ([network.md](network.md#the-secure-connection-https)) |
| `web/port` | `7303` | `neoaprs db set` only | the port of the page, read at the daemon's start. A port that is in use moves the page to the first free one of the ten after it. 0 takes a free one at once |
| `web/allowed_hosts` | empty | `neoaprs db set` only | names besides an IP address, `localhost` and the machine's own name (and `name.local`) that the page answers to, separated by commas |
| `messages/alert` | `true` | Settings tab, Notifications, On the NeoAPRS computer (Alert) | whether a message to you, and an alert you set on a station, runs `messages/alert_command` ([notifications.md](notifications.md)) |
| `messages/alert_command` | a notification and a sound | Settings tab, Notifications, On the NeoAPRS computer (Command) | the shell line that is run (at most 1000 characters; empty runs nothing). The default shows a notification and plays a sound, in a form that suits the system |
| `map/radius_km` | `150` | Settings tab, Map (Radius) | the detailed base map covers a square this far from your position in every direction (10 to 300 km). Read when the map is made ([page.md](page.md#the-base-map)) |
| `map/maxzoom` | `12` | `neoaprs db set` only | the deepest zoom the detailed map has tiles for (6 to 15): 10 shows towns, 12 streets, 14 houses. The page's Download map uses the stored value |
| `map/station_hours` | `3` | Stations tab, On map for | how many hours after its last position a station stays on the map: 1, 3, 6, 12, 24. The same for every station, in every browser; your own station and objects never leave. The Stations table keeps a station that has left the map, dim |
| `map/source` | empty | `neoaprs db set` only | where the map is cut from: empty is the latest daily build of build.protomaps.com; or a web address (`https://...`) or the path of a PMTiles file, such as a planet file of your own |
| `map/aircraft` | `none` | Settings tab, Map, Aircraft (Source) | where the map's aircraft come from: `none` (no aircraft on the map), `adsbfi` or `adsblol` (a service on the internet, asked for the map's circle round your position while a page shows the aircraft), `radarcape` (your own jetvision Radarcape, `map/aircraft_host`) or `receiver` (your own ADS-B receiver whose `aircraft.json` tar1090, dump1090 or readsb serves, `map/aircraft_host`). While it is not `none` the map's Layers box has the row Aircraft |
| `map/aircraft_host` | empty | Settings tab, Map, Aircraft (Receiver's address, with Radarcape or My own receiver) | your own aircraft receiver: a name or address (`192.168.1.20`, `pi.local`, `[fe80::1]`), the same with `:port`, or a whole `http://` or `https://` address, which is used as typed. With `receiver` a name is looked for on ports 80 and 8080 where tar1090, dump1090 and SkyAware keep their aircraft, and empty is this computer; with `radarcape` the Radarcape's own list of aircraft is asked at that name (port 80 unless one is given), and empty asks nothing |
| `map/ships` | `none` | Settings tab, Map, Ships (Source) | where the map's ships come from: `none` (no ships on the map), `fintraffic` (Fintraffic's AIS feed, offered where the map's circle reaches its waters, 57.7 to 65.8 N, 16.5 to 32.5 E), or `receiver` (your own AIS receiver, `map/ships_host`). A stored `fintraffic` that the station is not offered counts as `none` |
| `map/ships_host` | empty | Settings tab, Map, Ships (Receiver's address, with My own receiver) | your own AIS receiver: `host` or `host:port` of the TCP server that sends its AIS sentences (port 10110 when none is given); empty is this computer. The daemon connects to it, while `map/ships` is `receiver`, and listens on no port of its own |
| `update/url` | `https://neo.oh2gba.eu/version.php` | `neoaprs db set` only | the address of the version page that the daily update check asks (`http` or `https`; [install.md](install.md#the-update-check)) |
| `igate/enabled` | `false` | Settings tab, Internet | `true` shows the stations that APRS-IS has within `map/radius_km` of your position, marked as heard over the internet; nothing is sent, and nothing from the internet ever goes on the air ([igate.md](igate.md)) |
| `igate/server` | `rotate.aprs2.net:14580` | `neoaprs db set` only | `host:port` of the APRS-IS server the Internet switch logs in to. The default `rotate.aprs2.net:14580` is the round-robin name of the volunteer servers and the port of the filtered feed; empty leaves it waiting ([igate.md](igate.md#the-server)) |
| `igate/password` | empty | `neoaprs db set` only | the APRS-IS passcode of `station/call`, digits 0 to 32767: only for a person who lets NeoAPRS put what the radio hears on APRS-IS ([igate.md](igate.md#advanced-putting-what-the-radio-hears-on-aprs-is)). NeoAPRS does not work it out. `-1` is refused; empty is the read-only login of the page. A secret |
| `gps/source` | `off` | My station tab, Station (Position) | where your position comes from, and so whether you are a fixed or a moving station. `off` (**Fixed** on the page) is a fixed station at your location: the beacon goes every `beacon/interval_min` and can carry the PHG extension. `gpsd` (a gpsd daemon, at `gps/host`) or `serial` (the NMEA sentences of a receiver on `gps/device`) makes the beacon a moving station's: it follows the GPS (position, course, speed and altitude) and goes when SmartBeaconing says, not every `beacon/interval_min` (which is then only On or Off: 0 is off), with no PHG, and the 20-minute floor of the fixed beacon does not apply. With no fresh GPS fix nothing is sent at all, and never your home position ([beacon.md](beacon.md#mobile-operation)). Without `gps/host` (for `gpsd`) or `gps/device` (for `serial`) the GPS waits and says so, and nothing is opened |
| `gps/host` | `127.0.0.1:2947` | My station tab, Station (Position) | `host:port` of the gpsd that `gpsd` reads (gpsd's own port is 2947) |
| `gps/device` | empty | My station tab, Station (Position) | the serial port of the GPS receiver for `serial`, such as `/dev/ttyUSB1` or `COM4`, or `socket://host:port` for a receiver behind a TCP serial server. Keep it apart from the radio's port (`radio/<id>/port`) |
| `gps/baud` | `4800` | My station tab, Station (Position) | the receiver's speed on `gps/device` (300 to 921600); NMEA 0183 is 4800, and many USB receivers speak 9600 |
| `beacon/travel` | `car` | My station tab, Beacon (Travelling) | how you travel while the beacon follows the GPS: `car`, `bicycle`, `foot` or `boat`. It decides when SmartBeaconing beacons: `car` every 60 seconds from 100 km/h, a turn of more than 30 degrees (at least 15 seconds after the last beacon); `bicycle` every 60 seconds from 30 km/h, a turn of more than 35 degrees (at least 20 seconds after the last beacon); `foot` every 120 seconds from 7 km/h, a turn of more than 45 degrees (at least 60 seconds after the last beacon); `boat` every 60 seconds from 40 km/h, a turn of more than 20 degrees (at least 30 seconds after the last beacon). Below the slow speed a station counts as standing still, so there is a beacon only every 30 minutes and no turn is beaconed. The car's numbers are Dire Wolf's; the others are NeoAPRS's own choice |
| `units/non_metric` | `false` | Settings tab, at the top (Non-metric units) | whether every page of the station shows distances in miles (short ones in feet), heights in feet, speeds in mph, temperatures in °F, pressure in inHg and rain and snow in inches; aircraft in feet and knots, ships in knots. What you type stays metric, and nothing sent on the air changes |
<!-- /doc-settings -->

## Aircraft and ships

In Settings, Map, under the Radius, are a box **Aircraft** and a box **Ships**, each with a row **Source** that chooses where the map's aircraft or ships come from. Out of the box both are **None**: the Layers box of the map has no row for them and nothing is asked. A row is in the Layers box only once a source is chosen here ([page.md](page.md#aircraft-and-ships)).

| box | the choices of Source | key |
|---|---|---|
| **Aircraft** | **None**, **adsb.fi**, **adsb.lol**, **Radarcape**, **My own receiver** | `map/aircraft` |
| **Ships** | **None**, **Fintraffic**, **My own receiver** | `map/ships` |

- adsb.fi and adsb.lol are services on the internet, asked for the map's circle round your position (the Radius, at most 300 km). Fintraffic's feed of Finnish waters is in the list only where the map's circle reaches those waters (57.7 to 65.8 N, 16.5 to 32.5 E). Where it does not, the list has only **None** and **My own receiver**, and a Fintraffic stored earlier counts as None until the station is back in range.
- **Radarcape** is for a jetvision Radarcape on your network: choose it and type its address, and that is all; NeoAPRS asks the Radarcape for its list of aircraft itself. **My own receiver** is for any other ADS-B receiver whose aircraft tar1090, dump1090 or readsb serves (on a Raspberry Pi, for one); in the Ships list it is an AIS receiver. Each of them shows a row **Receiver's address** under it, with a state line. Your own receiver is not cut by the Radius: everything it hears is shown.
- **The address** is the name or the address of the computer the receiver runs on, such as `pi.local` or `192.168.1.20`. Left empty, the receiver is looked for on this computer; a Radarcape is a device of its own, so with Radarcape chosen an empty address asks nothing and the state line says **No answer from the receiver**.
  - For a Radarcape it is the name or address of the Radarcape (`192.168.1.160`), with a `:port` only if its web server is on another port than 80.
  - For My own receiver of aircraft a whole `http://` or `https://` address of the receiver's `aircraft.json` is taken as typed, and a name or address is tried with the known places of that file (on ports 80 and 8080); a `:port` after the name is allowed, and an IPv6 address goes in brackets (`[fe80::1]`).
  - For ships it is the name or address of the computer that sends the AIS sentences, with a `:port` if it is not 10110.
  - A text that is not an address is refused with a message and not saved. Any device that has the access key can set it.
- **The state line** is a word and a line, as a GPS receiver's: **looking** (**Looking for the receiver**), **receiving** (for aircraft how many it gave with a position and how long ago, for ships how many are held and how long since the last sentence, or **Receiving, no aircraft yet** and **Connected, no ship heard yet**) and **no answer** (**No answer from the receiver**).

- **For a Radarcape**: choose **Radarcape** as the Source of Aircraft, type its address and watch the state line turn to receiving; then, on the map, tick **Aircraft** in the Layers box.
- **For a receiver on a Raspberry Pi**: choose **My own receiver** as the Source of Aircraft (or of Ships, for an AIS receiver), type the Pi's name or address (`pi.local`) and watch the state line turn to receiving; then, on the map, tick **Aircraft** (or **Ships**) in the Layers box. The tick is off out of the box and is each browser's own, so it is made once on every phone and desktop that should show them.
- The receiver must be reachable from the computer NeoAPRS runs on, not only from the one the page is open on: the daemon is the one that asks. A **:port** typed after the name is tried with the same known places of `aircraft.json`, on that port only.

Changes apply as they are made, with no restart.

## The radios' own settings

Each radio keeps settings of its own, under `radio/<id>/<key>`. `neoaprs db radios` lists the radios with theirs, and `neoaprs db get` and `neoaprs db set` take such a key as they take a setting (`neoaprs db set radio/1/port /dev/ttyUSB0`). Which settings a radio has is its type's.

A new installation has no radio until you add one: in the setup guide, in the Settings tab, or with `neoaprs db radios add TYPE` (`neoaprs db radios add kiss`, or `neoaprs db radios add mercury --off`, a name after the type if you like). The radio is added after the others and gets the next number, which no radio had before. The data folder is made if it is not there, so a station can be set up before its first start; the daemon takes the radio at its next start.

The keys of the radios in versions before 0.20 (`tnc/profile`, `serial/port`, `hf/enabled`, `mercury/keying` ...) are no settings any more: the first start of this version made each the radio's own (a `tnc/enter_kiss` of `true` with no `tnc/profile` made the radio's type `kenwood-tnc2`), and `neoaprs db set` of one names its new key.

Two radios that both send, and are both Dummy radios or both real ones, can pass packets to each other as a pair (the Digipeater group of the Settings tab). Each pair keeps two rows of its own, `pair/<a>/<b>/enabled` and `pair/<a>/<b>/ssid`, with the radios' numbers as a and b, the lower first: the last table below. They are set in the Settings tab only; `neoaprs db set` does not take them.

<!-- doc-settings:radios -->
| type | kind | what it is | its own settings |
| --- | --- | --- | --- |
| `direwolf` | fm | Sound card | `sound_card`, `keying`, `tx_gain_db`, `tx_card`, `rx_card`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `kiss` | fm | KISS TNC (Kenwood TH-D74/D75, Mobilinkd…) | `port`, `baud`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `kenwood-d710` | fm | Kenwood TM-D710 / TH-D72 | `port`, `baud`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `kenwood-tnc2` | fm | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | `port`, `baud`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `kantronics` | fm | Kantronics KPC-3+ | `port`, `baud`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `kiss-tcp` | fm | Your own Direwolf or soundmodem | `port`, `tcp_host`, `tcp_port`, `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `tnc-text` | fm | Yaesu FTM, TNC in monitor mode (RX only) | `port`, `baud` |
| `dummy` | fm | Dummy FM radio | `beacon`, `status`, `ask`, `local_info`, `path`, `digipeat` |
| `dummy-hf` | hf | Dummy Mercury radio | `beacon`, `status`, `ask`, `local_info` |
| `mercury` | hf | Mercury modem (sound card) | `sound_card`, `keying`, `tx_gain_db`, `tx_card`, `rx_card`, `psk_report`, `psk_dial`, `beacon`, `status`, `ask`, `local_info` |
| `lora-tcp` | lora | LoRa APRS board on the network | `tcp_host`, `tcp_port`, `beacon`, `status`, `ask`, `local_info`, `path` |
| `lora-serial` | lora | LoRa APRS board on USB or Bluetooth | `port`, `baud`, `beacon`, `status`, `ask`, `local_info`, `path` |
| `lora-console` | lora | LoRa APRS iGate on USB (RX only) | `port`, `baud` |
| `dummy-lora` | lora | Dummy LoRa radio | `beacon`, `status`, `ask`, `local_info`, `path` |

| key | default | types | where | what it is |
| --- | --- | --- | --- | --- |
| `radio/<id>/port` | empty | `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `tnc-text`, `lora-serial`, `lora-console` | Settings tab, Radio (Port) | the radio's port: a serial port such as `/dev/ttyUSB0` or `COM3`, `socket://host:port` (KISS over TCP, with every type), `bt://AA:BB:CC:DD:EE:FF` (Linux, a paired Bluetooth device) or `ble://AA:BB:CC:DD:EE:FF` (a Bluetooth LE KISS TNC, with the extra `ble` installed). Empty: the port the search found last for radio 1 (`serial/last_port`), else on Linux the ports of `serial/pattern` are listened to for the radio ([radio.md](radio.md#the-port)) |
| `radio/<id>/baud` | empty | `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `tnc-text`, `lora-serial`, `lora-console` | Settings tab, Radio (Speed) | the speed of its serial line, 8N1 (300 to 921600); empty: the type's own, 9600 for every serial type. A TCP or Bluetooth port has none |
| `radio/<id>/tcp_host` | `127.0.0.1` | `kiss-tcp`, `lora-tcp` | Settings tab, Radio (Address) | where a `kiss-tcp` radio connects while its port is empty; a `lora-tcp` radio's is empty until the board's address is typed, and nothing is opened meanwhile |
| `radio/<id>/tcp_port` | `8001` | `kiss-tcp`, `lora-tcp` | Settings tab, Radio (Port) | the KISS port there (1 to 65535): Direwolf 8001, UZ7HO SoundModem and QtSoundModem 8100 |
| `radio/<id>/beacon` | `true` | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy`, `dummy-hf`, `mercury`, `lora-tcp`, `lora-serial`, `dummy-lora` | `neoaprs db set` only | `true`: the station's beacon goes out on this radio. Every radio that is on sends it in this version, whatever this says |
| `radio/<id>/status` | `false` | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy`, `dummy-hf`, `mercury`, `lora-tcp`, `lora-serial`, `dummy-lora` | My station tab, Status (Send on) | `true`: the status report goes out on this radio. With one radio that can send, on that one whatever this says; with several, on those ticked, and on none while none that is on is |
| `radio/<id>/ask` | `false` | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy`, `dummy-hf`, `mercury`, `lora-tcp`, `lora-serial`, `dummy-lora` | Nearby tab, Ask around (Send on) | `true`: Ask around sends its query on this radio. Read as `radio/<id>/status` is |
| `radio/<id>/local_info` | `false` | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy`, `dummy-hf`, `mercury`, `lora-tcp`, `lora-serial`, `dummy-lora` | Objects tab, Local info (Send on) | `true`: Local info's Ask sends its request on this radio. Read as `radio/<id>/status` is |
| `radio/<id>/path` | empty | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy`, `lora-tcp`, `lora-serial`, `dummy-lora` | My station tab, Beacon, Advanced | the digipeaters of the beacon on this radio: up to 8 calls separated by commas, each a call with an optional SSID. Empty is the recommended path of your station's type, which the symbol decides: `WIDE1-1,WIDE2-1` for a mobile symbol (a car, a bike, a boat, an aircraft ...), `WIDE2-2` for any other; on a LoRa radio it is `WIDE1-1`, the path of the LoRa networks. `DIRECT` is no digipeaters at all. Only a type that may carry a path has it |
| `radio/<id>/digipeat` | `false` | `direwolf`, `kiss`, `kenwood-d710`, `kenwood-tnc2`, `kantronics`, `kiss-tcp`, `dummy` | Settings tab, Digipeater | `true`: this radio repeats a packet that asks for `WIDE1-1`, or for our call: the fill-in digipeater ([beacon.md](beacon.md#the-fill-in-digipeater)) |
| `radio/<id>/sound_card` | empty | `direwolf`, `mercury` | Settings tab, Radio (Sound card) | the sound card of the radio's modem (the Mercury modem, Direwolf), as the list offers it (an id such as `plughw:1,0` on Linux, the device's name on Windows); one card is one radio's. The page stores the daemon's proposal here when it is empty (the one USB sound card that is both playback and capture, else the system's default device) and never offers the empty choice; a radio that has it empty runs on the daemon's own choice ([radio.md](radio.md#the-mercury-modem)) |
| `radio/<id>/keying` | empty | `direwolf`, `mercury` | Settings tab, Radio (Keying) | how the radio's modem keys the transmitter: `vox` (the radio keys itself: VOX, or its own data mode), `cm108` (the GPIO pin of a CM108 sound chip), `rts:PORT` or `dtr:PORT` (that line of the serial port named, `rts:/dev/ttyUSB0`, `dtr:COM3`: a DigiRig and most interfaces). The page stores the daemon's proposal here when it is empty (RTS of the one USB serial port of a radio or an interface when the sound card is a USB one, else VOX) and never offers the empty choice; a radio that has it empty runs on the daemon's own choice |
| `radio/<id>/tx_gain_db` | `0` | `direwolf`, `mercury` | Settings tab, Radio (Transmit level) | the transmit gain of the radio's modem in dB (Mercury -20 to 20, Direwolf -20 to 0; `0`: the modem's own level, a Mercury frame peaks at -6 dBFS). Set with the - and + beside Tune; it is sent to the running modem at once (Direwolf starts its program again with it) and written to the modem's configuration at every start, and the tune tone follows it, so that the radio's ALC on the tone moves as it will on a frame. Where the sound card has a playback level of its own and this is `0`, the row's slider sets that one instead (`tx_card`); a gain off `0` keeps the - and + and the card's playback level is left as it is |
| `radio/<id>/tx_card` | empty | `direwolf`, `mercury` | Settings tab, Radio (Transmit level) | the sound card's own playback level in percent, 0 to 100 (on Linux its ALSA Master, Speaker or PCM control, on Windows the playing device's volume; not on macOS). Empty: never set, the card stays as the system has it. Set with the slider of the Transmit level row, which is there only where the card has such a control and the transmit gain is `0`; it is set on the card at once, without a restart, and put back on it at every start of the radio's modem while the gain is `0` |
| `radio/<id>/rx_card` | empty | `direwolf`, `mercury` | Settings tab, Radio (Receive level) | the sound card's own capture level in percent, 0 to 100 (its ALSA Capture or Mic control, the recording device's volume on Windows). Empty: never set. Set with the slider of the Receive level row, beside the bar, which is there only where the card has such a control; set and put back as `tx_card`. A switch of the card (its Auto Gain Control, a mute) is never touched |
| `radio/<id>/psk_report` | `false` | `mercury` | Settings tab, Radio (Report to PSK Reporter) | `true`: every station this radio hears directly (no digipeater between, not passed on from the internet) is reported to pskreporter.info, where it shows on the map under the mode NEOAPRS, once every five minutes at most and only while `psk_dial` is set and the station has a position ([radio.md](radio.md#psk-reporter)) |
| `radio/<id>/psk_dial` | empty | `mercury` | Settings tab, Radio (Frequency) | the dial the radio is tuned to, written as `28.1800 MHz USB` (USB, at least 0.1 MHz): one of the suggested frequencies, or Other and the number typed; Other with no number yet, or one that is no dial, is empty. Empty: nothing is reported. Greyed while `psk_report` is `false` |

| key | default | where | what it is |
| --- | --- | --- | --- |
| `pair/<a>/<b>/enabled` | `false` | Settings tab, Digipeater | `true`: a packet heard on radio a or radio b whose path names the pair's call as its next unused hop is sent once on the other radio, with the call marked used. `false` by default. Set in the Settings tab only |
| `pair/<a>/<b>/ssid` | empty | Settings tab, Digipeater | the SSID (1 to 15) of the pair's call on the station's base call, `OH2GBA-12`; empty until the pair is first switched on, which takes the highest SSID that is neither the station's nor another pair's |
<!-- /doc-settings -->

## Values the program decides

These are not settings. They are fixed by design, and no field or `neoaprs db set` changes them.

<!-- doc-settings:fixed -->
- Packets, weather observations and stations are kept 7 days (packets from the internet 2 days) and cleaned up once a day. Messages and bulletins are kept until you delete them.
- The keep-alive asks a TNC that can be asked after 10 minutes of silence on the line (and a random minute or two more).
- A message to a station is sent 4 times, and one to the email gateway 2 times, before it has failed or is unconfirmed.
- Your own frames go out at least 10 seconds apart, except acks, answers to queries and digipeated packets.
- The first beacon goes out 30 seconds after the daemon starts.
- Every frame you send has the tocall `APZNEO`. The beacon of a station that stays is the plain uncompressed position; a moving station's (`gps/source` is not `off`) is a compressed one, with the altitude in its comment.
- A GPS fix older than 120 seconds is not used: a moving station sends no beacon on it, and never the home position instead.
- At most 50 objects and items, and 36 bulletins, of your own at once. A bulletin is sent for 1, 2, 4, 8 or 12 hours and an announcement for 1, 3 or 7 days, as chosen under Sent for (4 hours and 3 days until you choose).
- The update check asks the version page every 24 hours.
- A beacon interval below a radio's floor is raised to it: 30 minutes on a Mercury radio, 30 on a LoRa radio, 20 on an FM radio. Everything a radio sends by the clock waits a random extra time first (up to 300 seconds on a Mercury radio, 300 on LoRa, 30 on FM), so that stations started together do not key up together.
- A frame on a Mercury radio is at most 123 bytes, addresses included. A beacon's comment is cut to fit, and the longest message always fits.
<!-- /doc-settings -->

## State the daemon keeps

These rows are written by the daemon so that a restart goes on where it stopped. They are not settings and are not listed above:

<!-- doc-settings:state -->
- `radio/<id>/beacon_last_sent_at`: when the radio's beacon last went out, so that a restart waits out the rest of the interval.
- `radio/<id>/status_last_sent_at`: when the status report last went out on the radio, so that a restart waits out the rest of its interval there.
- `radio/<id>/last_port`: the port radio 1's search found (only radio 1 remembers one), which `serial/last_port` reads.
- `status/last_sent_at`: when the status report last went out.
- `status/last_text`: the text of that status report, which ?APRSS answers with and the page shows.
- `map/auto`: whether the detailed map that was begun by itself is still owed (`wanted`) or settled (`done`).
- `messages/radio_by_station`: the radio the operator chose for messages to a station, by call and the radio's number, while several radios that can send are on.
- `objects/send_on`: the radios of the object saved last with radios of its own (`1,3`), which a new object starts with.
- `bulletins/send_on`: the radios of the bulletin posted last with radios of its own, which a new bulletin starts with.
- `bulletins/sent_for_hours`: how long the post of each kind posted last is sent for, in hours, which a new post of that kind starts with.
- `update/install_id`: the random number of this installation that the update check sends.
- `update/not_counted`: `true` when the update check is to send the number 0 in place of this installation's own, so that the project does not count this run (a test machine; a run from the source tree does it by itself); set with `neoaprs db set update/not_counted true`, never shown on the page.
- `update/sked_token`: the secret of this installation that goes with each HF test it posts, so that only it can delete them; never shown in the log or the support bundle.
<!-- /doc-settings -->

## Rows that mean another setting

A database made by an older NeoAPRS may hold a row that is read as a setting while that setting has no row of its own. The first save writes the setting itself, and from then on the old row is not looked at.

- `web/bind` naming anything but the loopback, with no `web/network`, is read as `web/network` `true`.

A value in the database that is wrong falls back to its default and is logged with its key.
