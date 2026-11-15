"""The operator's settings as one immutable value: `Config`. The database keeps the station's as rows of text (`settings(key, value, rev)`, store.py) and the radios as rows of their own (`radio`,
`radio_setting`, radiosql.py); this module is the table of the keys, what each one is, what it may be, and the two conversions: `Config.from_data(rows, radios=...)` and `Config.to_data()`.
The radios of the settings and today's flat keys of radios 1 and 2, which are a view of them, are configradios.py's.

A value that is wrong falls back to its default and is logged with its key (a row somebody edited by hand must not stop the daemon); `Config.check(key, text)` is the strict form for a tool that is
about to write a value: it raises ValueError with the key in the text, or gives the text the way the program writes it."""
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .alertcommand import DEFAULT_ALERT_COMMAND
from .callsign import call_problem
from .coded import CodedError, Param
from .configlegacy import with_legacy, with_network
from .configstatus import DEFAULT_STATUS_TEMPLATE, MAX_STATUS, hostport, status_source, status_template, status_text
from .configradios import DEFAULT_RADIOS, FLAT_HOMES, FlatFields, RadioViews, accepting_flat, path_text, radio_key_of as radio_key_of, radio_state_key as radio_state_key, radios_from_flat as radios_from_flat     # (the radios of the settings, and today's flat keys as a view of radios 1 and 2)
from .mercuryscope import TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from .configvalues import ANTENNA_DIRECTIONS as ANTENNA_DIRECTIONS, SYMBOL_TABLES as SYMBOL_TABLES, antenna_direction, aprsis_server, device_globs, digipeater_path, hf_profile, host_list, host_name, map_source, mercury_keying, passcode, port_address, symbol_code, symbol_table, tnc_profile
from .configtypes import access_key, boolean, call_or_empty, int_among, int_in, int_or_off, optional_float, optional_int, over_the_air_refusal, text_of, web_address, word_among
from .beaconrule import SETTING_MIN_MIN, station_interval
from .radiospec import FM_ID, RadioId, RadioSpec
from .radiotype import stored_text as _show
from .route import DIRECT_ONLY, recommended_path
from .smartbeacon import PRESETS, TRAVEL, SmartSettings
from .tncprofile import Profile, names_tcp, profile_of
from .versions import UPDATE_URL

log = logging.getLogger("neoaprs.config")


class SettingError(CodedError):
    """A setting that cannot be put in force: `key` is the one it is about (the first that is wrong, or the one a rule between settings holds up), `code` and `params` say what is wrong, `text` is the
    English sentence with the key in front."""

    def __init__(self, key: str, code: str, params: Mapping[str, Param], text: str) -> None:
        super().__init__(text, code, **params)
        self.key = key

