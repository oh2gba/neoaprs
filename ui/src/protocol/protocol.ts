// The types of the wire protocol between the daemon and the page, written from the models of neoaprs/web/protocol.py by scripts/gen-protocol.py: never edited by hand.
// `Command` is what the page sends (tagged by `cmd`), `Message` what the daemon sends (tagged by `type`), `TopicValues` the value of each topic the page follows.

export type Command = PingCommand | AskStatusCommand | CheckUpdateCommand | ReleaseNotesCommand | SubscribeCommand | UnsubscribeCommand | ForgetStationCommand | ForgetAllStationsCommand | ListPortsCommand | FindRadioCommand | FindRadioCancelCommand | SetConfigCommand | BeaconNowCommand | StatusNowCommand | SendMessageCommand | QueryStationCommand | AskQruCommand | GeneralQueryCommand | MessageRetryCommand | MessageCancelCommand | MessageDeleteCommand | ConversationDeleteCommand | OverheardDeleteCommand | SetStationPathCommand | ClearStationPathCommand | SetStationRfOnlyCommand | WeatherSeriesCommand | PacketHistoryCommand | PositionHistoryCommand | SpeedSeriesCommand | AlertTestCommand | BulletinDeleteCommand | ObjectSetCommand | ObjectKillCommand | BulletinPostCommand | BulletinUnpostCommand | MapEstimateCommand | MapFetchCommand | MapWantedCommand | MapCancelCommand | UpdateNowCommand | UpdateCancelCommand | PageErrorCommand;

export type Message = HelloMessage | StatusMessage | PongMessage | ErrorMessage | PortsMessage | StateMessage | PatchMessage | WeatherSeriesMessage | PacketHistoryMessage | PositionHistoryMessage | SpeedSeriesMessage | AlertResultMessage | UpdateResultMessage | ReleaseNotesMessage | RadioSearchMessage;

/** The answer to `alert_test`, when the command has ended or run out of its 20 s. */
export interface AlertResultMessage {
  type: "alert_result";
  /** the command ended with exit code 0 */
  ok: boolean;
  /** `ran` when it worked; else why not: the exit code and the first line of stderr (`exit code 3: no display`), or that it could not start or was killed after 20 s */
  text: string;
}

/** Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM` is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`). */
export interface AlertTestCommand {
  cmd: "alert_test";
}

/** An area object (the symbol `\l`): its shape and colour, and how far down and to the right of the object's position it reaches. */
export interface AreaValues {
  /** open circle, line, open ellipse, open triangle, open box, filled circle, coloured line, filled ellipse, filled triangle or filled box */
  shape: string;
  colour: string;
  lat_offset_deg: number;
  lon_offset_deg: number;
}

/** Asks the stations near us for local info (repeaters, events, places): one message to the addressee `QRU` (the services/qruask.py of the daemon), whose `text` is `INFO` (which groups are served near us?), `NEXT` (the next objects of the group asked for last) or a group of 1 to 8 upper-case letters and digits (`RP70`), with a distance in kilometres, 1 to 20000, after it (`INFO 250`). A request to QRU is a broadcast: it is sent once, with no message id, is not kept as a message and is not sent again; it goes by `path` when one is given (digipeater calls or aliases separated by commas, checked as the setting `beacon/path` is, or `DIRECT` for none), else by the path of messages to the station QRU (its own path, else `beacon/path`), with RFONLY after it unless `rf_only` is false: by radio only. The answers come as messages to us (they are rows of the topic `messages` like any message) and as the topic `qru`; the objects arrive as objects. Answered with an `error` when the text is none, RX only is ticked or no call is set (`transmit.off`, or the interlock's reason), the radio is away, a request to QRU was sent less than 60 seconds ago, whatever it said (`qru.too_soon`, with the `seconds` that are left), or the path is no path or too long with RFONLY (`path.*`, `call.*`). */
export interface AskQruCommand {
  cmd: "qru_ask";
  text: string;
  /** the path the request goes by; left out (or null, or empty) the path of messages to QRU */
  path?: string | null;
  /** RFONLY after the path; left out it is true */
  rf_only?: boolean;
}

/** Answered with `status` at once (the daemon also sends one every 10 s). */
export interface AskStatusCommand {
  cmd: "status";
}

/** One transmission of a message of ours and what came back of it. */
export interface AttemptRow {
  /** UTC, ISO 8601 with a Z */
  sent_at: string;
  /** the digipeaters of the path the attempt went by, in order; empty for a direct path */
  hops: HopRow[];
  /** the call of the iGate that put a copy of the message back on the air as a third-party packet, when one was heard for this attempt; null otherwise */
  internet: string | null;
  /** the acknowledgement was heard after this attempt and before the next one: the attempt the ack answers */
  acked: boolean;
}

/** Sends our position packet now, with the settings as they are (the same packet as the timer's), and the next one is an interval later. It goes out through the TNC, so it is not answered: it arrives as the new `packets` row with direction `out`, and `status` follows with the time of the beacon. Answered with an `error` when it could not be sent: the TNC is not connected, or the settings make no frame. */
export interface BeaconNowCommand {
  cmd: "beacon_now";
}

/** Removes an entry from the message board, from the database and from every page: its row is a `del` of the topic `bulletins`. The same bulletin heard again afterwards is a new entry (heard once). Answered by the `del`, or by an `error` (no such entry). */
export interface BulletinDeleteCommand {
  cmd: "bulletin_delete";
  /** the call that sent it, as the row has it */
  sender: string;
  /** the addressee as the row has it: `BLN1`, `BLNA`, `BLN3HAMS`, `QST` */
  slot: string;
}

/** Posts a bulletin, an announcement or a group bulletin of ours: `slot` is `BLN0`..`BLN9`, `BLNA`..`BLNZ` or `BLN`, a number and a group of up to five characters (`BLN3HAMS`), `text` at most 67 characters of printable ASCII without `|`, `~` and `{`. It is sent at once and then on the schedule of the specification (a bulletin a few times early and every 20 minutes for 4 hours, an announcement every hour for 72 hours); a text for a slot that holds one replaces it. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_bulletins`, or by an `error` that names the reason. */
export interface BulletinPostCommand {
  cmd: "bulletin_post";
  slot: string;
  text: string;
}

/** One bulletin, announcement, group bulletin or group message on the board: what a station sent to `BLN0`..`BLN9`, `BLNA`..`BLNZ`, `BLN3HAMS` (a number or letter and a group of up to five characters) or `ALL`, `CQ` or `QST`. None of them is a conversation and none is acked. The rows are the values of the topic `bulletins`, keyed by `sender/slot` (`OH2XYZ/BLN1`): the board holds one row for each sender and slot, a sender sending the slot again replaces the text. A bulletin that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del`. Nothing ages out: an entry stays on the board until it is deleted. */
export interface BulletinRow {
  /** the call that sent it (for a third-party packet the call inside it) */
  sender: string;
  /** the addressee in capitals: `BLN1`, `BLNA`, `BLN3HAMS`, `QST` */
  slot: string;
  /** the group of a group bulletin (`HAMS` of `BLN3HAMS`); empty for any other */
  group: string;
  /** `announcement` is `BLNA`..`BLNZ`, `bulletin` is `BLN0`..`BLN9`, `group` is a group bulletin or a message to `ALL`, `CQ` or `QST`, `nws` is a weather service bulletin (`NWS-xxxxx`, `SKY...`, `CWA...`) */
  kind: "announcement" | "bulletin" | "group" | "nws";
  text: string;
  /** when this text was first heard; a sender that changes the text starts again */
  first_heard: string;
  /** when it was last heard */
  last_heard: string;
  /** how often this text was heard (the copies of one transmission that came by different digipeaters within 10 seconds are one) */
  times_heard: number;
}

/** Deletes a bulletin of ours: it is not sent again and leaves the board. Answered by the `del` of its row in `own_bulletins`, or by an `error` (no such bulletin of ours). */
export interface BulletinUnpostCommand {
  cmd: "bulletin_unpost";
  slot: string;
}

/** Asks the version page now, the question of the daily update check; the daily schedule is left as it was. Answered with `update_result` and then a `status` (with the newer version, if there is one) to the page that asked. */
export interface CheckUpdateCommand {
  cmd: "update_check";
}

/** Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path` (or the `del` of the entry when it was not RF only either), or by an `error`. */
export interface ClearStationPathCommand {
  cmd: "clear_station_path";
  call: string;
}

/** The settings: each key of the settings table (`station/call`, `serial/baud`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic `config`, told again after every save, though nothing differs. */
export interface ConfigValues {
  /** the settings in force, key to text; every key is there */
  values: { [key: string]: string };
  /** the same keys with their defaults, for a form's reset */
  defaults: { [key: string]: string };
  /** where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off (with `https` on, the https addresses) */
  urls: string[];
  /** the secure connection: whether it is served, its port, the fingerprint of the authority's certificate (which `GET /neoaprs-ca.crt` downloads), and why not when it could not start */
  https: HttpsState;
}

/** Removes the whole conversation with a station: every message we sent to it and every one it sent to us (not the messages it was only overheard sending to others), from the database in one write, from the daemon and from every page: each message's row is a `del` of the topic `messages`. A message that is still being sent is cancelled first. The path and the timeout of the station stay. Answered by the `del`s, or by an `error` (the call is none, or there is no message with that station). */
export interface ConversationDeleteCommand {
  cmd: "conversation_delete";
  call: string;
}

/** An item report: like an object, without a time. */
export interface DecodedItem {
  type: "item";
  name: string;
  alive: boolean;
  position: PositionFields;
}

/** A text message; an ack has `ack_id` and no text, a reject `rej_id`. */
export interface DecodedMessage {
  type: "message";
  addressee: string;
  text: string;
  msg_id: string | null;
  ack_id: string | null;
  rej_id: string | null;
}

/** An object report: a thing (a storm, an event) that a station puts on the map. */
export interface DecodedObject {
  type: "object";
  name: string;
  /** false when the report kills the object */
  alive: boolean;
  position: PositionFields;
  timestamp: string | null;
}

