"""The operator's settings as one immutable value: `Config`. The database keeps them as rows of text (`settings(key, value, rev)`, store.py); this module is the table of the keys, what each one is, what it
may be, and the two conversions: `Config.from_data(rows)` and `Config.to_data()`.

A value that is wrong falls back to its default and is logged with its key (a row somebody edited by hand must not stop the daemon); `Config.check(key, text)` is the strict form for a tool that is
about to write a value: it raises ValueError with the key in the text, or gives the text the way the program writes it."""
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .alertcommand import DEFAULT_ALERT_COMMAND
from .callsign import call_problem
from .coded import CodedError, Param
from .configlegacy import with_legacy
from .configstatus import DEFAULT_STATUS_TEMPLATE, MAX_STATUS, hostport, status_source, status_template, status_text
from .configtypes import access_key, boolean, call_or_empty, int_in, int_or_off, optional_float, optional_int, over_the_air_refusal, text_of, web_address
from .message import path_choice
from .route import DIRECT_ONLY, WIDE_PATH
from .tncprofile import DEFAULT as DEFAULT_PROFILE, Profile, names_tcp, profile_of
from .versions import UPDATE_URL

log = logging.getLogger("neoaprs.config")


class SettingError(CodedError):
    """A setting that cannot be put in force: `key` is the one it is about (the first that is wrong, or the one a rule between settings holds up), `code` and `params` say what is wrong, `text` is the
    English sentence with the key in front."""

    def __init__(self, key: str, code: str, params: Mapping[str, Param], text: str) -> None:
        super().__init__(text, code, **params)
        self.key = key

MAX_COMMENT = 43                     # what the comment of a position packet may be, with no data extension (spec 1517)
MAX_COMMENT_PHG = 36                 # with the 7-byte PHG data extension (spec 1546)
MIN_INTERVAL_MIN = 15                # the shortest time between two beacons or two status reports: the page offers 15, 30 and 60 minutes for the beacon and 30 minutes to 2 hours for the status; a stored lower value is raised to this, with a line in the log
MAX_ALERT_COMMAND = 1000             # the longest line of messages/alert_command
MAX_MAP_SOURCE = 500                 # the longest map/source
MAP_RADIUS_KM = (10, 1000)           # map/radius_km: the area of the detailed map round the station
MAP_MAXZOOM = (6, 15)                # map/maxzoom: the deepest zoom of the detailed map
LATITUDE = (-90.0, 90.0)
LONGITUDE = (-180.0, 180.0)
RANGES: dict[str, tuple[int, int]] = {          # the whole numbers of the settings and what each may be, from the least to the most: also the page's (LIMITS of ui/src/protocol/lists.ts)
    "serial/baud": (300, 921600),
    "tcp/port": (1, 65535),
    "beacon/power_w": (0, 9999),
    "beacon/antenna_height_m": (0, 9999),
    "beacon/antenna_gain_db": (0, 9),
    "beacon/interval_min": (MIN_INTERVAL_MIN, 1440),
    "status/interval_min": (MIN_INTERVAL_MIN, 1440),
    "map/radius_km": MAP_RADIUS_KM,
    "map/maxzoom": MAP_MAXZOOM,
}
DEFAULT_SERIAL_PATTERN = "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"     # the ports the search listens to: by-id first, so that the stable name of a device is the one kept
MAX_SERIAL_PATTERN = 500
STATUS_KEYS = frozenset({"status/source", "status/rigctld"})            # the settings that decide whether the radio can be the status's source
COMMENT_KEYS = frozenset({"station/comment", "beacon/power_w"})   # the settings that decide how long the comment may be
PORT_KEYS = frozenset({"tnc/profile", "serial/port"})                   # the settings that decide whether the profile and the port go together
SYMBOL_TABLES = "/\\" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
ANTENNA_DIRECTIONS = ("omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N")      # in the order of the specification's directivity digit: 0 omni, 1 NE ... 7 NW, 8 N


# ---- the types a setting can have: text to value (raising ValueError with the reason), value to text

def _globs(text: str) -> str:
    """One or more device globs, each an absolute path, separated by spaces (written with single spaces)."""
    parts = text.split()
    if not parts or any(not part.startswith("/") for part in parts):
        raise CodedError(f"{text!r} is not one or more absolute patterns separated by spaces, such as /dev/ttyUSB*", "setting.not_globs", value=text)
    return text_of(MAX_SERIAL_PATTERN)(" ".join(parts))


