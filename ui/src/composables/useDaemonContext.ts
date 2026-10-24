// What the panes of the page share, provided once by App.vue (useAppShell) and injected by the pane that needs it: the daemon's state and `send`, the clock, the settings that apply as they are changed, the first-run guide, the panel, the
// operator's choices for each station, what the page knows of the stations heard, and the alert of this browser. A pane takes from here what is the page's as a whole, and as props what is only its own (the rows it lists, the one that is open).
import { inject, provide, type InjectionKey, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import type { FindRadio } from "@/composables/useFindRadio";
import type { Panel } from "@/composables/usePanel";
import type { Settings } from "@/composables/useSettings";
import type { SetupGuide } from "@/composables/useSetupGuide";
import type { StationPrefs } from "@/composables/useStationPrefs";
import type { Aging } from "@/lib/aging";
import type { Home } from "@/lib/mapview";
import type { Connection } from "@/lib/hub";
import type {
  AlertResultMessage,
  Command,
  ConfigValues,
  InstallInfo,
  MapState,
  PortsMessage,
  StationRow,
  StatusMessage,
  TncState,
  UpdateResultMessage,
  UpdateState,
  WeatherSeriesMessage,
} from "@/protocol/protocol";

type Read<T> = Readonly<Ref<T>>;

export interface DaemonContext {
  /** Sends a command; the toast says so when the socket is not open. */
  send: (command: Command) => boolean;
  config: Read<ConfigValues | null>;
  status: Read<StatusMessage | null>;
  tnc: Read<TncState | null>;
  map: Read<MapState | null>;
  /** Update now: whether this copy can update itself, and how the update it is doing goes */
  selfUpdate: Read<UpdateState | null>;
  ports: Read<PortsMessage | null>;
  /** Find my radio: the button of the Settings tab, and the search it starts */
  findRadio: FindRadio;
  alertResult: Read<AlertResultMessage | null>;
  updateResult: Read<UpdateResultMessage | null>;
  lastError: Read<Toast | null>;
  connection: Read<Connection>;
  /** the version of the daemon */
  version: Read<string>;
  install: Read<InstallInfo | null>;
  /** the latest weather series for each station */
  weatherSeries: Read<ReadonlyMap<string, WeatherSeriesMessage>>;
  /** the radio link is up */
  connected: Read<boolean>;
  /** the clock the ages are held against */
  now: Read<number>;
  dark: Read<boolean>;
  /** our call from the settings, else the one of the status; null while neither has said */
  call: Read<string | null>;
  /** where our station is; null while there is no place */
  home: Read<Home | null>;
  /** the path of the setting beacon/path, which a station without one of its own has */
  fallbackPath: Read<string>;
  /** the stations heard, ours with the symbol of the settings */
  stations: Read<ReadonlyMap<string, StationRow>>;
  aging: Read<Aging>;
  /** the path to send by that the daemon suggests, for each station that has one */
  heardPaths: Read<ReadonlyMap<string, string | null>>;
  /** the stations heard direct */
  heardDirect: Read<ReadonlySet<string>>;
  prefs: StationPrefs;
  settings: Settings;
  guide: SetupGuide;
  panel: Panel;
  alerts: BrowserAlerts;
}

const KEY: InjectionKey<DaemonContext> = Symbol("daemon");

/** App.vue, once. */
export function provideDaemon(context: DaemonContext): void {
  provide(KEY, context);
}

/** What the page shares; a pane mounted without it (a test that gave none) is an error. */
export function useDaemonContext(): DaemonContext {
  const context = inject(KEY, null);
  if (context === null) throw new Error("the page's context is not provided (provideDaemon)");
  return context;
}

export { KEY as DAEMON_KEY };
