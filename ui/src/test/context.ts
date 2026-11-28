// The page's context for a test that mounts a pane on its own: every part a pane may inject is
// there, quiet, and a test gives the parts it cares about (a value, or a ref it changes later).
// `send` records the commands, `say` the toast; `withDaemon(context)` is the `global` option of a
// mount.
import { computed, isRef, nextTick, shallowReactive, shallowRef, watch, type Ref } from "vue";
import { vi, type Mock } from "vitest";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useChat } from "@/composables/useChat";
import { useFindRadio } from "@/composables/useFindRadio";
import { useLayerTables, useLayerThings, type TrafficParts } from "@/composables/useLayerThings";
import { useSatelliteStore, useSatellites } from "@/composables/useSatellites";
import { usePanel } from "@/composables/usePanel";
import { useIgateLook } from "@/composables/useIgateLook";
import { useRadioAsks } from "@/composables/useRadioAsks";
import { useScopeLooks, type ScopeLooks } from "@/composables/useScopeLooks";
import { scopeMemories } from "@/composables/useScopeRows";
import { pageVisible } from "@/composables/useVisible";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { useStationKeys } from "@/composables/useStationKeys";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { DEFAULT_TIMEOUT_MIN } from "@/lib/aging";
import { listensOnly } from "@/lib/radios";
import type { Connection } from "@/lib/hub";
import type {
  Command,
  PacketRow,
  RadioRow,
  RadioSearchMessage,
  SavedMessage,
  StationKey,
  StationPref,
  StationRow,
} from "@/protocol/protocol";
import { NOW, configValues, radiosOf, radiosTopic } from "@/test/fixtures";

export type FakeDaemon = {
  [K in keyof DaemonContext]: DaemonContext[K] extends Readonly<Ref<infer T>> ? Ref<T> : DaemonContext[K];
} & {
  send: Mock<(command: Command) => boolean>;
  say: Mock<(text: string) => void>;
  layerTables: ReturnType<typeof useLayerTables>;
  satelliteStore: ReturnType<typeof useSatelliteStore>;
  replayOpen: Ref<boolean>;
};
export type Given = {
  [K in keyof DaemonContext]?: DaemonContext[K] extends Readonly<Ref<infer T>> ? T | Ref<T> : DaemonContext[K];
};

/** Who looks at the scope: the one a test gave, else the page's own counting over `radios`. */
function scopeOf(
  over: Given,
  send: FakeDaemon["send"],
  connection: Ref<Connection>,
  radios: Ref<RadioTopic>,
): ScopeLooks {
  return over.scope ?? useScopeLooks(send, connection, pageVisible(), { radios });
}

/** The lines put on APRS-IS and who looks at them: those a test gave, else the page's own counting. */
function igateOf(over: Given, send: FakeDaemon["send"], connection: Ref<Connection>) {
  const sent = over.igateSent;
  return {
    igateSent: isRef(sent) ? sent : shallowRef(sent ?? []),
    igateLook: over.igateLook ?? useIgateLook(send, connection, pageVisible()),
  };
}

type RadioTopic = ReadonlyMap<string, RadioRow> | null;

/**
 * The aircraft and ships: the one a test gave, else the page's own with the tables a test sends.
 */
function trafficOf(over: Given, parts: Pick<TrafficParts, "send" | "connection" | "map" | "now">) {
  const layerTables = useLayerTables(() => parts.now.value);
  const replayOpen = shallowRef(false);
  const traffic =
    over.traffic ?? useLayerThings({ ...parts, visible: pageVisible(), replay: replayOpen, store: layerTables });
  const satelliteStore = useSatelliteStore();
  const satellites =
    over.satellites ?? useSatellites({ ...parts, visible: pageVisible(), replay: replayOpen, store: satelliteStore });
  return { layerTables, satelliteStore, replayOpen, traffic, satellites };
}

/** The topic `radios`: the one a test gave, else radio 1 alone, connected while the context is. */
function radiosPart(given: RadioTopic | Ref<RadioTopic> | undefined, connected: Ref<boolean>): Ref<RadioTopic> {
  if (isRef(given)) return given;
  const told = shallowRef<RadioTopic | "default">(given === undefined ? "default" : given);
  return computed({
    get: () => (told.value === "default" ? radiosOf(connected.value) : told.value),
    set: (value: RadioTopic) => (told.value = value),
  });
}

/** A part of the context as a test gave it (a value or a ref), else its fallback. */
const part = <T>(given: T | Ref<T> | undefined, fallback: T): Ref<T> =>
  isRef(given) ? given : shallowRef(given === undefined ? fallback : given);

/** The chat's topics, given or empty, and the chat the shell would make of them. */
function chatOf(
  over: Given,
  parts: Pick<DaemonContext, "lastError" | "connection" | "send">,
  panel: DaemonContext["panel"],
) {
  const topics = {
    chatState: part(over.chatState, null),
    chatLines: part(over.chatLines, null),
    chatFresh: part(over.chatFresh, null),
  };
  return { ...topics, chat: over.chat ?? useChat({ ...topics, ...parts }, panel, () => undefined) };
}

