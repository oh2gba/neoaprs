// The page's context (composables/useDaemonContext.ts) for a test that mounts a pane on its own: every part a pane may inject is there, quiet (a connected radio, the settings of the fixtures, no stations), and a test gives the parts it cares about
// (a plain value, or a ref that it changes later) and reads `send`, which records the commands, and `say`, which records what the page would say in its toast. `withDaemon(context)` is the `global` option of a mount.
import { computed, isRef, nextTick, shallowReactive, shallowRef, type Ref } from "vue";
import { vi, type Mock } from "vitest";
import { DAEMON_KEY, type DaemonContext } from "@/composables/useDaemonContext";
import { useBrowserAlerts } from "@/composables/useBrowserAlerts";
import { useFindRadio } from "@/composables/useFindRadio";
import { usePanel } from "@/composables/usePanel";
import { useSettings } from "@/composables/useSettings";
import { useSetupGuide } from "@/composables/useSetupGuide";
import { useStationPrefs } from "@/composables/useStationPrefs";
import { DEFAULT_TIMEOUT_MIN } from "@/lib/aging";
import type { Connection } from "@/lib/hub";
import type { Command, RadioSearchMessage, StationPref, StationRow } from "@/protocol/protocol";
import { NOW, configValues } from "@/test/fixtures";

/** The context as a test changes it: the parts that are refs are writable. */
export type FakeDaemon = { [K in keyof DaemonContext]: DaemonContext[K] extends Readonly<Ref<infer T>> ? Ref<T> : DaemonContext[K] } & {
  send: Mock<(command: Command) => boolean>;
  say: Mock<(text: string) => void>;
};
/** What a test gives: a plain value, or a ref it changes later. */
export type Given = { [K in keyof DaemonContext]?: DaemonContext[K] extends Readonly<Ref<infer T>> ? T | Ref<T> : DaemonContext[K] };

/** The context a test mounts a pane in; a part given as a value is put in a ref. */
export function fakeDaemon(over: Given = {}): FakeDaemon {
  const send = vi.fn((_command: Command) => true);
  const part = <T>(given: T | Ref<T> | undefined, fallback: T): Ref<T> => (isRef(given) ? given : shallowRef(given === undefined ? fallback : given));
  const config = part(over.config, configValues());
  const lastError = part(over.lastError, null);
  const ports = part(over.ports, null);
  const map = part(over.map, null);
  const sender = (over.send as typeof send | undefined) ?? send;
  const settings = over.settings ?? useSettings(config, lastError, sender);
  const context = {
    send: sender,
    say: over.say ?? vi.fn((_text: string) => undefined),
    config,
    status: part(over.status, null),
    tnc: part(over.tnc, null),
    gps: part(over.gps, null),
    igate: part(over.igate, null),
    map,
    selfUpdate: part(over.selfUpdate, null),
    ports,
    findRadio:
      over.findRadio ??
      useFindRadio(shallowRef<RadioSearchMessage | null>(null), lastError, shallowRef<Connection>("open"), sender, settings, config, () => undefined),
    alertResult: part(over.alertResult, null),
    updateResult: part(over.updateResult, null),
    lastError,
    connection: part(over.connection, "open" as const),
    version: part(over.version, ""),
    install: part(over.install, null),
    weatherSeries: part(over.weatherSeries, new Map()),
    connected: part(over.connected, true),
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
    settings,
    guide: over.guide ?? useSetupGuide(config, lastError, ports, sender, map),
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

/** What the daemon tells after the pane is up: those parts of the context change, and the pane follows. */
export async function tell(daemon: FakeDaemon, parts: Given): Promise<void> {
  for (const [key, value] of Object.entries(parts)) (Reflect.get(daemon, key) as Ref<unknown>).value = value;
  await nextTick();
}
