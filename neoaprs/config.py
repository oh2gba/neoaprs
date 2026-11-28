"""The operator's settings as one immutable value, `Config`.

The table of keys, types and limits, and `Config.from_data` / `Config.to_data`. A wrong stored value
falls back to its default; `Config.check` is the strict form and raises SettingError."""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from .alertcommand import DEFAULT_ALERT_COMMAND
from .callsign import call_problem
from .coded import CodedError, Param, Reason
from .configlegacy import with_legacy, with_network
from .configlayers import LAYER_ROWS, LayerFields
from .configstatus import (
    DEFAULT_STATUS_TEMPLATE,
    MAX_STATUS,
    host_port as _host_port,
    hostport,
    status_source,
    status_template,
    status_text,
)
from .configradios import (
    DEFAULT_RADIOS,
    FLAT_HOMES,
    FlatFields,
    RadioViews,
    accepting_flat,
    path_text,
    radio_key_of as radio_key_of,
    radio_state_key as radio_state_key,
    radios_from_flat as radios_from_flat,
)
from .mercuryscope import TX_GAIN_MAX_DB, TX_GAIN_MIN_DB
from .pairsetting import PairFields, pairs_from_rows
from .configvalues import (
    ANTENNA_DIRECTIONS as ANTENNA_DIRECTIONS,
    SYMBOL_TABLES as SYMBOL_TABLES,
    antenna_direction,
    aprsis_server,
    device_globs,
    digipeater_path,
    hf_profile,
    host_list,
    host_name,
    map_source,
    mercury_keying,
    passcode,
    port_address,
    symbol_code,
    symbol_table,
    tnc_profile,
)
from .configtypes import (
    access_key,
    boolean,
    call_or_empty,
    int_among,
    int_in,
    int_or_off,
    optional_float,
    optional_int,
    over_the_air_refusal,
    text_of,
    web_address,
    word_among,
)
from .beaconrule import SETTING_MIN_MIN, station_interval
from .radiospec import FM_ID, RadioId, RadioSpec
from .radiotype import stored_text as _show
from .route import DIRECT_ONLY, recommended_path
from .smartbeacon import PRESETS, TRAVEL, SmartSettings
from .tncprofile import Profile, names_tcp, profile_of
from .versions import UPDATE_URL

log = logging.getLogger("neoaprs.config")


class SettingError(CodedError):
    """A setting that cannot be put in force; `key` is the setting at fault."""

    def __init__(self, key: str, code: str, params: Mapping[str, Param], text: str) -> None:
        super().__init__(text, code, **params)
        self.key = key