RECEIVE_ONLY = "receive only: transmitting is switched off"      # why can_transmit refuses while station/transmit is false (a refusal to the page has the code "transmit.off" and says "RX only: nothing is sent")
LISTENS_ONLY = "receive only: no radio that is on can send"       # why it refuses while every enabled radio is one that only listens (to the page the same "transmit.off")
RX_ONLY_REASONS = (RECEIVE_ONLY, LISTENS_ONLY)
MAX_COMMENT = 43                     # what the comment of a position packet may be, with no data extension (spec 1517)
MAX_COMMENT_PHG = 36                 # with the 7-byte PHG data extension (spec 1546)
MIN_BEACON_INTERVAL_MIN = SETTING_MIN_MIN      # the shortest time between two beacons (the net cycle of a 2-hop path is 20 minutes, routine operation 30): the page offers 30 and 60 minutes and 3 hours; a stored lower value is raised to this, with a line in the log
MIN_STATUS_INTERVAL_MIN = 15         # the shortest time between two status reports: the page offers 30 minutes to 2 hours; a stored lower value is raised to this, with a line in the log
MAX_ALERT_COMMAND = 1000             # the longest line of messages/alert_command
MAP_RADIUS_KM, MAP_MAXZOOM = (10, 1000), (6, 15)           # map/radius_km: the area of the detailed map round the station; map/maxzoom: its deepest zoom
STATION_HOURS = (1, 3, 6, 12, 24)  # map/station_hours: the hours after its last position that a station stays on the map (the page hides it then; the table keeps it): the choices of the Stations tab
DEFAULT_STATION_HOURS = 3
LATITUDE, LONGITUDE = (-90.0, 90.0), (-180.0, 180.0)
RANGES: dict[str, tuple[int, int]] = {          # the whole numbers of the settings and what each may be, from the least to the most: also the page's (LIMITS of ui/src/protocol/lists.ts)
    "serial/baud": (300, 921600),
    "tcp/port": (1, 65535),
    "beacon/power_w": (0, 9999),
    "beacon/antenna_height_m": (0, 9999),
    "beacon/antenna_gain_db": (0, 9),
    "beacon/interval_min": (MIN_BEACON_INTERVAL_MIN, 1440),
    "status/interval_min": (MIN_STATUS_INTERVAL_MIN, 1440),
    "map/radius_km": MAP_RADIUS_KM,
    "map/maxzoom": MAP_MAXZOOM,
    "gps/baud": (300, 921600),
    "mercury/tx_gain_db": (TX_GAIN_MIN_DB, TX_GAIN_MAX_DB),
}
DEFAULT_SERIAL_PATTERN = "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"     # the ports the search listens to: by-id first, so that the stable name of a device is the one kept
STATUS_KEYS = frozenset({"status/source", "status/rigctld"})            # the settings that decide whether the radio can be the status's source
COMMENT_KEYS = frozenset({"station/comment", "beacon/power_w"})   # the settings that decide how long the comment may be
PORT_KEYS = frozenset({"tnc/profile", "serial/port"})                   # the settings that decide whether the profile and the port go together
GPS_SOURCES = ("off", "gpsd", "serial")                                # where the position of a moving station comes from: nowhere, a gpsd on the network, or a GPS receiver on a serial port


# ---- the types a setting can have: text to value (raising ValueError with the reason), value to text (the ones that are more than a number or a word are in configvalues.py)

def _host_port(text: str) -> tuple[str, int] | None:
    """A `host:port` as the pair (the name may be an IPv6 address in brackets); None for an empty text."""
    if not text:
        return None
    host, _, port = text.rpartition(":")
    return host.strip("[]"), int(port)


@dataclass(frozen=True)
class Setting:
    attr: str                        # the field of Config
    key: str                         # the row of the settings table
    parse: Callable[[str], Any]
    floor: int = 0                   # a stored whole number below this (and above 0 when 0 is not a value) is raised to it, with a line in the log; saving it is refused all the same


def _raised(setting: Setting, text: str) -> int | None:
    """The floor of the setting when its stored text is a whole number between 1 and the floor; else None."""
    try:
        value = int(text.strip())
    except ValueError:
        return None
    return setting.floor if 0 < value < setting.floor else None


