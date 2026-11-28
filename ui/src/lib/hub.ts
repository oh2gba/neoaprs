// The page's end of the daemon conversation (PROTOCOL.md): one WebSocket to /ws, `hello`, then the
// `state` of every topic and `patch` after it. Plain code without Vue: messages go to a `Store`,
// which useDaemon.ts makes reactive. The socket reopens when it closes (1, 2, 4 ... 30 s), at once
// after 25 s of silence or `wake`, and a topic whose revision skips is asked for again with
// `subscribe`.
import type {
  AlertResultMessage,
  SavedMessage,
  BulletinRow,
  Command,
  ErrorMessage,
  HelloMessage,
  IgateSentMessage,
  LayerThingsMessage,
  Message,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  PortsMessage,
  RadioAddedMessage,
  RadioLevelMessage,
  RadioRow,
  RadioSearchMessage,
  SatellitesMessage,
  StationAlertMessage,
  StationKey,
  StationPref,
  StationRow,
  StatusMessage,
  TopicValues,
  ReleaseNotesMessage,
  UpdateResultMessage,
  SignalSeriesMessage,
  SpeedSeriesMessage,
  StationTrafficMessage,
  WeatherSeriesMessage,
  PacketHistoryMessage,
  PacketStatsMessage,
  PositionHistoryMessage,
} from "@/protocol/protocol";
import { MESSAGE_TYPES, TOPIC_NAMES } from "@/protocol/lists";
import type { RadioId } from "@/lib/radios";
import { parseScopeFrame, type ScopeHistory, type ScopeRow } from "@/lib/scoperow";

export const FIRST_DELAY_MS = 1000;
export const MAX_DELAY_MS = 30000;
/**
 * The daemon sends the status every 10 s (neoaprs/web/api.py STATUS_EVERY_SEC); a socket silent for
 * longer is dead.
 */
export const QUIET_MS = 25000;
const CHECK_MS = 5000;
/** The messages that answer a command, by the store method that keeps each. */
const ANSWERS: Partial<Record<Message["type"], keyof Store>> = {
  weather_series: "weatherSeries",
  packet_history: "packetHistory",
  packet_stats: "packetStats",
  speed_series: "speedSeries",
  signal_series: "signalSeries",
  station_traffic: "stationTraffic",
  position_history: "positionHistory",
  alert_result: "alertResult",
  saved: "saved",
  update_result: "updateResult",
  release_notes: "releaseNotes",
  ports: "ports",
  radio_search: "radioSearch",
  radio_added: "radioAdded",
  radio_level: "radioLevel",
  layer_things: "layerThings",
  satellites: "satellites",
  igate_sent: "igateSent",
};

type TopicName = keyof TopicValues;
export type Connection = "connecting" | "open" | "closed";

