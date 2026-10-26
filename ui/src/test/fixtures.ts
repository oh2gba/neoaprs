// Rows of the protocol for the tests: every field present, the ones a test cares about given.
import type {
  BulletinRow,
  ConfigValues,
  ErrorMessage,
  GpsState,
  IgateState,
  MapFileInfo,
  MapState,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  QruState,
  StationRow,
  HelloMessage,
  StatusMessage,
  TncState,
  WeatherSeriesMessage,
  WeatherValues,
} from "@/protocol/protocol";
import type { Toast } from "@/composables/useDaemon";
import { PROTOCOL } from "@/protocol/lists";

export const NOW = Date.parse("2026-10-21T12:00:00Z");

export function ago(seconds: number): string {
  return new Date(NOW - seconds * 1000).toISOString();
}

/** An `error` the way the daemon sends it for a sentence "<cmd>: [<key>: ]<reason>": its command and its setting are the first words, as the daemon's handlers put them there; `code` and `params` say what is wrong. */
export function errorOf(text: string, code = "other", params: Record<string, string | number> = {}): ErrorMessage {
  const found = /^([a-z_]+): (?:([a-z_]+\/[a-z_]+): )?/.exec(text);
  return { type: "error", cmd: found?.[1] ?? "", key: found?.[2] ?? null, code, params, text };
}

/** The same as the page keeps it for the toast. */
export function toastOf(text: string, code = "other", params: Record<string, string | number> = {}, n = 1): Toast {
  const { cmd, key } = errorOf(text);
  return { cmd, key, code, params, text, n };
}

export function station(call: string, extra: Partial<StationRow> = {}): StationRow {
  return {
    call,
    kind: "station",
    reported_by: "",
    symbol_table: "/",
    symbol_code: ">",
    symbol_name: "Car",
    lat: 60.2,
    lon: 24.9,
    altitude_m: null,
    course_deg: null,
    speed_kmh: null,
    first_heard: ago(3600),
    last_heard: ago(60),
    last_position_at: ago(60),
    last_status: "",
    last_comment: "",
    packets: 3,
    heard_rf: 3,
    heard_rf_gated: 0,
    heard_is: 0,
    heard_dummy: 0,
    last_dummy_at: null,
    last_rf_gated_at: null,
    last_is_at: null,
    position_via: "rf",
    packets_hour: 2,
    device: "",
    last_path: ["OH2RCH-2*"],
    last_route: "via OH2RCH-2",
    heard_direct: 0,
    last_direct_at: null,
    gated: 0,
    igate: false,
    heard_via: [["OH2RCH-2", 3]],
    best_route: "via OH2RCH-2",
    suggested_path: "OH2RCH-2",
    heard_path: null,
    distance_km: 10,
    bearing_deg: 45,
    is_me: false,
    can_message: true,
    own: false,
    weather: null,
    weather_at: null,
    telemetry: null,
    telemetry_at: null,
    locator: null,
    extensions: null,
    frequency: null,
    storm: null,
    sign: null,
    track: [],
    ...extra,
    last_rf_at: extra.last_rf_at !== undefined ? extra.last_rf_at : extra.heard_rf === 0 ? null : (extra.last_heard ?? ago(60)),
  };
}

/** The latest observation of a weather station: a calm-weather report of OH2MUI, with what a test gives. */
export function weather(extra: Partial<WeatherValues> = {}): WeatherValues {
  return {
    wind_dir: 107,
    wind_kmh: 1.6,
    gust_kmh: 1.6,
    temp_c: 10,
    humidity: 85,
    pressure_hpa: 1028.4,
    rain_1h_mm: 0.3,
    rain_24h_mm: 4.1,
    rain_today_mm: 3.3,
    luminosity: null,
    snow_mm: null,
    ...extra,
  };
}

/** A weather station heard `heardAgo` seconds ago. */
export function weatherStation(call = "OH2MUI", extra: Partial<StationRow> = {}, heardAgo = 600): StationRow {
  return station(call, { symbol_code: "_", symbol_name: "Weather station", weather: weather(), weather_at: ago(heardAgo), ...extra });
}

