// Rows of the protocol for the tests: every field present, the ones a test cares about given. A field the daemon works out of others (a row's radio by its id beside its word of before) is made from them, as the
// daemon of the station of before sends it (radio 1 the FM radio, radio 2 the HF radio), unless the test gives it.
import type {
  AttemptRow,
  BulletinRow,
  ConfigValues,
  ErrorMessage,
  GpsState,
  IgateState,
  MapFileInfo,
  MapState,
  MessageRow,
  ModemState,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  PortRow,
  QruAsked,
  QruState,
  RadioRow,
  RadioSearchMessage,
  SkedRow,
  SkedsState,
  SoundCardRow,
  StationRow,
  HelloMessage,
  StatusMessage,
  TncStats,
  WeatherSeriesMessage,
  WeatherValues,
} from "@/protocol/protocol";
import type { Toast } from "@/composables/useDaemon";
import { PROTOCOL, RADIO_STATION_KEYS, RADIO_TYPES } from "@/protocol/lists";
import { mapLayer } from "@/test/layerfixtures";

export const NOW = Date.parse("2026-10-21T12:00:00Z");

export function ago(seconds: number): string {
  return new Date(NOW - seconds * 1000).toISOString();
}

/** An `error` the way the daemon sends it for a sentence "<cmd>: [<key>: ]<reason>": its command and its setting are the first words, as the daemon's handlers put them there; `code` and `params` say what is wrong. */
export function errorOf(text: string, code = "other", params: Record<string, string | number> = {}): ErrorMessage {
  const found = /^([a-z_]+): (?:([a-z_]+\/(?:\d+\/)?[a-z_]+): )?/.exec(text); // (a station's key, `station/call`, or a radio's own, `radio/3/port`)
  return { type: "error", cmd: found?.[1] ?? "", key: found?.[2] ?? null, code, params, text };
}

/** The same as the page keeps it for the toast. */
export function toastOf(text: string, code = "other", params: Record<string, string | number> = {}, n = 1): Toast {
  const { cmd, key } = errorOf(text);
  return { cmd, key, code, params, text, n };
}

type StationRadios = Pick<StationRow, "heard" | "last_path_radio" | "last_direct_any_at" | "radio_choice" | "radio_now" | "paths">;

/** The later of two times; null for neither. */
const latest = (a: string | null, b: string | null): string | null => (a === null ? b : b === null || a >= b ? a : b);

/** The radio 2 of the fixtures (an HF radio: what it hears is heard direct). */
const HF_RADIO = "2";

/** What a station's row says of the radios: what each radio heard of it (`heard`; unless a test gives it, radio 1 heard what was heard on the air), the one that heard it last, the choice, and the radio a message to it
 * goes on (the choice, else radio 2 for a station radio 2 alone heard, else radio 1; none for a station that takes no message), and when any radio heard it direct. */
function stationRadios(row: Omit<StationRow, keyof StationRadios>, extra: Partial<StationRow>): StationRadios {
  const heard: StationRow["heard"] = extra.heard ?? (row.heard_rf > 0 ? { "1": { count: row.heard_rf, last_at: row.last_rf_at } } : {});
  const ids = Object.keys(heard);
  const lastOf = (id: string): string => heard[id]?.last_at ?? "";
  const last = ids.length === 0 ? null : ids.reduce((best, id) => (lastOf(id) > lastOf(best) ? id : best));
  const choice = extra.radio_choice ?? null;
  return {
    heard,
    last_path_radio: last === null ? null : Number(last),
    last_direct_any_at: latest(row.last_direct_at, heard[HF_RADIO]?.last_at ?? null),
    radio_choice: choice,
    radio_now: !row.can_message ? null : (choice ?? (ids.length === 1 && ids[0] === HF_RADIO ? 2 : 1)),
    paths: {},
  };
}

/** What each radio heard of a station (`heard`), from [radio's id, how many packets, when the latest came] (the time the fixtures' minute ago where none is given). */
export function heardBy(...entries: readonly (readonly [number, number, (string | null)?])[]): StationRow["heard"] {
  return Object.fromEntries(
    entries.filter(([, count]) => count > 0).map(([id, count, at]) => [String(id), { count, last_at: at === undefined ? ago(60) : at }]),
  );
}

