// Rows of the protocol for the tests: every field present, the ones a test cares about given.
import type {
  BulletinRow,
  ConfigValues,
  MapFileInfo,
  MapState,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  StationRow,
  HelloMessage,
  StatusMessage,
  TncState,
  WeatherSeriesMessage,
  WeatherValues,
} from "@/protocol/protocol";
import { PAGE_VERSION } from "@/lib/build";
import { PROTOCOL } from "@/protocol/lists";

export const NOW = Date.parse("2026-10-21T12:00:00Z");

export function ago(seconds: number): string {
  return new Date(NOW - seconds * 1000).toISOString();
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
    last_path: ["OH2RCH-2*"],
    last_route: "via OH2RCH-2",
    heard_direct: 0,
    last_direct_at: null,
    heard_gated: 0,
    heard_via: [["OH2RCH-2", 3]],
    best_route: "via OH2RCH-2",
    suggested_path: "OH2RCH-2",
    distance_km: 10,
    bearing_deg: 45,
    is_me: false,
    own: false,
    weather: null,
    weather_at: null,
    telemetry: null,
    telemetry_at: null,
    locator: null,
    extensions: null,
    track: [],
    ...extra,
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
    via: "",
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
    describe: "/dev/brainbox_3 at 9600, KISS",
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
    },
    lines: ["12:00:00 NeoAPRS: opened /dev/brainbox_3 at 9600", "12:00:01 OH2RDG>APN391:!6007.47NN02429.82E#"],
    ...extra,
  };
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
    "tnc/check_sec": "60",
    "station/call": "OH2GBA",
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
    "log/keep_days": "30",
    "web/network": "false",
    "web/key": "",
    "web/port": "7303",
    "web/allowed_hosts": "",
    "beacon/interval_min": "0",
    "beacon/path": "WIDE1-1,WIDE2-1",
    "beacon/destination": "APZNEO",
    "beacon/compressed": "false",
    "beacon/dao": "false",
    "messages/attempts": "6",
    "messages/alert": "true",
    "messages/alert_command":
      '(notify-send -- "APRS message from $NEOAPRS_FROM" "$NEOAPRS_TEXT" 2>/dev/null || kdialog --title "APRS message from $NEOAPRS_FROM" --passivepopup "$NEOAPRS_TEXT" 10); paplay /usr/share/sounds/freedesktop/stereo/message-new-instant.oga',
    "status/rigctld": "",
    "status/interval_min": "30",
    "status/template": "QRV {freq} {mode}",
    "map/hide_after_min": "1440",
    "map/radius_km": "150",
    "map/maxzoom": "12",
    "map/source": "",
    "update/check": "true",
    "update/url": "https://oh2gba.eu/neoaprs/version.php",
    ...extra,
  };
  return { values, defaults: { ...values }, urls: [] };
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
    ...extra,
  };
}

/** The daemon's `hello` for a page of this build: the same version and protocol, so that the page does not load itself again. */
export function hello(extra: Partial<HelloMessage> = {}): HelloMessage {
  return { type: "hello", protocol: PROTOCOL, version: PAGE_VERSION, install: { kind: "pip", appimage: "", service: false }, topics: [], ...extra };
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