/** Where what the daemon says goes. Keyed topics are sent item by item, the others whole. */
export interface Store {
  connection(state: Connection): void;
  hello(message: HelloMessage): void;
  status(message: StatusMessage): void;
  error(message: ErrorMessage): void;
  weatherSeries(message: WeatherSeriesMessage): void;
  packetHistory(message: PacketHistoryMessage): void;
  packetStats(message: PacketStatsMessage): void;
  speedSeries(message: SpeedSeriesMessage): void;
  signalSeries(message: SignalSeriesMessage): void;
  stationTraffic(message: StationTrafficMessage): void;
  positionHistory(message: PositionHistoryMessage): void;
  alertResult(message: AlertResultMessage): void;
  /** The daemon has put a `set_config` that carried an id in force. */
  saved(message: SavedMessage): void;
  updateResult(message: UpdateResultMessage): void;
  releaseNotes(message: ReleaseNotesMessage): void;
  ports(message: PortsMessage): void;
  radioSearch(message: RadioSearchMessage): void;
  radioAdded(message: RadioAddedMessage): void;
  /**
   * A Sound card radio's receive level, ten times a second, to a page that asked (`radio_level`).
   */
  radioLevel(message: RadioLevelMessage): void;
  /**
   * A layer's whole table of aircraft or ships, sent to a page that looks at the layer
   * (`layer_look`).
   */
  layerThings(message: LayerThingsMessage): void;
  /** The satellites layer of now, sent to a page that looks at it (`satellite_look`). */
  satellites(message: SatellitesMessage): void;
  /** The lines put on APRS-IS, sent to a page that looks at them (`igate_look`). */
  igateSent(message: IgateSentMessage): void;
  /** An alert set on a station fired (sent once to every page, not an answer). */
  stationAlert(message: StationAlertMessage): void;
  /**
   * A row of a radio's waterfall for a page that asked for its scope: a binary frame (PROTOCOL.md).
   */
  hfScopeRow(row: ScopeRow, radio: RadioId): void;
  /**
   * The kept waterfall rows, oldest first with ages, and the daemon's clock; empty means forget
   * what is held.
   */
  hfScopeHistory(history: ScopeHistory, radio: RadioId): void;
  replaceStations(rows: Record<string, StationRow>): void;
  replacePackets(rows: Record<string, PacketRow>): void;
  replaceRadios(rows: Record<string, RadioRow>): void;
  replaceMessages(rows: Record<string, MessageRow>): void;
  replaceBulletins(rows: Record<string, BulletinRow>): void;
  replaceStationPrefs(rows: Record<string, StationPref>): void;
  replaceStationKeys(rows: Record<string, StationKey>): void;
  replaceOwnObjects(rows: Record<string, OwnObjectRow>): void;
  replaceOwnBulletins(rows: Record<string, OwnBulletinRow>): void;
  replaceConfig(value: TopicValues["config"]): void;
  replaceMap(value: TopicValues["map"]): void;
  replaceUpdate(value: TopicValues["update"]): void;
  replaceGps(value: TopicValues["gps"]): void;
  replaceIgate(value: TopicValues["igate"]): void;
  replaceQru(value: TopicValues["qru"]): void;
  replaceGeneral(value: TopicValues["general"]): void;
  replaceSkeds(value: TopicValues["skeds"]): void;
  setStation(key: string, row: StationRow): void;
  setPacket(key: string, row: PacketRow): void;
  setRadio(key: string, row: RadioRow): void;
  setMessage(key: string, row: MessageRow): void;
  setBulletin(key: string, row: BulletinRow): void;
  setStationPref(call: string, pref: StationPref): void;
  setStationKey(call: string, key: StationKey): void;
  setOwnObject(name: string, row: OwnObjectRow): void;
  setOwnBulletin(slot: string, row: OwnBulletinRow): void;
  delStation(key: string): void;
  delPacket(key: string): void;
  delRadio(key: string): void;
  delMessage(key: string): void;
  delBulletin(key: string): void;
  delStationPref(call: string): void;
  delStationKey(call: string): void;
  delOwnObject(name: string): void;
  delOwnBulletin(slot: string): void;
}

/** The store method that takes the whole value of each topic. */
const REPLACERS: Record<TopicName, keyof Store> = {
  stations: "replaceStations",
  packets: "replacePackets",
  radios: "replaceRadios",
  messages: "replaceMessages",
  bulletins: "replaceBulletins",
  station_prefs: "replaceStationPrefs",
  station_keys: "replaceStationKeys",
  own_objects: "replaceOwnObjects",
  own_bulletins: "replaceOwnBulletins",
  config: "replaceConfig",
  map: "replaceMap",
  update: "replaceUpdate",
  gps: "replaceGps",
  igate: "replaceIgate",
  qru: "replaceQru",
  general: "replaceGeneral",
  skeds: "replaceSkeds",
};

/** What the hub needs of a WebSocket (the browser's has more). */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  /** How a binary frame is given: `arraybuffer` where the socket has the field. */
  binaryType?: string;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(): void;
}

interface HubOptions {
  url: () => string;
  /** Makes the socket; the browser's WebSocket by default. */
  socket?: (url: string) => SocketLike;
  /** The daemon said hello: the caller checks its version and protocol (lib/reload.ts). */
  onHello?: (message: HelloMessage) => void;
  /** A socket closed before the daemon said anything; it may have been refused. */
  refused?: () => void;
}

/** Replaces what a keyed topic's table holds with the rows the daemon sent. */
export function fillTable<T>(into: Map<string, T>, rows: Record<string, T>): void {
  into.clear();
  for (const [key, row] of Object.entries(rows)) into.set(key, row);
}

