// The page's end of the conversation with the daemon (PROTOCOL.md): one WebSocket to /ws on the page's own host, `hello`, then the `state` of every topic and `patch` after it. Plain code with
// no Vue: what the messages say is handed to a `Store`, which the composable (composables/useDaemon.ts) makes reactive; the socket and the timers can be replaced, so the tests drive it.
// The socket is opened again by itself when it closes (1, 2, 4 ... 30 seconds), and a topic whose revision skips is asked for again with `subscribe`.
import type {
  AlertResultMessage,
  BulletinRow,
  Command,
  ErrorMessage,
  HelloMessage,
  Message,
  MessageRow,
  OwnBulletinRow,
  OwnObjectRow,
  PacketRow,
  PortsMessage,
  RadioSearchMessage,
  StationPref,
  StationRow,
  StatusMessage,
  TopicValues,
  ReleaseNotesMessage,
  UpdateResultMessage,
  WeatherSeriesMessage,
  PacketHistoryMessage,
  PositionHistoryMessage,
} from "@/protocol/protocol";
import { MESSAGE_TYPES, TOPIC_NAMES } from "@/protocol/lists";

export const FIRST_DELAY_MS = 1000;
export const MAX_DELAY_MS = 30000;
/** The messages that answer a command, by the method of the store that keeps each. */
const ANSWERS: Partial<Record<Message["type"], keyof Store>> = {
  weather_series: "weatherSeries",
  packet_history: "packetHistory",
  position_history: "positionHistory",
  alert_result: "alertResult",
  update_result: "updateResult",
  release_notes: "releaseNotes",
  ports: "ports",
  radio_search: "radioSearch",
};

type TopicName = keyof TopicValues;
export type Connection = "connecting" | "open" | "closed";

/** Where what the daemon says goes. A keyed topic (stations, packets, messages, bulletins, own_objects, own_bulletins, station_prefs) is told item by item, the others (tnc, config, map, update, gps, igate, qru) as a whole. */
export interface Store {
  connection(state: Connection): void;
  hello(message: HelloMessage): void;
  status(message: StatusMessage): void;
  error(message: ErrorMessage): void;
  weatherSeries(message: WeatherSeriesMessage): void;
  packetHistory(message: PacketHistoryMessage): void;
  positionHistory(message: PositionHistoryMessage): void;
  alertResult(message: AlertResultMessage): void;
  updateResult(message: UpdateResultMessage): void;
  releaseNotes(message: ReleaseNotesMessage): void;
  ports(message: PortsMessage): void;
  radioSearch(message: RadioSearchMessage): void;
  replaceStations(rows: Record<string, StationRow>): void;
  replacePackets(rows: Record<string, PacketRow>): void;
  replaceMessages(rows: Record<string, MessageRow>): void;
  replaceBulletins(rows: Record<string, BulletinRow>): void;
  replaceStationPrefs(rows: Record<string, StationPref>): void;
  replaceOwnObjects(rows: Record<string, OwnObjectRow>): void;
  replaceOwnBulletins(rows: Record<string, OwnBulletinRow>): void;
  replaceTnc(value: TopicValues["tnc"]): void;
  replaceConfig(value: TopicValues["config"]): void;
  replaceMap(value: TopicValues["map"]): void;
  replaceUpdate(value: TopicValues["update"]): void;
  replaceGps(value: TopicValues["gps"]): void;
  replaceIgate(value: TopicValues["igate"]): void;
  replaceQru(value: TopicValues["qru"]): void;
  setStation(key: string, row: StationRow): void;
  setPacket(key: string, row: PacketRow): void;
  setMessage(key: string, row: MessageRow): void;
  setBulletin(key: string, row: BulletinRow): void;
  setStationPref(call: string, pref: StationPref): void;
  setOwnObject(name: string, row: OwnObjectRow): void;
  setOwnBulletin(slot: string, row: OwnBulletinRow): void;
  delStation(key: string): void;
  delPacket(key: string): void;
  delMessage(key: string): void;
  delBulletin(key: string): void;
  delStationPref(call: string): void;
  delOwnObject(name: string): void;
  delOwnBulletin(slot: string): void;
}

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
  private wanted = false;
  private live = false;
  private readonly revs = new Map<TopicName, number>();

  constructor(
    private readonly store: Store,
    private readonly options: HubOptions,
  ) {}

  /** Opens the socket and keeps it open: a closed one is opened again after a wait that doubles. */
  open(): void {
    this.wanted = true;
    this.connect();
  }

  close(): void {
    this.wanted = false;
    clearTimeout(this.timer);
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
    this.store.connection("open");
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
    this.replace(topic, value);
  }

  private onPatch(topic: string, rev: number, ops: Extract<Message, { type: "patch" }>["ops"]): void {
    if (!isTopic(topic)) return;
    const before = this.revs.get(topic);
    if (before !== undefined && rev <= before) return; // what the page has already
    if (before === undefined || rev !== before + 1) {
      this.send({ cmd: "subscribe", topics: [topic] }); // a patch was missed: the topic is sent whole
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
    if (topic === "stations") this.store.replaceStations(value as TopicValues["stations"]);
    else if (topic === "packets") this.store.replacePackets(value as TopicValues["packets"]);
    else if (topic === "messages") this.store.replaceMessages(value as TopicValues["messages"]);
    else if (topic === "bulletins") this.store.replaceBulletins(value as TopicValues["bulletins"]);
    else if (topic === "station_prefs") this.store.replaceStationPrefs(value as TopicValues["station_prefs"]);
    else if (topic === "own_objects") this.store.replaceOwnObjects(value as TopicValues["own_objects"]);
    else if (topic === "own_bulletins") this.store.replaceOwnBulletins(value as TopicValues["own_bulletins"]);
    else if (topic === "tnc") this.store.replaceTnc(value as TopicValues["tnc"]);
    else if (topic === "map") this.store.replaceMap(value as TopicValues["map"]);
    else if (topic === "update") this.store.replaceUpdate(value as TopicValues["update"]);
    else if (topic === "gps") this.store.replaceGps(value as TopicValues["gps"]);
    else if (topic === "igate") this.store.replaceIgate(value as TopicValues["igate"]);
    else if (topic === "qru") this.store.replaceQru(value as TopicValues["qru"]);
    else this.store.replaceConfig(value as TopicValues["config"]);
  }

  private set(topic: TopicName, key: string, value: unknown): void {
    if (topic === "stations") this.store.setStation(key, value as StationRow);
    else if (topic === "packets") this.store.setPacket(key, value as PacketRow);
    else if (topic === "messages") this.store.setMessage(key, value as MessageRow);
    else if (topic === "bulletins") this.store.setBulletin(key, value as BulletinRow);
    else if (topic === "station_prefs") this.store.setStationPref(key, value as StationPref);
    else if (topic === "own_objects") this.store.setOwnObject(key, value as OwnObjectRow);
    else if (topic === "own_bulletins") this.store.setOwnBulletin(key, value as OwnBulletinRow);
  }

  private del(topic: TopicName, key: string): void {
    if (topic === "stations") this.store.delStation(key);
    else if (topic === "packets") this.store.delPacket(key);
    else if (topic === "messages") this.store.delMessage(key);
    else if (topic === "bulletins") this.store.delBulletin(key);
    else if (topic === "station_prefs") this.store.delStationPref(key);
    else if (topic === "own_objects") this.store.delOwnObject(key);
    else if (topic === "own_bulletins") this.store.delOwnBulletin(key);
  }
}