/** A data type that is recognised but not (fully) decoded: a positionless weather report is decoded (`weather`, `timestamp`), the station capabilities and an Agrelo DF report are read into `items`. */
export interface DecodedOther {
  type: "other";
  /** a short word: weather, nmea, query, test, capabilities, agrelo-df, shelter, space-weather, third-party, user-defined, telemetry (one that is not a report), ... */
  kind: string;
  /** the whole information field */
  text: string;
  /** the observation of a positionless weather report (`_`); null for anything else */
  weather: DecodedWeather | null;
  /** `capabilities`: the items of the list by token (`IGATE`, `MSG_CNT`...), the value empty for a token alone; `agrelo-df`: `bearing` and `quality`; null for anything else */
  items: { [key: string]: string } | null;
  /** the time of a positionless weather report (its MMDDhhmm, resolved to the latest such time that is not in the future) */
  timestamp: string | null;
}

/** A position report. */
export interface DecodedPosition {
  type: "position";
  lat: number;
  lon: number;
  symbol_table: string;
  symbol_code: string;
  comment: string;
  course_deg: number | null;
  speed_kmh: number | null;
  altitude_m: number | null;
  /** the time the packet itself carries, when it has one */
  timestamp: string | null;
  /** the station can receive messages */
  messaging: boolean;
  compressed: boolean;
  /** how many digits of the position were blanked out, 0 to 4 */
  ambiguity: number;
  /** the weather a station with the weather symbol (`_`) sent after its position; the rest of the text is the `comment` */
  weather: DecodedWeather | null;
  /** the PHG, RNG, DFS, DF bearing or area data after the symbol of an uncompressed position; null when there was none */
  extensions: ExtensionValues | null;
  /** the `timestamp` was sent in the sender's local time (`/`): it is the time as it was sent, not UTC */
  timestamp_local: boolean;
  /** the Maidenhead locator in the status text of a Mic-E packet; null for any other position */
  locator: LocatorValues | null;
  /** the base-91 telemetry `|ss11|` the comment carried (APRS 1.2), taken out of the `comment`; null when there was none */
  telemetry?: TelemetryFields | null;
  /** the local information the comment began with (`145.775MHz T100 -060 R40k`), or the name of a frequency object with the fields of its comment, taken out of the `comment`; null when there was none */
  frequency: FrequencyValues | null;
  /** the storm data the comment of a position with the symbol `@` began with (`/HC/150^200/0980>090&030%040`), taken out of the `comment`; null when there was none */
  storm: StormValues | null;
  /** the characters of a signpost (symbol `\m`): `55` for a comment that began `{55}`, taken out of the `comment`; null for any other position */
  sign: string | null;
}

/** A status report. */
export interface DecodedStatus {
  type: "status";
  /** the status text; after the locator when there is one */
  text: string;
  timestamp: string | null;
  /** a Maidenhead locator with a symbol at the start of the report (a report that has one has no timestamp) */
  locator: LocatorValues | null;
  /** the frequency the text began with (`>145.775MHz T100`), taken out of the `text`; null when there was none */
  frequency: FrequencyValues | null;
}

/** A telemetry report (`T#005,199,000,255,073,123,01101001`). The definitions of the channels are messages of the station, applied by the daemon: see `telemetry` of the station. */
export interface DecodedTelemetry {
  type: "telemetry";
  /** the sequence number; null for the `MIC` of a Mic-E unit */
  sequence: number | null;
  /** the analog values as sent, 1 to 5 (APRS 1.2: any width, signed, with a decimal point) */
  analog: number[];
  /** the digital values as a text of 0 and 1, B1 first: up to eight, empty when there were none */
  bits: string;
  comment: string;
}

/** A field that should have decoded and did not. */
export interface DecodedUndecoded {
  type: "undecoded";
  /** why it did not */
  error: string;
  /** the information field as latin-1 */
  text: string;
}

/** The weather fields of a weather station's position or of a positionless weather report, in metric units; null where the report did not have the field. */
export interface DecodedWeather {
  /** degrees the wind blows from */
  wind_dir: number | null;
  wind_kmh: number | null;
  gust_kmh: number | null;
  temp_c: number | null;
  /** per cent, 1 to 100 */
  humidity: number | null;
  pressure_hpa: number | null;
  rain_1h_mm: number | null;
  rain_24h_mm: number | null;
  /** since midnight */
  rain_today_mm: number | null;
  /** W/m2 */
  luminosity: number | null;
  /** in the last 24 hours */
  snow_mm: number | null;
  /** the raw rain counter, as the station counts it */
  rain_counter: number | null;
  /** the weather fields as they were sent */
  raw: string;
}

/** The item at `key` is gone. */
export interface DelOp {
  op: "del";
  /** the key of an item of a keyed topic: a station's call, a packet's id as text */
  key: string;
}

/** The bearing and quality of a DF report (`/270/729` after the course and speed). */
export interface DfBearingValues {
  bearing_deg: number;
  /** 0 nothing, 1 to 8 the share of the possible samples that hit, 9 a manual report */
  hits: number;
  /** the length the line is drawn to */
  range_km: number;
  quality: number;
}

/** The strength of a signal heard by a direction finder (`DFS2360`) with the height, gain and directivity of its antenna. */
export interface DfsValues {
  /** 0 to 9; 0 is where the signal is not heard */
  strength: number;
  height_m: number;
  gain_db: number;
  direction_deg: number | null;
}

/** A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed. A page goes by `cmd`, `key` and `code`; `text` is the English sentence for a log and for a code the page has no sentence for. */
export interface ErrorMessage {
  type: "error";
  /** the command it answers; empty for a frame that was no command (not JSON, not an object, no `cmd`, an unknown one) */
  cmd: string;
  /** the setting it is about (`set_config`), a key of `CONFIG_KEYS`; null for any other error */
  key: string | null;
  /** a stable word for what is wrong, such as `setting.range`, `call.ssid` or `message.too_long`; `other` for an error that has no code yet */
  code: string;
  /** the values the sentence is made of, by name, such as `value`, `min` and `max` of `setting.range`; empty when there are none */
  params: { [key: string]: string | number };
  /** what could not be done and why, in a sentence in English: the command, then the setting if there is one, then the reason (`set_config: station/lat: 95 is not between -90 and 90`) */
  text: string;
}

/** The data extensions after the symbol of an uncompressed position (taken off the comment); null for what the position did not have. */
export interface ExtensionValues {
  phg: PhgValues | null;
  /** a pre-calculated radio range (`RNG0050`) */
  range_km: number | null;
  dfs: DfsValues | null;
  df_bearing: DfBearingValues | null;
  area: AreaValues | null;
}

/** Ends the search of `find_radio`; the page that asked is told `cancelled`. An `error` (`radio.not_running`) when none is running. */
export interface FindRadioCancelCommand {
  cmd: "find_radio_cancel";
}

/** Find my radio: tries the serial ports and the paired Bluetooth devices that the search for the radio looks at (not a KISS TCP address), one after the other and each at the usual speeds, until a TNC answers in KISS or can be put into KISS the way a TNC profile does. The radio's own line is closed while it runs and opened again after it. It writes nothing but a carriage return and, to a TNC that answers with text, the steps of the TNC profiles that put it into KISS; nothing is sent to the air. Told to the page that asked with `radio_search` messages (`trying` before each try, then `found` or `cancelled`); the page puts the answer in the settings. An `error` when a search is running (`radio.busy`), when there is no port to try (`radio.no_ports`) and when none answered (`radio.not_found`). */
export interface FindRadioCommand {
  cmd: "find_radio";
}

/** A fresh start for what was heard: removes every station and every packet heard (and the weather of the stations), in the daemon and in its database. The station we are, the objects and bulletins we send, the messages, the settings and the maps stay, and so do the packets we sent. Answered by the stations' topic told whole, or by an `error`. */
export interface ForgetAllStationsCommand {
  cmd: "forget_all_stations";
}

/** Removes a station from the station book (and its cache in the database) until it is heard again. Not our own station. Answered by the `del` of the row, or by an `error`. */
export interface ForgetStationCommand {
  cmd: "forget_station";
  call: string;
}

/** A frequency to call on, from the local information at the start of a comment, a status text or the name of a frequency object (`145.775MHz T100 -060 R40k`); null where the text did not say. */
export interface FrequencyValues {
  /** the transmit frequency, MHz */
  mhz: number;
  /** the CTCSS tone of `Tnnn` or `Cnnn`, whole hertz (the tenths are dropped: 107 is 107.2) */
  tone_hz: number | null;
  /** `Cnnn`: the tone is needed to receive as well */
  tone_both: boolean;
  /** `Toff`: no tone and no DCS code */
  tone_off: boolean;
  /** the DCS code of `Dnnn`, three digits as sent */
  dcs: string | null;
  /** `1750`: a 1750 Hz tone burst opens the repeater */
  tone_burst: boolean;
  /** the first letter of the tone field was lower case: narrow modulation */
  narrow: boolean;
  /** the offset from the transmit frequency in kHz (`-060` is -600); 0 is simplex; null when the standard offset is meant */
  offset_khz: number | null;
  /** the nominal range (`R25m` is 40.2 km) */
  range_km: number | null;
  /** a separate receive frequency (`FFF.FFFrx`), MHz */
  rx_mhz: number | null;
}

/** A general query sent from here. */
export interface GeneralAsked {
  /** which query: `aprs` (?APRS?), `igate` (?IGATE?) or `wx` (?WX?) */
  kind: "aprs" | "igate" | "wx";
  /** the information field it went with, `?APRS?`, `?IGATE?` or `?WX?` */
  query: string;
  /** when it was sent */
  at: string;
  /** the path it went by, `RFONLY` last when it was RF only; empty for no digipeaters */
  path: string[];
  /** when the counting of `new` ends, two minutes after it was sent */
  until: string;
  /** the calls of the stations heard on the radio (not as a third-party packet, not from the internet) between the query and `until` that had not been heard on the radio in the ten minutes before it, in the order they were heard: most are answers, but a station cannot be told to answer, so this is no more than who spoke after a quiet spell */
  new: string[];
}