export function fakeDaemon(over: Given = {}): FakeDaemon {
  const send = vi.fn((_command: Command) => true);
  const config = part(over.config, configValues());
  const lastError = part(over.lastError, null);
  const ports = part(over.ports, null);
  const portsByRadio =
    over.portsByRadio === undefined
      ? computed(() => new Map(ports.value?.radio == null ? [] : [[ports.value.radio, ports.value]]))
      : part(over.portsByRadio, new Map());
  const map = part(over.map, null);
  const status = part(over.status, null);
  const connected = part(over.connected, true);
  const sender = (over.send as typeof send | undefined) ?? send;
  const connection = part(over.connection, "open" as const);
  // The components' tests read the commands sent without the number of a save (the queue's own tests
  // have it) and let the daemon accept a save by telling the settings.
  const saved = shallowRef<SavedMessage | null>(null);
  let out: number | null = null;
  const unnumbered = (command: Command): boolean => {
    if (command.cmd !== "set_config") return sender(command);
    out = command.id ?? null;
    return sender({ cmd: command.cmd, values: command.values });
  };
  watch(config, () => {
    if (out !== null) saved.value = { type: "saved", id: out };
    out = null;
  });
  const settings = over.settings ?? useSettings(config, lastError, unnumbered, { saved, connection });
  const radios = radiosPart(over.radios, connected);
  const now = part(over.now, NOW);
  const layers = trafficOf(over, { send: sender, connection, map, now });
  const context = {
    ...layers,
    send: sender,
    say: over.say ?? vi.fn((_text: string) => undefined),
    config,
    status,
    scopeOf: over.scopeOf ?? scopeMemories().of,
    radios,
    radioAdded: part(over.radioAdded, null),
    gps: part(over.gps, null),
    igate: part(over.igate, null),
    ...igateOf(over, sender, connection),
    qru: part(over.qru, null),
    general: part(over.general, null),
    skeds: part(over.skeds, null),
    map,
    selfUpdate: part(over.selfUpdate, null),
    ports,
    portsByRadio,
    findRadio:
      over.findRadio ??
      useFindRadio(
        shallowRef<RadioSearchMessage | null>(null),
        lastError,
        shallowRef<Connection>("open"),
        sender,
        settings,
        config,
        () => undefined,
      ),
    alertResult: part(over.alertResult, null),
    updateResult: part(over.updateResult, null),
    releaseNotes: part(over.releaseNotes, null),
    lastError,
    connection,
    scope: scopeOf(over, sender, connection, radios),
    level: over.level ?? useRadioAsks("radio_level", sender, connection, pageVisible(), () => null),
    radioLevels: part(over.radioLevels, new Map()),
    version: part(over.version, ""),
    install: part(over.install, null),
    local: part(over.local, true),
    weatherSeries: part(over.weatherSeries, new Map()),
    packetHistory: part(over.packetHistory, null),
    packetStats: part(over.packetStats, null),
    packetHistoryByCall: part(over.packetHistoryByCall, new Map()),
    speedSeriesByCall: part(over.speedSeriesByCall, new Map()),
    signalSeriesByCall: part(over.signalSeriesByCall, new Map()),
    stationTrafficByCall: part(over.stationTrafficByCall, new Map()),
    packets: over.packets ?? shallowReactive(new Map<string, PacketRow>()),
    positionHistory: part(over.positionHistory, null),
    connected,
    receiveOnly:
      over.receiveOnly === undefined
        ? computed(
            () =>
              config.value?.values["station/transmit"] === "false" ||
              settings.expected("station/transmit") === "false" ||
              listensOnly(radios.value),
          )
        : part(over.receiveOnly, false),
    now,
    dark: part(over.dark, false),
    call: part(over.call, "OH2GBA"),
    home: part(over.home, null),
    fallbackPath: part(over.fallbackPath, ""),
    stations: part(over.stations, new Map<string, StationRow>()),
    aging: part(over.aging, { defaultMin: DEFAULT_TIMEOUT_MIN }),
    heardPaths: part(over.heardPaths, new Map<string, string | null>()),
    heardDirect: part(over.heardDirect, new Set<string>()),
    prefs: over.prefs ?? useStationPrefs(shallowReactive(new Map<string, StationPref>()), sender),
    keys: over.keys ?? useStationKeys(shallowReactive(new Map<string, StationKey>()), status, sender),
    settings,
    guide: over.guide ?? useSetupGuide(config, lastError, unnumbered, radios, connection, saved),
    panel: over.panel ?? usePanel(),
  };
  Object.assign(context, chatOf(over, { lastError, connection, send: sender }, context.panel));
  // The browser alert listens to the window: it is made when a pane asks for it.
  let alerts = over.alerts;
  Object.defineProperty(context, "alerts", {
    enumerable: true,
    get: () => (alerts ??= useBrowserAlerts(() => undefined)),
  });
  return context as unknown as FakeDaemon;
}

export function withDaemon(context: DaemonContext = fakeDaemon()): { provide: Record<symbol, DaemonContext> } {
  return { provide: { [DAEMON_KEY as symbol]: context } };
}

export function ofRadios(...rows: RadioRow[]): Given {
  return { radios: radiosTopic(...rows), config: configValues() };
}

/** What the daemon sends after the pane is up: those parts of the context change. */
export async function tell(daemon: FakeDaemon, parts: Given): Promise<void> {
  for (const [key, value] of Object.entries(parts)) (Reflect.get(daemon, key) as Ref<unknown>).value = value;
  await nextTick();
}