export function nextDelay(delay: number): number {
  return Math.min(delay * 2, MAX_DELAY_MS);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTopic(name: string): name is TopicName {
  return (TOPIC_NAMES as readonly string[]).includes(name);
}

function isMessage(value: unknown): value is Message {
  return isRecord(value) && typeof value.type === "string" && (MESSAGE_TYPES as readonly string[]).includes(value.type);
}

/** The text of a frame as a daemon message, null if it is none. Only the tag is checked here. */
export function parseMessage(text: string): Message | null {
  try {
    const data: unknown = JSON.parse(text);
    return isMessage(data) ? data : null;
  } catch {
    return null;
  }
}

export class Hub {
  private socket: SocketLike | null = null;
  private delay = FIRST_DELAY_MS;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private watch: ReturnType<typeof setInterval> | undefined;
  private wanted = false;
  private live = false;
  /** When the daemon last said anything on the open socket. */
  private heardAt = 0;
  private readonly revs = new Map<TopicName, number>();
  /** Topics asked for again whose state has not come yet: one ask each. */
  private readonly asked = new Set<TopicName>();

  constructor(
    private readonly store: Store,
    private readonly options: HubOptions,
  ) {}

  /**
   * Opens the socket and keeps it open: a closed or silent socket is reopened after a doubling
   * wait.
   */
  open(): void {
    this.wanted = true;
    clearInterval(this.watch);
    this.watch = setInterval(() => this.dropQuiet(), CHECK_MS);
    this.connect();
  }

  /**
   * The page is in front again or the network is back: a quiet socket is reopened and a pending
   * wait ends.
   */
  wake(): void {
    if (!this.wanted) return;
    if (this.socket === null) {
      this.delay = FIRST_DELAY_MS;
      this.connect();
    } else {
      this.dropQuiet();
    }
  }

  close(): void {
    this.wanted = false;
    clearTimeout(this.timer);
    clearInterval(this.watch);
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.store.connection("closed");
  }

  /** Sends a command; false when the socket is not open. */
  send(command: Command): boolean {
    if (this.socket === null || !this.live) return false;
    this.socket.send(JSON.stringify(command));
    return true;
  }

  private connect(): void {
    clearTimeout(this.timer);
    const old = this.socket;
    this.socket = null;
    old?.close();
    this.store.connection("connecting");
    let socket: SocketLike;
    try {
      socket = this.options.socket ? this.options.socket(this.options.url()) : new WebSocket(this.options.url());
    } catch {
      this.retry();
      return;
    }
    this.socket = socket;
    this.live = false;
    this.heardAt = Date.now();
    socket.binaryType = "arraybuffer";
    socket.onmessage = (event: MessageEvent) => {
      if (this.socket !== socket) return;
      this.heardAt = Date.now();
      if (!this.live) this.up();
      if (typeof event.data === "string") this.handle(event.data);
      else if (event.data instanceof ArrayBuffer) this.row(event.data);
    };
    socket.onclose = () => {
      if (this.socket !== socket) return; // older socket closing late
      this.socket = null;
      const spoke = this.live;
      this.live = false;
      this.store.connection("closed");
      if (!spoke) this.options.refused?.();
      this.retry();
    };
    socket.onerror = () => undefined;
  }

  /** The daemon spoke: the connection is up and the wait starts over. */
  private up(): void {
    this.live = true;
    this.delay = FIRST_DELAY_MS;
    this.revs.clear();
    this.asked.clear();
    this.store.connection("open");
  }

  /**
   * Drops a socket silent for QUIET_MS (its late close is ignored): reconnects at once if it ever
   * spoke, else after the wait.
   */
  private dropQuiet(): void {
    const socket = this.socket;
    if (socket === null || Date.now() - this.heardAt < QUIET_MS) return;
    const spoke = this.live;
    this.socket = null;
    this.live = false;
    socket.close();
    this.store.connection("closed");
    if (spoke) this.connect();
    else this.retry();
  }

  private retry(): void {
    if (!this.wanted) return;
    this.timer = setTimeout(() => this.connect(), this.delay);
    this.delay = nextDelay(this.delay);
  }

  /** Handles one frame of the daemon. */
  handle(text: string): void {
    const message = parseMessage(text);
    if (message === null) return;
    switch (message.type) {
      case "hello":
        this.store.hello(message);
        this.options.onHello?.(message);
        break;
      case "status":
        this.store.status(message);
        break;
      case "error":
        this.store.error(message);
        break;
      case "state":
        this.onState(message.topic, message.rev, message.value);
        break;
      case "patch":
        this.onPatch(message.topic, message.rev, message.ops);
        break;
      case "station_alert":
        this.store.stationAlert(message);
        break;
      default:
        this.answer(message);
    }
  }

  /** A binary frame: a waterfall row, the kept rows, or an unknown kind, which is dropped. */
  private row(data: ArrayBuffer): void {
    const frame = parseScopeFrame(data);
    if (frame === null) return;
    if ("row" in frame) this.store.hfScopeRow(frame.row, frame.radio);
    else this.store.hfScopeHistory(frame.history, frame.radio);
  }

  /**
   * The answer to a command (weather series, packets by the hour, ports...), kept by the store
   * under its own name.
   */
  private answer(message: Message): void {
    const name = ANSWERS[message.type];
    if (name !== undefined) (this.store[name] as (m: Message) => void)(message);
  }

  private onState(topic: string, rev: number, value: unknown): void {
    if (!isTopic(topic) || !isRecord(value)) return;
    this.revs.set(topic, rev);
    this.asked.delete(topic);
    this.replace(topic, value);
  }

  private onPatch(topic: string, rev: number, ops: Extract<Message, { type: "patch" }>["ops"]): void {
    if (!isTopic(topic)) return;
    const before = this.revs.get(topic);
    if (before !== undefined && rev <= before) return;
    if (before === undefined || rev !== before + 1) {
      // A patch was missed: ask for the whole topic once, however many patches arrive before it.
      if (!this.asked.has(topic) && this.send({ cmd: "subscribe", topics: [topic] })) this.asked.add(topic);
      return;
    }
    this.revs.set(topic, rev);
    for (const op of ops) {
      if (op.op === "replace") {
        if (isRecord(op.value)) this.replace(topic, op.value);
      } else if (op.op === "del") {
        this.del(topic, op.key);
      } else if (isRecord(op.value)) {
        this.set(topic, op.key, op.value);
      }
    }
  }

  // The daemon checks every value against its models before sending (web/outbound.py), so the
  // topic's type is trusted.
  private replace(topic: TopicName, value: unknown): void {
    (this.store[REPLACERS[topic]] as (value: unknown) => void).call(this.store, value);
  }

  private set(topic: TopicName, key: string, value: unknown): void {
    if (topic === "stations") this.store.setStation(key, value as StationRow);
    else if (topic === "packets") this.store.setPacket(key, value as PacketRow);
    else if (topic === "radios") this.store.setRadio(key, value as RadioRow);
    else if (topic === "messages") this.store.setMessage(key, value as MessageRow);
    else if (topic === "bulletins") this.store.setBulletin(key, value as BulletinRow);
    else if (topic === "station_prefs") this.store.setStationPref(key, value as StationPref);
    else if (topic === "station_keys") this.store.setStationKey(key, value as StationKey);
    else if (topic === "own_objects") this.store.setOwnObject(key, value as OwnObjectRow);
    else if (topic === "own_bulletins") this.store.setOwnBulletin(key, value as OwnBulletinRow);
  }

  private del(topic: TopicName, key: string): void {
    if (topic === "stations") this.store.delStation(key);
    else if (topic === "packets") this.store.delPacket(key);
    else if (topic === "radios") this.store.delRadio(key);
    else if (topic === "messages") this.store.delMessage(key);
    else if (topic === "bulletins") this.store.delBulletin(key);
    else if (topic === "station_prefs") this.store.delStationPref(key);
    else if (topic === "station_keys") this.store.delStationKey(key);
    else if (topic === "own_objects") this.store.delOwnObject(key);
    else if (topic === "own_bulletins") this.store.delOwnBulletin(key);
  }
}