/** Asks the stations in radio range a general query of APRS 1.0.1 (the services/generalask.py of the daemon): one frame from our call to our tocall whose information field is exactly `?APRS?` (`kind` `aprs`: who is around? the stations answer with their positions), `?IGATE?` (`igate`: the iGates answer with their capabilities) or `?WX?` (`wx`: the weather stations answer with their weather). It goes once, by `path` (digipeater calls or aliases separated by commas, `OH2RDK-7,OH2RCH-2` or `WIDE1-1,WIDE2-1`, checked as the setting `beacon/path` is, or `DIRECT` for none; null or empty is `beacon/path`) with `RFONLY` after it when `rf_only`. The answers are ordinary packets (rows of `stations` and `packets`); the topic `general` tells the query and the stations heard after it. Answered with an `error` when RX only is ticked or no call is set (`transmit.off`, or the interlock's reason), the radio is away, the path is no path (`path.*`, `call.*`) or is too long with RFONLY (`path.too_long_rf_only`), or the query of that kind was sent less than 60 seconds ago (`general.too_soon`, with the `seconds` that are left). */
export interface GeneralQueryCommand {
  cmd: "general_query";
  kind: "aprs" | "igate" | "wx";
  path: string | null;
  rf_only: boolean;
}

/** The general queries sent from here: the last one of each kind. Forgotten when the daemon stops. Told whole as it changes. */
export interface GeneralState {
  /** the last query of each kind, the oldest first; empty before one */
  asked: GeneralAsked[];
}

/** The GPS receiver and what the beacon does with it: the latest fix, whether it can be used, and the beacon of a moving station. Told whole as it changes, at most once a second. */
export interface GpsState {
  /** `gps/source` as in force: where the fixes come from */
  source: "off" | "gpsd" | "serial";
  /** `off`: no source is set; `connecting`: the line to gpsd or the receiver is not up and no fix has come; `no_fix`: it is up and the receiver has no fix; `fix`: the latest fix is fresh; `stale`: the latest fix is older than 120 seconds and is not used (a mobile beacon sends nothing on it) */
  state: "off" | "connecting" | "no_fix" | "fix" | "stale";
  /** why there is no fix to use: the feed's own line (`Connection refused`, `the receiver has no position fix yet`) or that the latest fix is old; empty while the state is `fix` and for `off` */
  problem: string;
  /** the latest fix, degrees north; null before the first fix of the source (a stale fix is still told, with its `fix_at`) */
  lat: number | null;
  /** the latest fix, degrees east */
  lon: number | null;
  /** metres above mean sea level; null when the fix has none */
  altitude_m: number | null;
  /** kilometres per hour; null when the fix has none */
  speed_kmh: number | null;
  /** degrees from north, 0 to 359; null when the fix has none */
  course_deg: number | null;
  /** the satellites used for the fix; null when the source does not say */
  satellites: number | null;
  /** when the latest fix was received, by the daemon's clock */
  fix_at: string | null;
  /** `gps/source` is not `off`: the beacon follows the GPS. With no fresh fix nothing is sent at all (never the home position), which `state` and `problem` say */
  mobile: boolean;
  /** when the next beacon by time is due, for the speed of the latest fix (a turn sends one sooner); null unless the beacon is mobile and has a fresh fix and has sent its first */
  next_beacon_at: string | null;
  /** why the latest mobile beacon of this run went out: `start` (the first fix), `time`, `turn` (a corner), `request` (Beacon now); empty before the first */
  last_beacon_reason: "" | "start" | "time" | "turn" | "request";
  /** when it went out; null before the first */
  last_beacon_at: string | null;
}

/** The first message of a connection; `status` and the `state` of every topic follow it at once, so a page need not ask for them. */
export interface HelloMessage {
  type: "hello";
  /** the version of these messages: a page built for another one loads itself again, and when that does not help it does not run (it shows a notice and keeps the socket closed) */
  protocol: number;
  /** the version of the daemon, which the page shows (Settings → Update check); the page has no version of its own and does not compare this one */
  version: string;
  /** the build of the page this daemon serves, the name of its main script (`index-<hash>.js` of assets/); the daemon serves the page it took when it started, so this is the build a browser gets from it. A page of another build loads itself again, once for each build, and shows a notice when that does not help; empty when the daemon has no built page */
  page: string;
  /** how this daemon was installed, for the steps of an update */
  install: InstallInfo;
  /** the topics the page is following from the start: all of them (a page may `unsubscribe` from one) */
  topics: string[];
}

/** One digipeater of the path an attempt went by, and whether a copy of our own message was heard back with that hop used. */
export interface HopRow {
  /** the digipeater as the path named it (`OH2RCH-2`, or an alias such as `WIDE1-1`); once heard, the call that did it, which replaces an alias */
  call: string;
  /** a copy was heard by radio with this hop's has-been-repeated bit set (or a later hop's: a hop works the first unused address) */
  heard: boolean;
  /** when the first copy that showed the hop was heard (by radio if there was one, else over the internet); null when it was not heard */
  heard_at: string | null;
  /** a copy gated back by an iGate as a third-party packet showed the hop used; with `heard` false the hop is known only that way */
  by_internet: boolean;
}

/** The secure connection (`web/https`) as the daemon has it. */
export interface HttpsState {
  /** the page is served over https right now (`web/https` and `web/network` are on, and it started) */
  on: boolean;
  /** the https port; 0 while it is not served */
  port: number;
  /** SHA-256 fingerprint of NeoAPRS's certificate authority, `AB:CD:...`, for a person to compare with what the device shows when the certificate is installed; empty while it is not served */
  fingerprint: string;
  /** why the secure connection could not start or go on, when it was asked for; empty otherwise */
  problem: string;
}

/** The iGate (neoaprs/services/igate.py): what the radio hears is put on APRS-IS, and nothing from APRS-IS is ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon started. Told whole as it changes, at most once a second. */
export interface IgateState {
  /** `igate/enabled` as in force */
  enabled: boolean;
  /** `off`: the switch is off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `problem` says is missing); `connected`: logged in and verified, packets are gated; `listening`: logged in without a passcode, so that nothing is gated and the stations of the internet are read only; `unverified`: the server did not accept the passcode, nothing is gated (the connection reads, as `listening` does) and the login is not tried again with another until the settings change */
  state: "off" | "connecting" | "connected" | "listening" | "unverified";
  /** the name the server gave at the login (`T2FINLAND`); empty until it has answered */
  server: string;
  /** why it is not connected: what is missing (the call, the password, the server) or the connection's own words (`Connection refused`, `the server did not accept the password`); empty while `connected`, `listening` and `off` */
  problem: string;
  /** packets put on APRS-IS since the daemon started */
  gated: number;
  /** packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), `source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), `frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key */
  dropped: { [key: string]: number };
  /** when the latest packet was gated; null before the first */
  last_gated_at: string | null;
}

/** How this copy of the daemon was installed, which is what the steps of an update depend on (neoaprs/versions.py, neoaprs/cli/installkind.py). */
export interface InstallInfo {
  /** `windows-installer` (the frozen program of the installer), `appimage`, `deb` (the Debian package, in /opt/neoaprs), `uv-tool` (the install script, or `uv tool install`), `pip` (a plain environment) or `source` (a clone of the repository) */
  kind: "windows-installer" | "appimage" | "deb" | "uv-tool" | "pip" | "source";
  /** the AppImage file this runs from; empty for the other kinds */
  appimage: string;
  /** whether a service starts it: the systemd unit, the launchd agent or the Windows Run key */
  service: boolean;
  /** the architecture of the package it was installed from, `amd64` or `arm64`; empty for the other kinds, and for a machine that has no package */
  arch: string;
}

/** Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a port of the machine: it is typed. */
export interface ListPortsCommand {
  cmd: "list_ports";
}

/** A Maidenhead locator (grid square) with the symbol that came with it, in a status report or in the status text of a Mic-E packet; the position is the centre of the square. */
export interface LocatorValues {
  /** 4 or 6 characters, `IO91sx` */
  grid: string;
  lat: number;
  lon: number;
  symbol_table: string;
  symbol_code: string;
}

/** Ends the running job; the files it was making are removed and the maps stay as they were. An `error` when no job is running. */
export interface MapCancelCommand {
  cmd: "map_cancel";
}

/** Starts a dry run: how big the detailed map for `map/radius_km` and `map/maxzoom` round our position will be. Answered by the topic `map` (state `estimating`, then `estimate` filled in), or by an `error` when no job can start (no position, or a job is running). The pmtiles program is fetched first when it is not there. */
export interface MapEstimateCommand {
  cmd: "map_estimate";
}

/** Starts making the maps: the world map first when it is not there, then the detailed map for `map/radius_km` and `map/maxzoom` round our position, from `map/source` or the latest daily build. The progress is the topic `map`. An `error` when no job can start (no position, or a job is running). */
export interface MapFetchCommand {
  cmd: "map_fetch";
}

/** A map file in the data folder. */
export interface MapFileInfo {
  /** `basemap.pmtiles` (the detailed map) or `basemap-world.pmtiles` (the world: zoom 4 when it is the one that ships with the program, zoom 5 when the daemon made it) */
  name: string;
  bytes: number;
  /** when the file was made */
  modified: string;
  /** the area it covers, [west, south, east, north] in degrees, as its header says; null for a file whose header cannot be read */
  bbox: number[] | null;
  min_zoom: number | null;
  /** the deepest zoom it has tiles for; the page draws a deeper one from these */
  max_zoom: number | null;
  /** the day (`20261022`) of the Protomaps build it was cut from; empty if not known (a file made by hand) */
  build: string;
}

/** What a dry run said: how big the detailed map will be for the area and the zoom it was made for. */
export interface MapSizeEstimate {
  /** the tiles it will hold */
  bytes: number;
  tiles: number;
  /** the radius it was estimated for; it is stale when `map/radius_km` is another number now */
  radius_km: number;
  /** the zoom it was estimated for */
  maxzoom: number;
  /** the area, [west, south, east, north] */
  box: number[];
  /** the day of the build it was estimated from; empty for a source that is not a daily build */
  build: string;
}

