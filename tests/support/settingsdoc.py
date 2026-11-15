"""The table of settings and the list of fixed values in docs/manual/settings.md, made from `neoaprs.config.SETTINGS`, the types of radio (`neoaprs.radiotypes`: each type's own fields) and the
constants of the program.

The keys, the defaults and every number come from the code; the words are the `DESCRIPTIONS` below (and `RADIO_DESCRIPTIONS` for a radio's own settings, `radio/<id>/<key>`), with the numbers as `{name}`
fields that are filled in from the code, so a limit cannot be changed in one place only. The tables are blocks between `<!-- doc-settings:NAME -->` and `<!-- /doc-settings -->` in the document;
`scripts/doc-settings --write` makes them and `tests/test_docs.py` fails when one differs, when a setting or a field of a type has no description, or when a description names one that is gone. A
block of `PENDING` is held to the code once the document has it, and is not yet asked of it.
"""
import re

from neoaprs import TOCALL
from neoaprs import config as cfg
from neoaprs.configstatus import MAX_STATUS
from neoaprs.decay import ANNOUNCEMENT, BULLETIN
from neoaprs.message import EMAIL_ATTEMPTS, STATION_ATTEMPTS
from neoaprs.ownbulletin import MAX_POSTED
from neoaprs.policy import GPS_STALE_SEC, INTERNET_KEEP_DAYS, LOG_KEEP_DAYS, TNC_CHECK_SEC
from neoaprs.radiorules import HF_BEACON_JITTER_SEC, HF_BEACON_MIN_MIN, HF_MAX_FRAME
from neoaprs.radiotype import KINDS
from neoaprs.radiotypes import TYPES, kind_fields, types_of
from neoaprs.services.beacon import FIRST_DELAY_SEC
from neoaprs.services.ownobjects import MAX_OBJECTS
from neoaprs.services.pace import SPACING_SEC
from neoaprs.services.updatecheck import EVERY_SEC as UPDATE_EVERY_SEC
from neoaprs.skeds import SKED_TOKEN
from neoaprs.smartbeacon import PRESETS
from neoaprs.versions import NOT_COUNTED

BLOCK = re.compile(r"(<!-- doc-settings:(\w+)[^>\n]*-->\n)(.*?)(<!-- /doc-settings -->)", re.S)
DB_ONLY = "`neoaprs db set` only"           # the settings the page does not show (ui/src/lib/settings.ts, NOT_ON_THE_PAGE: tests/test_docs.py holds the two lists together)
DAEMON_MEMORY = "the daemon's own memory"
EMPTY = "empty"


def _numbers() -> dict[str, object]:
    """The `{name}` fields of the descriptions."""
    fields: dict[str, object] = {key.replace("/", "_"): f"{low} to {high}" for key, (low, high) in cfg.RANGES.items()}
    fields.update(
        comment=cfg.MAX_COMMENT, comment_phg=cfg.MAX_COMMENT_PHG, status=MAX_STATUS, beacon_min=cfg.MIN_BEACON_INTERVAL_MIN, hf_min=HF_BEACON_MIN_MIN, status_min=cfg.MIN_STATUS_INTERVAL_MIN, alert_command=cfg.MAX_ALERT_COMMAND,
        map_station_hours_choices=", ".join(str(h) for h in cfg.STATION_HOURS),
        moving_presets="; ".join(
            f"`{name}` every {p.fast_sec:g} seconds from {p.fast_kmh:g} km/h, a turn of more than {p.turn_min_deg:g} degrees (at least {p.turn_min_sec:g} seconds after the last beacon)" for name, p in PRESETS.items()),
        profiles=", ".join(f"`{t.key}`" for t in types_of("fm")), directions=" ".join(f"`{d}`" for d in cfg.ANTENNA_DIRECTIONS if d != "omni"), tocall=TOCALL,
    )
    return fields