def _path(text: str) -> str:
    """A list of digipeater calls separated by commas, each checked as a call; written the way the frame carries it (capitals, no blanks). Empty is the recommended path (WIDE1-1,WIDE2-1), DIRECT alone
    is no digipeaters at all."""
    calls = path_choice(text)
    return "" if calls is None else DIRECT_ONLY if not calls else ",".join(calls)


def _direction(text: str) -> str:
    """"omni" or a point of the compass (N NE E SE S SW W NW), written the way the setting keeps it."""
    word = text.strip()
    if word.lower() == "omni":
        return "omni"
    if word.upper() in ANTENNA_DIRECTIONS:
        return word.upper()
    raise CodedError(f"{text!r} is not omni or one of N NE E SE S SW W NW", "setting.not_direction", value=text)


def _symbol_table(text: str) -> str:
    if len(text) != 1 or text not in SYMBOL_TABLES:
        raise CodedError(f"{text!r} is not / or \\ or an overlay character A-Z, 0-9", "setting.not_symbol_table", value=text)
    return text


def _symbol_code(text: str) -> str:
    if len(text) != 1 or not "!" <= text <= "~":
        raise CodedError(f"{text!r} is not one printable ASCII character", "setting.not_symbol_code", value=text)
    return text


def _host(text: str) -> str:
    value = text.strip()
    if not value or any(c.isspace() for c in value) or not value.isprintable():
        raise CodedError(f"{text!r} is not an address or a name", "setting.not_host", value=text)
    return value