/** The base map: the files, the area and detail the settings ask for, the size estimated, and the job that is running. The value of the topic `map`, told whole at most four times a second. */
export interface MapState {
  /** `none`: there is no detailed map. `ready`: there is one. `estimating` and `downloading`: a job is running (`step` and `percent` say how far). `error`: the last job failed and `problem` says why; the map files are as they were */
  state: "none" | "estimating" | "downloading" | "ready" | "error";
  /** what the running job is doing: fetching the pmtiles program (`tool`), looking for the latest build (`build`), making the world map (`world`) or the detailed map (`area`); empty while no job runs */
  step: "" | "tool" | "build" | "world" | "area";
  /** how far the step is; null when it cannot say (the program and the build have no bar) */
  percent: number | null;
  /** the size so far of the file the step is making, in bytes (it grows while the download moves); null when no file is being made yet */
  downloaded: number | null;
  /** what the job says of a download that has not moved for a while: `no progress: trying again (2 of 3)`; empty when all is well */
  note: string;
  /** why no job can be started now (no position, or a job is running); empty when one can */
  blocked: string;
  /** why the last job failed; empty if it did not, and while a job runs */
  problem: string;
  /** the latest dry run (`map_estimate`); null before one, and after a download */
  estimate: MapSizeEstimate | null;
  /** `map/radius_km` */
  radius_km: number;
  /** `map/maxzoom` */
  maxzoom: number;
  /** the area those settings make round our position, [west, south, east, north]; null without a position */
  box: number[] | null;
  /** `basemap.pmtiles`; null if it is not there */
  detail: MapFileInfo | null;
  /** `basemap-world.pmtiles`: the data folder's own when it has one, else the one that ships with the program; null if there is neither (a base map the page cannot draw) */
  world: MapFileInfo | null;
  /** the detailed map was begun without being asked for (a place was set, or the setup guide said the map is wanted) and could not be fetched yet, most likely for want of a connection; it is tried again at the next start. False once a job runs or a detailed map is there */
  later: boolean;
  /** the radius of the ALOHA circle round our position, in km to a tenth: the distance within which the stations heard on RF would fill the 1200 baud channel (WB4APR's method, worked out again every minute); null without a position and while the stations heard do not fill the channel */
  aloha_km: number | null;
}

/** The setup guide went on from its Position step with the place the daemon has: the map of the area is wanted. The daemon begins making the detailed map for `map/radius_km` round our position, as `map_fetch` does (the progress is the topic `map`), unless the detailed map that is there covers the place already or a job is running; it is never an error, and without a position nothing happens. A new place saved with `set_config` asks the same by itself. The job is not the operator's: when it fails it is tried again at the next start of the daemon (`later` of the topic `map`), and `map_cancel` ends it. */
export interface MapWantedCommand {
  cmd: "map_wanted";
}

/** Stops sending a message of ours that is still being sent; its row becomes `cancelled`. Answered by the new state of its row, or by an `error`. */
export interface MessageCancelCommand {
  cmd: "message_cancel";
  id: number;
}

/** Removes a message of any kind (one of ours, one sent to us, one we only overheard) from the database, from the daemon and from every page: its row is a `del` of the topic `messages`. A message that is still being sent is cancelled first, so that no attempt is made while it goes. Answered by the `del`, or by an `error` (no such message). */
export interface MessageDeleteCommand {
  cmd: "message_delete";
  id: number;
}

/** Sends a message of ours that failed, is unconfirmed, was rejected or was cancelled again, from the first attempt of the schedule. Answered by the new state of its row, or by an `error` (no such message, or it is not in a state that can be sent again). */
export interface MessageRetryCommand {
  cmd: "message_retry";
  id: number;
}

/** One message: one we sent or one that was sent to us. The rows are the values of the topic `messages`, keyed by `id` as text: the daemon holds every message (none leaves on its own; a database with more than 10000 gives the latest 10000 at a start). A message that is new or changes (its state, its attempts) is a `set` of its row, one that is deleted (`message_delete`, `conversation_delete`) a `del`. The conversation a message belongs to is the other station: `from_call` of a message that came in, `to_call` of one we sent. */
export interface MessageRow {
  /** the number the database gave the message; it counts up and is kept across runs of the daemon */
  id: number;
  /** when the message was made (sent messages) or heard (received messages) */
  at: string;
  /** `in` was heard (sent to us, or overheard), `out` is one of ours */
  direction: "in" | "out";
  /** the sender: the packet's source for a message that came in, our call for one of ours */
  from_call: string;
  /** the addressee: our call for a message sent to us, the other station for one of ours, whoever it is for when overheard */
  to_call: string;
  text: string;
  /** the message id the acknowledgement quotes (1 to 5 letters or digits); null for a message that came in without one */
  msg_id: string | null;
  /** `queued`: it waits, with no attempt made, for another message of ours to the same station to be acked, rejected, failed or cancelled (one message to a station is on the air at a time; one not expected to be acked, given 1 or 2 attempts, never waits); it can be cancelled, and becomes `sending` when its turn comes; `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; `received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for) */
  state: "queued" | "sending" | "acked" | "rejected" | "failed" | "unconfirmed" | "cancelled" | "received" | "overheard";
  /** how many times it has been transmitted (at most `attempts_max`: 0, 32, 64, 128, 256, 512, 1024 ... seconds after the first, no wait longer than 960) */
  attempts: number;
  /** how many attempts the message was given when it was sent: 4, 2 for the email gateway `EMAIL-2`, 1 for a bulletin (messages from before the count was fixed have their own, up to 10) */
  attempts_max: number;
  /** when it was transmitted last; null until the first attempt (the TNC may be away) */
  last_attempt_at: string | null;
  /** when the acknowledgement was heard */
  acked_at: string | null;
  /** for a message of ours, each attempt made (`attempts` of them, the oldest first; fewer for a message sent before the delivery chain was kept, none until the first attempt) with the hops of its path that a copy of our own message was heard back with; a hop heard is a `set` of the message's row. Empty for a message that came in */
  attempts_detail: AttemptRow[];
  /** how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept */
  route: string;
}

/** One version's section of the changelog. */
export interface NoteSection {
  /** the version the section is of */
  version: string;
  /** the section as it is written, markdown: paragraphs, `- ` bullets, `**bold**` and `code` */
  text: string;
}

/** Kills an object or an item of ours: the killed form is sent three times (at once, after a minute and after three) and then it is forgotten, and it leaves the map now. One that was never sent is removed at once. Answered by the `del` of its row in `stations` (and in `own_objects` once the kill is sent, or at once), or by an `error` (no such object of ours). */
export interface ObjectKillCommand {
  cmd: "object_kill";
  name: string;
}

/** Makes an object or an item of ours, or changes the one of that name (a changed object starts its schedule again, and is sent at once, never sooner than a minute after its last packet). `name` is 1 to 9 characters for an object and 3 to 9 for an item, printable ASCII without `!`, `_`, `|` and `~` and without a blank at either end, and not our own call or the call of a station; `lat` and `lon` the position in decimal degrees; the symbol is a table character and a code character; `comment` at most 43 characters (36 with a course or speed); `course_deg` and `speed_kmh` the course and speed, each or both or none; `path` the digipeaters, calls separated by commas, or `DIRECT` for none at all (null or empty: `beacon/path`); `qru_group` the group of QRU it belongs to (up to 8 letters and digits, not `INFO` or `NEXT`; empty for none) and `on_request` true to send it only to a station that asks for it, never on the schedule. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason. */
export interface ObjectSetCommand {
  cmd: "object_set";
  name: string;
  kind: "object" | "item";
  lat: number;
  lon: number;
  symbol_table: string;
  symbol_code: string;
  comment: string;
  course_deg: number | null;
  speed_kmh: number | null;
  path: string | null;
  qru_group: string;
  on_request: boolean;
}

/** Removes every message we only overheard `from_call` sending to `to_call` (the state `overheard`, that sender, that addressee: one pair of the Messages list's overheard rows) from the database in one write, from the daemon and from every page: each message's row is a `del` of the topic `messages`. The conversations are not touched: a message we sent or one sent to us is never removed by this. Answered by the `del`s, or by an `error` (no overheard message of that pair). */
export interface OverheardDeleteCommand {
  cmd: "overheard_delete";
  from_call: string;
  to_call: string;
}

/** One bulletin, announcement or group bulletin of ours: its text and where its schedule stands. The rows are the values of the topic `own_bulletins`, keyed by `slot` (`BLN1`): a bulletin that is posted, and each time it is sent, is a `set` of its row, one that is deleted (`bulletin_unpost`) a `del`. One whose schedule is over stays, with a null `next_at`, until it is deleted or posted again. */
export interface OwnBulletinRow {
  /** the addressee: `BLN1`, `BLNA`, `BLN3HAMS` */
  slot: string;
  /** the group of a group bulletin (`HAMS`); empty for any other */
  group: string;
  kind: "bulletin" | "announcement" | "group";
  text: string;
  /** when the text was posted */
  posted_at: string;
  /** how often it was sent */
  sent: number;
  /** when it was last sent; null while it has not been sent */
  last_sent_at: string | null;
  /** when it is sent next; null when its schedule is over (a bulletin: now, after 2 and 6 minutes, then every 20 minutes until 4 hours after the first; an announcement: the same early, then every hour until 72 hours after the first) */
  next_at: string | null;
}

