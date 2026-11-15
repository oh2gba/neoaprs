// The page's context (composables/useDaemonContext.ts) for a test that mounts a pane on its own: every part a pane may inject is there, quiet (a connected radio, the settings of the fixtures, no stations, the topic `radios` as the daemon tells it for those settings), and a test gives the parts it cares about
// (a plain value, or a ref that it changes later) and reads `send`, which records the commands, and `say`, which records what the page would say in its toast. `withDaemon(context)` is the `global` option of a mount.
import { computed, isRef, nextTick, shallowReactive, shallowRef, type Ref } from "vue";
import { vi, type Mock } from "vitest";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useFindRadio } from "@/composables/useFindRadio";
import { usePanel } from "@/composables/usePanel";
import { useScopeLooks, type ScopeLooks, type ScopeParts } from "@/composables/useScopeLooks";
import { scopeMemories } from "@/composables/useScopeRows";
import { pageVisible } from "@/composables/useVisible";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { useStationKeys } from "@/composables/useStationKeys";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { DEFAULT_TIMEOUT_MIN } from "@/lib/aging";
import { enabledRadios, pageRadios } from "@/lib/radios";
import { pageRows, type RadioKind } from "@/lib/radiosides";
import { ScopeMemory } from "@/lib/scopememory";
import type { Connection } from "@/lib/hub";
import type { Command, ConfigValues, PacketRow, RadioRow, RadioSearchMessage, StationKey, StationPref, StationRow, TncState } from "@/protocol/protocol";
import { NOW, configValues, radiosOf, radiosTopic } from "@/test/fixtures";

/** The context as a test changes it: the parts that are refs are writable. */
export type FakeDaemon = { [K in keyof DaemonContext]: DaemonContext[K] extends Readonly<Ref<infer T>> ? Ref<T> : DaemonContext[K] } & {
  send: Mock<(command: Command) => boolean>;
  say: Mock<(text: string) => void>;
};
/** What a test gives: a plain value, or a ref it changes later. */
export type Given = { [K in keyof DaemonContext]?: DaemonContext[K] extends Readonly<Ref<infer T>> ? T | Ref<T> : DaemonContext[K] };

/** Who looks at the scope: the one a test gave, else the page's own counting over the given parts. */
function scopeOf(over: Given, send: FakeDaemon["send"], hf: Ref<TncState | null>, connection: Ref<Connection>, parts: ScopeParts): ScopeLooks {
  return over.scope ?? useScopeLooks(send, hf, connection, pageVisible(), parts);
}

type RadioTopic = ReadonlyMap<string, RadioRow> | null;

/** The topic `radios`: the one a test gave, else as this daemon tells it for the settings (radio 1 the FM radio, radio 2 the HF radio), following them until a test tells its own (null: a daemon of the wire of
 * before). */
function radiosPart(
  given: RadioTopic | Ref<RadioTopic> | undefined,
  config: Ref<ConfigValues | null>,
  connected: Ref<boolean>,
  tnc: Ref<TncState | null>,
  hf: Ref<TncState | null>,
): Ref<RadioTopic> {
  if (isRef(given)) return given;
  const told = shallowRef<RadioTopic | "settings">(given === undefined ? "settings" : given);
  return computed({
    get: () => (told.value === "settings" ? radiosOf(config.value?.values ?? {}, connected.value, tnc.value, hf.value) : told.value),
    set: (value: RadioTopic) => (told.value = value),
  });
}

/** Whether the radios are named: the one a test gave, else as the page has it, more than one radio on. */
function namedPart(
  given: Given["radiosNamed"],
  radios: Ref<RadioTopic>,
  config: Ref<ConfigValues | null>,
  tnc: Ref<TncState | null>,
  hf: Ref<TncState | null>,
): Readonly<Ref<boolean>> {
  if (given !== undefined) return isRef(given) ? given : shallowRef(given);
  return computed(() => enabledRadios(pageRadios(pageRows(radios.value, config.value, tnc.value, hf.value), config.value)).length > 1);
}