SETTINGS: tuple[Setting, ...] = (
    Setting("tnc_profile", "tnc/profile", tnc_profile),                         # what kind of TNC the radio is: what is said to it to put it in KISS, whether it can be asked if it is there, and how it is reached
    Setting("serial_port", "serial/port", port_address),                     # empty: find the radio by listening to the ports of serial/pattern (a TCP profile connects to tcp/host and tcp/port instead)
    Setting("serial_baud", "serial/baud", optional_int(*RANGES["serial/baud"])),        # empty: the speed of the profile
    Setting("tcp_host", "tcp/host", host_name),                                  # where the TCP KISS server (Direwolf, a sound-card modem) runs
    Setting("tcp_port", "tcp/port", int_in(*RANGES["tcp/port"])),                       # and its KISS port: 8001 for Direwolf, 8100 for the sound-card modems
    Setting("hf_enabled", "hf/enabled", boolean),                           # true: the HF radio (the Mercury modem the daemon starts, with mercury/*) is there beside the FM one, or alone
    Setting("hf_profile", "hf/profile", hf_profile),                        # what the HF radio is: the Mercury modem (mercury), or the Dummy HF radio (dummy-hf) that makes up distant stations and keys nothing
    Setting("mercury_sound_card", "mercury/sound_card", text_of(200)),           # the radio's sound card for the Mercury HF modem, as `mercury -z` names it (plughw:1,0); empty: the daemon's own choice (mercury.choose_sound_card), else the system's default device
    Setting("mercury_keying", "mercury/keying", mercury_keying),                 # how the Mercury modem keys the radio: vox (the radio keys itself), cm108 (the sound chip's GPIO), rts:PORT or dtr:PORT (a line of a serial port); empty: the daemon's own choice (mercury.choose_keying)
    Setting("mercury_tx_gain_db", "mercury/tx_gain_db", int_in(*RANGES["mercury/tx_gain_db"])),           # the Mercury modem's transmit gain in dB (0: its own level, a frame peaks at -6 dBFS): set live from the HF box beside Tune, written to its ini at every start
    Setting("serial_last_port", "serial/last_port", port_address),           # what the search found last time, tried first the next time
    Setting("serial_pattern", "serial/pattern", device_globs),                   # space-separated globs of the device files the search listens to when no port is named
    Setting("serial_skip", "serial/skip", text_of(500)),                     # device paths, separated by commas, that the search for the radio never opens (a rotator's port, say)
    Setting("station_call", "station/call", call_or_empty),                 # empty: nothing is transmitted until a call is set (can_transmit)
    Setting("station_transmit", "station/transmit", boolean),               # false: receive only, nothing is transmitted whatever is asked or due (can_transmit); kept in the database, so it holds after a restart
    Setting("main_choice", "station/main_radio", optional_int(1, 2**31 - 1)),        # the radio the operator chose as the main one, by its id (bulletins, the status, the first choice of Ask and email); empty: the first enabled by position
    Setting("fm_enabled", "fm/enabled", boolean),                           # true: the FM radio (the KISS TNC of tnc/profile) is there; false: no FM radio, no port searched, no FM beacon (a station with the HF radio alone)
    Setting("station_lat", "station/lat", optional_float(*LATITUDE)),     # empty: no position (no beacon; the map opens on the world)
    Setting("station_lon", "station/lon", optional_float(*LONGITUDE)),
    Setting("station_symbol_table", "station/symbol_table", symbol_table),
    Setting("station_symbol_code", "station/symbol_code", symbol_code),
    Setting("station_comment", "station/comment", text_of(MAX_COMMENT, ascii_only=True)),
    Setting("station_status", "station/status", status_text(MAX_STATUS)),   # free text sent as a status report (at most every status/interval_min, when it changed) and in answer to ?APRSS; empty: none
    Setting("beacon_power_w", "beacon/power_w", optional_int(*RANGES["beacon/power_w"])),    # the transmitter's power for the PHG extension of the beacon; empty: no PHG is sent
    Setting("beacon_antenna_height_m", "beacon/antenna_height_m", int_in(*RANGES["beacon/antenna_height_m"])),   # the antenna above average terrain, for the PHG extension
    Setting("beacon_antenna_gain_db", "beacon/antenna_gain_db", int_in(*RANGES["beacon/antenna_gain_db"])),        # its gain in dBi, for the PHG extension
    Setting("beacon_antenna_direction", "beacon/antenna_direction", antenna_direction),    # "omni" or the point of the compass it favours, for the PHG extension
    Setting("web_network", "web/network", boolean),                           # true: the page listens on every interface and a device other than this one logs in with web/key
    Setting("web_key", "web/key", access_key),                                # what a device on the network types to log in; made when web/network is first on, empty until then
    Setting("web_https", "web/https", boolean),                               # true (with web/network): the page is also served over https, on the port after web/port, with NeoAPRS's own certificate authority (neoaprs/web/tls.py)
    Setting("web_port", "web/port", int_in(0, 65535)),                        # 0: the system picks a free port (the log says which)
    Setting("web_allowed_hosts", "web/allowed_hosts", host_list),         # names besides localhost, 127.0.0.1 and this machine's that a Host header may carry, separated by commas
    Setting("beacon_interval_min", "beacon/interval_min", int_or_off(*RANGES["beacon/interval_min"]), MIN_BEACON_INTERVAL_MIN),   # 0: the beacon is off, for a moving station too (any other value is On there, and unused)
    Setting("beacon_path", "beacon/path", digipeater_path),                           # the digipeaters of our beacon, empty: the recommended path of the station's symbol (route.recommended_path); DIRECT: none
    Setting("messages_alert", "messages/alert", boolean),                                       # true: a message to us runs messages/alert_command
    Setting("messages_alert_command", "messages/alert_command", text_of(MAX_ALERT_COMMAND)),    # a shell line, run with NEOAPRS_FROM, NEOAPRS_TEXT, NEOAPRS_AT and NEOAPRS_MSG_ID in its environment; empty: none
    Setting("status_source", "status/source", status_source),                                # where the status comes from: off, text (station/status) or rig (status/rigctld, status/template); empty: rig when status/rigctld is set, else text when station/status is, else off
    Setting("status_rigctld", "status/rigctld", hostport),                                   # host:port of a rigctld whose frequency and mode make the status; empty: the static station/status is the status
    Setting("status_interval_min", "status/interval_min", int_in(*RANGES["status/interval_min"]), MIN_STATUS_INTERVAL_MIN),   # a status report goes out at most this often
    Setting("status_template", "status/template", status_template),                         # the text of a status made from the radio: {freq} and {mode}
    Setting("map_radius_km", "map/radius_km", int_in(*RANGES["map/radius_km"])),      # the detailed base map covers a square this far from our position in every direction
    Setting("map_maxzoom", "map/maxzoom", int_in(*RANGES["map/maxzoom"])),            # and goes down to this zoom (10 towns, 12 streets, 14 houses)
    Setting("map_station_hours", "map/station_hours", int_among(STATION_HOURS)),     # how long a station stays on the map after its last position (the Stations tab chooses; our own station and objects stay)
    Setting("map_source", "map/source", map_source),                       # where the map is cut from; empty: the latest daily build of build.protomaps.com
    Setting("update_url", "update/url", web_address),                         # that page: it is sent this program's version and platform and nothing else
    Setting("digi_enabled", "digi/enabled", boolean),                         # true: a packet that asks for WIDE1-1, or for our call, is sent again by our radio (services/digipeater.py)
    Setting("igate_enabled", "igate/enabled", boolean),                       # true: what the radio hears is put on APRS-IS by a receive-only iGate (services/igate.py); nothing from the internet is ever sent on the air
    Setting("igate_server", "igate/server", aprsis_server),                   # host:port of the APRS-IS server the iGate logs in to (the filtered port 14580 of the round-robin name)
    Setting("igate_password", "igate/password", passcode),                    # the APRS-IS passcode of station/call (digits; a secret; -1, the read-only login, is refused). NeoAPRS does not work it out: the operator types it
    Setting("gps_source", "gps/source", word_among(GPS_SOURCES)),             # where the position of a moving station comes from: off, gpsd (a gpsd daemon, gps/host) or serial (a GPS receiver's NMEA on gps/device)
    Setting("gps_host", "gps/host", hostport),                                # host:port of the gpsd that gps/source gpsd reads; 2947 is gpsd's port
    Setting("gps_device", "gps/device", port_address),                        # the serial port of the GPS receiver for gps/source serial, such as /dev/ttyUSB1; a socket://host:port address too
    Setting("gps_baud", "gps/baud", int_in(*RANGES["gps/baud"])),             # its speed: 4800 is NMEA 0183's
    Setting("beacon_travel", "beacon/travel", word_among(TRAVEL)),    # how a station that follows the GPS (gps/source is not off) travels: by car, bicycle, foot or boat, which decides how often SmartBeaconing beacons
)
BY_KEY = {s.key: s for s in SETTINGS}
KEYS = tuple(s.key for s in SETTINGS)             # every key of the settings table and of the wire's `config`, in the form's order: the station's rows, and today's flat keys of radios 1 and 2 (configradios.FLAT_HOMES: a view until the wire names a radio)
RADIO_STATION_KEYS = ("station/main_radio",)      # the station's settings of the radios, which the wire's `config` tells beside the radios' own keys (`radio_values`), not among the settings the form of before shows
LAST_PORT = radio_state_key(FM_ID, "last_port")   # the row `serial/last_port` is kept in once the radios are stored: radio 1's own state
STATION_KEYS = tuple(s.key for s in SETTINGS if s.attr not in FLAT_HOMES and s.key != "serial/last_port")       # the settings that are the station's: the rows of the table `settings` under their own key
BEACON_SENT = "beacon/last_sent_at"          # the rows of before of the two beacons' last sends, which migration 31 renamed radio/1/ and radio/2/beacon_last_sent_at; a Beacon made without the station's maker of frames (tests, until the round's removals) still keeps the first
HF_BEACON_SENT = "hf/beacon_last_sent_at"
STATE_BEFORE_31 = (BEACON_SENT, HF_BEACON_SENT)
RADIO_STATE = ("beacon_last_sent_at", "last_port")    # a radio's own state rows, radio_state_key(id, name): when its beacon last went out (services/beacon.py), the port its search found (LAST_PORT)
STATUS_SENT, STATUS_TEXT = "status/last_sent_at", "status/last_text"     # the rows the status report keeps to survive a restart (services/memory.py): state of the daemon, not settings, so not in SETTINGS
MAP_AUTO = "map/auto"                        # whether the detailed map begun without a click is still owed: wanted (begun, not finished: tried again at the next start), or done (services/mapauto.py)
MESSAGE_RADIOS = "messages/radio_by_station"   # the radio the operator chose for messages to a station, by call, as JSON, by the radio's id since migration 31 ({"OH2GAX-2": 2}; neoaprs/radioregistry.py)
STATE_KEYS = (STATUS_SENT, STATUS_TEXT, MAP_AUTO, MESSAGE_RADIOS)       # the station's state rows; each radio's are RADIO_STATE's
INSTALL_ID = "update/install_id"             # the random number of this installation that the update check sends (services/updatecheck.py); state of the daemon too, but not one of STATE_KEYS, which are the schedule's rows
HF_DIAL = "update/hf_dial"                   # the HF dial the version page named last ("7.0541 MHz USB"; services/updatecheck.py): the frequency the group meets on moves with the page, not with a release; empty: the built-in one (mercury.DIAL_TEXT)


