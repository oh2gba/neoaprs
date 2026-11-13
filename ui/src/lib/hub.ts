// The page's end of the conversation with the daemon (PROTOCOL.md): one WebSocket to /ws on the page's own host, `hello`, then the `state` of every topic and `patch` after it. Plain code with
// no Vue: what the messages say is handed to a `Store`, which the composable (composables/useDaemon.ts) makes reactive; the socket and the timers can be replaced, so the tests drive it.
// The socket is opened again by itself when it closes (1, 2, 4 ... 30 seconds), at once when the daemon has said nothing on it for 25 s or the page is woken (`wake`: a phone that slept may never see the close), and a topic whose revision skips is asked for again with `subscribe`.
import type {
  AlertResultMessage,
  BulletinRow,
  Command,
  ErrorMessage,
  HelloMessage,
  HfScopeMessage,
  Message,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  PortsMessage,
  RadioSearchMessage,
  StationAlertMessage,
  StationKey,
  StationPref,
  StationRow,
  StatusMessage,
  TopicValues,
  ReleaseNotesMessage,
  UpdateResultMessage,
  SpeedSeriesMessage,
  StationTrafficMessage,
  WeatherSeriesMessage,
  PacketHistoryMessage,
  PositionHistoryMessage,
} from "@/protocol/protocol";
import { MESSAGE_TYPES, TOPIC_NAMES } from "@/protocol/lists";

export const FIRST_DELAY_MS = 1000;
export const MAX_DELAY_MS = 30000;
/** The daemon tells every page its status every 10 s (neoaprs/web/api.py STATUS_EVERY_SEC): an open socket that has said nothing for this long is gone though no close came (a phone that slept, a network that changed). */
export const QUIET_MS = 25000;
const CHECK_MS = 5000;
/** The messages that answer a command, by the method of the store that keeps each. */
const ANSWERS: Partial<Record<Message["type"], keyof Store>> = {
  weather_series: "weatherSeries",
  packet_history: "packetHistory",
  speed_series: "speedSeries",
  station_traffic: "stationTraffic",
  position_history: "positionHistory",
  alert_result: "alertResult",
  update_result: "updateResult",
  release_notes: "releaseNotes",
  ports: "ports",
  radio_search: "radioSearch",
};

type TopicName = keyof TopicValues;
export type Connection = "connecting" | "open" | "closed";

/** Where what the daemon says goes. A keyed topic (stations, packets, messages, bulletins, own_objects, own_bulletins, station_prefs, station_keys) is told item by item, the others (tnc, hf, config, map, update, gps, igate, qru, general) as a whole. */
export interface Store {
  connection(state: Connection): void;
  hello(message: HelloMessage): void;
  status(message: StatusMessage): void;
  error(message: ErrorMessage): void;
  weatherSeries(message: WeatherSeriesMessage): void;
  packetHistory(message: PacketHistoryMessage): void;
  speedSeries(message: SpeedSeriesMessage): void;
  stationTraffic(message: StationTrafficMessage): void;
  positionHistory(message: PositionHistoryMessage): void;
  alertResult(message: AlertResultMessage): void;
  updateResult(message: UpdateResultMessage): void;
  releaseNotes(message: ReleaseNotesMessage): void;
  ports(message: PortsMessage): void;
  radioSearch(message: RadioSearchMessage): void;
  /** an alert set on a station fired (not an answer: every page is told, once) */
  stationAlert(message: StationAlertMessage): void;
  /** a picture of the HF radio's audio, told to a page that asked for the scope (`hf_scope`) */
  hfScope(message: HfScopeMessage): void;
  replaceStations(rows: Record<string, StationRow>): void;
  replacePackets(rows: Record<string, PacketRow>): void;
  replaceMessages(rows: Record<string, MessageRow>): void;
  replaceBulletins(rows: Record<string, BulletinRow>): void;
  replaceStationPrefs(rows: Record<string, StationPref>): void;
  replaceStationKeys(rows: Record<string, StationKey>): void;
  replaceOwnObjects(rows: Record<string, OwnObjectRow>): void;
  replaceOwnBulletins(rows: Record<string, OwnBulletinRow>): void;
  replaceTnc(value: TopicValues["tnc"]): void;
  replaceHf(value: TopicValues["hf"]): void;
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
  setMessage(key: string, row: MessageRow): void;
  setBulletin(key: string, row: BulletinRow): void;
  setStationPref(call: string, pref: StationPref): void;
  setStationKey(call: string, key: StationKey): void;
  setOwnObject(name: string, row: OwnObjectRow): void;
  setOwnBulletin(slot: string, row: OwnBulletinRow): void;
  delStation(key: string): void;
  delPacket(key: string): void;
  delMessage(key: string): void;
  delBulletin(key: string): void;
  delStationPref(call: string): void;
  delStationKey(call: string): void;
  delOwnObject(name: string): void;
  delOwnBulletin(slot: string): void;
}

