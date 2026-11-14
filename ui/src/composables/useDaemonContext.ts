// What the panes of the page share, provided once by App.vue (useAppShell) and injected by the pane that needs it: the daemon's state and `send`, the clock, the settings that apply as they are changed, the first-run guide, the panel, the
// operator's choices for each station, what the page knows of the stations heard, and the alert of this browser. A pane takes from here what is the page's as a whole, and as props what is only its own (the rows it lists, the one that is open).
import { inject, provide, type InjectionKey, type Ref } from "vue";
import type { Toast } from "@/composables/useDaemon";
import type { BrowserAlerts } from "@/composables/useBrowserAlerts";
import type { FindRadio } from "@/composables/useFindRadio";
import type { Panel } from "@/composables/usePanel";
import type { ScopeLooks } from "@/composables/useScopeLooks";
import type { Settings } from "@/composables/useSettings";
import type { SetupGuide } from "@/composables/useSetupGuide";
import type { StationKeys } from "@/composables/useStationKeys";
import type { StationPrefs } from "@/composables/useStationPrefs";
import type { Aging } from "@/lib/aging";
import type { Home } from "@/lib/mapview";
import type { RadioKind } from "@/lib/radiosides";
import type { Connection } from "@/lib/hub";
import type { ScopeRow } from "@/lib/scoperow";
import type {
  AlertResultMessage,
  Command,
  ConfigValues,
  GeneralState,
  GpsState,
  InstallInfo,
  IgateState,
  MapState,
  PacketHistoryMessage,
  PacketRow,
  PortsMessage,
  PositionHistoryMessage,
  QruState,
  ReleaseNotesMessage,
  SkedsState,
  SignalSeriesMessage,
  SpeedSeriesMessage,
  StationTrafficMessage,
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
  /** the HF radio (the Mercury modem), the same shape as `tnc`; its state is `stopped` while HF is off, null until the daemon has told */
  hf: Read<TncState | null>;
  /** whether the radios are named on the page: only where there are two, while the HF radio is on (the FM radio's channel tag is "FM" beside "HF", else "RF") */
  radiosNamed: Read<boolean>;
  /** the rows of the HF radio's waterfall (binary frames), told as they come to a pane that has asked for the scope; the function it gets back stops them */
  onScopeRow: (listener: (row: ScopeRow) => void) => () => void;
  /** who looks at the scope (the box in Settings, the monitor card over the map), counted in one place: the rows are asked for only while someone does */
  scope: ScopeLooks;
  /** the GPS receiver and the moving station's beacon; null until the daemon has told */
  gps: Read<GpsState | null>;
  /** the receive-only iGate: connected or not, what it gated; null until the daemon has told */
  igate: Read<IgateState | null>;
  /** local info (QRU): the last request sent from here and the servers that answered it; null until the daemon has told */
  qru: Read<QruState | null>;
  /** asking around: the last general query of each kind sent from here and who spoke after it; null until the daemon has told */
  general: Read<GeneralState | null>;
  /** the sked board: where it stands, the dials the project suggests and the skeds to come; null until the daemon has told */
  skeds: Read<SkedsState | null>;
  map: Read<MapState | null>;
  /** Update now: whether this copy can update itself, and how the update it is doing goes */
  selfUpdate: Read<UpdateState | null>;
  ports: Read<PortsMessage | null>;
  /** Find my radio: the button of the Settings tab, and the search it starts */
  findRadio: FindRadio;
  alertResult: Read<AlertResultMessage | null>;
  updateResult: Read<UpdateResultMessage | null>;
  /** what is new up to the version the update dialog asked for; null until it has */
  releaseNotes: Read<ReleaseNotesMessage | null>;
  lastError: Read<Toast | null>;
  connection: Read<Connection>;
  /** the version of the daemon */
  version: Read<string>;
  install: Read<InstallInfo | null>;
  /** the page is on the computer the daemon runs on (the daemon's hello says so): only there are the settings shown that name a program the daemon runs, and the alert's Test */
  local: Read<boolean>;
  /** the latest weather series for each station */
  weatherSeries: Read<ReadonlyMap<string, WeatherSeriesMessage>>;
  /** the packets heard by the hour, the answer to the statistics card's `packet_history`; null until one came */
  packetHistory: Read<PacketHistoryMessage | null>;
  /** the packets of each station by the hour, the answers to the station cards' `packet_history` with a call */
  packetHistoryByCall: Read<ReadonlyMap<string, PacketHistoryMessage>>;
  /** the speeds of each moving station, the answers to the station cards' `speed_series` */
  speedSeriesByCall: Read<ReadonlyMap<string, SpeedSeriesMessage>>;
  /** the readings of each station's signal, the answers to the station cards' `signal_series` */
  signalSeriesByCall: Read<ReadonlyMap<string, SignalSeriesMessage>>;
  /** the latest packets of each station, the answers to the station panel's `station_traffic` */
  stationTrafficByCall: Read<ReadonlyMap<string, StationTrafficMessage>>;
  /** the latest 200 packets (the topic `packets`), by id */
  packets: ReadonlyMap<string, PacketRow>;
  /** where the stations were over the span the map's replay asked for (`position_history`); null until one came */
  positionHistory: Read<PositionHistoryMessage | null>;
  /** a radio link is up (either one: what a message to every radio, the beacon, asks) */
  connected: Read<boolean>;
  /** the link of one radio is up: what a message asks that goes over the radio it takes (lib/radiosides.ts `radioFor`) */
  connectedOn: (radio: RadioKind) => boolean;
  /** transmitting is switched off (station/transmit false): RX only */
  receiveOnly: Read<boolean>;
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
  /** encrypted messages: the stations' keys, our own, the switch and the commands */
  keys: StationKeys;
  settings: Settings;
  guide: SetupGuide;
  panel: Panel;
  alerts: BrowserAlerts;
  /** A word in the toast that is no error ("up to date (0.7.0)", "Sound played"): the result of a button goes there, not beside the button, so that nothing moves */
  say: (text: string) => void;
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
