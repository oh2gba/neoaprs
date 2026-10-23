"""The operator's settings as one immutable value: `Config`. The database keeps them as rows of text (`settings(key, value, rev)`, store.py); this module is the table of the keys, what each one is, what it
may be, and the two conversions: `Config.from_data(rows)` and `Config.to_data()`.

A value that is wrong falls back to its default and is logged with its key (a row somebody edited by hand must not stop the daemon); `Config.check(key, text)` is the strict form for a tool that is
about to write a value: it raises ValueError with the key in the text, or gives the text the way the program writes it."""
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .alertcommand import DEFAULT_ALERT_COMMAND
from .callsign import call_problem
from .configlegacy import with_legacy
from .configtypes import access_key, boolean, call_or_empty, int_in, int_or_off, optional_float, optional_int, over_the_air_problem, text_of, web_address
from .message import normal_call, normal_path
from .tncprofile import DEFAULT as DEFAULT_PROFILE, Profile, names_tcp, profile_of
from .versions import UPDATE_URL

log = logging.getLogger("neoaprs.config")

MAX_HIDE_AFTER_MIN = 10080           # a week: the longest a station may stay on the map after its last position
MAX_COMMENT = 43                     # what the comment of a position packet may be, with no data extension (spec 1517)
MAX_COMMENT_PHG = 36                 # with the 7-byte PHG data extension (spec 1546)
MAX_COMMENT_COMPRESSED = 40          # after a compressed position, which has no data extension (spec 1875)
MAX_STATUS = 55                      # the most characters of the text of a status report: ours always carries a day-hour-minute time, which leaves 55 of the spec's 62 (62 only without a time)
MIN_INTERVAL_MIN = 10                # the shortest time between two beacons or two status reports: the net cycle time of a station one hop from a digipeater (spec 646-662)
MAX_ALERT_COMMAND = 1000             # the longest line of messages/alert_command
MAX_MAP_SOURCE = 500                 # the longest map/source
MAP_RADIUS_KM = (10, 1000)           # map/radius_km: the area of the detailed map round the station
MAP_MAXZOOM = (6, 15)                # map/maxzoom: the deepest zoom of the detailed map
DEFAULT_STATUS_TEMPLATE = "QRV {freq} {mode}"
DEFAULT_SERIAL_PATTERN = "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"     # the ports the search listens to: by-id first, so that the stable name of a device is the one kept
MAX_SERIAL_PATTERN = 500
STATUS_FIELDS = ("freq", "mode")     # what status/template may name in braces
_LONGEST_FREQ, _LONGEST_MODE = "1296.000 MHz", "PKTUSB"       # the widest a frequency and a mode come out, to check that a template can fit MAX_STATUS
COMMENT_KEYS = frozenset({"station/comment", "beacon/power_w", "beacon/compressed"})   # the settings that decide how long the comment may be
PORT_KEYS = frozenset({"tnc/profile", "serial/port"})                   # the settings that decide whether the profile and the port go together
_BRACES = re.compile(r"\{([^{}]*)\}")
SYMBOL_TABLES = "/\\" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
ANTENNA_DIRECTIONS = ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")      # in the order of the specification's directivity digit: 0 omni, 1 NE ... 7 NW, 8 N


# ---- the types a setting can have: text to value (raising ValueError with the reason), value to text

def _globs(text: str) -> str:
    """One or more device globs, each an absolute path, separated by spaces (written with single spaces)."""
    parts = text.split()
    if not parts or any(not part.startswith("/") for part in parts):
        raise ValueError(f"{text!r} is not one or more absolute patterns separated by spaces, such as /dev/ttyUSB*")
    return text_of(MAX_SERIAL_PATTERN)(" ".join(parts))


def _status_text(max_length: int) -> Callable[[str], str]:
    """Printable ASCII, without `|` and `~`, of at most `max_length` characters."""
    def parse(text: str) -> str:
        value = text.strip()
        if problem := over_the_air_problem(value):
            raise ValueError(problem)
        if len(value) > max_length:
            raise ValueError(f"{len(value)} characters is more than the {max_length} allowed")
        return value
    return parse


def _path(text: str) -> str:
    """A list of digipeater calls separated by commas, each checked as a call; written the way the frame carries it (capitals, no blanks), empty for none."""
    return ",".join(normal_path(text))


def _destination(text: str) -> str:
    call = normal_call(text)
    if "-" in call:
        raise ValueError(f"{call!r} has an SSID; a destination is a call without one")
    return call


def _direction(text: str) -> str:
    """"omni" or a point of the compass (N NE E SE S SW W NW), written the way the setting keeps it."""
    word = text.strip()
    if word.lower() == "omni":
        return "omni"
    if word.upper() in ANTENNA_DIRECTIONS:
        return word.upper()
    raise ValueError(f"{text!r} is not omni or one of N NE E SE S SW W NW")