/** The answer to `weather_series`: an observation every `every` seconds for `count` observations ending `last` seconds ago, the values given by `value` of the index. */
export function series(call: string, hours: number, count: number, every = 600, last = 600): WeatherSeriesMessage {
  const points = Array.from({ length: count }, (_, i): WeatherSeriesMessage["points"][number] => {
    const age = last + (count - 1 - i) * every;
    return [ago(age), 8 + (i % 5), 1020 + i * 0.1, 3 + (i % 4), 6 + (i % 4), i % 3 === 0 ? 0.3 : 0, 80];
  });
  return { type: "weather_series", call, hours, points };
}

export function packet(id: number, extra: Partial<PacketRow> = {}): PacketRow {
  return {
    id,
    heard_at: ago(100 - id),
    direction: "in",
    source: "OH2RDG",
    destination: "APN391",
    path: ["OH2RCH-2*"],
    route: "via OH2RCH-2",
    via: "rf",
    gate: "",
    kind: "position",
    summary: "position 60.12 24.49",
    tnc2: `OH2RDG>APN391,OH2RCH-2*:!6007.47NN02429.82E#`,
    decoded: {
      type: "position",
      lat: 60.12,
      lon: 24.49,
      symbol_table: "N",
      symbol_code: "#",
      comment: "",
      course_deg: null,
      speed_kmh: null,
      altitude_m: null,
      timestamp: null,
      messaging: false,
      compressed: false,
      ambiguity: 0,
      weather: null,
      extensions: null,
      timestamp_local: false,
      locator: null,
      frequency: null,
      storm: null,
      sign: null,
    },
    ...extra,
  };
}

/** A message we sent, being sent by default; `incoming` makes one that came in. */
export function message(id: number, extra: Partial<MessageRow> = {}): MessageRow {
  return {
    id,
    at: ago(1000 - id),
    direction: "out",
    from_call: "OH2GBA",
    to_call: "OH2RDG",
    text: `message ${id}`,
    msg_id: String(id),
    state: "sending",
    attempts: 1,
    attempts_max: 6,
    last_attempt_at: ago(1000 - id),
    acked_at: null,
    attempts_detail: [],
    route: "",
    ...extra,
  };
}

export function incoming(id: number, from: string, extra: Partial<MessageRow> = {}): MessageRow {
  return message(id, {
    direction: "in",
    from_call: from,
    to_call: "OH2GBA",
    state: "received",
    attempts: 0,
    last_attempt_at: null,
    text: `from ${from} ${id}`,
    route: "via OH2RCH-2",
    ...extra,
  });
}

/** A bulletin of the message board: a bulletin from OH2XYZ heard a minute ago, once. */
export function bulletin(slot: string, extra: Partial<BulletinRow> = {}): BulletinRow {
  return {
    sender: "OH2XYZ",
    slot,
    group: "",
    kind: "bulletin",
    text: `text of ${slot}`,
    first_heard: ago(60),
    last_heard: ago(60),
    times_heard: 1,
    ...extra,
  };
}

/** An object of ours: a live object "LEADER" sent twice, the next one in 3 minutes. */
export function ownObject(name: string, extra: Partial<OwnObjectRow> = {}): OwnObjectRow {
  return {
    name,
    kind: "object",
    lat: 60.2,
    lon: 24.9,
    symbol_table: "/",
    symbol_code: ">",
    comment: "",
    course_deg: null,
    speed_kmh: null,
    path: null,
    qru_group: "",
    on_request: false,
    state: "live",
    created_at: ago(600),
    updated_at: ago(600),
    sent: 2,
    last_sent_at: ago(60),
    next_at: new Date(NOW + 180_000).toISOString(),
    ...extra,
  };
}

