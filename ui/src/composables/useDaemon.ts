// The daemon as the page sees it: the twelve topics as reactive state (the stations' own paths and timeouts are `stationPrefs`), the status, the latest answer to `weather_series`, to `alert_test` and to `list_ports`, the state of the connection, and `send`. Opens the socket when the component that calls it is mounted and
// closes it when it is unmounted. The conversation itself is lib/hub.ts.
import { onBeforeUnmount, onMounted, ref, shallowReactive, shallowRef, type Ref } from "vue";
import type {
  BulletinRow,
  ConfigValues,
  ErrorMessage,
  GpsState,
  HelloMessage,
  InstallInfo,
  MapState,
  MessageRow,
  PacketRow,
  StationPref,
  StationRow,
  StatusMessage,
  TncState,
  UpdateState,
} from "@/protocol/protocol";
import { useAnswers } from "@/composables/useAnswers";
import { useOwnTables } from "@/composables/useOwnTables";
import { probe } from "@/lib/access";
import { Hub, type Connection, type Store } from "@/lib/hub";
import { describeMismatch, reloadForDaemon, type Mismatch } from "@/lib/reload";

/** The page's own socket: beside the page, so that it works from any path. */
export function socketUrl(): string {
  const url = new URL("ws", document.baseURI);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** An `error` of the daemon, or of the page itself (`cmd` empty, `code` `not_connected`): the page goes by `cmd`, `key` and `code`, and shows `text`. */
export interface Toast extends Omit<ErrorMessage, "type"> {
  /** counts up, so that the same text twice is two toasts */
  n: number;
}

/** Replaces what a keyed topic holds with the rows the daemon told; `done` is set once it has. */
function fill<T>(into: Map<string, T>, rows: Record<string, T>, done?: Ref<boolean>): void {
  into.clear();
  for (const [key, row] of Object.entries(rows)) into.set(key, row);
  if (done) done.value = true;
}

/** The topics that are told whole: the radio, the settings, the base map, Update now and the GPS. */
function useWholeTopics() {
  const refs = {
    tnc: shallowRef<TncState | null>(null),
    config: shallowRef<ConfigValues | null>(null),
    map: shallowRef<MapState | null>(null),
    selfUpdate: shallowRef<UpdateState | null>(null),
    gps: shallowRef<GpsState | null>(null),
  };
  const handlers: Pick<Store, "replaceTnc" | "replaceConfig" | "replaceMap" | "replaceUpdate" | "replaceGps"> = {
    replaceTnc: (value) => (refs.tnc.value = value),
    replaceConfig: (value) => (refs.config.value = value),
    replaceMap: (value) => (refs.map.value = value),
    replaceUpdate: (value) => (refs.selfUpdate.value = value),
    replaceGps: (value) => (refs.gps.value = value),
  };
  return { refs, handlers };
}

/** A hello of a daemon that the page does not go with, after the load that was made for it (lib/reload.ts): the notice is set and the socket closed for good, so that nothing the daemon sends reaches the page and it is not opened again. */
function refuseMismatch(hello: HelloMessage, mismatch: Ref<Mismatch | null>, close: () => void): void {
  if (reloadForDaemon(hello) !== "stale") return;
  mismatch.value = describeMismatch(hello);
  close();
}

export function useDaemon(url: () => string = socketUrl) {
  const stations = shallowReactive(new Map<string, StationRow>());
  const stationsLoaded = ref(false); // the daemon has told the stations once: `stations` is then what was there, not a part of it
  const packets = shallowReactive(new Map<string, PacketRow>());
  const messages = shallowReactive(new Map<string, MessageRow>());
  const messagesLoaded = ref(false); // the daemon has told the messages once: `messages` is then what was there, not a part of it
  const bulletins = shallowReactive(new Map<string, BulletinRow>());
  const stationPrefs = shallowReactive(new Map<string, StationPref>());
  const own = useOwnTables();
  const answers = useAnswers();
  const whole = useWholeTopics();
  const status = shallowRef<StatusMessage | null>(null);
  const connection = ref<Connection>("connecting");
  const lastError = shallowRef<Toast | null>(null);
  const version = ref("");
  const mismatch = shallowRef<Mismatch | null>(null); // the daemon is another protocol or serves another build of the page, and a load did not help: the page does not run against it (refuseMismatch)
  const install = shallowRef<InstallInfo | null>(null);
  let toasts = 0;

  const store: Store = {
    connection: (state) => (connection.value = state),
    hello: (message) => {
      version.value = message.version;
      install.value = message.install;
    },
    status: (message) => (status.value = message),
    error: ({ cmd, key, code, params, text }) => (lastError.value = { cmd, key, code, params, text, n: ++toasts }),
    replaceStations: (rows) => fill(stations, rows, stationsLoaded),
    replacePackets: (rows) => fill(packets, rows),
    replaceMessages: (rows) => fill(messages, rows, messagesLoaded),
    replaceBulletins: (rows) => fill(bulletins, rows),
    replaceStationPrefs: (rows) => fill(stationPrefs, rows),
    ...own.handlers,
    ...answers.handlers,
    ...whole.handlers,
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
  const hub = new Hub(store, { url, onHello: (hello) => refuseMismatch(hello, mismatch, () => hub.close()), refused });

  /** Sends a command; the toast says so when the socket is not open. */
  function send(command: Parameters<Hub["send"]>[0]): boolean {
    const sent = hub.send(command);
    if (!sent) store.error({ type: "error", cmd: "", key: null, code: "not_connected", params: {}, text: "Not connected to the daemon." });
    return sent;
  }

  onMounted(() => hub.open());
  onBeforeUnmount(() => hub.close());

  return {
    stations,
    stationsLoaded,
    packets,
    messages,
    messagesLoaded,
    bulletins,
    stationPrefs,
    ownObjects: own.ownObjects,
    ownBulletins: own.ownBulletins,
    ...whole.refs,
    status,
    connection,
    lastError,
    version,
    mismatch,
    install,
    updateResult: answers.updateResult,
    weatherSeriesByCall: answers.weatherSeriesByCall,
    alertResult: answers.alertResult,
    ports: answers.ports,
    radioSearch: answers.radioSearch,
    send,
  };
}
