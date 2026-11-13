// The daemon as the page sees it: the fifteen topics as reactive state (the stations' own paths, RF only and alerts are `stationPrefs`), the status, the latest alert of a station that fired (`stationAlert`), the latest answer to `weather_series`, to `alert_test` and to `list_ports`, the state of the connection, and `send`. Opens the socket when the component that calls it is mounted and
// closes it when it is unmounted. The conversation itself is lib/hub.ts.
import { onBeforeUnmount, onMounted, ref, shallowReactive, shallowRef, type Ref } from "vue";
import type {
  BulletinRow,
  ConfigValues,
  ErrorMessage,
  GeneralState,
  SkedsState,
  GpsState,
  HelloMessage,
  HfScopeMessage,
  IgateState,
  InstallInfo,
  MapState,
  MessageRow,
  PacketRow,
  QruState,
  StationAlertMessage,
  StationRow,
  StatusMessage,
  TncState,
  UpdateState,
} from "@/protocol/protocol";
import { useAnswers } from "@/composables/useAnswers";
import { useOwnTables } from "@/composables/useOwnTables";
import { useStationTables } from "@/composables/useStationTables";
import { usePageErrorReport } from "@/composables/usePageErrorReport";
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

/** The topics that are told whole: the FM radio, the HF radio, the settings, the base map, Update now, the GPS, the iGate, local info (QRU) and the general queries asked (Ask around). */
function useWholeTopics() {
  const refs = {
    tnc: shallowRef<TncState | null>(null),
    hf: shallowRef<TncState | null>(null),
    config: shallowRef<ConfigValues | null>(null),
    map: shallowRef<MapState | null>(null),
    selfUpdate: shallowRef<UpdateState | null>(null),
    gps: shallowRef<GpsState | null>(null),
    igate: shallowRef<IgateState | null>(null),
    qru: shallowRef<QruState | null>(null),
    general: shallowRef<GeneralState | null>(null),
    skeds: shallowRef<SkedsState | null>(null),
    hfScope: shallowRef<HfScopeMessage | null>(null), // (not a topic: the latest picture of the HF radio's audio, told to a page that has the scope open, composables/useHfScope.ts)
  };
  const handlers: Pick<
    Store,
    | "replaceTnc"
    | "replaceHf"
    | "replaceConfig"
    | "replaceMap"
    | "replaceUpdate"
    | "replaceGps"
    | "replaceIgate"
    | "replaceQru"
    | "replaceGeneral"
    | "replaceSkeds"
    | "hfScope"
  > = {
    replaceTnc: (value) => (refs.tnc.value = value),
    replaceHf: (value) => (refs.hf.value = value),
    replaceConfig: (value) => (refs.config.value = value),
    replaceMap: (value) => (refs.map.value = value),
    replaceUpdate: (value) => (refs.selfUpdate.value = value),
    replaceGps: (value) => (refs.gps.value = value),
    replaceIgate: (value) => (refs.igate.value = value),
    replaceQru: (value) => (refs.qru.value = value),
    replaceGeneral: (value) => (refs.general.value = value),
    replaceSkeds: (value) => (refs.skeds.value = value),
    hfScope: (message) => (refs.hfScope.value = message),
  };
  return { refs, handlers };
}

/** A hello of a daemon that the page does not go with, after the load that was made for it (lib/reload.ts): the notice is set and the socket closed for good, so that nothing the daemon sends reaches the page and it is not opened again. */
function refuseMismatch(hello: HelloMessage, mismatch: Ref<Mismatch | null>, close: () => void): void {
  if (reloadForDaemon(hello) !== "stale") return;
  mismatch.value = describeMismatch(hello);
  close();
}

/** What the daemon's hello says of it: its version, how it was installed, and whether this page is on the computer it runs on (until the hello has said so, it is not). */
function useHello() {
  const version = ref("");
  const install = shallowRef<InstallInfo | null>(null);
  const local = ref(false);
  const hello = (message: HelloMessage): void => {
    version.value = message.version;
    install.value = message.install;
    local.value = message.local;
  };
  return { hello, refs: { version, install, local } };
}

export function useDaemon(url: () => string = socketUrl) {
  const stations = shallowReactive(new Map<string, StationRow>());
  const stationsLoaded = ref(false); // the daemon has told the stations once: `stations` is then what was there, not a part of it
  const packets = shallowReactive(new Map<string, PacketRow>());
  const messages = shallowReactive(new Map<string, MessageRow>());
  const messagesLoaded = ref(false); // the daemon has told the messages once: `messages` is then what was there, not a part of it
  const bulletins = shallowReactive(new Map<string, BulletinRow>());
  const own = useOwnTables();
  const station = useStationTables();
  const answers = useAnswers();
  const whole = useWholeTopics();
  const status = shallowRef<StatusMessage | null>(null);
  const connection = ref<Connection>("connecting");
  const lastError = shallowRef<Toast | null>(null);
  const said = useHello();
  const mismatch = shallowRef<Mismatch | null>(null); // the daemon is another protocol or serves another build of the page, and a load did not help: the page does not run against it (refuseMismatch)
  const stationAlert = shallowRef<StationAlertMessage | null>(null); // the latest alert of a station that fired: each is a message of its own, so the same words twice are two (composables/useStationAlerts.ts)
  let toasts = 0;

  const store: Store = {
    connection: (state) => (connection.value = state),
    hello: said.hello,
    status: (message) => (status.value = message),
    error: ({ cmd, key, code, params, text }) => (lastError.value = { cmd, key, code, params, text, n: ++toasts }),
    stationAlert: (message) => (stationAlert.value = message),
    replaceStations: (rows) => fill(stations, rows, stationsLoaded),
    replacePackets: (rows) => fill(packets, rows),
    replaceMessages: (rows) => fill(messages, rows, messagesLoaded),
    replaceBulletins: (rows) => fill(bulletins, rows),
    ...own.handlers,
    ...station.handlers,
    ...answers.handlers,
    ...whole.handlers,
    setStation: (key, row) => void stations.set(key, row),
    setPacket: (key, row) => void packets.set(key, row),
    setMessage: (key, row) => void messages.set(key, row),
    setBulletin: (key, row) => void bulletins.set(key, row),
    delStation: (key) => void stations.delete(key),
    delPacket: (key) => void packets.delete(key),
    delMessage: (key) => void messages.delete(key),
    delBulletin: (key) => void bulletins.delete(key),
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
  wakeWithThePage(hub);
  usePageErrorReport(hub, connection);

  return {
    stations,
    stationsLoaded,
    packets,
    messages,
    messagesLoaded,
    bulletins,
    stationPrefs: station.stationPrefs,
    stationKeys: station.stationKeys,
    ownObjects: own.ownObjects,
    ownBulletins: own.ownBulletins,
    ...whole.refs,
    status,
    connection,
    lastError,
    ...said.refs,
    mismatch,
    stationAlert,
    ...answers.refs,
    send,
  };
}

/** A phone that slept, or a network that came back: the page in front again looks at its socket at once (OH2GAX: the phone showed old messages until it was reloaded). */
function wakeWithThePage(hub: Hub): void {
  const wake = (): void => {
    if (document.visibilityState === "visible") hub.wake();
  };
  const events: [EventTarget, string][] = [
    [document, "visibilitychange"],
    [window, "online"],
    [window, "pageshow"],
  ];
  onMounted(() => events.forEach(([target, name]) => target.addEventListener(name, wake)));
  onBeforeUnmount(() => events.forEach(([target, name]) => target.removeEventListener(name, wake)));
}