@accepting_flat
@dataclass(frozen=True)
class Config(FlatFields, RadioViews):
    serial_last_port: str = ""
    serial_pattern: str = DEFAULT_SERIAL_PATTERN
    serial_skip: str = ""
    station_call: str = ""
    station_transmit: bool = True
    station_lat: float | None = None
    station_lon: float | None = None
    station_symbol_table: str = "/"
    station_symbol_code: str = "-"
    station_comment: str = "NeoAPRS"
    station_status: str = ""
    beacon_power_w: int | None = None
    beacon_antenna_height_m: int = 0
    beacon_antenna_gain_db: int = 0
    beacon_antenna_direction: str = "omni"
    web_network: bool = False
    web_key: str = ""
    web_https: bool = False
    web_port: int = 7303
    web_allowed_hosts: str = ""
    beacon_interval_min: int = 0
    messages_alert: bool = True
    messages_alert_command: str = DEFAULT_ALERT_COMMAND
    status_source: str = ""
    status_rigctld: str = ""
    status_interval_min: int = 30
    status_template: str = DEFAULT_STATUS_TEMPLATE
    map_radius_km: int = 150
    map_maxzoom: int = 12
    map_station_hours: int = DEFAULT_STATION_HOURS
    map_source: str = ""
    update_url: str = UPDATE_URL
    igate_enabled: bool = False
    igate_server: str = "rotate.aprs2.net:14580"
    igate_password: str = ""
    gps_source: str = "off"
    gps_host: str = "127.0.0.1:2947"
    gps_device: str = ""
    gps_baud: int = 4800
    beacon_travel: str = TRAVEL[0]
    radios: tuple[RadioSpec, ...] = DEFAULT_RADIOS         # every radio, removed ones too, by id, as they are stored (Store.radios()); settings that say nothing have today's two, the FM radio on and the HF radio off
    main_choice: RadioId | None = None                    # the radio the operator chose as the main one (station/main_radio); None: the first enabled

    @property
    def mobile(self) -> bool:
        """True when the beacon follows the GPS (gps/source is gpsd or serial); off is a fixed station at the home position."""
        return self.gps_source != "off"

    @property
    def beacon_on(self) -> bool:
        """Whether the beacon is on: `beacon/interval_min` is not 0. Off sends no beacon (the timer, SmartBeaconing, Beacon now) and no status report; it is not receive only, messages, acks, answers, objects, bulletins and the digipeater go on."""
        return self.beacon_interval_min > 0

    @property
    def smart(self) -> SmartSettings:
        """The SmartBeaconing numbers of the preset that beacon/travel names."""
        return PRESETS[self.beacon_travel]

    def beacon_interval(self) -> int:
        """How often our position goes out on some radio, in minutes (0: off): the shortest interval in force on a radio the beacon goes out on (beaconrule.station_interval; each radio's own is
        `beaconrule.beacon_interval`, the setting raised to that radio's floor). The one number of the page's status (`beacon_interval_min`, neoaprs/web/api.py) until the wire tells each radio's."""
        return station_interval(self.beacon_interval_min, self.radios, self.main_radio)

    def radio_refusal(self, key: str = "hf/enabled") -> SettingError | None:
        """Why the radios' tickboxes do not go together, or None when they do: at least one radio that is not removed stays on (the page greys the last one that is on, so this is for the shell). `key`
        is the one that was set, which the refusal names."""
        if not self.enabled_radios:
            return SettingError(key, "radio.last_enabled", {}, f"{key}: at least one radio stays on: turn another radio on first")
        return None

    @property
    def station_position(self) -> tuple[float, float] | None:
        """Where we are as latitude and longitude, None while either is empty."""
        if self.station_lat is None or self.station_lon is None:
            return None
        return self.station_lat, self.station_lon

    @property
    def profile(self) -> Profile:
        """The TNC profile that tnc/profile names."""
        return profile_of(self.tnc_profile)

    @property
    def tnc_baud(self) -> int:
        """The speed to open a serial line at: serial/baud, else the profile's, else 9600."""
        return self.serial_baud or self.profile.baud or 9600

    def port_refusal(self, key: str = "tnc/profile") -> SettingError | None:
        """Why the profile and serial/port do not go together, or None when they do: a TCP profile connects to tcp/host and tcp/port, not to a serial device (a `tcp://` address in serial/port is fine)."""
        if self.profile.transport == "tcp" and self.serial_port and not names_tcp(self.serial_port):
            return SettingError(key, "setting.profile_port", {"profile": self.profile.name, "port": self.serial_port},
                                f"{key}: {self.profile.name} connects over TCP (tcp/host and tcp/port), not to the serial port {self.serial_port}: clear serial/port, or choose a serial TNC")
        return None

    @property
    def serial_skip_paths(self) -> tuple[str, ...]:
        """serial/skip as the list of paths it names."""
        return tuple(part for part in (piece.strip() for piece in self.serial_skip.split(",")) if part)

    @property
    def status_choice(self) -> str:
        """Where the status comes from: `status/source`, and while that is empty what the other settings say (the radio when status/rigctld is set, else the text when there is one, else none)."""
        if self.status_source:
            return self.status_source
        return "rig" if self.status_rigctld else "text" if self.station_status else "off"

    @property
    def status_rig_address(self) -> tuple[str, int] | None:
        """status/rigctld as host and port, None while it is empty or the status does not come from the radio."""
        return _host_port(self.status_rigctld) if self.status_choice == "rig" else None

    @property
    def igate_address(self) -> tuple[str, int] | None:
        """igate/server as host and port, None while it is empty."""
        return _host_port(self.igate_server)

    def path_calls(self, radio: RadioId) -> tuple[str, ...]:
        """The calls of the radio's own path (configradios.path_text): empty the path its kind recommends (LoRa WIDE1-1), else the recommended path of the station's symbol; none at all for DIRECT."""
        path = path_text(self.radios, radio)
        return () if path == DIRECT_ONLY else tuple(call for call in (path or self.recommended_path).split(",") if call)

    @property
    def beacon_path_calls(self) -> tuple[str, ...]:
        """beacon/path as the list of calls it names (radio 1's own path: path_calls)."""
        return self.path_calls(FM_ID)

    @property
    def recommended_path(self) -> str:
        """The path that is recommended for this station: WIDE1-1,WIDE2-1 when its symbol is a mobile one, WIDE2-2 for any other (route.recommended_path)."""
        return recommended_path(self.station_symbol_table, self.station_symbol_code)

    @property
    def comment_limit(self) -> int:
        """How many characters the comment may have for what the beacon sends with these settings: 36 when the PHG extension is sent (beacon/power_w is set), else 43."""
        return MAX_COMMENT if self.beacon_power_w is None else MAX_COMMENT_PHG

    def comment_refusal(self) -> SettingError | None:
        """Why station/comment cannot be sent with the other settings, or None when it can."""
        if refusal := over_the_air_refusal(self.station_comment):
            return SettingError("station/comment", refusal.code, refusal.params, f"station/comment: {refusal}")
        limit = self.comment_limit
        if len(self.station_comment) <= limit:
            return None
        return SettingError("station/comment", "setting.comment_too_long", {"length": len(self.station_comment), "limit": limit},
                            f"station/comment: {len(self.station_comment)} characters is more than the {limit} allowed with the PHG extension (clear beacon/power_w to send none)")

    def comment_problem(self) -> str:
        """The sentence of comment_refusal; empty when the comment can be sent."""
        return str(refusal) if (refusal := self.comment_refusal()) else ""

    @classmethod
    def checked(cls, base: "Config", values: Mapping[str, str]) -> "Config":
        """The settings in force with these values (key to text) put in, for a save: every value is checked and the first wrong one raises ValueError with its key, and when one of the
        settings that decide the length of the comment is among them, so is the comment against the new settings. The error is a SettingError: its key, code and params are what the page goes by.
        The radios of `base` stay, with the flat keys among the values put into radios 1 and 2."""
        parsed = {key: cls.check(key, text) for key, text in values.items()}
        rows = {key: text for key, text in {**base.to_data(), **parsed}.items() if BY_KEY[key].attr not in FLAT_HOMES}
        flat = {BY_KEY[key].attr: cls.parse(key, text) for key, text in parsed.items() if BY_KEY[key].attr in FLAT_HOMES}
        config = replace(cls.from_data(rows, radios=base.radios), **flat)
        if COMMENT_KEYS & parsed.keys() and (refusal := config.comment_refusal()):
            raise refusal
        if STATUS_KEYS & parsed.keys() and config.status_source == "rig" and not config.status_rigctld:
            raise SettingError("status/source", "setting.status_needs_rigctld", {}, "status/source: the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)")
        if (set_now := [key for key in ("fm/enabled", "hf/enabled") if key in parsed]) and (refusal := config.radio_refusal(set_now[0])):
            raise refusal
        if PORT_KEYS & parsed.keys() and (refusal := config.port_refusal("tnc/profile" if "tnc/profile" in parsed else "serial/port")):
            raise refusal
        return config

    @classmethod
    def from_data(cls, rows: Mapping[str, str], *, radios: Iterable[RadioSpec] | None = None) -> "Config":
        """The settings as the database keeps them (key to the raw text of the value). A key that is missing, and one whose value is wrong (logged, with the key), has its default;
        a key that is not a setting is left alone. `radios`: the radios as they are stored (Store.radios()); the flat keys of radios 1 and 2 are then not read from the rows, and radio 1's last port
        is its own state row. None, the call from before the radios were rows, reads today's two radios from the flat keys among the rows, with the rules of an older version (configlegacy.py)."""
        rows = with_legacy(rows) if radios is None else with_network(rows)
        if radios is not None and LAST_PORT in rows:
            rows = {**rows, "serial/last_port": rows[LAST_PORT]}          # (radio 1's own row wins over one under the old name, which nothing writes once the radios are stored)
        values: dict[str, Any] = {} if radios is None else {"radios": tuple(sorted(radios, key=lambda spec: spec.id))}
        for setting in SETTINGS:
            if setting.key in rows and (radios is None or setting.attr not in FLAT_HOMES):
                try:
                    values[setting.attr] = cls.parse(setting.key, rows[setting.key])
                except ValueError as e:
                    if (raised := _raised(setting, rows[setting.key])) is not None:
                        log.warning("%s; %d is used", e, raised)
                        values[setting.attr] = raised
                    else:
                        log.warning("%s; the default %s is used", e, _show(getattr(DEFAULTS, setting.attr)) or "(empty)")
        return cls(**values)

    def to_data(self) -> dict[str, str]:
        """Every setting as key and text, in the order of SETTINGS."""
        return {s.key: _show(getattr(self, s.attr)) for s in SETTINGS}

    @staticmethod
    def parse(key: str, text: str) -> Any:
        """The value of one setting from its text; SettingError (a ValueError, with the key in its text) when the key is not a setting or the text is not a value of it."""
        setting = BY_KEY.get(key)
        if setting is None:
            raise SettingError(key, "setting.unknown", {}, f"{key}: no such setting (the settings are {', '.join(KEYS)})")
        try:
            return setting.parse(text)
        except CodedError as e:
            raise SettingError(key, e.code, e.params, f"{key}: {e}") from None
        except ValueError as e:
            raise SettingError(key, "other", {}, f"{key}: {e}") from None

    @classmethod
    def check(cls, key: str, text: str) -> str:
        """The text of the setting as it is stored ("oh2gba" gives "OH2GBA"); ValueError naming the key when it is wrong."""
        return _show(cls.parse(key, text))

    def changed(self, other: "Config") -> list[str]:
        """The keys whose value differs between this and the other, in the order of SETTINGS."""
        return [s.key for s in SETTINGS if getattr(self, s.attr) != getattr(other, s.attr)]


DEFAULTS = Config()


def can_transmit(config: Config) -> str | None:
    """The transmit interlock, the one place that decides it: None when this station may transmit, else the reason it may not. Nothing at all is transmitted while there is one: no beacon, status,
    message, ack or answer to a query. Receive only is the first reason: `station/transmit` false, or every enabled radio one that cannot send (`listens_only`)."""
    if not config.station_transmit or config.listens_only:
        return RECEIVE_ONLY if not config.station_transmit else LISTENS_ONLY
    return call_problem(config.station_call) or None