def _hostport(text: str) -> str:
    """"host:port" of a rigctld, or empty for none; the port 1 to 65535 (the name may be an IPv6 address in brackets)."""
    value = text.strip()
    if value == "":
        return ""
    host, _, port = value.rpartition(":")
    if not host.strip("[]") or not port.isdigit() or not 1 <= int(port) <= 65535 or any(c.isspace() for c in value) or not value.isprintable():
        raise ValueError(f"{text!r} is not host:port (4532 is rigctld's port)")
    return value


def fill_template(template: str, freq: str, mode: str) -> str:
    """The template with {freq} and {mode} replaced; any other text, braces too, stays."""
    return _BRACES.sub(lambda m: {"freq": freq, "mode": mode}.get(m.group(1), m.group(0)), template)


def _status_template(text: str) -> str:
    """Printable ASCII that names only {freq} and {mode} in braces and, with the widest values, is at most MAX_STATUS characters."""
    value = _status_text(MAX_STATUS * 2)(text)
    unknown = [name for name in _BRACES.findall(value) if name not in STATUS_FIELDS]
    if unknown:
        raise ValueError(f"{{{unknown[0]}}} is not a field of the template (the fields are {{freq}} and {{mode}})")
    size = len(fill_template(value, _LONGEST_FREQ, _LONGEST_MODE))
    if size > MAX_STATUS:
        raise ValueError(f"{size} characters with a long frequency and mode is more than the {MAX_STATUS} allowed")
    return value


def _symbol_table(text: str) -> str:
    if len(text) != 1 or text not in SYMBOL_TABLES:
        raise ValueError(f"{text!r} is not / or \\ or an overlay character A-Z, 0-9")
    return text


def _symbol_code(text: str) -> str:
    if len(text) != 1 or not "!" <= text <= "~":
        raise ValueError(f"{text!r} is not one printable ASCII character")
    return text


def _host(text: str) -> str:
    value = text.strip()
    if not value or any(c.isspace() for c in value) or not value.isprintable():
        raise ValueError(f"{text!r} is not an address or a name")
    return value


def _map_source(text: str) -> str:
    """Empty (the latest daily build of build.protomaps.com), a web address (http or https) or a path of a PMTiles file; never a word that starts with a dash, which the extract tool would take for an option."""
    value = text.strip()
    if value == "":
        return ""
    if len(value) > MAX_MAP_SOURCE or any(c.isspace() for c in value) or not value.isprintable() or value.startswith("-"):
        raise ValueError(f"{text!r} is not a web address or the path of a PMTiles file")
    if "://" in value and urlsplit(value).scheme not in ("http", "https"):
        raise ValueError(f"{text!r} is not an http or https address")
    return value


def _profile(text: str) -> str:
    """The key of a TNC profile (tncprofile.py), written the way the setting keeps it."""
    return profile_of(text).key


