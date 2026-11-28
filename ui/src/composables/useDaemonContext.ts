// What the panes of the page share, provided once by App.vue (useAppShell) and injected where
// needed: the daemon's state and `send`, the clock, settings, the first-run guide, the panel, the
// operator's choices per station, what the page knows of the heard stations, and this browser's
// alert. A pane takes page-wide state from here and its own rows as props.
import type { ChatModel } from "@/composables/useChat";
import { inject, provide, type InjectionKey, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import type { FindRadio } from "@/composables/useFindRadio";
import type { IgateLook } from "@/composables/useIgateLook";
import type { LayerTraffic } from "@/composables/useLayerThings";
import type { Panel } from "@/composables/usePanel";
import type { RadioAsks } from "@/composables/useRadioAsks";
import type { SatelliteLayer } from "@/composables/useSatellites";
import type { ScopeLooks } from "@/composables/useScopeLooks";
import type { Settings } from "@/composables/useSettings";
import type { SetupGuide } from "@/composables/useSetupGuide";
import type { StationKeys } from "@/composables/useStationKeys";
import type { StationPrefs } from "@/composables/useStationPrefs";
import type { Aging } from "@/lib/aging";
import type { Home } from "@/lib/mapview";
import type { RadioId } from "@/lib/radios";
import type { Connection } from "@/lib/hub";
import type { ScopeMemory } from "@/lib/scopememory";
import type {
  AlertResultMessage,
  Command,
  CallRoute,
  ConfigValues,
  GeneralState,
  GpsState,
  InstallInfo,
  IgateSentLine,
  IgateState,
  MapState,
  PacketHistoryMessage,
  PacketStatsMessage,
  PacketRow,
  PortsMessage,
  PositionHistoryMessage,
  QruState,
  RadioAddedMessage,
  RadioRow,
  ReleaseNotesMessage,
  SkedsState,
  ChatFreshMessage,
  ChatLineRow,
  ChatState,
  SignalSeriesMessage,
  SpeedSeriesMessage,
  StationTrafficMessage,
  StationRow,
  StatusMessage,
  UpdateResultMessage,
  UpdateState,
  WeatherSeriesMessage,
} from "@/protocol/protocol";

type Read<T> = Readonly<Ref<T>>;

export interface DaemonContext {
  send: (command: Command) => boolean;
  config: Read<ConfigValues | null>;
  status: Read<StatusMessage | null>;
  radios: Read<ReadonlyMap<string, RadioRow> | null>;
  radioAdded: Read<RadioAddedMessage | null>;
  scopeOf: (radio: RadioId) => ScopeMemory;
  scope: ScopeLooks;
  level: RadioAsks;
  radioLevels: Read<ReadonlyMap<RadioId, number | null>>;
  traffic: LayerTraffic;
  satellites: SatelliteLayer;
  gps: Read<GpsState | null>;
  igate: Read<IgateState | null>;
  /** The lines put on APRS-IS, oldest first, while the page looks (`igate`'s box is open). */
  igateSent: Read<readonly IgateSentLine[]>;
  igateLook: IgateLook;
  qru: Read<QruState | null>;
  general: Read<GeneralState | null>;
  skeds: Read<SkedsState | null>;
  chatState: Read<ChatState | null>;
  chatLines: Read<ReadonlyMap<string, ChatLineRow> | null>;
  chatFresh: Read<ChatFreshMessage | null>;
  /** The chat of the HF tests tab, held by the shell so that a line being written survives a change of tab. */
  chat: ChatModel;
  map: Read<MapState | null>;
  selfUpdate: Read<UpdateState | null>;
  ports: Read<PortsMessage | null>;
  portsByRadio: Read<ReadonlyMap<number, PortsMessage>>;
  findRadio: FindRadio;
  alertResult: Read<AlertResultMessage | null>;
  updateResult: Read<UpdateResultMessage | null>;
  releaseNotes: Read<ReleaseNotesMessage | null>;
  lastError: Read<Toast | null>;
  connection: Read<Connection>;
  version: Read<string>;
  install: Read<InstallInfo | null>;
  /**
   * The page is on the daemon's computer: only then are settings shown that name a program it runs.
   */
  local: Read<boolean>;
  weatherSeries: Read<ReadonlyMap<string, WeatherSeriesMessage>>;
  packetHistory: Read<PacketHistoryMessage | null>;
  packetStats: Read<PacketStatsMessage | null>;
  packetHistoryByCall: Read<ReadonlyMap<string, PacketHistoryMessage>>;
  speedSeriesByCall: Read<ReadonlyMap<string, SpeedSeriesMessage>>;
  signalSeriesByCall: Read<ReadonlyMap<string, SignalSeriesMessage>>;
  stationTrafficByCall: Read<ReadonlyMap<string, StationTrafficMessage>>;
  /** The latest 200 packets (topic `packets`), by id. */
  packets: ReadonlyMap<string, PacketRow>;
  positionHistory: Read<PositionHistoryMessage | null>;
  connected: Read<boolean>;
  receiveOnly: Read<boolean>;
  now: Read<number>;
  dark: Read<boolean>;
  call: Read<string | null>;
  home: Read<Home | null>;
  fallbackPath: Read<string>;
  stations: Read<ReadonlyMap<string, StationRow>>;
  /** How messages go to each call the stations do not hold (topic `call_routes`), by call. */
  callRoutes: Read<ReadonlyMap<string, CallRoute>>;
  aging: Read<Aging>;
  heardPaths: Read<ReadonlyMap<string, string | null>>;
  heardDirect: Read<ReadonlySet<string>>;
  prefs: StationPrefs;
  keys: StationKeys;
  settings: Settings;
  guide: SetupGuide;
  panel: Panel;
  alerts: BrowserAlerts;
  /**
   * A toast word that is no error ("Sound played"); the result of a button goes there so nothing
   * moves.
   */
  say: (text: string) => void;
}

const KEY: InjectionKey<DaemonContext> = Symbol("daemon");

export function provideDaemon(context: DaemonContext): void {
  provide(KEY, context);
}

/** What the page shares; a pane mounted without it is an error. */
export function useDaemonContext(): DaemonContext {
  const context = inject(KEY, null);
  if (context === null) throw new Error("the page's context is not provided (provideDaemon)");
  return context;
}

export { KEY as DAEMON_KEY };