def _map_source(text: str) -> str:
    """Empty (the latest daily build of build.protomaps.com), a web address (http or https) or a path of a PMTiles file; never a word that starts with a dash, which the extract tool would take for an option."""
    value = text.strip()
    if value == "":
        return ""
    if len(value) > MAX_MAP_SOURCE or any(c.isspace() for c in value) or not value.isprintable() or value.startswith("-"):
        raise CodedError(f"{text!r} is not a web address or the path of a PMTiles file", "setting.not_map_source", value=text)
    if "://" in value and urlsplit(value).scheme not in ("http", "https"):
        raise CodedError(f"{text!r} is not an http or https address", "setting.not_web_address", value=text)
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
    Setting("serial_baud", "serial/baud", optional_int(*RANGES["serial/baud"])),        # empty: the speed of the profile
    Setting("tcp_host", "tcp/host", _host),                                  # where the TCP KISS server (Direwolf, a sound-card modem) runs
    Setting("tcp_port", "tcp/port", int_in(*RANGES["tcp/port"])),                       # and its KISS port: 8001 for Direwolf, 8100 for the sound-card modems
    Setting("serial_last_port", "serial/last_port", text_of(255)),           # what the search found last time, tried first the next time
    Setting("serial_pattern", "serial/pattern", _globs),                   # space-separated globs of the device files the search listens to when no port is named
    Setting("serial_skip", "serial/skip", text_of(500)),                     # device paths, separated by commas, that the search for the radio never opens (a rotator's port, say)
    Setting("station_call", "station/call", call_or_empty),                 # empty: nothing is transmitted until a call is set (can_transmit)
    Setting("station_lat", "station/lat", optional_float(*LATITUDE)),     # empty: no position (no beacon; the map opens on the world)
    Setting("station_lon", "station/lon", optional_float(*LONGITUDE)),
    Setting("station_symbol_table", "station/symbol_table", _symbol_table),
    Setting("station_symbol_code", "station/symbol_code", _symbol_code),
    Setting("station_comment", "station/comment", text_of(MAX_COMMENT, ascii_only=True)),
    Setting("station_status", "station/status", status_text(MAX_STATUS)),   # free text sent as a status report (at most every status/interval_min, when it changed) and in answer to ?APRSS; empty: none
    Setting("beacon_power_w", "beacon/power_w", optional_int(*RANGES["beacon/power_w"])),    # the transmitter's power for the PHG extension of the beacon; empty: no PHG is sent
    Setting("beacon_antenna_height_m", "beacon/antenna_height_m", int_in(*RANGES["beacon/antenna_height_m"])),   # the antenna above average terrain, for the PHG extension
    Setting("beacon_antenna_gain_db", "beacon/antenna_gain_db", int_in(*RANGES["beacon/antenna_gain_db"])),        # its gain in dBi, for the PHG extension
    Setting("beacon_antenna_direction", "beacon/antenna_direction", _direction),    # "omni" or the point of the compass it favours, for the PHG extension
    Setting("web_network", "web/network", boolean),                           # true: the page listens on every interface and a device other than this one logs in with web/key
    Setting("web_key", "web/key", access_key),                                # what a device on the network types to log in; made when web/network is first on, empty until then
    Setting("web_https", "web/https", boolean),                               # true (with web/network): the page is also served over https, on the port after web/port, with NeoAPRS's own certificate authority (neoaprs/web/tls.py)
    Setting("web_port", "web/port", int_in(0, 65535)),                        # 0: the system picks a free port (the log says which)
    Setting("web_allowed_hosts", "web/allowed_hosts", text_of(500)),         # names besides localhost, 127.0.0.1 and this machine's that a Host header may carry, separated by commas
    Setting("beacon_interval_min", "beacon/interval_min", int_or_off(*RANGES["beacon/interval_min"]), MIN_INTERVAL_MIN),   # 0: no beacon
    Setting("beacon_path", "beacon/path", _path),                           # the digipeaters of our beacon, "WIDE1-1,WIDE2-1"; empty: the same, recommended; DIRECT: none
    Setting("messages_alert", "messages/alert", boolean),                                       # true: a message to us runs messages/alert_command
    Setting("messages_alert_command", "messages/alert_command", text_of(MAX_ALERT_COMMAND)),    # a shell line, run with NEOAPRS_FROM, NEOAPRS_TEXT, NEOAPRS_AT and NEOAPRS_MSG_ID in its environment; empty: none
    Setting("status_source", "status/source", status_source),                                # where the status comes from: off, text (station/status) or rig (status/rigctld, status/template); empty: rig when status/rigctld is set, else text when station/status is, else off
    Setting("status_rigctld", "status/rigctld", hostport),                                   # host:port of a rigctld whose frequency and mode make the status; empty: the static station/status is the status
    Setting("status_interval_min", "status/interval_min", int_in(*RANGES["status/interval_min"]), MIN_INTERVAL_MIN),   # a status report goes out at most this often
    Setting("status_template", "status/template", status_template),                         # the text of a status made from the radio: {freq} and {mode}
    Setting("map_radius_km", "map/radius_km", int_in(*RANGES["map/radius_km"])),      # the detailed base map covers a square this far from our position in every direction
    Setting("map_maxzoom", "map/maxzoom", int_in(*RANGES["map/maxzoom"])),            # and goes down to this zoom (10 towns, 12 streets, 14 houses)
    Setting("map_source", "map/source", _map_source),                       # where the map is cut from; empty: the latest daily build of build.protomaps.com
    Setting("update_url", "update/url", web_address),                         # that page: it is sent this program's version and platform and nothing else
    Setting("digi_enabled", "digi/enabled", boolean),                         # true: a packet that asks for WIDE1-1, or for our call, is sent again by our radio (services/digipeater.py)
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
    web_network: bool = False
    web_key: str = ""
    web_https: bool = False
    web_port: int = 7303
    web_allowed_hosts: str = ""
    beacon_interval_min: int = 0
    beacon_path: str = "WIDE1-1,WIDE2-1"
    messages_alert: bool = True
    messages_alert_command: str = DEFAULT_ALERT_COMMAND
    status_source: str = ""
    status_rigctld: str = ""
    status_interval_min: int = 30
    status_template: str = DEFAULT_STATUS_TEMPLATE
    map_radius_km: int = 150
    map_maxzoom: int = 12
    map_source: str = ""
    update_url: str = UPDATE_URL
    digi_enabled: bool = False

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
        if not self.status_rigctld or self.status_choice != "rig":
            return None
        host, _, port = self.status_rigctld.rpartition(":")
        return host.strip("[]"), int(port)

    @property
    def beacon_path_calls(self) -> tuple[str, ...]:
        """beacon/path as the list of calls it names: the recommended path when it is empty, none at all for DIRECT."""
        if self.beacon_path == DIRECT_ONLY:
            return ()
        return tuple(call for call in (self.beacon_path or WIDE_PATH).split(",") if call)

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
        settings that decide the length of the comment is among them, so is the comment against the new settings. The error is a SettingError: its key, code and params are what the page goes by."""
        parsed = {key: cls.check(key, text) for key, text in values.items()}
        config = cls.from_data({**base.to_data(), **parsed})
        if COMMENT_KEYS & parsed.keys() and (refusal := config.comment_refusal()):
            raise refusal
        if STATUS_KEYS & parsed.keys() and config.status_source == "rig" and not config.status_rigctld:
            raise SettingError("status/source", "setting.status_needs_rigctld", {}, "status/source: the radio needs status/rigctld (host:port of a rigctld, 127.0.0.1:4532)")
        if PORT_KEYS & parsed.keys() and (refusal := config.port_refusal("tnc/profile" if "tnc/profile" in parsed else "serial/port")):
            raise refusal
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
    message, ack or answer to a query."""
    return call_problem(config.station_call) or None