/** The context a test mounts a pane in; a part given as a value is put in a ref. */
export function fakeDaemon(over: Given = {}): FakeDaemon {
  const send = vi.fn((_command: Command) => true);
  const part = <T>(given: T | Ref<T> | undefined, fallback: T): Ref<T> => (isRef(given) ? given : shallowRef(given === undefined ? fallback : given));
  const config = part(over.config, configValues());
  const lastError = part(over.lastError, null);
  const ports = part(over.ports, null);
  const map = part(over.map, null);
  const status = part(over.status, null);
  const connected = part(over.connected, true);
  const sender = (over.send as typeof send | undefined) ?? send;
  const settings = over.settings ?? useSettings(config, lastError, sender);
  const tnc = part(over.tnc, null);
  const hf = part(over.hf, null);
  const connection = part(over.connection, "open" as const);
  const radios = radiosPart(over.radios, config, connected, tnc, hf);
  const scopeRows = over.scopeRows ?? new ScopeMemory();
  const context = {
    send: sender,
    say: over.say ?? vi.fn((_text: string) => undefined),
    config,
    status,
    tnc,
    hf,
    scopeRows,
    scopeOf: over.scopeOf ?? scopeMemories(scopeRows).of,
    radios,
    radioAdded: part(over.radioAdded, null),
    radiosNamed: namedPart(over.radiosNamed, radios, config, tnc, hf),
    gps: part(over.gps, null),
    igate: part(over.igate, null),
    qru: part(over.qru, null),
    general: part(over.general, null),
    skeds: part(over.skeds, null),
    map,
    selfUpdate: part(over.selfUpdate, null),
    ports,
    findRadio:
      over.findRadio ??
      useFindRadio(shallowRef<RadioSearchMessage | null>(null), lastError, shallowRef<Connection>("open"), sender, settings, config, () => undefined),
    alertResult: part(over.alertResult, null),
    updateResult: part(over.updateResult, null),
    releaseNotes: part(over.releaseNotes, null),
    lastError,
    connection,
    scope: scopeOf(over, sender, hf, connection, { radios }),
    version: part(over.version, ""),
    install: part(over.install, null),
    local: part(over.local, true),
    weatherSeries: part(over.weatherSeries, new Map()),
    packetHistory: part(over.packetHistory, null),
    packetHistoryByCall: part(over.packetHistoryByCall, new Map()),
    speedSeriesByCall: part(over.speedSeriesByCall, new Map()),
    signalSeriesByCall: part(over.signalSeriesByCall, new Map()),
    stationTrafficByCall: part(over.stationTrafficByCall, new Map()),
    packets: over.packets ?? shallowReactive(new Map<string, PacketRow>()),
    positionHistory: part(over.positionHistory, null),
    connected,
    connectedOn: over.connectedOn ?? ((_radio: RadioKind) => connected.value),
    receiveOnly: over.receiveOnly === undefined ? computed(() => config.value?.values["station/transmit"] === "false") : part(over.receiveOnly, false),
    now: part(over.now, NOW),
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
    guide: over.guide ?? useSetupGuide(config, lastError, sender),
    panel: over.panel ?? usePanel(),
  };
  // the alert of the browser listens to the window: it is made when a pane asks for it
  let alerts = over.alerts;
  Object.defineProperty(context, "alerts", { enumerable: true, get: () => (alerts ??= useBrowserAlerts(() => undefined)) });
  return context as unknown as FakeDaemon;
}

/** The `global` option of a mount: the context provided to the pane. */
export function withDaemon(context: DaemonContext = fakeDaemon()): { provide: Record<symbol, DaemonContext> } {
  return { provide: { [DAEMON_KEY as symbol]: context } };
}

/** A station of these radios as the daemon tells them once the settings of before are gone: the topic, and settings without the Enable of before (lib/radiosides.ts takes the Enable of radios 1 and 2 from those while they are there). */
export function ofRadios(...rows: RadioRow[]): Given {
  const config = configValues();
  const values = Object.fromEntries(Object.entries(config.values).filter(([key]) => key !== "fm/enabled" && key !== "hf/enabled"));
  return { radios: radiosTopic(...rows), config: { ...config, values } };
}

/** What the daemon tells after the pane is up: those parts of the context change, and the pane follows. */
export async function tell(daemon: FakeDaemon, parts: Given): Promise<void> {
  for (const [key, value] of Object.entries(parts)) (Reflect.get(daemon, key) as Ref<unknown>).value = value;
  await nextTick();
}