export function station(call: string, extra: Partial<StationRow> = {}): StationRow {
  const row: Omit<StationRow, keyof StationRadios> = {
    call,
    kind: "station",
    reported_by: "",
    symbol_table: "/",
    symbol_code: ">",
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
    snr: null,
    rssi: null,
    signal_at: null,
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
    internet_reach: null,
    route_marks: [{ kind: "rf", hops: ["OH2RCH-2"], gate: "", at: ago(60), lat: null, lon: null }],
    distance_km: 10,
    bearing_deg: 45,
    is_me: false,
    can_message: true,
    may_not_message: false,
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
  return { ...stationRadios(row, extra), ...row }; // (a field of the radios that the test gave is in `row`, and stays)
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
  return station(call, { symbol_code: "_", weather: weather(), weather_at: ago(heardAgo), ...extra });
}

/** The answer to `weather_series`: an observation every `every` seconds for `count` observations ending `last` seconds ago, the values given by `value` of the index. */
export function series(call: string, hours: number, count: number, every = 600, last = 600): WeatherSeriesMessage {
  const points = Array.from({ length: count }, (_, i): WeatherSeriesMessage["points"][number] => {
    const age = last + (count - 1 - i) * every;
    return [ago(age), 8 + (i % 5), 1020 + i * 0.1, 3 + (i % 4), 6 + (i % 4), i % 3 === 0 ? 0.3 : 0, 80];
  });
  return { type: "weather_series", call, hours, points };
}

/** The time of a packet `seconds` from NOW, as the daemon writes it (whole seconds). */
export function packetAt(seconds: number): string {
  return new Date(NOW + seconds * 1000).toISOString().replace(/\.\d+Z$/, "Z");
}

/** A message packet `from` sent to `to` (ours, from OH2GBA, go out), `seconds` from NOW, with no message id. */
export function sentMessage(id: number, from: string, to: string, text: string, seconds: number, extra: Partial<PacketRow> = {}): PacketRow {
  return packet(id, {
    source: from,
    direction: from === "OH2GBA" ? "out" : "in",
    heard_at: packetAt(seconds),
    kind: "message",
    tnc2: `${from}>APRS::${to.padEnd(9)}:${text}`,
    decoded: { type: "message", addressee: to, text, msg_id: null, ack_id: null, rej_id: null },
    ...extra,
  });
}

export function packet(id: number, extra: Partial<PacketRow> = {}): PacketRow {
  return {
    radio_id: 1,
    id,
    heard_at: ago(100 - id),
    direction: "in",
    source: extra.source ?? "OH2RDG",
    sender: extra.source ?? "OH2RDG",
    destination: "APN391",
    path: ["OH2RCH-2*"],
    route: "via OH2RCH-2",
    via: "rf",
    snr: null,
    rssi: null,
    gate: "",
    kind: "position",
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

/** A message we sent, being sent by default; `incoming` makes one that came in. One of ours on its way that went on a radio (`radio`) keeps it for its next attempt (`radio_now`); one that has not gone yet takes the
 * station's radio now, which a test that cares gives. */
export function message(id: number, extra: Partial<MessageRow> = {}): MessageRow {
  const onItsWay = (extra.direction ?? "out") === "out" && ["sending", "queued"].includes(extra.state ?? "sending");
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
    radio_id: extra.radio_id ?? null,
    radio_now: onItsWay ? (extra.radio_id ?? null) : null,
    seal: "",
    failure: null,
    snr: null,
    rssi: null,
    ...extra,
  };
}

/** An attempt of a message of ours: sent at the fixtures' time on the FM radio, by no digipeater, not acked. */
export function attemptRow(extra: Partial<AttemptRow> = {}): AttemptRow {
  return { sent_at: "2026-10-22T12:00:00Z", hops: [], internet: null, acked: false, radio_id: 1, ...extra };
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

/** A sked on the board: OH2XYZ on 7.0541 MHz USB from two hours after the fixtures' time for two hours, not ours. */
export function sked(id: string, extra: Partial<SkedRow> = {}): SkedRow {
  return {
    id,
    call: "OH2XYZ",
    from: new Date(NOW + 2 * 3_600_000).toISOString().slice(0, 19) + "Z",
    to: new Date(NOW + 4 * 3_600_000).toISOString().slice(0, 19) + "Z",
    dial: "7.0541 MHz USB",
    note: "",
    ours: false,
    ...extra,
  };
}

/** The topic `skeds` as the daemon tells it: the board read, the four suggested dials, the rows given. */
export function skedsState(rows: SkedRow[] = [], extra: Partial<SkedsState> = {}): SkedsState {
  return {
    state: "ok",
    fetched_at: ago(60),
    frequencies: [
      { band: "80 m", dial: "3.5850 MHz USB" },
      { band: "40 m", dial: "7.0541 MHz USB" },
      { band: "20 m", dial: "14.1070 MHz USB" },
      { band: "6 m", dial: "50.6200 MHz USB" },
    ],
    rows,
    ...extra,
  };
}

/** An object of ours: a live object "LEADER" sent twice, the next one in 3 minutes. Its `radios` are those of its `radio` with both radios on; a test with a radio off gives them (the daemon sends those on, none while
 * none of them is). */
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
    radios: [1],
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
    radios: [1],
    sent: 2,
    last_sent_at: ago(60),
    next_at: new Date(NOW + 18 * 60_000).toISOString(),
    ...extra,
  };
}

/** What a radio's line counted since the daemon started: a line that has been open a while. */
export function lineStats(extra: Partial<TncStats> = {}): TncStats {
  return {
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
    passed: [],
    ...extra,
  };
}

/** The Mercury HF modem of a radio, running; a test gives what it cares about. */
export function modemState(extra: Partial<ModemState> = {}): ModemState {
  return {
    state: "running",
    reason: "",
    mode: "DATAC3",
    keyed: false,
    busy: false,
    test: "",
    snr: null,
    frames_keyed: 0,
    max_frame: 123,
    frequencies: [
      { band: "80 m", dial: "3.5850 MHz USB" },
      { band: "40 m", dial: "7.0541 MHz USB" },
      { band: "20 m", dial: "14.1070 MHz USB" },
      { band: "6 m", dial: "50.6200 MHz USB" },
    ],
    sound_card: "plughw:1,0",
    keying: "rts:/dev/ttyUSB0",
    scope: false,
    tx_gain_db: 0,
    tx_peak_dbfs: null,
    rx_level: null,
    ...extra,
  };
}

/** The GPS topic with a fresh fix (60.4295 N 24.1452 E, 48 km/h, course 215, 103 m, 9 satellites, 2 s old) of a station whose beacon follows it (`mobile`: the source is not off); a test gives what it cares about. */
export function gpsState(extra: Partial<GpsState> = {}): GpsState {
  return {
    source: "gpsd",
    state: "fix",
    reason: "",
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
    reason: "",
    gated: 1234,
    dropped: { tcpip: 31, duplicate: 6, query: 3 },
    last_gated_at: ago(12),
    ...extra,
  };
}

/** The topic `qru`: a request for INFO 20 s ago, and the server DF8LS-10 that answered it with two groups and has sent the closing line of one (five objects, all of which arrived); a test gives what it cares about. */
/** A request for local info that went on the FM radio, or on the radios given. */
export const qruAsked = (text: string, at: string, ...radios: number[]): QruAsked => ({ text, at, radios: radios.length > 0 ? radios : [1] });

export function qruState(extra: Partial<QruState> = {}): QruState {
  return {
    asked: qruAsked("INFO", ago(20)),
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
        sent_objects: 5,
        request: "RP70 150",
        received: ["RPKUM", "RPOTA", "RPTAP", "RPVAN", "RPESP"],
        settles_at: ago(-22),
        radio: 1,
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

export function configValues(extra: Record<string, string> = {}, radios: Record<string, string> = {}): ConfigValues {
  const values: Record<string, string> = {
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
    "map/aircraft": "none",
    "map/aircraft_host": "",
    "map/ships": "none",
    "map/ships_host": "",
    "update/url": "https://oh2gba.eu/neoaprs/version.php",
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
  const radioValues = { ...radioValuesOf(), ...radios };
  return {
    values,
    defaults: { ...values },
    radio_values: radioValues,
    radio_defaults: { ...radioValues },
    urls: [],
    https: { on: false, port: 0, fingerprint: "", reason: "" },
  };
}

/** The radios' own settings as the daemon tells them (`radio_values`): radio 1's, an FM radio's (radiosOf), and the station's (`RADIO_STATION_KEYS`) unset. */
function radioValuesOf(): Record<string, string> {
  return {
    "radio/1/port": "",
    "radio/1/baud": "9600",
    "radio/1/beacon": "true",
    "radio/1/path": "",
    "radio/1/digipeat": "false",
    "radio/1/tcp_host": "127.0.0.1",
    "radio/1/tcp_port": "8001",
    ...Object.fromEntries(RADIO_STATION_KEYS.map((key) => [key, ""])),
  };
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
    retry: null,
    blocked: "",
    problem: null,
    estimate: null,
    radius_km: 150,
    maxzoom: 12,
    box: [22.1, 58.8, 27.8, 61.5],
    detail: null,
    world: null,
    later: false,
    aloha: [],
    layers: [mapLayer("aircraft"), mapLayer("ships")],
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
    local: true,
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
    unheard_radio: 1,
    email_radio: 1,
    unavailable_types: [],
    new_object_radios: [1],
    new_bulletin_radios: [1],
    station_status: "",
    station_status_last_sent: null,
    rig_state: "unused",
    message_key: "",
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

/** A port the system lists, held by no radio of ours. */
export function portRow(device: string, description: string, extra: Partial<PortRow> = {}): PortRow {
  return { device, description, hwid: "n/a", vid: null, pid: null, held_by: null, ...extra };
}

/** A sound card the system lists, held by no modem of ours. */
export function soundCard(id: string, name: string, extra: Partial<SoundCardRow> = {}): SoundCardRow {
  return { id, name, default: false, pick: false, held_by: null, ...extra };
}

/** A step of Find my radio: trying the first of 14 ports at 9600, for a search that named no radio (radio 1); `found` has the type that fits the TNC, its profile. */
export function radioSearch(extra: Partial<RadioSearchMessage> = {}): RadioSearchMessage {
  const state = extra.state ?? "trying";
  const profile = extra.profile ?? "";
  return {
    type: "radio_search",
    state,
    port: "/dev/ttyUSB0",
    baud: 9600,
    profile,
    number: 1,
    total: 14,
    radio: null,
    radio_type: state === "found" ? profile : "",
    ...extra,
  };
}

/** The value of the topic `radios` as the socket tells it: the rows by the radio's id as text. */
export const radiosValue = (...rows: RadioRow[]): Record<string, RadioRow> => Object.fromEntries(rows.map((row) => [String(row.id), row]));

/** Radio 1, the FM radio of the tests, with a modem-less line as a test gives it (its state, its problem). */
export const fmRow = (extra: Partial<RadioRow> = {}): RadioRow => radioRow(1, "kenwood-tnc2", extra);

/** Radio 2, a Mercury HF radio whose modem runs, with what a test gives of it and of its modem. */
export const hfRow = (extra: Partial<RadioRow> = {}, modem: Partial<ModemState> = {}): RadioRow =>
  radioRow(2, "mercury", { modem: modemState(modem), ...extra });

/** The topic `radios` of these rows, by the radio's id as text. */
export const radiosTopic = (...rows: RadioRow[]): Map<string, RadioRow> => new Map(rows.map((row) => [String(row.id), row]));

/** The topic `radios` of a station of radio 1 alone, an FM radio of the TNC the tests are about, connected (`connected`) or waiting. */
export function radiosOf(connected = true): Map<string, RadioRow> {
  return radiosTopic(radioRow(1, "kenwood-tnc2", { state: connected ? "connected" : "waiting" }));
}

/** The modem of a Sound card radio (Direwolf) running on its card, no packet heard yet; a test gives what it cares about. */
export function soundCardModem(extra: Partial<ModemState> = {}): ModemState {
  return {
    state: "running",
    reason: "",
    mode: "AFSK1200",
    keyed: false,
    busy: false,
    test: "",
    snr: null,
    frames_keyed: 0,
    max_frame: null,
    sound_card: "plughw:CARD=AIOC,DEV=0",
    frequencies: [],
    keying: "cm108",
    scope: false,
    tx_gain_db: 0,
    tx_peak_dbfs: null,
    rx_level: null,
    ...extra,
  };
}

/** A radio of the topic `radios`, as the daemon tells it: of the type given, on, connected, at its own place, with what its type may and can do; a test gives what it cares about. */
export function radioRow(id: number, type: string, extra: Partial<RadioRow> = {}): RadioRow {
  const known = RADIO_TYPES.find((entry) => entry.key === type);
  if (known === undefined) throw new Error(`no radio type ${type}`);
  return {
    id,
    type,
    kind: known.kind,
    name: "",
    number: 1,
    enabled: true,
    position: id,
    removed: false,
    dummy: type.startsWith("dummy"),
    state: "connected",
    problem: null,
    stats: lineStats(),
    lines: [],
    limits: { ...known.limits },
    allowed: { ...known.allowed },
    can: { ...known.can },
    choices: {
      beacon: true,
      status: false,
      ask: false,
      local_info: false,
      path: known.allowed.paths ? "" : null,
      digipeat: known.allowed.digipeat ? false : null,
    },
    beacon: { last_sent: null, next_due: null, interval_min: 30, problem: null },
    status: { last_sent: null, next_due: null, interval_min: 0 },
    modem: type === "direwolf" ? soundCardModem() : known.kind === "hf" && !type.startsWith("dummy") ? modemState() : null,
    card: { tx: null, rx: null, read: true },
    holds: [],
    ...extra,
  };
}