RECEIVE_ONLY = Reason("receive only: transmitting is switched off", "transmit.off")
LISTENS_ONLY = Reason("receive only: no radio that is on can send", "transmit.off")
# Position comment length without a data extension (spec 1517).
MAX_COMMENT = 43
MAX_COMMENT_PHG = 36  # with the PHG extension (spec 1546)
# A stored interval below its minimum is raised to it.
MIN_BEACON_INTERVAL_MIN = SETTING_MIN_MIN
MIN_STATUS_INTERVAL_MIN = 15
MAX_ALERT_COMMAND = 1000
MAP_RADIUS_KM, MAP_MAXZOOM = (10, 300), (6, 15)
# Hours a station stays on the map after its last position.
STATION_HOURS = (1, 3, 6, 12, 24)
DEFAULT_STATION_HOURS = 3
LATITUDE, LONGITUDE = (-90.0, 90.0), (-180.0, 180.0)
# Integer settings and their limits; the page's LIMITS (ui/src/protocol/lists.ts) must agree.
RANGES: dict[str, tuple[int, int]] = {
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
# by-id first, so the device's stable name is kept
DEFAULT_SERIAL_PATTERN = "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*"
STATUS_KEYS = frozenset({"status/source", "status/rigctld"})
COMMENT_KEYS = frozenset({"station/comment", "beacon/power_w"})
PORT_KEYS = frozenset({"tnc/profile", "serial/port"})
GPS_SOURCES = ("off", "gpsd", "serial")


@dataclass(frozen=True)
class Setting:
    attr: str  # field of Config
    key: str  # row of the settings table
    parse: Callable[[str], Any]
    # A stored integer from 1 up to below this is raised to it.
    floor: int = 0


def _raised(setting: Setting, text: str) -> int | None:
    """Return the floor if the text is an integer from 1 up to below the floor, else None."""
    try:
        value = int(text.strip())
    except ValueError:
        return None
    return setting.floor if 0 < value < setting.floor else None


EMAIL_RADIO = "email/radio"
SETTINGS: tuple[Setting, ...] = (
    Setting("tnc_profile", "tnc/profile", tnc_profile),
    # Empty: search the ports of serial/pattern.
    Setting("serial_port", "serial/port", port_address),
    # Empty: the profile's speed.
    Setting("serial_baud", "serial/baud", optional_int(*RANGES["serial/baud"])),
    Setting("tcp_host", "tcp/host", host_name),
    Setting("tcp_port", "tcp/port", int_in(*RANGES["tcp/port"])),
    Setting("hf_enabled", "hf/enabled", boolean),
    Setting("hf_profile", "hf/profile", hf_profile),
    # As `mercury -z` names it (plughw:1,0).
    Setting("mercury_sound_card", "mercury/sound_card", text_of(200)),
    # vox, cm108, rts:PORT or dtr:PORT.
    Setting("mercury_keying", "mercury/keying", mercury_keying),
    # dB; 0 is the modem's own level (frames peak at -6 dBFS).
    Setting("mercury_tx_gain_db", "mercury/tx_gain_db", int_in(*RANGES["mercury/tx_gain_db"])),
    Setting("serial_last_port", "serial/last_port", port_address),
    Setting("serial_pattern", "serial/pattern", device_globs),
    Setting("serial_skip", "serial/skip", text_of(500)),
    Setting("station_call", "station/call", call_or_empty),
    Setting("station_transmit", "station/transmit", boolean),
    Setting("email_choice", EMAIL_RADIO, optional_int(1, 2**31 - 1)),
    Setting("fm_enabled", "fm/enabled", boolean),
    Setting("station_lat", "station/lat", optional_float(*LATITUDE)),
    Setting("station_lon", "station/lon", optional_float(*LONGITUDE)),
    Setting("station_symbol_table", "station/symbol_table", symbol_table),
    Setting("station_symbol_code", "station/symbol_code", symbol_code),
    Setting("station_comment", "station/comment", text_of(MAX_COMMENT, ascii_only=True)),
    Setting("station_status", "station/status", status_text(MAX_STATUS)),
    # Empty: no PHG extension is sent.
    Setting("beacon_power_w", "beacon/power_w", optional_int(*RANGES["beacon/power_w"])),
    Setting("beacon_antenna_height_m", "beacon/antenna_height_m", int_in(*RANGES["beacon/antenna_height_m"])),
    Setting("beacon_antenna_gain_db", "beacon/antenna_gain_db", int_in(*RANGES["beacon/antenna_gain_db"])),
    Setting("beacon_antenna_direction", "beacon/antenna_direction", antenna_direction),
    Setting("web_network", "web/network", boolean),
    Setting("web_key", "web/key", access_key),
    # With web/network: also serve https on the port after web/port.
    Setting("web_https", "web/https", boolean),
    # 0: the system picks a free port.
    Setting("web_port", "web/port", int_in(0, 65535)),
    Setting("web_allowed_hosts", "web/allowed_hosts", host_list),
    # A reverse proxy on this computer passes the page on: its forwarding headers are believed.
    Setting("web_proxy", "web/proxy", boolean),
    # 0: the beacon is off, also for a moving station.
    Setting(
        "beacon_interval_min",
        "beacon/interval_min",
        int_or_off(*RANGES["beacon/interval_min"]),
        MIN_BEACON_INTERVAL_MIN,
    ),
    # Empty: the path recommended for the symbol; DIRECT: none.
    Setting("beacon_path", "beacon/path", digipeater_path),
    # A new line of the chat of the HF tests tab notifies (the alert command and the pages).
    Setting("messages_chat_alert", "messages/chat_alert", boolean),
    Setting("messages_alert", "messages/alert", boolean),
    Setting("messages_alert_command", "messages/alert_command", text_of(MAX_ALERT_COMMAND)),
    # off, text or rig. Empty: see Config.status_choice.
    Setting("status_source", "status/source", status_source),
    Setting("status_rigctld", "status/rigctld", hostport),
    Setting(
        "status_interval_min", "status/interval_min", int_in(*RANGES["status/interval_min"]), MIN_STATUS_INTERVAL_MIN
    ),
    Setting("status_template", "status/template", status_template),
    Setting("map_radius_km", "map/radius_km", int_in(*RANGES["map/radius_km"])),
    Setting("map_maxzoom", "map/maxzoom", int_in(*RANGES["map/maxzoom"])),
    Setting("map_station_hours", "map/station_hours", int_among(STATION_HOURS)),
    Setting("map_source", "map/source", map_source),
    *(Setting(*row) for row in LAYER_ROWS),
    Setting("update_url", "update/url", web_address),
    Setting("digi_enabled", "digi/enabled", boolean),
    # Show the stations of APRS-IS; gate what the radios hear to it. Nothing from the internet goes on the air.
    Setting("igate_enabled", "igate/enabled", boolean),
    Setting("igate_gate", "igate/gate", boolean),
    # Show the packets an iGate put on the air from the internet (rf-gated).
    Setting("igate_show_gated", "igate/show_gated", boolean),
    Setting("igate_server", "igate/server", aprsis_server),
    # Empty: the passcode of station/call. -1 (read-only login) is refused.
    Setting("igate_password", "igate/password", passcode),
    Setting("units_non_metric", "units/non_metric", boolean),
    Setting("gps_source", "gps/source", word_among(GPS_SOURCES)),
    Setting("gps_host", "gps/host", hostport),
    Setting("gps_device", "gps/device", port_address),
    Setting("gps_baud", "gps/baud", int_in(*RANGES["gps/baud"])),
    Setting("beacon_travel", "beacon/travel", word_among(TRAVEL)),
)
BY_KEY = {s.key: s for s in SETTINGS}
KEYS = tuple(s.key for s in SETTINGS)
RADIO_STATION_KEYS = (EMAIL_RADIO,)
LAST_PORT = radio_state_key(FM_ID, "last_port")
STATION_KEYS = tuple(s.key for s in SETTINGS if s.attr not in FLAT_HOMES and s.key != "serial/last_port")
BEACON_SENT, HF_BEACON_SENT = "beacon/last_sent_at", "hf/beacon_last_sent_at"
STATE_BEFORE_31 = (BEACON_SENT, HF_BEACON_SENT)
RADIO_STATE = ("beacon_last_sent_at", "status_last_sent_at", "last_port")
# State rows that survive a restart; not settings.
STATUS_SENT, STATUS_TEXT = "status/last_sent_at", "status/last_text"
MAP_AUTO = "map/auto"
# JSON: the radio chosen per station call.
MESSAGE_RADIOS = "messages/radio_by_station"
NEW_OBJECTS, NEW_BULLETINS = "objects/send_on", "bulletins/send_on"
# JSON: the Sent for of the post of each kind posted last, in hours.
NEW_BULLETIN_HOURS = "bulletins/sent_for_hours"
# Station state rows; each radio's are RADIO_STATE.
STATE_KEYS = (STATUS_SENT, STATUS_TEXT, MAP_AUTO, MESSAGE_RADIOS, NEW_OBJECTS, NEW_BULLETINS, NEW_BULLETIN_HOURS)
INSTALL_ID = "update/install_id"
HF_DIAL = "update/hf_dial"


@accepting_flat
@dataclass(frozen=True)
class Config(FlatFields, RadioViews, LayerFields, PairFields):
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
    web_proxy: bool = False
    beacon_interval_min: int = 0
    messages_chat_alert: bool = True
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
    igate_gate: bool = False
    igate_show_gated: bool = True
    igate_server: str = "rotate.aprs2.net:14580"
    igate_password: str = ""
    units_non_metric: bool = False
    gps_source: str = "off"
    gps_host: str = "127.0.0.1:2947"
    gps_device: str = ""
    gps_baud: int = 4800
    beacon_travel: str = TRAVEL[0]
    radios: tuple[RadioSpec, ...] = DEFAULT_RADIOS  # every stored radio, removed ones too, by id
    email_choice: RadioId | None = None

    @property
    def mobile(self) -> bool:
        return self.gps_source != "off"

    @property
    def beacon_on(self) -> bool:
        """Return whether the beacon is on; off also stops the status report."""
        return self.beacon_interval_min > 0

    @property
    def smart(self) -> SmartSettings:
        return PRESETS[self.beacon_travel]

    def beacon_interval(self) -> int:
        """Return the shortest beacon interval in minutes in force on any radio (0: off)."""
        return station_interval(self.beacon_interval_min, self.radios)

    def radio_refusal(self, key: str = "hf/enabled") -> SettingError | None:
        """Return a refusal if no radio would stay on, else None."""
        if not self.enabled_radios:
            return SettingError(
                key, "radio.last_enabled", {}, f"{key}: at least one radio stays on: turn another radio on first"
            )
        return None

    @property
    def station_position(self) -> tuple[float, float] | None:
        if self.station_lat is None or self.station_lon is None:
            return None
        return self.station_lat, self.station_lon

    @property
    def profile(self) -> Profile:
        return profile_of(self.tnc_profile)

    @property
    def tnc_baud(self) -> int:
        return self.serial_baud or self.profile.baud or 9600

    def port_refusal(self, key: str = "tnc/profile") -> SettingError | None:
        """Return a refusal if a TCP profile is combined with a serial port (`tcp://` is fine)."""
        if self.profile.transport == "tcp" and self.serial_port and not names_tcp(self.serial_port):
            return SettingError(
                key,
                "setting.profile_port",
                {"profile": self.profile.name, "port": self.serial_port},
                f"{key}: {self.profile.name} connects over TCP (tcp/host and tcp/port), not to the serial port {self.serial_port}: clear serial/port, or choose a serial TNC",
            )
        return None

    @property
    def serial_skip_paths(self) -> tuple[str, ...]:
        return tuple(part for part in (piece.strip() for piece in self.serial_skip.split(",")) if part)

    @property
    def status_choice(self) -> str:
        """Return status/source, else rig if status/rigctld is set, else text if there is one."""
        if self.status_source:
            return self.status_source
        return "rig" if self.status_rigctld else "text" if self.station_status else "off"

    @property
    def status_rig_address(self) -> tuple[str, int] | None:
        """Return status/rigctld as (host, port), or None if empty or not the status source."""
        return _host_port(self.status_rigctld) if self.status_choice == "rig" else None

    @property
    def igate_address(self) -> tuple[str, int] | None:
        return _host_port(self.igate_server)

    @property
    def internet_on(self) -> bool:
        """Return whether APRS-IS is logged in to: to show its stations, to gate to it, or both."""
        return self.igate_enabled or self.igate_gate

    def path_calls(self, radio: RadioId) -> tuple[str, ...]:
        """Return the calls of the radio's path (the recommended one if empty; none for DIRECT)."""
        path = path_text(self.radios, radio)
        return () if path == DIRECT_ONLY else tuple(call for call in (path or self.recommended_path).split(",") if call)

    @property
    def beacon_path_calls(self) -> tuple[str, ...]:
        return self.path_calls(FM_ID)

    @property
    def recommended_path(self) -> str:
        return recommended_path(self.station_symbol_table, self.station_symbol_code)

    @property
    def comment_limit(self) -> int:
        """Return 36 when the PHG extension is sent (beacon/power_w set), else 43."""
        return MAX_COMMENT if self.beacon_power_w is None else MAX_COMMENT_PHG

    def comment_refusal(self) -> SettingError | None:
        """Return a refusal if station/comment cannot be sent with the other settings, else None."""
        if refusal := over_the_air_refusal(self.station_comment):
            return SettingError("station/comment", refusal.code, refusal.params, f"station/comment: {refusal}")
        limit = self.comment_limit
        if len(self.station_comment) <= limit:
            return None
        return SettingError(
            "station/comment",
            "setting.comment_too_long",
            {"length": len(self.station_comment), "limit": limit},
            f"station/comment: {len(self.station_comment)} characters is more than the {limit} allowed with the PHG extension (clear beacon/power_w to send none)",
        )

    def comment_problem(self) -> str:
        return str(refusal) if (refusal := self.comment_refusal()) else ""

    @classmethod
    def checked(cls, base: "Config", values: Mapping[str, str]) -> "Config":
        """Return `base` with these values (key to text) put in, for a save.

        The first wrong value or broken rule between settings raises SettingError."""
        parsed = {key: cls.check(key, text) for key, text in values.items()}
        rows = {key: text for key, text in {**base.to_data(), **parsed}.items() if BY_KEY[key].attr not in FLAT_HOMES}
        flat = {
            BY_KEY[key].attr: cls.parse(key, text) for key, text in parsed.items() if BY_KEY[key].attr in FLAT_HOMES
        }
        config = replace(cls.from_data(rows, radios=base.radios), pairs=base.pairs, **flat)
        if COMMENT_KEYS & parsed.keys() and (refusal := config.comment_refusal()):
            raise refusal
        if STATUS_KEYS & parsed.keys() and config.status_source == "rig" and not config.status_rigctld:
            raise SettingError(
                "status/source",
                "setting.status_needs_rigctld",
                {},
                "status/source: the radio needs status/rigctld (host:port of a rigctld)",
            )
        if (set_now := [key for key in ("fm/enabled", "hf/enabled") if key in parsed]) and (
            refusal := config.radio_refusal(set_now[0])
        ):
            raise refusal
        if PORT_KEYS & parsed.keys() and (
            refusal := config.port_refusal("tnc/profile" if "tnc/profile" in parsed else "serial/port")
        ):
            raise refusal
        return config

    @classmethod
    def from_data(cls, rows: Mapping[str, str], *, radios: Iterable[RadioSpec] | None = None) -> "Config":
        """Build the settings from database rows; a missing or wrong key gets its default.

        With `radios` the flat keys of radios 1 and 2 are not read; without, legacy rules apply."""
        rows = with_legacy(rows) if radios is None else with_network(rows)
        if radios is not None and LAST_PORT in rows:
            rows = {**rows, "serial/last_port": rows[LAST_PORT]}  # radio 1's row wins
        values: dict[str, Any] = {} if radios is None else {"radios": tuple(sorted(radios, key=lambda spec: spec.id))}
        values.update({} if radios is None else {"pairs": pairs_from_rows(rows)})
        for setting in SETTINGS:
            if setting.key in rows and (radios is None or setting.attr not in FLAT_HOMES):
                try:
                    values[setting.attr] = cls.parse(setting.key, rows[setting.key])
                except ValueError as e:
                    if (raised := _raised(setting, rows[setting.key])) is not None:
                        log.warning("%s; %d is used", e, raised)
                        values[setting.attr] = raised
                    else:
                        log.warning(
                            "%s; the default %s is used", e, _show(getattr(DEFAULTS, setting.attr)) or "(empty)"
                        )
        return cls(**values)

    def to_data(self) -> dict[str, str]:
        return {s.key: _show(getattr(self, s.attr)) for s in SETTINGS}

    @staticmethod
    def parse(key: str, text: str) -> Any:
        """Return the value of one setting from its text; raise SettingError if invalid."""
        setting = BY_KEY.get(key)
        if setting is None:
            raise SettingError(
                key, "setting.unknown", {}, f"{key}: no such setting (the settings are {', '.join(KEYS)})"
            )
        try:
            return setting.parse(text)
        except CodedError as e:
            raise SettingError(key, e.code, e.params, f"{key}: {e}") from None
        except ValueError as e:
            raise SettingError(key, "other", {}, f"{key}: {e}") from None

    @classmethod
    def check(cls, key: str, text: str) -> str:
        """Return the text as stored ("oh2gba" gives "OH2GBA"); raise SettingError if wrong."""
        return _show(cls.parse(key, text))

    def changed(self, other: "Config") -> list[str]:
        return [s.key for s in SETTINGS if getattr(self, s.attr) != getattr(other, s.attr)]


DEFAULTS = Config()


def can_transmit(config: Config) -> str | None:
    """The transmit interlock: return None if the station may transmit, else the reason not."""
    if not config.station_transmit or config.listens_only:
        return RECEIVE_ONLY if not config.station_transmit else LISTENS_ONLY
    return call_problem(config.station_call) or None