# key: (where it is on the page, what it is). The order is the order of the table.
DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "station/call": ("My station tab, Station", "your call, with an SSID if any, as one text such as `OH2GBA-9` (the page has the call in its field and the SSID in a dropdown beside it, [beacon.md](beacon.md#the-call-and-its-ssid)). **While it is empty, `N0CALL`, `NOCALL`, `MYCALL` or not an amateur call (3 to 6 letters and digits with at least one of each), nothing at all is transmitted** ([start.md](start.md#the-setup-guide))"),
    "station/transmit": ("Settings tab, Radio", "`false` is RX only (the tickbox RX only of Settings → Radio is ticked): nothing at all is transmitted (beacon, status, messages, acks, answers to queries, objects, bulletins, the digipeater) and every button that sends is off; messages being sent wait, with no attempt used up. It takes effect at once. The header shows a lime RX only mark ([beacon.md](beacon.md#rx-only)). A beacon that is off is not this"),
    "station/main_radio": ("`neoaprs db set`, and the page once it lists the radios", "the radio that carries what is addressed to no station (bulletins, the status, the first choice of Ask around, Local info and email), by its id as `neoaprs db radios` lists it; empty is the first radio that is on by position. A radio that is off or removed is not the main one: the first that is on is"),
    "fm/enabled": ("Settings tab, Radio (FM radio)", "`true`: the FM radio is there, the TNC of `tnc/profile` on its port; `false`: no FM radio, no port searched, no FM beacon, no digipeater (a station with the HF radio alone)"),
    "station/lat": ("My station tab, Location (Position: Fixed)", "where you are, decimal degrees, north positive (−90 to 90). The map opens here and distances are measured from here. The page shows it for a fixed station only; with a GPS chosen it stays stored and is used until the first fix. Empty with the longitude: no position, no beacon, no station of your own, and the map opens on the world"),
    "station/lon": ("My station tab, Location (Position: Fixed)", "decimal degrees, east positive (−180 to 180)"),
    "station/symbol_table": ("My station tab, Station (the symbol)", "`/` is the primary table, `\\` the alternate one, `0`-`9` and `A`-`Z` an overlay on the alternate table"),
    "station/symbol_code": ("My station tab, Station (the symbol)", "one printable character (`-` is a house, `>` a car)"),
    "station/comment": ("My station tab, Beacon", "the comment of your position: printable ASCII without `|` and `~`, at most {comment} characters, {comment_phg} when the PHG extension is sent. A save that breaks it is refused with the reason"),
    "station/status": ("My station tab, Status", "the text of a status of your own when the status source is the text: printable ASCII without `|` and `~`, at most {status} characters (the report always carries a time). Empty sends none ([beacon.md](beacon.md#the-status))"),
    "beacon/interval_min": ("My station tab, Beacon", "minutes between your position packets: 0 is off, else {beacon_interval_min}. 0 switches the beacon off ([beacon.md](beacon.md#beacon-off)): no beacon and no status report, while messages, answers, objects, bulletins and the digipeater go on. The page offers Off and every 30 min, 60 min and 3 hours; a moving station (a GPS is chosen) is offered Off and On (SmartBeaconing), where any value but 0 is On and the value is not used, and On stores 30. A stored value below {beacon_min} is raised to {beacon_min}, with a line in the log (a stored 20 or 45 is shown as one more choice). On the HF radio an interval below {hf_min} is raised to {hf_min}, with a line in the log; the FM radio keeps the interval set: a frame on a shared HF channel is not sent often. The default is off so that an upgrade never starts to transmit"),
    "beacon/path": ("My station tab, Beacon, Advanced", "the digipeaters of your beacon: up to 8 calls separated by commas, each a call with an optional SSID. Empty is the recommended path of your station's type, which the symbol decides: `WIDE1-1,WIDE2-1` for a mobile symbol (a car, a bike, a boat, an aircraft ...), `WIDE2-2` for any other. `DIRECT` is no digipeaters at all"),
    "beacon/power_w": ("My station tab, Beacon, Antenna", "the transmitter's power in watts ({beacon_power_w}) for the PHG extension of the beacon. Empty sends no PHG ([beacon.md](beacon.md#power-height-and-gain-phg))"),
    "beacon/antenna_height_m": ("My station tab, Beacon, Antenna", "the antenna's height above average terrain in metres ({beacon_antenna_height_m}), for PHG"),
    "beacon/antenna_gain_db": ("My station tab, Beacon, Antenna", "its gain in dBi ({beacon_antenna_gain_db}), for PHG"),
    "beacon/antenna_direction": ("My station tab, Beacon, Antenna", "`omni` or the point of the compass it favours ({directions}), for PHG"),
    "status/source": ("My station tab, Status", "where the status comes from: `off`, `text` (`station/status`) or `rig` (the frequency and mode of the radio, from `status/rigctld` and `status/template`). Empty follows the other settings: `rig` while `status/rigctld` is set, else `text` while `station/status` is not empty, else `off`. A save of `rig` without `status/rigctld` is refused"),
    "status/rigctld": ("My station tab, Status", "`host:port` of a Hamlib rigctld (its default is `127.0.0.1:4532`) whose frequency and mode make the status. Ignored for `text` and `off`"),
    "status/interval_min": ("My station tab, Status", "a status report goes out at most this often, whatever made it ({status_interval_min}). The page offers 30 min, 60 min and 2 hours. A stored value below {status_min} is raised to {status_min}, with a line in the log"),
    "status/template": ("My station tab, Status", "the text of a status made from the radio. `{{freq}}` is `14.074 MHz` (megahertz with three decimals), `{{mode}}` is the mode as rigctld names it (`USB`, `LSB`, `CW`, `FM` ...). No other field in braces, printable ASCII without `|` and `~`, and at most {status} characters with the widest values (`1296.000 MHz`, `PKTUSB`)"),
    "tnc/profile": ("Settings tab, TNC (Radio type)", "what kind of TNC the radio is: {profiles}. It decides what is written to the TNC to put it in KISS, whether the TNC is asked if it is there, and how it is reached ([radio.md](radio.md#the-tnc-type)). A TCP type is refused, with the reason, while `serial/port` names a serial device"),
    "serial/port": ("Settings tab, TNC (Port)", "the radio's port: a serial port such as `/dev/ttyUSB0` or `COM3`, `socket://host:port` (KISS over TCP, with every type), `bt://AA:BB:CC:DD:EE:FF` (Linux, a paired Bluetooth device) or `ble://AA:BB:CC:DD:EE:FF` (a Bluetooth LE KISS TNC, with the extra `ble` installed). Empty means: open `serial/last_port` if there is one, else on Linux listen to the ports of `serial/pattern` for the radio ([radio.md](radio.md#the-port))"),
    "serial/baud": ("Settings tab, TNC (Speed)", "the speed of the serial line, 8N1 ({serial_baud}). Empty is the type's own, 9600 for every serial type. A TCP or Bluetooth port has none"),
    "tcp/host": ("Settings tab, TNC", "where the `kiss-tcp` type connects when `serial/port` is empty. The serial types ignore it"),
    "tcp/port": ("Settings tab, TNC", "the KISS port of that program ({tcp_port}): Direwolf 8001, UZ7HO SoundModem and QtSoundModem 8100"),
    "hf/enabled": ("Settings tab, Radio (HF radio)", "`true`: the HF radio is there, the Mercury modem the daemon starts with the sound card and keying below, beside the FM radio or alone; `false`: no HF radio. Default `false`: nothing of HF is there, or changes, until it is ticked ([radio.md](radio.md#the-mercury-hf-modem))"),
    "hf/profile": ("Settings tab, Radio (HF radio, Radio type)", "what the HF radio is: `mercury`, Rhizomatica's Mercury modem on an SSB radio's sound card, or `dummy-hf`, the Dummy HF radio, which makes up a handful of distant fixed stations, keys nothing and plays your own frames through the computer's speakers as the modem's audio ([radio.md](radio.md#the-dummy-hf-radio)). Counts while `hf/enabled` is `true`"),
    "mercury/sound_card": ("Settings tab, Radio (HF radio, Sound card)", "the HF radio's sound card, as the list offers it (an id such as `plughw:1,0` on Linux, the device's name on Windows). The page stores the daemon's proposal here when it is empty (the one USB sound card that is both playback and capture, else the system's default device) and never offers the empty choice; a station that has it empty runs on the daemon's own choice as before. The other types ignore it ([radio.md](radio.md#the-mercury-hf-modem))"),
    "mercury/tx_gain_db": ("Settings tab, Radio (HF radio, Transmit level)", "the HF radio's transmit gain in dB, a whole number from -20 to 20 (`0`: the modem's own level, a frame peaks at -6 dBFS). Set with the - and + beside Tune; it is sent to the running modem at once and written to the modem's configuration at every start, and the tune tone follows it, so that the radio's ALC on the tone moves as it will on a frame. Default `0`"),
    "mercury/keying": ("Settings tab, Radio (HF radio, Keying)", "how the HF radio (the Mercury modem) keys the transmitter: `vox` (the radio keys itself: VOX, or its own data mode), `cm108` (the GPIO pin of a CM108 sound chip), `rts:PORT` or `dtr:PORT` (that line of the serial port named, `rts:/dev/ttyUSB0`, `dtr:COM3`: a DigiRig and most interfaces). The page stores the daemon's proposal here when it is empty (RTS of the one USB serial port of a radio or an interface when the sound card is a USB one, else VOX) and never offers the empty choice; a station that has it empty runs on the daemon's own choice as before. The other types ignore it"),
    "serial/last_port": (DAEMON_MEMORY, "the port the search found last time, tried first while `serial/port` is empty. Written by the daemon, in radio 1's own row `radio/1/last_port`; the page shows it as `found: PORT` beside an automatic Port"),
    "serial/pattern": (DB_ONLY, "the device files the search listens to (Linux only): shell globs (`*`, `?`, `[0-3]`), each an absolute path, separated by spaces. A device that several globs match keeps the name of the earliest glob, so a stable `by-id` name comes first. A change restarts the search, and **Find my radio** tries the same ports ([radio.md](radio.md#finding-the-radio))"),
    "serial/skip": (DB_ONLY, "ports the search never opens, nor does **Find my radio**, separated by commas (`/dev/brainbox_2`, a rotator's adapter, say)"),
    "web/network": ("Settings tab, Web page", "`true` lets other devices on the network open the page: it then listens on every interface, and a device other than this computer logs in with `web/key` first. It counts at once, with no restart ([network.md](network.md))"),
    "web/key": ("Settings tab, Web page", "the access key a device on the network types to log in: three groups of four lowercase letters and digits without `0 1 i l o` (`k7m2-x9pq-4hrt`). Made by the daemon when `web/network` is first on; a key of your own is accepted in the same form. A new one logs every device out"),
    "web/https": ("Settings tab, Web page", "`true` (with `web/network`) also serves the page over https, on the port after `web/port`, with a certificate NeoAPRS makes itself ([network.md](network.md#the-secure-connection-https))"),
    "web/port": (DB_ONLY, "the port of the page, read at the daemon's start. A port that is in use moves the page to the first free one of the ten after it. 0 takes a free one at once"),
    "web/allowed_hosts": (DB_ONLY, "names besides an IP address, `localhost` and the machine's own name (and `name.local`) that the page answers to, separated by commas"),
    "messages/alert": ("Settings tab, Notifications, On the NeoAPRS computer (Alert)", "whether a message to you, and an alert you set on a station, runs `messages/alert_command` ([notifications.md](notifications.md))"),
    "messages/alert_command": ("Settings tab, Notifications, On the NeoAPRS computer (Command)", "the shell line that is run (at most {alert_command} characters; empty runs nothing). The default shows a notification and plays a sound, in a form that suits the system"),
    "map/radius_km": ("Settings tab, Map (Radius)", "the detailed base map covers a square this far from your position in every direction ({map_radius_km} km). Read when the map is made ([page.md](page.md#the-base-map))"),
    "map/maxzoom": (DB_ONLY, "the deepest zoom the detailed map has tiles for ({map_maxzoom}): 10 shows towns, 12 streets, 14 houses. The page's Download map uses the stored value"),
    "map/station_hours": ("Stations tab, On map for", "how many hours after its last position a station stays on the map: {map_station_hours_choices}. The same for every station, in every browser; your own station and objects never leave. The Stations table keeps a station that has left the map, dim"),
    "map/source": (DB_ONLY, "where the map is cut from: empty is the latest daily build of build.protomaps.com; or a web address (`https://...`) or the path of a PMTiles file, such as a planet file of your own"),
    "update/url": (DB_ONLY, "the address of the version page that the daily update check asks (`http` or `https`; [install.md](install.md#the-update-check))"),
    "digi/enabled": ("Settings tab, Digipeater", "`true` switches the fill-in digipeater on ([beacon.md](beacon.md#the-fill-in-digipeater))"),
    "igate/enabled": ("Settings tab, Internet", "`true` shows the stations that APRS-IS has within `map/radius_km` of your position, marked as heard over the internet; nothing is sent, and nothing from the internet ever goes on the air ([igate.md](igate.md))"),
    "igate/server": (DB_ONLY, "`host:port` of the APRS-IS server the Internet switch logs in to. The default `rotate.aprs2.net:14580` is the round-robin name of the volunteer servers and the port of the filtered feed; empty leaves it waiting ([igate.md](igate.md#the-server))"),
    "igate/password": (DB_ONLY, "the APRS-IS passcode of `station/call`, digits 0 to 32767: only for a person who lets NeoAPRS put what the radio hears on APRS-IS ([igate.md](igate.md#advanced-putting-what-the-radio-hears-on-aprs-is)). NeoAPRS does not work it out. `-1` is refused; empty is the read-only login of the page. A secret"),
    "gps/source": ("My station tab, Station (Position)", "where your position comes from, and so whether you are a fixed or a moving station. `off` (**Fixed** on the page) is a fixed station at your location: the beacon goes every `beacon/interval_min` and can carry the PHG extension. `gpsd` (a gpsd daemon, at `gps/host`) or `serial` (the NMEA sentences of a receiver on `gps/device`) makes the beacon a moving station's: it follows the GPS (position, course, speed and altitude) and goes when SmartBeaconing says, not every `beacon/interval_min` (which is then only On or Off: 0 is off), with no PHG, and the {beacon_min}-minute floor of the fixed beacon does not apply. With no fresh GPS fix nothing is sent at all, and never your home position ([beacon.md](beacon.md#mobile-operation)). Without `gps/host` (for `gpsd`) or `gps/device` (for `serial`) the GPS waits and says so, and nothing is opened"),
    "gps/host": ("My station tab, Station (Position)", "`host:port` of the gpsd that `gpsd` reads (gpsd's own port is 2947)"),
    "gps/device": ("My station tab, Station (Position)", "the serial port of the GPS receiver for `serial`, such as `/dev/ttyUSB1` or `COM4`, or `socket://host:port` for a receiver behind a TCP serial server. Keep it apart from the radio's `serial/port`"),
    "gps/baud": ("My station tab, Station (Position)", "the receiver's speed on `gps/device` ({gps_baud}); NMEA 0183 is 4800, and many USB receivers speak 9600"),
    "beacon/travel": ("My station tab, Beacon (Travelling)", "how you travel while the beacon follows the GPS: `car`, `bicycle`, `foot` or `boat`. It decides when SmartBeaconing beacons: {moving_presets}. Below the slow speed a station counts as standing still, so there is a beacon only every 30 minutes and no turn is beaconed. The car's numbers are Dire Wolf's; the others are NeoAPRS's own choice"),
}

