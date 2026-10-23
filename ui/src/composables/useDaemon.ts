// The daemon as the page sees it: the eight topics as reactive state (the stations' own paths and timeouts are `stationPrefs`), the status, the latest answer to `weather_series`, to `alert_test` and to `list_ports`, the state of the connection, and `send`. Opens the socket when the component that calls it is mounted and
// closes it when it is unmounted. The conversation itself is lib/hub.ts.
import { onBeforeUnmount, onMounted, ref, shallowReactive, shallowRef } from "vue";
import type {
  AlertResultMessage,
  BulletinRow,
  ConfigValues,
  MapState,
  MessageRow,
  PacketRow,
  PortsMessage,
  StationPref,
  StationRow,
  StatusMessage,
  TncState,
  WeatherSeriesMessage,
} from "@/protocol/protocol";
import { probe } from "@/lib/access";
import { Hub, type Connection, type Store } from "@/lib/hub";
import { reloadOnce } from "@/lib/reload";

/** The page's own socket: beside the page, so that it works from any path. */
export function socketUrl(): string {
  const url = new URL("ws", document.baseURI);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export interface Toast {
  text: string;
  /** counts up, so that the same text twice is two toasts */
  n: number;
}

export function useDaemon(url: () => string = socketUrl) {
  const stations = shallowReactive(new Map<string, StationRow>());
  const packets = shallowReactive(new Map<string, PacketRow>());
  const messages = shallowReactive(new Map<string, MessageRow>());
  const bulletins = shallowReactive(new Map<string, BulletinRow>());
  const stationPrefs = shallowReactive(new Map<string, StationPref>());
  const tnc = shallowRef<TncState | null>(null);
  const config = shallowRef<ConfigValues | null>(null);
  const map = shallowRef<MapState | null>(null);
  const status = shallowRef<StatusMessage | null>(null);
  const connection = ref<Connection>("connecting");
  const lastError = shallowRef<Toast | null>(null);
  const weatherSeries = shallowRef<WeatherSeriesMessage | null>(null);
  const alertResult = shallowRef<AlertResultMessage | null>(null);
  const ports = shallowRef<PortsMessage | null>(null);
  const version = ref("");
  let toasts = 0;

  function fill<T>(into: Map<string, T>, rows: Record<string, T>): void {
    into.clear();
    for (const [key, row] of Object.entries(rows)) into.set(key, row);
  }

  const store: Store = {
    connection: (state) => (connection.value = state),
    hello: (message) => (version.value = message.version),
    status: (message) => (status.value = message),
    weatherSeries: (message) => (weatherSeries.value = message),
    alertResult: (message) => (alertResult.value = message),
    ports: (message) => (ports.value = message),
    error: (text) => (lastError.value = { text, n: ++toasts }),
    replaceStations: (rows) => fill(stations, rows),
    replacePackets: (rows) => fill(packets, rows),
    replaceMessages: (rows) => fill(messages, rows),
    replaceBulletins: (rows) => fill(bulletins, rows),
    replaceStationPrefs: (rows) => fill(stationPrefs, rows),
    replaceTnc: (value) => (tnc.value = value),
    replaceConfig: (value) => (config.value = value),
    replaceMap: (value) => (map.value = value),
    setStation: (key, row) => void stations.set(key, row),
    setPacket: (key, row) => void packets.set(key, row),
    setMessage: (key, row) => void messages.set(key, row),
    setBulletin: (key, row) => void bulletins.set(key, row),
    setStationPref: (call, pref) => void stationPrefs.set(call, pref),
    delStation: (key) => void stations.delete(key),
    delPacket: (key) => void packets.delete(key),
    delMessage: (key) => void messages.delete(key),
    delBulletin: (key) => void bulletins.delete(key),
    delStationPref: (call) => void stationPrefs.delete(call),
  };
  // a socket that closes before it has heard anything may have been refused for want of a login: if the daemon says so, the page loads again and shows the key screen
  const refused = (): void => void probe().then((access) => access === "locked" && location.reload());
  const hub = new Hub(store, { url, outOfDate: () => void reloadOnce(), refused });

  /** Sends a command; the toast says so when the socket is not open. */
  function send(command: Parameters<Hub["send"]>[0]): boolean {
    const sent = hub.send(command);
    if (!sent) store.error("Not connected to the daemon.");
    return sent;
  }

  onMounted(() => hub.open());
  onBeforeUnmount(() => hub.close());

  return {
    stations,
    packets,
    messages,
    bulletins,
    stationPrefs,
    tnc,
    config,
    map,
    status,
    connection,
    lastError,
    version,
    weatherSeries,
    alertResult,
    ports,
    send,
  };
}