/** One object or item of ours: what we send and where its schedule stands. The rows are the values of the topic `own_objects`, keyed by `name`: an object that is made or changed, and each time it is sent, is a `set` of its row, one that is gone (the kill was sent three times, or another station took the name over) a `del`. A live object is also a row of the topic `stations` with `own` true, which is what the map shows; a killed one leaves that topic at once and stays here, as `killing`, until its kill has been sent. */
export interface OwnObjectRow {
  /** the name of the object (1 to 9 characters) or of the item (3 to 9), as it is sent: case-sensitive */
  name: string;
  kind: "object" | "item";
  lat: number;
  lon: number;
  /** `/` (primary), `\` (alternate) or an overlay character 0-9, A-Z */
  symbol_table: string;
  symbol_code: string;
  /** at most 43 characters, 36 when it follows a course and speed */
  comment: string;
  /** the course in degrees from north (0 to 359); null for none */
  course_deg: number | null;
  /** the speed in km/h; null for none */
  speed_kmh: number | null;
  /** the digipeaters it goes by, calls separated by commas, or `DIRECT` for none at all; null: the path of the setting `beacon/path` is used */
  path: string | null;
  /** the group of QRU (1 to 8 upper-case letters and digits) a station that asks the addressee `QRU` for it is answered with this object in; empty for none */
  qru_group: string;
  /** true: it is never sent on the decay schedule, only to a station that asks for it (`?APRSO`, or its QRU group); false: it is sent on the schedule */
  on_request: boolean;
  /** `live`: it is being sent on the decay schedule; `killing`: it was killed and its killed form is being sent (three times), then it is forgotten */
  state: "live" | "killing";
  /** when it was first made */
  created_at: string;
  /** when it was last changed or killed */
  updated_at: string;
  /** how often it was sent since it was last changed or killed */
  sent: number;
  /** when it was last sent; null while it has not been sent (the call is not set, or the radio is away) */
  last_sent_at: string | null;
  /** when it is sent next: 1, 2, 4 ... minutes after the last packet, never more than the net cycle time of its path apart; a time that has passed means it waits for the radio or for the call; null for one that is `on_request` */
  next_at: string | null;
}

/** Asks how many packets were heard (not sent by us) in each of the last `hours` hours: all of them, or those of one station (`call`). Answered with a `packet_history` message to the page that asked, or an `error` for hours out of range or a call that is empty; a station with no packets is answered with every count 0. */
export interface PacketHistoryCommand {
  cmd: "packet_history";
  /** how far back to go: 24 for a day, 168 for a week */
  hours: number;
  /** only the packets whose sender (the source of the frame heard) is this station, as the `stations` topic has it; absent or null for every packet heard */
  call?: string | null;
}

/** The packets heard by the hour, the answer to `packet_history`: a count for each whole hour of the clock from `start`, the oldest first, as many as were asked for; the last is the hour that is running, so it counts what has come since the top of the hour. */
export interface PacketHistoryMessage {
  type: "packet_history";
  /** the hours asked for */
  hours: number;
  /** the station asked about, null for every packet heard: a page that asked for several stations and for all of them tells the answers apart by it */
  call: string | null;
  /** the top of the first hour counted, UTC */
  start: string;
  /** the packets heard in each hour from `start`, the oldest first (an hour with none is 0) */
  counts: number[];
}

/** One packet heard or sent. The rows are the values of the topic `packets`, keyed by `id` as text: the daemon holds the latest 200, a packet that comes is a `set` and the one that falls out of the 200 a `del`. The page shows them newest first (the highest id). */
export interface PacketRow {
  /** counts up in the order the packets came in this run of the daemon; not kept in the database */
  id: number;
  /** UTC, ISO 8601 with a Z */
  heard_at: string;
  /** heard on the air, or sent by us */
  direction: "in" | "out";
  /** who sent the frame we heard; for a third-party packet the iGate (see `gate`); for a packet from the internet the station that sent it */
  source: string;
  destination: string;
  /** the digipeaters, the one that repeated it marked with `*`; for a packet from the internet everything between the destination and the colon of the line (`TCPIP*`, the q-construct `qAC`, the server `T2FINLAND`) */
  path: string[];
  /** a telemetry report is `other`; its `decoded.type` is `telemetry` */
  kind: "position" | "message" | "object" | "item" | "status" | "other" | "undecoded";
  /** how a packet that was heard on the radio reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours and for one from the internet */
  route: string;
  /** the channel the packet came by, set once where it was made: `rf` heard on the radio (direct or by digipeaters; every packet of ours too), `rf-gated` heard on the radio as a third-party packet that an iGate put on the air, `is` received from APRS-IS over the internet (never on the air), `dummy` made up by the Dummy radio (it works as `rf` does and never goes to the internet) */
  via: "rf" | "rf-gated" | "is" | "dummy";
  /** the iGate, for a third-party packet (`via` is `rf-gated`): `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet */
  gate: string;
  /** one line, as the log has it */
  summary: string;
  /** the packet as a line of TNC2 monitor text */
  tnc2: string;
  decoded: DecodedPosition | DecodedMessage | DecodedObject | DecodedItem | DecodedStatus | DecodedTelemetry | DecodedOther | DecodedUndecoded;
}

/** An error that happened in the page itself (the browser's script, not a refusal of the daemon): the daemon writes it to its log as a warning, `page error (vue) on page BUILD: MESSAGE | FIRST LINE OF THE STACK`, and keeps the latest 100 for the support bundle. At most 20 of a connection are logged in a minute; the rest are counted in one line. No answer: a page that cannot report must not fail twice. */
export interface PageErrorCommand {
  cmd: "page_error";
  /** what the error says */
  message: string;
  /** where it happened, as the browser gives it; empty for none */
  stack: string;
  /** who caught it: `vue` (the component framework's error handler), `window` (an uncaught error of the window), `promise` (a promise nobody caught) */
  source: "vue" | "window" | "promise";
  /** when it happened, by the page's clock */
  at: string;
  /** the build of the page that reported it (the `page` of `hello`) */
  build: string;
}

/** What changed in a topic: apply the ops in order; the copy is then at `rev`. An op says what the item is, not what to add, so an op that is applied twice ends where it should. Changes are told on a tick of 100 ms (the topic `tnc` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key. */
export interface PatchMessage {
  type: "patch";
  topic: string;
  /** how many changes the topic has had since the daemon started */
  rev: number;
  ops: (SetOp | DelOp | ReplaceOp)[];
}

/** A station's power, antenna height above average terrain, antenna gain and directivity (`PHG5132`), and the radio range that the formula of the APRS specification gives them. */
export interface PhgValues {
  power_w: number;
  height_m: number;
  gain_db: number;
  /** the direction of the best gain, degrees from north; null for an omni antenna */
  direction_deg: number | null;
  range_km: number;
}

/** Answered with `pong`. */
export interface PingCommand {
  cmd: "ping";
}

/** The answer to `ping`. */
export interface PongMessage {
  type: "pong";
  /** the daemon's clock */
  now: string;
}

/** A serial port the system lists, or a Bluetooth device paired with it (Linux; on Windows a paired Bluetooth serial port is a COM port of the system's list). Nothing was opened or connected to find it. */
export interface PortRow {
  /** the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`, `bt://AA:BB:CC:DD:EE:FF` for a paired Bluetooth device */
  device: string;
  /** what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say */
  description: string;
  /** the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say */
  hwid: string;
  /** the USB vendor id of an adapter; null for a port that is not USB */
  vid: number | null;
  /** the USB product id of an adapter; null for a port that is not USB */
  pid: number | null;
}

/** The answer to `list_ports`. */
export interface PortsMessage {
  type: "ports";
  /** the ports, in natural order (`COM2` before `COM10`), then the paired Bluetooth devices */
  ports: PortRow[];
  /** whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list */
  search: boolean;
  /** whether Find my radio (`find_radio`) can be asked for: on Linux, Windows and macOS */
  find: boolean;
}

/** A position as the parser made it: decimal degrees, south and west negative, speed in km/h, altitude in metres. */
export interface PositionFields {
  lat: number;
  lon: number;
  symbol_table: string;
  symbol_code: string;
  comment: string;
  course_deg: number | null;
  speed_kmh: number | null;
  altitude_m: number | null;
  /** the time the packet itself carries, when it has one */
  timestamp: string | null;
  /** the station can receive messages */
  messaging: boolean;
  compressed: boolean;
  /** how many digits of the position were blanked out, 0 to 4 */
  ambiguity: number;
  /** the weather a station with the weather symbol (`_`) sent after its position; the rest of the text is the `comment` */
  weather: DecodedWeather | null;
  /** the PHG, RNG, DFS, DF bearing or area data after the symbol of an uncompressed position; null when there was none */
  extensions: ExtensionValues | null;
  /** the `timestamp` was sent in the sender's local time (`/`): it is the time as it was sent, not UTC */
  timestamp_local: boolean;
  /** the Maidenhead locator in the status text of a Mic-E packet; null for any other position */
  locator: LocatorValues | null;
  /** the base-91 telemetry `|ss11|` the comment carried (APRS 1.2), taken out of the `comment`; null when there was none */
  telemetry?: TelemetryFields | null;
  /** the local information the comment began with (`145.775MHz T100 -060 R40k`), or the name of a frequency object with the fields of its comment, taken out of the `comment`; null when there was none */
  frequency: FrequencyValues | null;
  /** the storm data the comment of a position with the symbol `@` began with (`/HC/150^200/0980>090&030%040`), taken out of the `comment`; null when there was none */
  storm: StormValues | null;
  /** the characters of a signpost (symbol `\m`): `55` for a comment that began `{55}`, taken out of the `comment`; null for any other position */
  sign: string | null;
}

/** Asks where the stations were in the last `hours` hours, for the replay of the map. Answered with a `position_history` message to the page that asked, or an `error` for hours out of range. */
export interface PositionHistoryCommand {
  cmd: "position_history";
  /** how far back to go: the replay offers 1, 3, 6, 12 and 24, the choices of the Stations tab's On map for */
  hours: number;
}

/** The positions of the stations over the span asked for, the answer to `position_history`, from the packet log: every position heard in it (a station's own, or the one inside a third-party packet), the live objects and items heard by their names, and what we sent under our call (our beacons, and our objects by their names). A station's points are thinned: one less than 10 m from the point before it, or less than 30 s after it, is left out, and the last is always there. The latest 50 000 position packets at most are read: on a very busy feed the oldest part of a long span may be missing. */
export interface PositionHistoryMessage {
  type: "position_history";
  /** the hours asked for */
  hours: number;
  /** where the span begins, UTC: `hours` hours before the daemon answered */
  start: string;
  /** [time, lat, lon] for each position kept, the oldest first, by the station's call (an object's or item's name); a station with no position in the span is not in it */
  stations: { [key: string]: [string, number, number][] };
}

/** The request we sent last. */
export interface QruAsked {
  /** what was asked (`INFO`, `RP70 150`) */
  text: string;
  /** when it was sent */
  at: string;
}