def _show(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


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
    Setting("tnc_profile", "tnc/profile", _profile),                         # what kind of TNC the radio is: what is said to it to put it in KISS, whether it can be asked if it is there, and how it is reached
    Setting("serial_port", "serial/port", text_of(255)),                     # empty: find the radio by listening to the ports of serial/pattern (a TCP profile connects to tcp/host and tcp/port instead)
    Setting("serial_baud", "serial/baud", optional_int(300, 921600)),        # empty: the speed of the profile
    Setting("tcp_host", "tcp/host", _host),                                  # where the TCP KISS server (Direwolf, a sound-card modem) runs
    Setting("tcp_port", "tcp/port", int_in(1, 65535)),                       # and its KISS port: 8001 for Direwolf, 8100 for the sound-card modems
    Setting("serial_last_port", "serial/last_port", text_of(255)),           # what the search found last time, tried first the next time
    Setting("serial_pattern", "serial/pattern", _globs),                   # space-separated globs of the device files the search listens to when no port is named
    Setting("serial_skip", "serial/skip", text_of(500)),                     # device paths, separated by commas, that the search for the radio never opens (a rotator's port, say)
    Setting("tnc_check_sec", "tnc/check_sec", int_or_off(10, 3600)),        # seconds of nothing at all on the line before the keep-alive checks that the radio is there; 0: off
    Setting("station_call", "station/call", call_or_empty),                 # empty: nothing is transmitted until a call is set (can_transmit)
    Setting("station_lat", "station/lat", optional_float(-90.0, 90.0)),     # empty: no position (no beacon; the map opens on the world)
    Setting("station_lon", "station/lon", optional_float(-180.0, 180.0)),
    Setting("station_symbol_table", "station/symbol_table", _symbol_table),
    Setting("station_symbol_code", "station/symbol_code", _symbol_code),
    Setting("station_comment", "station/comment", text_of(MAX_COMMENT, ascii_only=True)),
    Setting("station_status", "station/status", _status_text(MAX_STATUS)),   # free text sent as a status report (at most every status/interval_min, when it changed) and in answer to ?APRSS; empty: none
    Setting("beacon_power_w", "beacon/power_w", optional_int(0, 9999)),    # the transmitter's power for the PHG extension of the beacon; empty: no PHG is sent
    Setting("beacon_antenna_height_m", "beacon/antenna_height_m", int_in(0, 9999)),   # the antenna above average terrain, for the PHG extension
    Setting("beacon_antenna_gain_db", "beacon/antenna_gain_db", int_in(0, 9)),        # its gain over a dipole's isotropic figure, for the PHG extension
    Setting("beacon_antenna_direction", "beacon/antenna_direction", _direction),    # "omni" or the point of the compass it favours, for the PHG extension
    Setting("log_keep_days", "log/keep_days", int_in(1, 3650)),
    Setting("web_network", "web/network", boolean),                           # true: the page listens on every interface and a device other than this one logs in with web/key
    Setting("web_key", "web/key", access_key),                                # what a device on the network types to log in; made when web/network is first on, empty until then
    Setting("web_https", "web/https", boolean),                               # true (with web/network): the page is also served over https, on the port after web/port, with NeoAPRS's own certificate authority (neoaprs/web/tls.py)
    Setting("web_port", "web/port", int_in(0, 65535)),                        # 0: the system picks a free port (the log says which)
    Setting("web_allowed_hosts", "web/allowed_hosts", text_of(500)),         # names besides localhost, 127.0.0.1 and this machine's that a Host header may carry, separated by commas
    Setting("beacon_interval_min", "beacon/interval_min", int_or_off(MIN_INTERVAL_MIN, 1440), MIN_INTERVAL_MIN),   # 0: no beacon
    Setting("beacon_path", "beacon/path", _path),                           # the digipeaters of our beacon, "WIDE1-1,WIDE2-1"; empty: none
    Setting("beacon_destination", "beacon/destination", _destination),     # APZ is the experimental prefix of the tocalls
    Setting("beacon_compressed", "beacon/compressed", boolean),               # false: the uncompressed form, which every receiver reads
    Setting("beacon_dao", "beacon/dao", boolean),                             # true: `!Wxy!` at the end of the comment, one more digit of the minutes of the position (not with the compressed form)
    Setting("messages_alert", "messages/alert", boolean),                                       # true: a message to us runs messages/alert_command
    Setting("messages_alert_command", "messages/alert_command", text_of(MAX_ALERT_COMMAND)),    # a shell line, run with NEOAPRS_FROM, NEOAPRS_TEXT, NEOAPRS_AT and NEOAPRS_MSG_ID in its environment; empty: none
    Setting("status_rigctld", "status/rigctld", _hostport),                                   # host:port of a rigctld whose frequency and mode make the status; empty: the static station/status is the status
    Setting("status_interval_min", "status/interval_min", int_in(MIN_INTERVAL_MIN, 1440), MIN_INTERVAL_MIN),   # a status report goes out at most this often
    Setting("status_template", "status/template", _status_template),                         # the text of a status made from the radio: {freq} and {mode}
    Setting("map_hide_after_min", "map/hide_after_min", int_in(0, MAX_HIDE_AFTER_MIN)),    # a station whose last position is older than this leaves the map (the page hides it); 0: never. A station can have its own
    Setting("map_radius_km", "map/radius_km", int_in(*MAP_RADIUS_KM)),      # the detailed base map covers a square this far from our position in every direction
    Setting("map_maxzoom", "map/maxzoom", int_in(*MAP_MAXZOOM)),            # and goes down to this zoom (10 towns, 12 streets, 14 houses)
    Setting("map_source", "map/source", _map_source),                       # where the map is cut from; empty: the latest daily build of build.protomaps.com
    Setting("update_check", "update/check", boolean),                         # true: once a day the daemon asks the version page for the latest version (services/updatecheck.py)
    Setting("update_url", "update/url", web_address),                         # that page: it is sent this program's version and platform and nothing else
)
BY_KEY = {s.key: s for s in SETTINGS}
KEYS = tuple(s.key for s in SETTINGS)
BEACON_SENT = "beacon/last_sent_at"          # the rows the beacon and the status report keep to survive a restart (services/memory.py): state of the daemon, not settings, so not in SETTINGS
STATUS_SENT = "status/last_sent_at"
STATUS_TEXT = "status/last_text"
STATE_KEYS = (BEACON_SENT, STATUS_SENT, STATUS_TEXT)