/** A bulletin of ours: a bulletin in the slot, sent twice, the next one in 18 minutes. */
export function ownBulletin(slot: string, extra: Partial<OwnBulletinRow> = {}): OwnBulletinRow {
  return {
    slot,
    group: "",
    kind: "bulletin",
    text: `ours in ${slot}`,
    posted_at: ago(600),
    sent: 2,
    last_sent_at: ago(60),
    next_at: new Date(NOW + 18 * 60_000).toISOString(),
    ...extra,
  };
}

export function tncState(extra: Partial<TncState> = {}): TncState {
  return {
    state: "connected",
    problem: "",
    last_error: "",
    path: "/dev/brainbox_3",
    baud: 9600,
    dummy: false,
    describe: "/dev/brainbox_3 at 9600, KISS",
    searching: [],
    silent_since: null,
    last_watchdog_action: "",
    last_watchdog_at: null,
    stats: {
      opens: 1,
      bytes_in: 2048,
      bytes_out: 0,
      frames_in: 12,
      packets: 11,
      rejected: 1,
      last_packet: ago(30),
      keepalive_checks: 0,
      watchdog_probes: 0,
      port_reopens: 0,
      digipeated: 0,
      digipeated_at: null,
      digipeat_held: 0,
    },
    lines: [
      { at: "2026-10-21T12:00:00Z", text: "NeoAPRS: opened /dev/brainbox_3 at 9600" },
      { at: "2026-10-21T12:00:01Z", text: "OH2RDG>APN391:!6007.47NN02429.82E#" },
    ],
    ...extra,
  };
}

/** The GPS topic with a fresh fix (60.4295 N 24.1452 E, 48 km/h, course 215, 103 m, 9 satellites, 2 s old) of a station whose beacon follows it (`mobile`: the source is not off); a test gives what it cares about. */
export function gpsState(extra: Partial<GpsState> = {}): GpsState {
  return {
    source: "gpsd",
    state: "fix",
    problem: "",
    lat: 60.4295,
    lon: 24.1452,
    altitude_m: 103,
    speed_kmh: 48,
    course_deg: 215,
    satellites: 9,
    fix_at: ago(2),
    mobile: true,
    next_beacon_at: null,
    last_beacon_reason: "",
    last_beacon_at: null,
    ...extra,
  };
}

/** The topic `igate`: connected to T2FINLAND with 1234 packets gated, the latest 12 s ago and some left out; a test gives what it cares about. */
export function igateState(extra: Partial<IgateState> = {}): IgateState {
  return {
    enabled: true,
    state: "connected",
    server: "T2FINLAND",
    problem: "",
    gated: 1234,
    dropped: { tcpip: 31, duplicate: 6, query: 3 },
    last_gated_at: ago(12),
    ...extra,
  };
}

/** The topic `qru`: a request for INFO 20 s ago, and the server DF8LS-10 that answered it with two groups and has sent the closing line of one; a test gives what it cares about. */
export function qruState(extra: Partial<QruState> = {}): QruState {
  return {
    asked: { text: "INFO", at: ago(20) },
    servers: [
      {
        call: "DF8LS-10",
        groups: [
          { name: "RP70", count: 10 },
          { name: "RP2M", count: 3 },
        ],
        max_objects: 5,
        range: 50,
        unit: "km",
        at: ago(15),
        sent: "Sent 5 RP70 Objects Max 5@50km de DF8LS-10",
        sent_at: ago(8),
      },
    ],
    ...extra,
  };
}

/** The GPS topic of a daemon with no GPS source set: a fixed station, whose beacon does not follow the GPS. */
export function gpsOff(): GpsState {
  return gpsState({
    source: "off",
    state: "off",
    mobile: false,
    lat: null,
    lon: null,
    altitude_m: null,
    speed_kmh: null,
    course_deg: null,
    satellites: null,
    fix_at: null,
  });
}