/** The method of the store that takes the whole value of each topic. */
const REPLACERS: Record<TopicName, keyof Store> = {
  stations: "replaceStations",
  packets: "replacePackets",
  messages: "replaceMessages",
  bulletins: "replaceBulletins",
  station_prefs: "replaceStationPrefs",
  station_keys: "replaceStationKeys",
  own_objects: "replaceOwnObjects",
  own_bulletins: "replaceOwnBulletins",
  tnc: "replaceTnc",
  hf: "replaceHf",
  config: "replaceConfig",
  map: "replaceMap",
  update: "replaceUpdate",
  gps: "replaceGps",
  igate: "replaceIgate",
  qru: "replaceQru",
  general: "replaceGeneral",
  skeds: "replaceSkeds",
};

/** What the hub needs of a WebSocket: the browser's has more. */
export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(): void;
}

interface HubOptions {
  url: () => string;
  /** makes the socket; the browser's WebSocket by default */
  socket?: (url: string) => SocketLike;
  /** the daemon has said hello: the caller looks at its version and protocol (lib/reload.ts) */
  onHello?: (message: HelloMessage) => void;
  /** a socket closed before the daemon said anything: it may have been refused */
  refused?: () => void;
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

/** The text of a frame as a message of the daemon, null when it is none (the daemon's output is checked against the same models in its tests; this only looks at the tag). */
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
  /** When the daemon last said anything on the socket that is open. */
  private heardAt = 0;
  private readonly revs = new Map<TopicName, number>();
  /** The topics asked for again, whose state has not come yet: one ask each. */
  private readonly asked = new Set<TopicName>();

  constructor(
    private readonly store: Store,
    private readonly options: HubOptions,
  ) {}

  /** Opens the socket and keeps it open: a closed one is opened again after a wait that doubles, and one that has gone quiet at once. */
  open(): void {
    this.wanted = true;
    clearInterval(this.watch);
    this.watch = setInterval(() => this.dropQuiet(), CHECK_MS);
    this.connect();
  }

  /** The page is in front again, or the network is back: a socket that has gone quiet is opened again, and a wait for the next try ends now. */
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

  /** Sends a command; false when the socket is not open (the caller says so). */
  send(command: Command): boolean {
    if (this.socket === null || !this.live) return false;
    this.socket.send(JSON.stringify(command));
    return true;
  }

  private connect(): void {
    clearTimeout(this.timer);
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
    socket.onmessage = (event: MessageEvent) => {
      if (this.socket !== socket || typeof event.data !== "string") return;
      this.heardAt = Date.now();
      if (!this.live) this.up();
      this.handle(event.data);
    };
    socket.onclose = () => {
      if (this.socket !== socket) return; // an older socket that closes late
      this.socket = null;
      const spoke = this.live;
      this.live = false;
      this.store.connection("closed");
      if (!spoke) this.options.refused?.();
      this.retry();
    };
    socket.onerror = () => undefined; // the close that follows says it
  }

  /** The daemon has spoken: the connection is up and the wait starts over. */
  private up(): void {
    this.live = true;
    this.delay = FIRST_DELAY_MS;
    this.revs.clear();
    this.asked.clear();
    this.store.connection("open");
  }

  /** An open socket the daemon has said nothing on for QUIET_MS is let go (its late close is ignored) and a new one opened at once. */
  private dropQuiet(): void {
    const socket = this.socket;
    if (socket === null || !this.live || Date.now() - this.heardAt < QUIET_MS) return;
    this.socket = null;
    this.live = false;
    socket.close();
    this.store.connection("closed");
    this.connect();
  }

  private retry(): void {
    if (!this.wanted) return;
    this.timer = setTimeout(() => this.connect(), this.delay);
    this.delay = nextDelay(this.delay);
  }

  /** One frame of the daemon. */
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
      case "hf_scope":
        this.store.hfScope(message);
        break;
      default:
        this.answer(message);
    }
  }

  /** The answer to a command (the weather series, the packets by the hour, the ports...), kept by the store under its own name; a pong is nothing to keep. */
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
    if (before !== undefined && rev <= before) return; // what the page has already
    if (before === undefined || rev !== before + 1) {
      // a patch was missed: the topic is sent whole, once, however many patches follow before it comes
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

  // The values arrive as `unknown`; the daemon checks every one against its models before it sends (web/outbound.py), so an object of the right topic is taken as the topic's type.
  private replace(topic: TopicName, value: unknown): void {
    (this.store[REPLACERS[topic]] as (value: unknown) => void).call(this.store, value);
  }

  private set(topic: TopicName, key: string, value: unknown): void {
    if (topic === "stations") this.store.setStation(key, value as StationRow);
    else if (topic === "packets") this.store.setPacket(key, value as PacketRow);
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
    else if (topic === "messages") this.store.delMessage(key);
    else if (topic === "bulletins") this.store.delBulletin(key);
    else if (topic === "station_prefs") this.store.delStationPref(key);
    else if (topic === "station_keys") this.store.delStationKey(key);
    else if (topic === "own_objects") this.store.delOwnObject(key);
    else if (topic === "own_bulletins") this.store.delOwnBulletin(key);
  }
}