/** A group of objects a server serves near us. */
export interface QruGroup {
  /** the group, 1 to 8 upper-case letters and digits (`RP70`, `FOOD`) */
  name: string;
  /** how many objects the group has in the server's range */
  count: number;
}

/** A QRU server that answered, as it last said. */
export interface QruServer {
  /** the server's call */
  call: string;
  /** the groups it serves near us, in the order it listed them; empty when it has only sent the closing line of a group */
  groups: QruGroup[];
  /** the most objects it sends for one request; null when its list did not say */
  max_objects: number | null;
  /** the range round us it serves, in `unit`; null when its list did not say */
  range: number | null;
  /** the unit of `range` (kilometres or miles, as the server counts); empty when the list did not say */
  unit: "km" | "mi" | "";
  /** when it answered last */
  at: string;
  /** its last closing line as it was heard (`Sent 5 RP70 Objects Max 5@50km de DF8LS-10`); empty before one */
  sent: string;
  /** when the closing line was heard; null before one */
  sent_at: string | null;
  /** how many objects its last closing line says it sent; null before one */
  sent_objects: number | null;
  /** the request its closing line answers, which Ask again sends once more (`TEST 150`); empty before a closing line, and when the request is not known */
  request: string;
  /** the names of the objects heard on the radio from the server since that request, until `settles_at` (or the last answer, before a closing line); each is an ordinary object of the stations and the map */
  received: string[];
  /** when the counting of `received` ends, 30 seconds after the closing line (a late object may still come); null before a closing line. Fewer `received` than `sent_objects` after it means objects were lost */
  settles_at: string | null;
}

/** The servers that answered a request for local info, and the last request. What is older than an hour is forgotten, with the daemon's restart. Told whole as it changes. */
export interface QruState {
  /** the last request sent from here; null before one, and an hour after it */
  asked: QruAsked | null;
  /** the servers that answered in the last hour, by call */
  servers: QruServer[];
}

/** Asks a station a directed query (APRS 1.0.1 chapter 15): a message to it with the text of the query, `?APRSP` (`kind` `position`: its position packet), `?APRSS` (`status`: its status report), `?APRSD` (`heard`: the stations it hears direct, as a message) or `?APRST` (`trace`: the path our query reached it by, as a message). The query is sent once, without a message id: no attempts follow and no ack is expected. It is kept as a row of the topic `messages` to the station, in state `sending` until it has been transmitted and then `unconfirmed`, whose `text` is the query; the page shows such a row (an `out` message with no `msg_id` whose text is one of the four) as a note of what was asked. The answer is whatever the station sends: a packet (the station's card changes) or a message (a row `in`). Not more than one query of a kind to a station in 60 seconds. Answered with an `error` when the station is not in the station book (`station.unknown`), is no station that takes messages (`query.not_capable`: an object, an item, ourselves, a station whose position says it takes none and that never sent a message), the same query was sent less than 60 seconds ago (`query.too_soon`) or the message is refused as `send_message` refuses it (the call is not set, the radio is silent). */
export interface QueryStationCommand {
  cmd: "query";
  call: string;
  kind: "position" | "status" | "heard" | "trace";
}

/** How `find_radio` goes, to the page that asked. */
export interface RadioSearchMessage {
  type: "radio_search";
  /** `trying`: about to try `port` at `baud`; `found`: a TNC answered at `port` at `baud` and `profile` fits it, and the search is over; `cancelled`: `find_radio_cancel` ended it */
  state: "trying" | "found" | "cancelled";
  /** the port being tried or found; empty for `cancelled` */
  port: string;
  /** the speed; null for a port that has none (a Bluetooth device) and for `cancelled` */
  baud: number | null;
  /** for `found`, the key of the TNC profile (`tnc/profile`); empty otherwise */
  profile: string;
  /** the try that is under way, from 1; 0 for `found` and `cancelled` */
  number: number;
  /** how many tries there are if nothing answers; 0 for `found` and `cancelled` */
  total: number;
}

/** How a station's latest packet from the internet got there, read from the q-construct of its APRS-IS path. */
export interface ReachValues {
  /** `igate`: an iGate heard it on the radio and put it on the internet (`qAR`, `qAO`); `app`: it was sent from the internet by an app or a program and never was on the air (`TCPIP*`, `qAC`, `qAS`, `qAX`) */
  kind: "igate" | "app";
  /** the call of the iGate that heard it; empty for `app` */
  igate: string;
  /** the digipeaters that repeated it on the radio before the iGate heard it, in order (`?` for one that put no call in); empty for a packet the iGate heard direct, and for `app` */
  hops: string[];
}

/** Asks what is new from this version to `version`, the newer one the update check found: the changelog of the project at the tag of that release (neoaprs/releasenotes.py), fetched once. Answered with `release_notes`. */
export interface ReleaseNotesCommand {
  cmd: "release_notes";
  /** the newer version, as `status.update.version` names it; another is answered with no sections */
  version: string;
}

/** The answer to `release_notes`: the sections of the versions newer than this one up to the one asked for, the newest first; none with `problem` saying why (the notes could not be fetched, or the version is not the newer one known). */
export interface ReleaseNotesMessage {
  type: "release_notes";
  /** the version asked for */
  version: string;
  /** the newest first; empty with `problem` */
  sections: NoteSection[];
  /** why there are no sections, in a sentence; empty when there are */
  problem: string;
}

/** The whole value of the topic is `value`. */
export interface ReplaceOp {
  op: "replace";
  value: unknown;
}

/** One route a packet of a station came by, which the map draws (a line, or none for `app` and for a packet heard direct). */
export interface RouteMarkValues {
  /** `rf`: heard on the radio, direct when `hops` is empty; `gated`: heard on the radio as a third-party packet that the iGate `gate` put on the air, `hops` the digipeaters that repeated the iGate's frame; `igate`: heard on the radio by the iGate `gate`, which put it on the internet, `hops` the digipeaters before it; `app`: sent from the internet, never on the air */
  kind: "rf" | "gated" | "igate" | "app";
  /** the digipeaters in order, `?` for one that put no call in */
  hops: string[];
  /** the iGate of `gated` and `igate`; empty for the others */
  gate: string;
  /** when the packet was heard */
  at: string;
  /** where the station was when the packet was heard (the position it reported, else the one it had before); null when that is not known: the map takes its position now */
  lat: number | null;
  lon: number | null;
}

/** Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`. When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused. */
export interface SendMessageCommand {
  cmd: "send_message";
  to: string;
  text: string;
}

/** Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `serial/*`, `tcp/*` and `tnc/profile` restart the TNC, `station/*` move our own station on the map. */
export interface SetConfigCommand {
  cmd: "set_config";
  /** key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`) */
  values: { [key: string]: string };
}

/** The item at `key` is `value` (the whole item, new or changed). */
export interface SetOp {
  op: "set";
  /** the key of an item of a keyed topic: a station's call, a packet's id as text */
  key: string;
  value: unknown;
}

/** Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting `beacon/path` is, or `DIRECT` for a path of its own with no digipeaters at all; an empty `path` is no path of its own, as `clear_station_path` makes it. Answered by the `set` of the station's entry in the topic `station_prefs` (its `rf_only` is whatever it was), or by an `error` that names the reason. */
export interface SetStationPathCommand {
  cmd: "set_station_path";
  call: string;
  path: string;
}

/** Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE` already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set` of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason. */
export interface SetStationRfOnlyCommand {
  cmd: "set_station_rf_only";
  call: string;
  on: boolean;
}

/** Asks for the speeds a station reported in its positions in the last `hours` hours. Answered with a `speed_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a station that reported no speed is answered with no points. */
export interface SpeedSeriesCommand {
  cmd: "speed_series";
  /** the station, as the `stations` topic has it: its position packets are those whose sender (the source of the frame heard) it is */
  call: string;
  /** how far back to go: 24 for a day */
  hours: number;
}

/** The speeds of one station, the answer to `speed_series`: one point for each position packet of it heard in the span that carried a speed (a course and speed after the position, a compressed position's, a Mic-E's), the oldest first (a packet that came by two digipeaters is two points). */
export interface SpeedSeriesMessage {
  type: "speed_series";
  /** the station asked about: a page with several cards open tells the answers apart by it */
  call: string;
  /** the hours asked for */
  hours: number;
  /** [time, speed_kmh] for each position that had a speed, the oldest first; a station standing still that says so has 0 */
  points: [string, number][];
}

/** A topic as it is now: its revision and its whole `value`, which replaces what the page had. Patches for the changes made meanwhile follow. */
export interface StateMessage {
  type: "state";
  topic: string;
  /** how many changes the topic has had since the daemon started */
  rev: number;
  value: unknown;
}

/** What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path of its own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`. */
export interface StationPref {
  /** the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); null if none is set, and the setting `beacon/path` counts */
  path: string | null;
  /** true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet */
  rf_only: boolean;
}