export function configValues(extra: Record<string, string> = {}): ConfigValues {
  const values: Record<string, string> = {
    "tnc/profile": "kenwood-tnc2",
    "serial/port": "",
    "serial/baud": "9600",
    "tcp/host": "127.0.0.1",
    "tcp/port": "8001",
    "serial/last_port": "/dev/brainbox_3",
    "serial/pattern": "/dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*",
    "serial/skip": "",
    "station/call": "OH2GBA",
    "station/transmit": "true",
    "station/lat": "60.17",
    "station/lon": "24.94",
    "station/symbol_table": "/",
    "station/symbol_code": "-",
    "station/comment": "NeoAPRS",
    "station/status": "",
    "beacon/power_w": "",
    "beacon/antenna_height_m": "0",
    "beacon/antenna_gain_db": "0",
    "beacon/antenna_direction": "omni",
    "web/network": "false",
    "web/key": "",
    "web/https": "false",
    "web/port": "7303",
    "web/allowed_hosts": "",
    "beacon/interval_min": "30",
    "beacon/path": "",
    "messages/alert": "true",
    "messages/alert_command":
      '(notify-send -- "APRS message from $NEOAPRS_FROM" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "APRS message from $NEOAPRS_FROM" --passivepopup "$NEOAPRS_TEXT" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga',
    "status/source": "",
    "status/rigctld": "",
    "status/interval_min": "30",
    "status/template": "QRV {freq} {mode}",
    "map/radius_km": "150",
    "map/maxzoom": "12",
    "map/station_hours": "3",
    "map/source": "",
    "update/url": "https://oh2gba.eu/neoaprs/version.php",
    "digi/enabled": "false",
    "igate/enabled": "false",
    "igate/server": "rotate.aprs2.net:14580",
    "igate/password": "",
    "gps/source": "off",
    "gps/host": "127.0.0.1:2947",
    "gps/device": "",
    "gps/baud": "4800",
    "beacon/travel": "car",
    ...extra,
  };
  return { values, defaults: { ...values }, urls: [], https: { on: false, port: 0, fingerprint: "", problem: "" } };
}

/** A map file of the daemon: the detailed map round Helsinki by default. */
export function mapFile(extra: Partial<MapFileInfo> = {}): MapFileInfo {
  return {
    name: "basemap.pmtiles",
    bytes: 123_400_000,
    modified: "2026-10-22T19:03:53Z",
    bbox: [22.1, 58.8, 27.8, 61.5],
    min_zoom: 0,
    max_zoom: 12,
    build: "20261022",
    ...extra,
  };
}

/** The topic `map` with no map and no job: the state of a fresh install that has a position. */
export function mapState(extra: Partial<MapState> = {}): MapState {
  return {
    state: "none",
    step: "",
    percent: null,
    downloaded: null,
    note: "",
    blocked: "",
    problem: "",
    estimate: null,
    radius_km: 150,
    maxzoom: 12,
    box: [22.1, 58.8, 27.8, 61.5],
    detail: null,
    world: null,
    later: false,
    aloha_km: null,
    ...extra,
  };
}

/** The version the daemon of the tests says it is: the page has none of its own, so any is as good as another. */
export const DAEMON_VERSION = "1.2.3";

/** The daemon's `hello` for a page of this build: the same protocol and no build to compare, so that the page does not load itself again. */
export function hello(extra: Partial<HelloMessage> = {}): HelloMessage {
  return {
    type: "hello",
    protocol: PROTOCOL,
    version: DAEMON_VERSION,
    page: "",
    install: { kind: "pip", appimage: "", service: false, arch: "" },
    topics: [],
    ...extra,
  };
}

export function status(extra: Partial<StatusMessage> = {}): StatusMessage {
  return {
    type: "status",
    version: "0.1.0",
    started_at: ago(100),
    packets: 2,
    stations: 4,
    call: "OH2GBA",
    lat: 60.17,
    lon: 24.94,
    beacon_interval_min: 0,
    beacon_last_sent: null,
    beacon_next_due: null,
    station_status: "",
    rig_state: "unused",
    cpu_percent: 0.3,
    rss_mb: 42.4,
    uptime_sec: 10800,
    update: null,
    ...extra,
  };
}

/** The map of a station table: call to row. */
export function table(...rows: StationRow[]): Map<string, StationRow> {
  return new Map(rows.map((r) => [r.call, r]));
}