SHOWN = {"messages/alert_command": "a notification and a sound"}       # a default that is too long for a table


def _default(key: str) -> str:
    if key in SHOWN:
        return SHOWN[key]
    text = cfg.Config().to_data()[key]
    return f"`{text}`" if text else EMPTY


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


def _table(head: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    return "\n".join([_row(*head), _row(*["---"] * len(head)), *[_row(*r) for r in rows]]) + "\n"


def own_keys() -> list[str]:
    """Every key of a radio's own settings that some type has, in the order of the kinds and their fields."""
    return list(dict.fromkeys(f.key for kind in KINDS for f in kind_fields(kind)))


def undescribed() -> list[str]:
    """The settings of the code that DESCRIPTIONS lacks, and the keys it describes that are gone; the same for the radios' own settings and RADIO_DESCRIPTIONS."""
    return ([k for k in cfg.KEYS if k not in DESCRIPTIONS] + [f"{k} (gone)" for k in DESCRIPTIONS if k not in cfg.BY_KEY]
            + [f"radio/<id>/{k}" for k in own_keys() if k not in RADIO_DESCRIPTIONS] + [f"radio/<id>/{k} (gone)" for k in RADIO_DESCRIPTIONS if k not in own_keys()])


def settings() -> str:
    fields = _numbers()
    rows: list[tuple[object, ...]] = []
    for key, (where, text) in DESCRIPTIONS.items():
        if key in cfg.BY_KEY:
            rows.append((f"`{key}`", _default(key), where, text.format(**fields)))
    return _table(("key", "default", "where", "what it is"), rows)


def fixed() -> str:
    """Numbers the program decides, with no setting."""
    updates = int(UPDATE_EVERY_SEC // 3600)
    items = [
        f"Packets, weather observations and stations are kept {LOG_KEEP_DAYS} days (packets from the internet {INTERNET_KEEP_DAYS} days) and cleaned up once a day. Messages and bulletins are kept until you delete them.",
        f"The keep-alive asks a TNC that can be asked after {TNC_CHECK_SEC // 60} minutes of silence on the line (and a random minute or two more).",
        f"A message to a station is sent {STATION_ATTEMPTS} times, and one to the email gateway {EMAIL_ATTEMPTS} times, before it has failed or is unconfirmed.",
        f"Your own frames go out at least {int(SPACING_SEC)} seconds apart, except acks, answers to queries and digipeated packets.",
        f"The first beacon goes out {int(FIRST_DELAY_SEC)} seconds after the daemon starts.",
        f"Every frame you send has the tocall `{TOCALL}`. The beacon of a station that stays is the plain uncompressed position; a moving station's (`gps/source` is not `off`) is a compressed one, with the altitude in its comment.",
        f"A GPS fix older than {GPS_STALE_SEC} seconds is not used: a moving station sends no beacon on it, and never the home position instead.",
        f"At most {MAX_OBJECTS} objects and items, and {MAX_POSTED} bulletins, of your own at once. A bulletin is sent for {BULLETIN.lasts // 3600} hours and an announcement for {ANNOUNCEMENT.lasts // 3600} hours.",
        f"The update check asks the version page every {updates} hours.",
        f"On the HF radio a beacon interval below {HF_BEACON_MIN_MIN} minutes is raised to {HF_BEACON_MIN_MIN}; the FM radio keeps the interval set. The HF beacon waits a random extra time of up to {HF_BEACON_JITTER_SEC} seconds after each interval, so that stations started together do not key up together.",
        f"A frame on the HF radio is at most {HF_MAX_FRAME} bytes, addresses included. A beacon's comment is cut to fit, and the longest message always fits.",
    ]
    return "\n".join(f"- {item}" for item in items) + "\n"


RADIO_STATE_WORDS = {           # a radio's own state rows, `radio/<id>/<name>` (config.RADIO_STATE)
    "beacon_last_sent_at": "when the radio's beacon last went out, so that a restart waits out the rest of the interval",
    "last_port": "the port radio 1's search found (only radio 1 remembers one), which `serial/last_port` reads",
}
STATE_WORDS = {
    cfg.STATUS_SENT: "when the status report last went out",
    cfg.STATUS_TEXT: "the text of that status report, which ?APRSS answers with and the page shows",
    cfg.MAP_AUTO: "whether the detailed map that was begun by itself is still owed (`wanted`) or settled (`done`)",
    cfg.MESSAGE_RADIOS: "the radio the operator chose for messages to a station, by call and the radio's number (1 the FM radio, 2 the HF radio), while both radios are on",
    cfg.INSTALL_ID: "the random number of this installation that the update check sends",
    NOT_COUNTED: "`true` when the update check is to send the number 0 in place of this installation's own, so that the project does not count this run (a test machine; a run from the source tree does it by itself); set with `neoaprs db set update/not_counted true`, never shown on the page",
    SKED_TOKEN: "the secret of this installation that goes with each HF test it posts, so that only it can delete them; never shown in the log or the support bundle",
}


def state() -> str:
    """The rows the daemon keeps that are not settings: each radio's (`neoaprs.config.RADIO_STATE`), then the station's (`STATE_KEYS`, the update check's number and its switch, and the sked token)."""
    radio = [f"- `radio/<id>/{name}`: {RADIO_STATE_WORDS[name]}." for name in cfg.RADIO_STATE]
    return "\n".join([*radio, *(f"- `{key}`: {STATE_WORDS[key]}." for key in (*cfg.STATE_KEYS, cfg.INSTALL_ID, NOT_COUNTED, SKED_TOKEN))]) + "\n"


# a radio's own setting, `radio/<id>/<key>`: (where it is on the page, what it is). The order is the order of the table. Radio 1 is the FM radio and radio 2 the HF radio of today's flat keys.
RADIO_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "port": ("Settings tab, TNC (Port)", "the radio's port, as `serial/port` says it for radio 1: a serial port, `socket://host:port`, `bt://` or `ble://`; empty: the port the search finds"),
    "baud": ("Settings tab, TNC (Speed)", "the speed of its serial line, as `serial/baud` ({serial_baud}); empty: the type's own"),
    "tcp_host": ("Settings tab, TNC", "where a `kiss-tcp` radio connects while its port is empty, as `tcp/host`; a `lora-tcp` radio's is empty until the board's address is typed, and nothing is opened meanwhile"),
    "tcp_port": ("Settings tab, TNC", "the KISS port there ({tcp_port}), as `tcp/port`"),
    "beacon": (DB_ONLY, "`true`: the station's beacon goes out on this radio. Every radio that is on sends it in this version, whatever this says"),
    "path": ("My station tab, Beacon, Advanced", "the digipeaters of the beacon on this radio, as `beacon/path` says them for radio 1; only a type that may carry a path has it"),
    "digipeat": ("Settings tab, Digipeater", "`true`: this radio repeats what asks for it, as `digi/enabled` says it for radio 1"),
    "sound_card": ("Settings tab, Radio (HF radio, Sound card)", "the Mercury modem's sound card, as `mercury/sound_card` says it for radio 2"),
    "keying": ("Settings tab, Radio (HF radio, Keying)", "how the Mercury modem keys the transmitter, as `mercury/keying` says it for radio 2"),
    "tx_gain_db": ("Settings tab, Radio (HF radio, Transmit level)", "the Mercury modem's transmit gain in dB ({mercury_tx_gain_db}), as `mercury/tx_gain_db` says it for radio 2"),
}


def radios() -> str:
    """The types of radio with their own settings, then the own settings (`radio/<id>/<key>`) with their defaults and the types that have each."""
    fields = _numbers()
    types: list[tuple[object, ...]] = [(f"`{t.key}`", t.kind, t.name, ", ".join(f"`{f.key}`" for f in t.fields) or "none") for t in TYPES]
    own: list[tuple[object, ...]] = []
    for key in RADIO_DESCRIPTIONS:
        having = [t for t in TYPES if any(f.key == key for f in t.fields)]
        default = next(f.default for t in having for f in t.fields if f.key == key) if having else ""
        where, text = RADIO_DESCRIPTIONS[key]
        own.append((f"`radio/<id>/{key}`", f"`{default}`" if default else EMPTY, ", ".join(f"`{t.key}`" for t in having) or "none", where, text.format(**fields)))
    return _table(("type", "kind", "what it is", "its own settings"), types) + "\n" + _table(("key", "default", "types", "where", "what it is"), own)


MAKERS = {"settings": settings, "fixed": fixed, "state": state, "radios": radios}
PENDING: frozenset[str] = frozenset()     # blocks the document need not have yet (a new block that lands before the document has it)


def blocks_of(text: str) -> dict[str, str]:
    return {m.group(2): m.group(3) for m in BLOCK.finditer(text)}


def stale_blocks(text: str) -> list[str]:
    """The blocks the text lacks or whose content is not what the code says now."""
    found = blocks_of(text)
    return [name for name, make in MAKERS.items() if found.get(name) != make() and (name in found or name not in PENDING)]


def refreshed(text: str) -> str:
    """The text with every block made again."""
    def one(m: re.Match[str]) -> str:
        return m.group(1) + MAKERS[m.group(2)]() + m.group(4)
    return BLOCK.sub(one, text)