/** One station of the station book: who it is, where it was heard and how often. An object or an item is a row of its own, named by the object. The rows are the values of the topic `stations` (keyed by `call`): a station heard again is a `set` of its row, a station that is forgotten or pruned (or an object that was killed) a `del`. When our own position changes in the settings every row has a new distance and bearing, and the topic is told whole again. */
export interface StationRow {
  /** the call with its SSID, or the name of the object or item */
  call: string;
  kind: "station" | "object" | "item";
  /** who sent the report, for an object or an item; empty for a station */
  reported_by: string;
  /** `/` (primary), `\` (alternate) or an overlay character 0-9, A-Z; empty until a position is heard */
  symbol_table: string;
  /** the character of the symbol in its table; empty until a position is heard */
  symbol_code: string;
  /** the name of the symbol ("Car", "Digipeater"), `unknown` for none */
  symbol_name: string;
  /** decimal degrees, south negative; null until a position is heard */
  lat: number | null;
  /** decimal degrees, west negative; null until a position is heard */
  lon: number | null;
  altitude_m: number | null;
  course_deg: number | null;
  speed_kmh: number | null;
  /** UTC, ISO 8601 with a Z */
  first_heard: string;
  /** UTC, ISO 8601 with a Z */
  last_heard: string;
  last_position_at: string | null;
  /** the text of the latest status report */
  last_status: string;
  /** the comment of the latest position */
  last_comment: string;
  /** how many packets of this station were received, whatever the channel (`heard_rf` + `heard_rf_gated` + `heard_is` + `heard_dummy`) */
  packets: number;
  /** how many of them were heard on the radio, direct or by digipeaters (`rf`) */
  heard_rf: number;
  /** how many came on the radio as third-party packets: an iGate put what it heard on the internet on the air (`rf-gated`); counted, but never a route to send by */
  heard_rf_gated: number;
  /** how many were received from APRS-IS over the internet (`is`); they were never on the air */
  heard_is: number;
  /** how many were made up by the Dummy radio (`dummy`), the radio for trying the program with no radio; they work as the radio's do, and never go to the internet */
  heard_dummy: number;
  /** when a packet of the station was last heard on the radio (`rf`); null when none was */
  last_rf_at: string | null;
  /** when a third-party packet of the station was last heard on the radio (`rf-gated`); null when none was */
  last_rf_gated_at: string | null;
  /** when a packet of the station was last received from the internet (`is`); null when none was */
  last_is_at: string | null;
  /** when a packet of the station was last made up by the Dummy radio (`dummy`); null when none was */
  last_dummy_at: string | null;
  /** the channel of the packet that gave its position (the latest one wins); null for a station without a position and for our own */
  position_via: "rf" | "rf-gated" | "is" | "dummy" | null;
  /** how many of them were heard in the last hour (counted from the packets of the hour at the start and as they come; the row is told again each minute that it becomes fewer) */
  packets_hour: number;
  /** what the station runs, as the APRS device identification list names it ("Kenwood TH-D74", "APRSdroid"): by the destination call of its packets, or by the type code of a Mic-E packet; empty when unknown */
  device: string;
  /** the digipeaters of the latest packet heard on the radio, the one that repeated it marked with `*` */
  last_path: string[];
  /** how the latest packet heard on the radio reached us (empty for a station known from the internet only): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in) */
  last_route: string;
  /** how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept) */
  heard_direct: number;
  /** when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`; null for a station never heard direct */
  last_direct_at: string | null;
  /** [the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted */
  heard_via: [string, number][];
  /** how many third-party packets this station put on the air that we heard (an iGate wrapping what it took from the internet in a frame of its own; counted from the packets heard in this run and the latest 2000 the database kept, and for a station that is in the book); not `heard_rf_gated`, which counts the packets of this station that some iGate put on the air */
  gated: number;
  /** a capabilities packet of the station said `IGATE`: it says it is an iGate */
  igate: boolean;
  /** the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted */
  best_route: string;
  /** the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned) */
  suggested_path: string | null;
  /** the path that has lately been heard to reach the station, which the first two attempts of a message to it go by when the operator has set no path of its own (the later ones go by `beacon/path`): empty for direct (at least 2 packets heard direct within 60 minutes), else the latest named route that at least 2 packets came by within 60 minutes, turned round, as `suggested_path` writes it (no hop without a call, no iGate, at most 3 digipeaters); null when there is none. Worked out when the row is sent, so a path that goes stale is told with the station's next row */
  heard_path: string | null;
  /** how the latest packet of the station that came from the internet got there; null for a station none came from, and for one whose path does not say */
  internet_reach: ReachValues | null;
  /** the route of the station's latest packet and the one before it that came another way (any channel, the newest first): what the map draws of its routes, and no others; empty for a station nothing is known of (our own, our objects) */
  route_marks: RouteMarkValues[];
  /** the latest weather the station sent (a position with the weather symbol, or a positionless weather report); null for a station that sent none since the weather log began (or was made from the packets kept) */
  weather: WeatherValues | null;
  /** when `weather` was heard; null as it is */
  weather_at: string | null;
  /** the latest telemetry report of the station, scaled and named by the definitions it sent (read again from the latest packets at the start); null for a station that sent none */
  telemetry: TelemetryValues | null;
  /** when `telemetry` was heard; null as it is */
  telemetry_at: string | null;
  /** the Maidenhead locator of the station's latest status report (or Mic-E status text): where it says it is, to the square; null when it sent none */
  locator: LocatorValues | null;
  /** the PHG, RNG, DF or area data of the latest position of the station that had any (a position without them keeps the last); null while none had */
  extensions: ExtensionValues | null;
  /** the voice frequency the station gave last, in the comment of a position (or the name of an object) or in a status text; null when it gave none (not kept over a restart of the daemon for a station that does not send it again) */
  frequency: FrequencyValues | null;
  /** the storm data of the latest position of a storm object; null for anything else */
  storm: StormValues | null;
  /** what a signpost object says (`55`); null for anything else */
  sign: string | null;
  /** from our position, null for us and for a station without a position */
  distance_km: number | null;
  /** the direction from our position, degrees from north; null as the distance is */
  bearing_deg: number | null;
  /** our own station: the row of the call in the settings, at the position in the settings */
  is_me: boolean;
  /** an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row */
  own: boolean;
  /** a message to the station makes sense, and the card has a Message button: false for an object or an item and for our own station; for a station true when it has sent a message or an ack (heard, overheard too) or its latest position began with `=` or `@` or was a Mic-E one, false when that began with `!` or `/` or was a Mic-E one whose comment begins with the type code `'` (no messaging); true for a station of which nothing of that is known; false for a station known only from the internet (`heard_is` > 0 and nothing on the radio): a message goes out by radio only */
  can_message: boolean;
  /** the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed */
  track: [string, number, number][];
}

/** What the daemon is, for the status bar: sent after `hello`, every 10 s, when asked (`status`), and when a packet of ours has gone out (the count of packets and the beacon's times have changed). It also says what the daemon costs the machine: the CPU share, the resident memory and the uptime. */
export interface StatusMessage {
  type: "status";
  /** the version of the daemon */
  version: string;
  /** when the daemon started */
  started_at: string;
  /** how many packets the database holds */
  packets: number;
  /** how many stations the station book holds */
  stations: number;
  /** our own call, from the settings; empty while none is set (nothing is transmitted then) */
  call: string;
  /** our own latitude, from the settings; null while none is set */
  lat: number | null;
  /** our own longitude, from the settings; null while none is set */
  lon: number | null;
  /** minutes between our position packets, from the settings; 0 is off */
  beacon_interval_min: number;
  /** when the latest beacon was sent, by the timer or on request; null for none since the daemon started */
  beacon_last_sent: string | null;
  /** when the timer sends the next one; null while the interval is 0 */
  beacon_next_due: string | null;
  /** the text of the status report last sent in this run (services/rigstatus.py); empty until one has gone */
  station_status: string;
  /** when the latest status report was sent (kept over a restart); null for none yet */
  station_status_last_sent: string | null;
  /** whether the radio the status is made from answers: `on`, `off` (rigctld is away or the radio is off, nothing is sent), or `unused` while the status does not come from a radio (`status/source` is `text` or `off`) */
  rig_state: "off" | "on" | "unused";
  /** the daemon's CPU time (user and system) as a share of one core, in percent to a tenth, since the previous status that was at least a second before; the first counts from the start */
  cpu_percent: number;
  /** the daemon's resident memory in megabytes, to a tenth; null where the system does not say */
  rss_mb: number | null;
  /** seconds since the daemon started, by its clock */
  uptime_sec: number;
  /** the latest version while it is newer than this one, from the daily update check; null when there is none or the check has not been answered */
  update: UpdateInfo | null;
}

/** Sends our status report now, with the settings as they are (from the text or from the radio, as `status/source` says), whether it changed and inside the interval; the next one of the timer is an interval later. It goes out through the TNC, so it is not answered: it arrives as the new `packets` row with direction `out`, and `status` follows with the text. Answered with an `error` when it could not be sent: the status is off or has no text, the radio is away, the call is not set, the TNC is not connected or the settings make no frame. */
export interface StatusNowCommand {
  cmd: "status_now";
}

/** The storm data of a tropical storm, hurricane or tropical depression (APRS101, chapter 12), in metric units; null where the report did not have the field. The movement is the course and speed of the position. */
export interface StormValues {
  /** TS tropical storm, HC hurricane, TD tropical depression */
  storm_type: "TS" | "HC" | "TD";
  /** the sustained wind */
  wind_kmh: number | null;
  gust_kmh: number | null;
  /** the central pressure */
  pressure_hpa: number | null;
  /** the radius of hurricane winds */
  hurricane_radius_km: number | null;
  /** the radius of tropical storm winds */
  storm_radius_km: number | null;
  /** the radius of whole gale (50 knot) winds */
  gale_radius_km: number | null;
}

/** Follow these topics (all are followed from the start): each is answered with `state`, then with `patch` as it changes. A topic that is followed already is sent whole again. A topic that is not there is refused with an `error` that names it; the others in the command are not affected. */
export interface SubscribeCommand {
  cmd: "subscribe";
  topics: string[];
}

/** One digital channel of a station's latest telemetry report. */
export interface TelemetryBit {
  /** from the station's `PARM.` message, else `B1` to `B8` */
  name: string;
  /** the bit has the sense that its `BITS.` message gives (1 when there is none) */
  on: boolean;
}

/** One analog channel of a station's latest telemetry report. */
export interface TelemetryChannel {
  /** from the station's `PARM.` message, else `A1` to `A5` */
  name: string;
  /** from its `UNIT.` message; empty when it sent none */
  unit: string;
  /** the value as it was sent (0 to 255) */
  raw: number;
  /** `a*raw^2 + b*raw + c` with the coefficients of its `EQNS.` message; the raw value when it sent none */
  value: number;
}

/** A telemetry report as the parser made it. */
export interface TelemetryFields {
  /** the sequence number; null for the `MIC` of a Mic-E unit */
  sequence: number | null;
  /** the analog values as sent, 1 to 5 (APRS 1.2: any width, signed, with a decimal point) */
  analog: number[];
  /** the digital values as a text of 0 and 1, B1 first: up to eight, empty when there were none */
  bits: string;
  comment: string;
}

