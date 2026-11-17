// The daemon as the page sees it: the topics as reactive state (the stations' own paths, RF only and alerts are `stationPrefs`), the status, the latest alert of a station that fired (`stationAlert`), the latest answer to `weather_series`, to `alert_test`, to `list_ports` and to `radio_add`, the state of the connection, and `send`. Opens the socket when the component that calls it is mounted and
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
  IgateState,
  InstallInfo,
  MapState,
  MessageRow,
  PacketRow,
  QruState,
  RadioAddedMessage,
  RadioRow,
  StationAlertMessage,
  StationRow,
  StatusMessage,
  UpdateState,
} from "@/protocol/protocol";
import { useAnswers } from "@/composables/useAnswers";
import { useOwnTables } from "@/composables/useOwnTables";
import { useScopeRows } from "@/composables/useScopeRows";
import { useStationTables } from "@/composables/useStationTables";
import { useTrafficTables } from "@/composables/useTrafficTables";
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

/** The topics that are held as one value each: those told whole (the settings, the base map, Update now, the GPS, the iGate, local info (QRU) and the general queries asked (Ask around)),
 * and the radios (useRadioTopic). */
function useWholeTopics() {
  const radios = useRadioTopic();
  const refs = {
    radios: radios.radios,
    radioAdded: radios.radioAdded,
    radioLevels: radios.radioLevels,
    config: shallowRef<ConfigValues | null>(null),
    map: shallowRef<MapState | null>(null),
    selfUpdate: shallowRef<UpdateState | null>(null),
    gps: shallowRef<GpsState | null>(null),
    igate: shallowRef<IgateState | null>(null),
    qru: shallowRef<QruState | null>(null),
    general: shallowRef<GeneralState | null>(null),
    skeds: shallowRef<SkedsState | null>(null),
  };
  const handlers: Pick<
    Store,
    | "replaceConfig"
    | "replaceMap"
    | "replaceUpdate"
    | "replaceGps"
    | "replaceIgate"
    | "replaceQru"
    | "replaceGeneral"
    | "replaceSkeds"
    | "replaceRadios"
    | "setRadio"
    | "delRadio"
    | "radioAdded"
    | "radioLevel"
  > = {
    replaceConfig: (value) => (refs.config.value = value),
    replaceMap: (value) => (refs.map.value = value),
    replaceUpdate: (value) => (refs.selfUpdate.value = value),
    replaceGps: (value) => (refs.gps.value = value),
    replaceIgate: (value) => (refs.igate.value = value),
    replaceQru: (value) => (refs.qru.value = value),
    replaceGeneral: (value) => (refs.general.value = value),
    replaceSkeds: (value) => (refs.skeds.value = value),
    ...radios.handlers,
  };
  return { refs, handlers };
}

/** The topic `radios`, by the radio's id as text: null until the daemon has told it (a daemon of the wire of before never does). A change makes a new map, as the radios are few. And the answer to this page's
 * `radio_add`, the id of the radio it made (its row comes with the topic's next patch), and the receive level of each Sound card radio this page asked for (`radio_level`), the latest by the radio's id. */
function useRadioTopic() {
  const radios = shallowRef<ReadonlyMap<string, RadioRow> | null>(null);
  const radioAdded = shallowRef<RadioAddedMessage | null>(null);
  const radioLevels = shallowRef<ReadonlyMap<number, number | null>>(new Map());
  const handlers: Pick<Store, "replaceRadios" | "setRadio" | "delRadio" | "radioAdded" | "radioLevel"> = {
    replaceRadios: (rows) => (radios.value = new Map(Object.entries(rows))),
    setRadio: (key, row) => (radios.value = new Map(radios.value ?? []).set(key, row)),
    delRadio: (key) => (radios.value = new Map([...(radios.value ?? [])].filter(([id]) => id !== key))),
    radioAdded: (message) => (radioAdded.value = message),
    radioLevel: (message) => (radioLevels.value = new Map(radioLevels.value).set(message.radio, message.level)),
  };
  return { radios, radioAdded, radioLevels, handlers };
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

/** The bulletins, and whether the daemon has told them once (`bulletins` is then what was there, not a part of it). */
function useBulletinTable() {
  return { bulletins: shallowReactive(new Map<string, BulletinRow>()), bulletinsLoaded: ref(false) };
}

export function useDaemon(url: () => string = socketUrl) {
  const stations = shallowReactive(new Map<string, StationRow>());
  const stationsLoaded = ref(false); // the daemon has told the stations once: `stations` is then what was there, not a part of it
  const packets = shallowReactive(new Map<string, PacketRow>());
  const messages = shallowReactive(new Map<string, MessageRow>());
  const messagesLoaded = ref(false); // the daemon has told the messages once: `messages` is then what was there, not a part of it
  const board = useBulletinTable();
  const [own, station, traffic] = [useOwnTables(), useStationTables(), useTrafficTables()]; // (the objects and bulletins of ours, the stations' own prefs and keys, the map's ships and aircraft)
  const answers = useAnswers();
  const whole = useWholeTopics();
  const scope = useScopeRows(packets);
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
    replaceBulletins: (rows) => fill(board.bulletins, rows, board.bulletinsLoaded),
    ...own.handlers,
    ...station.handlers,
    ...traffic.handlers,
    ...answers.handlers,
    ...whole.handlers,
    hfScopeRow: scope.hfScopeRow,
    hfScopeHistory: scope.hfScopeHistory,
    setStation: (key, row) => void stations.set(key, row),
    setPacket: (key, row) => void packets.set(key, row),
    setMessage: (key, row) => void messages.set(key, row),
    setBulletin: (key, row) => void board.bulletins.set(key, row),
    delStation: (key) => void stations.delete(key),
    delPacket: (key) => void packets.delete(key),
    delMessage: (key) => void messages.delete(key),
    delBulletin: (key) => void board.bulletins.delete(key),
  };
  // a socket that closes before it has heard anything may have been refused for want of a login: if the daemon says so, the page loads again and shows the key screen
  const refused = (): void => void probe().then((access) => access === "locked" && location.reload());
  const hub = new Hub(store, { url, onHello: (hello) => refuseMismatch(hello, mismatch, () => hub.close()), refused });

  /** Sends a command; the toast says so when the socket is not open. */
  function send(command: Parameters<Hub["send"]>[0]): boolean {
    const sent = hub.send(command);
    if (!sent) store.error({ type: "error", cmd: "", key: null, code: "not_connected", params: {}, text: "Not sent: there is no connection to NeoAPRS" }); // (the page says it in its language: error.not_connected)
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
    ...board,
    stationPrefs: station.stationPrefs,
    stationKeys: station.stationKeys,
    ownObjects: own.ownObjects,
    ownBulletins: own.ownBulletins,
    ...traffic.refs,
    ...whole.refs,
    scopeOf: scope.of,
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