@dataclass(frozen=True)
class Config:
    tnc_profile: str = DEFAULT_PROFILE.key
    serial_port: str = ""
    serial_baud: int | None = None
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 8001
    serial_last_port: str = ""
    serial_pattern: str = DEFAULT_SERIAL_PATTERN
    serial_skip: str = ""
    tnc_check_sec: int = 60
    station_call: str = ""
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
    log_keep_days: int = 30
    web_network: bool = False
    web_key: str = ""
    web_https: bool = False
    web_port: int = 7303
    web_allowed_hosts: str = ""
    beacon_interval_min: int = 0
    beacon_path: str = "WIDE1-1,WIDE2-1"
    beacon_destination: str = "APZNEO"
    beacon_compressed: bool = False
    beacon_dao: bool = False
    messages_alert: bool = True
    messages_alert_command: str = DEFAULT_ALERT_COMMAND
    status_rigctld: str = ""
    status_interval_min: int = 30
    status_template: str = DEFAULT_STATUS_TEMPLATE
    map_hide_after_min: int = 180
    map_radius_km: int = 150
    map_maxzoom: int = 12
    map_source: str = ""
    update_check: bool = True
    update_url: str = UPDATE_URL

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

    def port_problem(self, key: str = "tnc/profile") -> str:
        """Why the profile and serial/port do not go together, or empty when they do: a TCP profile connects to tcp/host and tcp/port, not to a serial device (a `tcp://` address in serial/port is fine)."""
        if self.profile.transport == "tcp" and self.serial_port and not names_tcp(self.serial_port):
            return f"{key}: {self.profile.name} connects over TCP (tcp/host and tcp/port), not to the serial port {self.serial_port}: clear serial/port, or choose a serial TNC"
        return ""

    @property
    def serial_skip_paths(self) -> tuple[str, ...]:
        """serial/skip as the list of paths it names."""
        return tuple(part for part in (piece.strip() for piece in self.serial_skip.split(",")) if part)

    @property
    def status_rig_address(self) -> tuple[str, int] | None:
        """status/rigctld as host and port, None while it is empty."""
        if not self.status_rigctld:
            return None
        host, _, port = self.status_rigctld.rpartition(":")
        return host.strip("[]"), int(port)

    @property
    def beacon_path_calls(self) -> tuple[str, ...]:
        """beacon/path as the list of calls it names."""
        return tuple(call for call in self.beacon_path.split(",") if call)

    @property
    def comment_limit(self) -> int:
        """How many characters the comment may have for what the beacon sends with these settings: 40 after a compressed position (which has no data extension), 36 when the PHG extension is
        sent (beacon/power_w is set), else 43. The `!Wxy!` of beacon/dao is the datum addendum's exception: its 5 bytes come on top."""
        if self.beacon_compressed:
            return MAX_COMMENT_COMPRESSED
        return MAX_COMMENT if self.beacon_power_w is None else MAX_COMMENT_PHG

    def comment_problem(self) -> str:
        """Why station/comment cannot be sent with the other settings, or empty when it can."""
        if problem := over_the_air_problem(self.station_comment):
            return f"station/comment: {problem}"
        limit = self.comment_limit
        if len(self.station_comment) <= limit:
            return ""
        why = "a compressed position" if self.beacon_compressed else "the PHG extension (clear beacon/power_w to send none)"
        return f"station/comment: {len(self.station_comment)} characters is more than the {limit} allowed with {why}"

    @classmethod
    def checked(cls, base: "Config", values: Mapping[str, str]) -> "Config":
        """The settings in force with these values (key to text) put in, for a save: every value is checked and the first wrong one raises ValueError with its key, and when one of the
        settings that decide the length of the comment is among them, so is the comment against the new settings."""
        parsed = {key: cls.check(key, text) for key, text in values.items()}
        config = cls.from_data({**base.to_data(), **parsed})
        if COMMENT_KEYS & parsed.keys() and (problem := config.comment_problem()):
            raise ValueError(problem)
        if PORT_KEYS & parsed.keys() and (problem := config.port_problem("tnc/profile" if "tnc/profile" in parsed else "serial/port")):
            raise ValueError(problem)
        return config

    @classmethod
    def from_data(cls, rows: Mapping[str, str]) -> "Config":
        """The settings as the database keeps them (key to the raw text of the value). A key that is missing, and one whose value is wrong (logged, with the key), has its default;
        a key that is not a setting is left alone."""
        rows = with_legacy(rows)
        values: dict[str, Any] = {}
        for setting in SETTINGS:
            if setting.key in rows:
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
        """The value of one setting from its text; ValueError with the key in it when the key is not a setting or the text is not a value of it."""
        setting = BY_KEY.get(key)
        if setting is None:
            raise ValueError(f"{key}: no such setting (the settings are {', '.join(KEYS)})")
        try:
            return setting.parse(text)
        except ValueError as e:
            raise ValueError(f"{key}: {e}") from None

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
    message, ack or answer to a query."""
    return call_problem(config.station_call) or None
