// The daemon as the page sees it: the topics as reactive state, the status, the latest answers,
// the connection state and `send`. Opens the socket on mount and closes it on unmount.
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
import { useLayerTables } from "@/composables/useLayerThings";
import { useOwnTables } from "@/composables/useOwnTables";
import { useScopeRows } from "@/composables/useScopeRows";
import { useStationTables } from "@/composables/useStationTables";
import { usePageErrorReport } from "@/composables/usePageErrorReport";
import { probe } from "@/lib/access";
import { fillTable, Hub, type Connection, type Store } from "@/lib/hub";
import { describeMismatch, reloadForDaemon, type Mismatch } from "@/lib/reload";

export function socketUrl(): string {
  const url = new URL("ws", document.baseURI);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** An `error` of the daemon or of the page itself (`cmd` empty, `code` `not_connected`). */
export interface Toast extends Omit<ErrorMessage, "type"> {
  /** Counts up, so that the same text twice is two toasts. */
  n: number;
}

function fill<T>(into: Map<string, T>, rows: Record<string, T>, done?: Ref<boolean>): void {
  fillTable(into, rows);
  if (done) done.value = true;
}

/** The topics held as one value each: those told whole, the radios and the layer tables. */
function useWholeTopics() {
  const radios = useRadioTopic();
  const layers = useLayerTables();
  const refs = {
    layerTables: { told: layers.told, forget: layers.forget },
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
    | "layerThings"
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
    ...layers.handlers,
  };
  return { refs, handlers };
}

/**
 * The topic `radios` by radio id as text, null until the daemon has sent it; a change makes a new
 * map. Also the id from `radio_add` and the receive level of each Sound card radio (`radio_level`).
 */
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

/**
 * A hello of a daemon the page does not go with, after the reload: set the notice and close the
 * socket for good.
 */
function refuseMismatch(hello: HelloMessage, mismatch: Ref<Mismatch | null>, close: () => void): void {
  if (reloadForDaemon(hello) !== "stale") return;
  mismatch.value = describeMismatch(hello);
  close();
}

/**
 * What the daemon's hello says: its version, how it was installed, and whether this page is on its
 * computer.
 */
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

function useBulletinTable() {
  return { bulletins: shallowReactive(new Map<string, BulletinRow>()), bulletinsLoaded: ref(false) };
}

export function useDaemon(url: () => string = socketUrl) {
  const stations = shallowReactive(new Map<string, StationRow>());
  const stationsLoaded = ref(false);
  const packets = shallowReactive(new Map<string, PacketRow>());
  const messages = shallowReactive(new Map<string, MessageRow>());
  const messagesLoaded = ref(false);
  const board = useBulletinTable();
  const own = useOwnTables();
  const station = useStationTables();
  const answers = useAnswers();
  const whole = useWholeTopics();
  const scope = useScopeRows(packets);
  const status = shallowRef<StatusMessage | null>(null);
  const connection = ref<Connection>("connecting");
  const lastError = shallowRef<Toast | null>(null);
  const said = useHello();
  // The daemon speaks another protocol or serves another build and a reload did not help.
  const mismatch = shallowRef<Mismatch | null>(null);
  // Each alert is a message of its own, so the same words twice are two alerts.
  const stationAlert = shallowRef<StationAlertMessage | null>(null);
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
  // A socket that closes before hearing anything may have been refused for want of a login: if
  // the daemon says so, reload and show the key screen.
  const refused = (): void => void probe().then((access) => access === "locked" && location.reload());
  const hub = new Hub(store, { url, onHello: (hello) => refuseMismatch(hello, mismatch, () => hub.close()), refused });

  function send(command: Parameters<Hub["send"]>[0]): boolean {
    const sent = hub.send(command);
    if (!sent) store.error({ type: "error", cmd: "", key: null, code: "not_connected", params: {}, text: "Not sent: there is no connection to NeoAPRS" });
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

/**
 * A phone that slept or a network that came back: check the socket at once when the page is in
 * front.
 */
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