/** A station's latest telemetry report with the definitions the station sent as messages (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`) applied. */
export interface TelemetryValues {
  /** the sequence number; null for the `MIC` of a Mic-E unit */
  sequence: number | null;
  /** the analog channels, as many as the report had (1 to 5) */
  channels: TelemetryChannel[];
  /** the digital channels, as many as the report had (up to 8) */
  bits: TelemetryBit[];
  /** the project title of the `BITS.` message; empty when there is none */
  project: string;
  comment: string;
}

/** One line of the TNC's log. */
export interface TncLine {
  /** when the line was written */
  at: string;
  /** what the TNC saw (TNC2 text and what it understood of it) or did (`NeoAPRS: ...`), without the time */
  text: string;
}

/** The TNC, the one feed of packets: its state and why it is not connected, the port, and the latest lines of what it saw and did. The value of the topic `tnc`. */
export interface TncState {
  /** `waiting` is between two attempts to open the line; `problem` says why. `silent`: the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer); nothing is sent until it does */
  state: "stopped" | "connecting" | "connected" | "waiting" | "silent";
  /** why it is not (yet) connected or not sending KISS; empty when all is well */
  problem: string;
  /** the latest reason for waiting */
  last_error: string;
  /** the serial port in use; empty while none is open */
  path: string;
  baud: number;
  /** the radio is the Dummy radio: the traffic is made up and nothing goes on the air; `path` and `baud` mean nothing then */
  dummy: boolean;
  /** one line for the log and `neoaprs doctor`: the port, the speed and what the TNC does; while `silent` it says since when, in UTC */
  describe: string;
  /** the ports the daemon is listening to while it looks for the radio; empty when it is not searching */
  searching: string[];
  /** while `state` is `silent`, when the latest byte came; null otherwise */
  silent_since: string | null;
  stats: TncStats;
  /** what the watchdog did last: `check` (the radio asked whether it is there, after a quiet period), `probe` (the same, while the radio is silent) or `reopen` (the port closed and opened again); empty if it has done nothing since the daemon started */
  last_watchdog_action: "" | "check" | "probe" | "reopen";
  /** when the watchdog did that; null if it has done nothing since the daemon started */
  last_watchdog_at: string | null;
  /** the latest 100 lines of what the TNC saw and did, oldest first */
  lines: TncLine[];
}

/** What the TNC has counted since the daemon started. */
export interface TncStats {
  /** times the line was opened */
  opens: number;
  bytes_in: number;
  bytes_out: number;
  /** frames received, including the ones that could not be read as a packet */
  frames_in: number;
  /** packets handed on */
  packets: number;
  /** frames that could not be read as a packet */
  rejected: number;
  /** when the latest packet was heard; null for none yet */
  last_packet: string | null;
  /** times the keep-alive checked that the radio is there (after 60 seconds of nothing heard) */
  keepalive_checks: number;
  /** times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds) */
  watchdog_probes: number;
  /** times the port was closed and opened again (every 5th probe of a silent radio) */
  port_reopens: number;
  /** frames the digipeater (`digi/enabled`) sent again for other stations */
  digipeated: number;
  /** when the latest of them went out; null for none yet */
  digipeated_at: string | null;
  /** frames the digipeater left unsent because it had already sent the most it sends in a burst (`BURST_MAX` in 10 seconds) */
  digipeat_held: number;
}

/** The value of each topic a page follows (neoaprs/web/topics.py): what `state` carries as `value`, and what `patch` replaces. */
export interface TopicValues {
  /** the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del` */
  stations: { [key: string]: StationRow };
  /** the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest */
  packets: { [key: string]: PacketRow };
  /** the radio; told whole as it changes, at most four times a second */
  tnc: TncState;
  /** the settings; told again after every save, though nothing differs: the settings form waits for it */
  config: ConfigValues;
  /** what the operator set for each station that has anything set, by call: its own path (null where none is set) and whether it is RF only. `set_station_path`, `clear_station_path` and `set_station_rf_only` each give a `set` of the entry, or a `del` when nothing is left in it */
  station_prefs: { [key: string]: StationPref };
  /** every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own */
  messages: { [key: string]: MessageRow };
  /** the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del` */
  bulletins: { [key: string]: BulletinRow };
  /** the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations` */
  own_objects: { [key: string]: OwnObjectRow };
  /** the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`) */
  own_bulletins: { [key: string]: OwnBulletinRow };
  /** the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps, and the ALOHA circle; told whole as it changes, at most four times a second */
  map: MapState;
  /** Update now: whether this copy can update itself, and the steps of the update it is doing; told whole as it changes, at most four times a second */
  update: UpdateState;
  /** the GPS receiver and the moving station's beacon: the latest fix, its state, and when the next beacon by time is due; told whole as it changes, at most once a second */
  gps: GpsState;
  /** the receive-only iGate: whether it is connected to APRS-IS, the server's name, the packets gated and not gated; told whole as it changes, at most once a second */
  igate: IgateState;
  /** local info (QRU): the last request sent from here and the servers that answered it, forgotten an hour after; told whole as it changes */
  qru: QruState;
  /** asking around: the last general query of each kind sent from here (?APRS?, ?IGATE?, ?WX?) and the stations heard after it that had been quiet before it; told whole as it changes */
  general: GeneralState;
}

/** Stop following these topics. A topic that was not followed is ignored. */
export interface UnsubscribeCommand {
  cmd: "unsubscribe";
  topics: string[];
}

/** Ends the download of Update now; nothing of it is left. An `error` (`update.not_running`) when no download is running: an install that has begun is not stopped. */
export interface UpdateCancelCommand {
  cmd: "update_cancel";
}

/** A newer version than the daemon's, as the version page named it (services/updatecheck.py). */
export interface UpdateInfo {
  /** the latest version */
  version: string;
  /** where to get it: an https address, or empty */
  url: string;
  /** a short note from the project, at most 200 characters; empty for none */
  message: string;
}

/** Starts Update now to `version`, which must be the version the update check announced (the `update` of `status`): the daemon fetches the file for this copy and SHA256SUMS from the GitHub release of exactly that version, checks the file's SHA-256 and installs it, and NeoAPRS restarts. The progress is the topic `update`. An `error` when this copy cannot update itself (`update.unsupported`, `update.blocked`), the version is not the one announced (`update.not_announced`) or an update is running (`update.busy`). */
export interface UpdateNowCommand {
  cmd: "update_now";
  version: string;
}

/** The answer to `update_check`: what the version page said, or why it said nothing. */
export interface UpdateResultMessage {
  type: "update_result";
  /** `newer`: a newer version is out; `current`: this is the latest; `no_answer`: the page could not be reached or did not name a version */
  outcome: "newer" | "current" | "no_answer";
  /** the latest version for `newer`, this version for `current`; empty for `no_answer` */
  version: string;
  /** for `no_answer` why, in a sentence; empty otherwise */
  text: string;
}

/** Update now (neoaprs/services/selfupdate.py): whether this copy can update itself, and the steps of the update it is doing. The value of the topic `update`, told whole as it changes, at most four times a second. */
export interface UpdateState {
  /** this copy can update itself (the Windows installer, an AppImage in a folder its user can write): the page offers Update now; else it shows the steps */
  supported: boolean;
  /** `idle`: no update is running. `downloading`: SHA256SUMS and then the file of the release are fetched (`percent`). `verifying`: the file's SHA-256 is held to SHA256SUMS. `installing`: the file is put in place. `restarting`: NeoAPRS ends and starts again as the new version (the page loses its socket and finds the new daemon). `error`: the update failed, `problem` says how */
  state: "idle" | "downloading" | "verifying" | "installing" | "restarting" | "error";
  /** the version being installed; empty while idle */
  version: string;
  /** how much of the file has come; null when the server did not say its size */
  percent: number | null;
  /** the bytes of the file so far */
  downloaded: number;
  /** the size of the file in bytes, when the server said it */
  total: number | null;
  /** for `error`: `download` (the file or SHA256SUMS could not be fetched), `no_checksum` (SHA256SUMS does not name the file), `checksum` (the file's SHA-256 is not the one SHA256SUMS gives it: it was deleted), `install` (it could not be put in place, or the installer could not be started), `no_restart` (it was installed but NeoAPRS did not restart); empty otherwise */
  problem: "" | "download" | "no_checksum" | "checksum" | "install" | "no_restart";
  /** the English sentence of the problem, for the log and the page's details; empty when all is well */
  detail: string;
}

/** Asks for the observations a weather station made in the last `hours` hours. Answered with a `weather_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a call with no observations is answered with no points. */
export interface WeatherSeriesCommand {
  cmd: "weather_series";
  /** the station, as the `stations` topic has it (an object's name for a weather object) */
  call: string;
  /** how far back to go: 24 for a day, 168 for a week */
  hours: number;
}

/** The observations of one weather station, the answer to `weather_series`: one point for each weather packet heard, the oldest first (a packet that came by two digipeaters is two points). */
export interface WeatherSeriesMessage {
  type: "weather_series";
  /** the station asked about */
  call: string;
  /** the hours asked for: a page that asked twice (a day, then a week) tells the answers apart by it */
  hours: number;
  /** [time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity] for each observation; a value the report did not have is null */
  points: ([string, number | null, number | null, number | null, number | null, number | null, number | null])[];
}

/** One weather observation in metric units; each field is null where the report did not have it. */
export interface WeatherValues {
  /** the direction the wind blows from, degrees from north (0 to 360) */
  wind_dir: number | null;
  /** the sustained wind, km/h */
  wind_kmh: number | null;
  /** the gust, km/h */
  gust_kmh: number | null;
  /** degrees Celsius */
  temp_c: number | null;
  /** per cent (1 to 100) */
  humidity: number | null;
  /** barometric pressure, hPa */
  pressure_hpa: number | null;
  /** rain in the last hour, mm */
  rain_1h_mm: number | null;
  /** rain in the last 24 hours, mm */
  rain_24h_mm: number | null;
  /** rain since midnight, mm */
  rain_today_mm: number | null;
  /** W/m2 */
  luminosity: number | null;
  /** snow in the last 24 hours, mm */
  snow_mm: number | null;
}
