// The types of the wire protocol between the daemon and the page, written from the models of neoaprs/web/protocol.py by scripts/gen-protocol.py: never edited by hand.
// `Command` is what the page sends (tagged by `cmd`), `Message` what the daemon sends (tagged by `type`), `TopicValues` the value of each topic the page follows.

export type Command = PingCommand | AskStatusCommand | CheckUpdateCommand | ReleaseNotesCommand | SubscribeCommand | UnsubscribeCommand | ForgetStationCommand | ForgetAllStationsCommand | ListPortsCommand | FindRadioCommand | FindRadioCancelCommand | SetConfigCommand | BeaconNowCommand | StatusNowCommand | SendMessageCommand | SendKeyCommand | ForgetStationKeyCommand | NewMessageKeyCommand | QueryStationCommand | AskQruCommand | GeneralQueryCommand | MessageRetryCommand | MessageCancelCommand | MessageDeleteCommand | ConversationDeleteCommand | OverheardDeleteCommand | SetStationPathCommand | ClearStationPathCommand | SetStationRfOnlyCommand | SetStationAlertCommand | WeatherSeriesCommand | PacketHistoryCommand | PacketStatsCommand | PositionHistoryCommand | SpeedSeriesCommand | SignalSeriesCommand | StationTrafficCommand | AlertTestCommand | BulletinDeleteCommand | ObjectSetCommand | ObjectKillCommand | BulletinPostCommand | BulletinUnpostCommand | MapEstimateCommand | MapFetchCommand | MapWantedCommand | MapCancelCommand | UpdateNowCommand | UpdateCancelCommand | SkedsWantedCommand | SkedPostCommand | SkedDeleteCommand | ChatSayCommand | PageErrorCommand | RadioAddCommand | RadioRemoveCommand | RadioChangeCommand | RadioTuneCommand | RadioKeyTestCommand | RadioScopeCommand | RadioLevelCommand | StationRadioCommand | FrequenciesCommand | StationTrackCommand | LayerLookCommand | SatelliteLookCommand | IgateLookCommand;

export type Message = HelloMessage | StatusMessage | PongMessage | ErrorMessage | SavedMessage | PortsMessage | StateMessage | PatchMessage | WeatherSeriesMessage | PacketHistoryMessage | PacketStatsMessage | PositionHistoryMessage | SpeedSeriesMessage | SignalSeriesMessage | StationTrafficMessage | AlertResultMessage | UpdateResultMessage | ReleaseNotesMessage | RadioSearchMessage | StationAlertMessage | ChatFreshMessage | RadioAddedMessage | StationTrackMessage | RadioLevelMessage | LayerThingsMessage | SatellitesMessage | IgateSentMessage;

/** The answer to `alert_test`, when the command has ended or run out of its 20 s. */
export interface AlertResultMessage {
  type: "alert_result";
  /** the command ended with exit code 0 */
  ok: boolean;
  /** how it ended, which the page says in its words: `ran` it worked; `exit` it ended with the exit code `status`; `timeout` it did not end within `seconds` and was killed; `no_start` it could not start (the log says why) */
  outcome: "ran" | "exit" | "timeout" | "no_start";
  /** the exit code for `exit`; 0 otherwise */
  status: number;
  /** how long a run may take, in seconds */
  seconds: number;
  /** for `exit`, the first line the command wrote to stderr, its own words (`no display`); empty otherwise */
  line: string;
}

/** Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM` is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`). A page of another device is refused with `setting.local_only`. */
export interface AlertTestCommand {
  cmd: "alert_test";
}

/** When the operator is told about a station: any of the three, each once for each time it happens (it is not told again for every packet), by the message `station_alert` to every page and by the alert command of the settings (`messages/alert`, `messages/alert_command`), as a message to us is. */
export interface AlertWhen {
  /** a packet of the station is heard after it was silent for 30 minutes or more, or for the first time; a packet over the internet counts while `igate/enabled` is on */
  on_air: boolean;
  /** its position comes from farther to this many km from us or nearer (it is outside again only some way beyond: a tenth more, at least 0.5 km); null if the distance is not watched. A station that is that near already when the alert is set is not told until it has been outside */
  within_km: number | null;
  /** a packet of it is heard direct (no digipeater) after none was for 30 minutes or more */
  direct: boolean;
}

/** The ALOHA circle of one radio: the distance within which the stations that radio heard would fill its 1200 baud channel (WB4APR's method, worked out again every minute). */
export interface AlohaCircle {
  /** the radio's id */
  radio: number;
  /** the radius round our position, in km to a tenth */
  km: number;
}

/** An area object (the symbol `\l`): its shape and colour, and how far down and to the right of the object's position it reaches. */
export interface AreaValues {
  /** the shape, which the page says in its words */
  shape: "open circle" | "line" | "open ellipse" | "open triangle" | "open box" | "filled circle" | "line down-left" | "filled ellipse" | "filled triangle" | "filled box";
  /** the colour, which the page says in its words; `unknown` for a number the specification has no colour for */
  colour: "black" | "blue" | "green" | "cyan" | "red" | "violet" | "yellow" | "gray" | "dim black" | "dim blue" | "dim green" | "dim cyan" | "dim red" | "dim violet" | "dim yellow" | "dim gray" | "unknown";
  lat_offset_deg: number;
  lon_offset_deg: number;
}

/** Asks the stations near us for local info (repeaters, events, places): one message to the addressee `QRU` (the services/qruask.py of the daemon), whose `text` is `INFO` (which groups are served near us?), `NEXT` (the next objects of the group asked for last) or a group of 1 to 8 upper-case letters and digits (`RP70`), with a distance in kilometres, 1 to 20000, after it (`INFO 250`). A request to QRU is a broadcast: it is sent once, with no message id, is not kept as a message and is not sent again; it goes by `path` when one is given (digipeater calls or aliases separated by commas, checked as a radio's path is, or `DIRECT` for none), else by the path of messages to the station QRU (its own path, else the radio's), with RFONLY after it unless `rf_only` is false: by radio only. With no `radio` it goes once on each radio of Local info's Send on (the radios whose `radio/<id>/local_info` is ticked; with one radio that can send, that one) that takes frames now; with `radio`, on that radio alone. The answers come as messages to us (they are rows of the topic `messages` like any message) and as the topic `qru`; the objects arrive as objects. All or nothing: answered with an `error`, and nothing is sent on any radio, when the text is none, the station is RX only or no call is set (`transmit.off`, or the interlock's reason), there is no radio (`radio.none`) or none takes frames now, a request to QRU went on one of its radios less than 60 seconds ago with the same text or any less than 10 seconds ago (`qru.too_soon`, with the `seconds` that are left, the longest), or the path is no path or too long with RFONLY (`path.*`, `call.*`). */
export interface AskQruCommand {
  cmd: "qru_ask";
  text: string;
  /** the path the request goes by; left out (or null, or empty) the path of messages to QRU */
  path?: string | null;
  /** RFONLY after the path; left out it is true. The page no longer sends it (the request always goes with RFONLY); a page of an older build may */
  rf_only?: boolean;
  /** the one radio the request goes on, its id: the radio a server answered on (`QruServer.radio`), for a request of a group it listed or one asked again; left out: the radios of Local info's Send on. Refused with `radio.unknown` for a radio that is none, `radio.off` for one that is off, `radio.receive_only` for one that only receives and `radio.not_connected` for one that is not connected */
  radio?: number | null;
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
  /** the radio the attempt went out on, its id (a row of the topic `radios`); null for an attempt kept before the radio was */
  radio_id: number | null;
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

/** Posts a bulletin, an announcement or a group bulletin of ours in the lowest free slot of its kind: `BLN0`..`BLN9` for a bulletin, `BLNA`..`BLNZ` for an announcement, `BLN0`..`BLN9` and the group for a group bulletin (`BLN0HAMS`); a slot is free while no post of ours is in it, an ended one included. Nothing of ours is replaced: with every slot of the kind (of the group) taken it is refused (`bulletin.taken`), and so it is with 36 posts of ours (`bulletin.full`). `text` is at most 67 characters of printable ASCII without `|`, `~` and `{`. It is sent at once and then on the schedule of the specification (a bulletin a few times early and every 20 minutes, an announcement every hour) for `hours`. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_bulletins`, or by an `error` that names the reason. */
export interface BulletinPostCommand {
  cmd: "bulletin_post";
  kind: "bulletin" | "announcement" | "group";
  /** the group of a group bulletin, 1 to 5 letters and digits (written in capitals); ignored for the other kinds */
  group?: string;
  text: string;
  /** how long it is sent after its first packet, in hours: 1, 2, 4, 8 or 12 for a bulletin and a group bulletin, 24, 72 or 168 for an announcement; left out: `status.new_bulletin_hours` of its kind */
  hours?: number | null;
  /** the radios it goes out on, their ids; left out: `status.new_bulletin_radios` */
  radios?: number[] | null;
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

/** How messages go to a call the station book does not hold (a conversation opened by its call): the entries of the topic `call_routes`, as the station's row says them once it is heard. */
export interface CallRoute {
  /** the radio the operator chose for messages to the call (`station_radio`), its id, while that radio is enabled; null for the daemon's choice */
  radio_choice: number | null;
  /** the radio a message to the call goes out on now, its id: the choice while it is in force, else the first radio that can send (`unheard_radio` of `status`); null while there is none */
  radio_now: number | null;
  /** the path the operator set for the call on each radio, by the radio's id as text, as `paths` of a station's row */
  paths: { [key: string]: string };
}

/** The radio's sound card's own levels (the radio's `tx_card` and `rx_card` set them): a slider is drawn only where the card has the control, at the card's level. */
export interface CardLevelsRow {
  /** the card's playback level in percent, what the radio is given to transmit (ALSA's Speaker, PCM or Master control; the playing device's master volume on Windows); null where the card has no such control, the radio has no sound card or its card was never read */
  tx: number | null;
  /** the card's capture level in percent, what it takes from the radio (ALSA's Capture or Mic control; the recording device's master volume on Windows); null as `tx` */
  rx: number | null;
  /** the levels are the card's: its card was read in this run of the daemon, or there is nothing to wait for (this system has no mixer, the radio has no sound card of its own); false while an enabled radio's card was not read yet, and for a radio that is off and was never read in this run. While false the page draws neither the slider nor the modem's - and +, so that the row has one shape from its first paint */
  read: boolean;
}

/** The packets one radio, or the internet, heard in each hour. */
export interface ChannelHours {
  /** the radio that heard them, its id (a row of the topic `radios`, a removed one too); null for the internet */
  radio: number | null;
  /** the packets heard in each hour from the message's `start`, the oldest first, `hours` of them (an hour with none is 0) */
  counts: number[];
}

/** Lines of others came into the chat that were not seen before (newer than the newest this installation had seen, a restart too): told to every page that is open, once for the lines of one reading, and only while `messages/chat_alert` is on. The page alerts as for a message to us (the sound, the notification, the browser tab, as its own choice says). */
export interface ChatFreshMessage {
  type: "chat_fresh";
  /** how many lines came */
  count: number;
  /** the newest of them */
  id: number;
  /** who said the newest */
  call: string;
  /** what the newest says */
  text: string;
}

/** A line of the chat, checked again by the daemon: one line of text of at most 200 characters, without control or invisible characters, never empty. The page shows it as text, never as markup. */
export interface ChatLineRow {
  /** the server's id of the line, which grows by one with each line said */
  id: number;
  /** when the server took it, by the server's clock */
  at: string;
  /** the call that said it, upper case without an SSID of 0 (`OH2GBA`, `OH2GBA-7`) */
  call: string;
  /** what was said */
  text: string;
  /** this installation said it, or it is under our call: it never notifies */
  ours: boolean;
}

/** Says a line in the chat of the HF tests tab: the daemon posts it to the project's server with our call (the setting `station/call`, as the board has it) and this installation's token, over the Internet and never by radio. Cleaned as the server cleans it (white space becomes single spaces, control and invisible characters go, at most 200 characters). Answered by the topic `chat_lines`, which then has it with `ours` true. An `error` when no call is set (the interlock's reason; RX only does not matter), too many lines were said from here in the last minute (`chat.rate`), the chat takes no lines now (`chat.closed`; the topic `chat` then says `closed`), or the project's server could not be reached or would not take it (`chat.unreachable`). */
export interface ChatSayCommand {
  cmd: "chat_say";
  /** the line; not empty once cleaned */
  text: string;
}

/** Where the chat stands. The value of the topic `chat`, told whole as it changes. */
export interface ChatState {
  /** `ok`: the chat was read (or has not been tried yet), and a line may be said. `offline`: the project's server could not be read; `chat_lines` are the last ones known. `off`: the check is off (`NEOAPRS_UPDATE_CHECK=0`): nothing is read or said, `chat_lines` is empty. `closed`: the chat takes no lines now (closed by the project, or for this call); the lines are still shown */
  state: "ok" | "offline" | "off" | "closed";
}

/** Asks the version page now, the question of the daily update check; the daily schedule is left as it was. Answered with `update_result` and then a `status` (with the newer version, if there is one) to the page that asked. */
export interface CheckUpdateCommand {
  cmd: "update_check";
}

/** Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path` (or the `del` of the entry when it was not RF only either), or by an `error`. */
export interface ClearStationPathCommand {
  cmd: "clear_station_path";
  call: string;
  /** the radio whose path for the station is taken away, its id; left out: radio 1 */
  radio?: number | null;
}

/** The settings: each key of the station's settings (`station/call`, `beacon/interval_min`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic `config`, told again after every save, though nothing differs. */
export interface ConfigValues {
  /** the settings in force, key to text; every key is there (the keys of `CONFIG_KEYS`: the station's settings, and `serial/last_port`, the port radio 1's search found last, which the page shows and does not set) */
  values: { [key: string]: string };
  /** the same keys with their defaults, for a form's reset */
  defaults: { [key: string]: string };
  /** the radios' own settings in force, `radio/<id>/<key>` to text, every field of its kind for each radio that is not removed (the fields of `RADIO_TYPES`), and the station's settings of the radios (`email/radio`, the id of the radio chosen for email, empty for none chosen: the radio in force is `status.email_radio`): what `set_config` takes beside `values`; kept apart from `values`, whose form shows none of them; and both keys of every two radios that are not removed and may form a pair (both transmit, both Dummy or both real), enabled or not: `pair/<low>/<high>/enabled` (`true` or `false`) and `pair/<low>/<high>/ssid` (1 to 15, the SSID of the pair's call on the station's base call; empty while none is chosen, and a pair switched on is given the highest free one), by the radios' ids, low first */
  radio_values: { [key: string]: string };
  /** the same keys with their defaults (the field's of the radio's kind; a pair's `false` and empty) */
  radio_defaults: { [key: string]: string };
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
  /** what kind of packet it is: one of these words, which the page says in its words; `telemetry` is one that is not a report, `unknown` a data type the parser does not know */
  kind: "weather" | "nmea" | "query" | "test" | "capabilities" | "agrelo-df" | "shelter" | "space-weather" | "third-party" | "user-defined" | "telemetry" | "unknown";
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
  /** what could not be read, which the page says in its words (the log has the parser's own): `empty` the information field is empty; `position` a position (of an object or an item too); `mice` a Mic-E position; `message` a message; `nmea` a GPS sentence; `damaged` anything else, and a packet kept before there was a code */
  code: "empty" | "position" | "mice" | "message" | "nmea" | "damaged";
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

/** A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed. A page goes by `cmd`, `key` and `code` (with the sentence of `why` for a refusal that passes another's on); `text` is the English sentence for the log, which the page never shows: a code it has no sentence for is said with its plain words of a failure. */
export interface ErrorMessage {
  type: "error";
  /** the command it answers; empty for a frame that was no command (not JSON, not an object, no `cmd`, an unknown one) */
  cmd: string;
  /** the setting it is about (`set_config`), a key of `CONFIG_KEYS`; null for any other error */
  key: string | null;
  /** a stable word for what is wrong, such as `setting.range`, `call.ssid` or `message.too_long`; `failed` for one the operator can do nothing about; `other` for an error that has no code */
  code: string;
  /** the values the sentence is made of, by name, such as `value`, `min` and `max` of `setting.range`, and `why`, the code of the reason, for a refusal that passes another's on (`status.not_sent`, `beacon.not_sent`, `transmit.call`); empty when there are none */
  params: { [key: string]: string | number };
  /** what could not be done and why, in a sentence in English: the command, then the setting if there is one, then the reason (`set_config: station/lat: 95 is not between -90 and 90`) */
  text: string;
  /** the `id` of the request this answers, when the command carried one (only `set_config` does: the `id` of another command is a radio's, a message's or a packet's number and is never echoed); the field is left out otherwise */
  id?: number | null;
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

/** Ends the search of `find_radio`; the page that asked is told `cancelled`. An `error` (`radio.not_running`) when none is running. One search runs at a time, so `radio` changes nothing: it is taken so that the page names the radio in every command of its box. */
export interface FindRadioCancelCommand {
  cmd: "find_radio_cancel";
  /** the radio whose search is ended; left out: the one running */
  radio?: number | null;
}

/** Find my radio: tries the serial ports and the paired Bluetooth devices that the search for the radio looks at (not a KISS TCP address), one after the other and each at the usual speeds, until a TNC answers in KISS or can be put into KISS the way a TNC profile does. The radio's own line is closed while it runs and opened again after it. It writes nothing but a carriage return and, to a TNC that answers with text, the steps of the TNC profiles that put it into KISS; nothing is sent to the air. Told to the page that asked with `radio_search` messages (`trying` before each try, then `found` or `cancelled`); the page puts the answer in the settings. An `error` when a search is running (`radio.busy`), when there is no port to try (`radio.no_ports`), when none answered (`radio.not_found`), for a `radio` that is none (`radio.unknown`) and for one of a type that has no serial line (`radio.no_line`). Only that radio's line is let go (radio 1's when `radio` is left out), the ports another radio or the GPS receiver holds are passed over, and the messages name it. */
export interface FindRadioCommand {
  cmd: "find_radio";
  /** the radio the search is for (its id); left out: radio 1, the packet radio of before */
  radio?: number | null;
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

/** Takes a station's key away (the topic `station_keys`): the first key a station announces is kept, and a later announcement of a different key is not taken until the old one is forgotten. Answered by the `del` of the station's entry, or by an `error` (`lock.no_key` when there is none). */
export interface ForgetStationKeyCommand {
  cmd: "forget_station_key";
  call: string;
}

/** The page shows the station's suggested frequencies (the box of a radio whose type can show them, the HF tests tab): the daemon asks the project's server for them again, unless it asked less than 15 minutes ago or the update check is off (`NEOAPRS_UPDATE_CHECK=0`). The suggested dials are the project's, not a radio's: one list for the station. Nothing is answered; the topic `skeds` and each Mercury radio's `modem` have the list when it changes. */
export interface FrequenciesCommand {
  cmd: "frequencies";
}

/** A frequency the project suggests for the HF radio. */
export interface FrequencyRow {
  /** the band, `40 m` */
  band: string;
  /** the dial with its mode, `7.0541 MHz USB` */
  dial: string;
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

/** A general query sent from here: one press, on one or more radios. */
export interface GeneralAsked {
  /** which query: `aprs` (?APRS?), `igate` (?IGATE?) or `wx` (?WX?) */
  kind: "aprs" | "igate" | "wx";
  /** the information field it went with, `?APRS?`, `?IGATE?` or `?WX?` */
  query: string;
  /** the radios it went on, their ids, in the order of their boxes; what any of them heard is counted in `new` */
  radios: number[];
  /** when it was sent */
  at: string;
  /** the path it went by on the radios that carry one, `RFONLY` last when it was RF only; empty for no digipeaters; null when none was given and those radios' own paths differ */
  path: string[] | null;
  /** when the counting of `new` ends, two minutes after it was sent */
  until: string;
  /** the calls of the stations heard on one of its radios (not as a third-party packet, not from the internet) between the query and `until` that this radio had not heard in the ten minutes before it, in the order they were heard, each once whatever number of radios heard it: most are answers, but a station cannot be told to answer, so this is no more than who spoke after a quiet spell */
  new: string[];
}

/** Asks the stations in radio range a general query of APRS 1.0.1 (the services/generalask.py of the daemon): one frame from our call to our tocall whose information field is exactly `?APRS?` (`kind` `aprs`: who is around? the stations answer with their positions), `?IGATE?` (`igate`: the iGates answer with their capabilities) or `?WX?` (`wx`: the weather stations answer with their weather). It goes once on each radio of asking around's Send on (the radios whose `radio/<id>/ask` is ticked; with one radio that can send, that one) that takes frames now, by `path` (digipeater calls or aliases separated by commas, `OH2RDK-7,OH2RCH-2` or `WIDE1-1,WIDE2-1`, checked as a radio's path is, or `DIRECT` for none; null or empty is each radio's own path, and a radio that carries no path goes without one) with `RFONLY` after it when `rf_only`. The answers are ordinary packets (rows of `stations` and `packets`); the topic `general` tells the query and the stations heard after it. All or nothing: answered with an `error`, and nothing is sent on any radio, when the station is RX only or no call is set (`transmit.off`, or the interlock's reason), there is no radio (`radio.none`) or none of them takes frames now, the path is no path (`path.*`, `call.*`) or is too long with RFONLY (`path.too_long_rf_only`), or the query of that kind went on one of those radios less than 60 seconds ago (`general.too_soon`, with the `seconds` that are left, the longest). */
export interface GeneralQueryCommand {
  cmd: "general_query";
  kind: "aprs" | "igate" | "wx";
  path: string | null;
  /** RFONLY after the path; left out it is true. The page no longer sends it (the request always goes with RFONLY); a page of an older build may */
  rf_only?: boolean;
}

/** The last query of a kind on one radio. */
export interface GeneralSent {
  kind: "aprs" | "igate" | "wx";
  /** the radio, its id */
  radio: number;
  /** when it went on that radio */
  at: string;
}

/** The general queries sent from here: the last one of each kind. Forgotten when the daemon stops. Told whole as it changes. */
export interface GeneralState {
  /** the last query of each kind, the oldest first; empty before one */
  asked: GeneralAsked[];
  /** when the last query of each kind went on each radio, the oldest first: the wait before the next of a kind is each radio's, and a query waits for every radio it would go on (`general.too_soon`) */
  by_radio: GeneralSent[];
}

/** The GPS receiver and what the beacon does with it: the latest fix, whether it can be used, and the beacon of a moving station. Told whole as it changes, at most once a second. */
export interface GpsState {
  /** `gps/source` as in force: where the fixes come from */
  source: "off" | "gpsd" | "serial";
  /** `off`: no source is set; `connecting`: the line to gpsd or the receiver is not up and no fix has come; `no_fix`: it is up and the receiver has no fix; `fix`: the latest fix is fresh; `stale`: the latest fix is older than 120 seconds and is not used (a mobile beacon sends nothing on it) */
  state: "off" | "connecting" | "no_fix" | "fix" | "stale";
  /** why there is no fix to use, as a code the page says in its words, where `state` does not say it already (the log has the feed's own words): `no_port` no port of the receiver is set; `no_address` no address of gpsd is set; `held` the receiver's port is held by a radio; `no_answer` the receiver or gpsd does not answer, or its line was lost; empty for `off`, `fix`, `stale` and a plain wait or no fix */
  reason: "" | "no_port" | "no_address" | "held" | "no_answer";
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
  /** `gps/source` is not `off`: the beacon follows the GPS. With no fresh fix nothing is sent at all (never the home position), which `state` and `reason` say */
  mobile: boolean;
  /** when the next beacon by time is due, for the speed of the latest fix (a turn sends one sooner); null unless the beacon is mobile and has a fresh fix and has sent its first */
  next_beacon_at: string | null;
  /** why the latest mobile beacon of this run went out: `start` (the first fix), `time`, `turn` (a corner), `request` (Beacon now); empty before the first */
  last_beacon_reason: "" | "start" | "time" | "turn" | "request";
  /** when it went out; null before the first */
  last_beacon_at: string | null;
}

/** What one radio heard of a station. */
export interface HeardOn {
  /** how many of the packets of the air (`rf`, `rf-gated` and `dummy` alike) came on the radio */
  count: number;
  /** when the latest of them did; null when that is not known */
  last_at: string | null;
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
  /** whether this page is on the computer the daemon runs on (the loopback, with a request addressed to it): only such a page changes the settings that name a program or an address the daemon runs or fetches from (messages/alert_command, update/url, map/source, web/allowed_hosts) and runs the alert's Test; a page of another device does not show them */
  local: boolean;
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
  /** why the secure connection could not start or go on, when it was asked for, as a code the page says in its words (the log has the details): `no_library` this installation cannot make it; `clock` the clock of this computer is not set; `certificates` the certificates could not be made, read or loaded; `no_port` no port after the page's own was free for it; empty otherwise */
  reason: "" | "no_library" | "clock" | "certificates" | "no_port";
}

/** With `on`, this page shows the lines that Send what I hear has put on APRS-IS (the Internet box of the settings is open, `igate/gate` is on and the page is in front): it is sent `igate_sent` with the kept lines at once and then each line as it is sent. With `on` false, or when the page closes, no more. Never refused. */
export interface IgateLookCommand {
  cmd: "igate_look";
  on: boolean;
}

/** A line that was put on APRS-IS. */
export interface IgateSentLine {
  /** when it was sent */
  at: string;
  /** the radio that heard the packet; null for our own position */
  radio: number | null;
  /** the line as it went to the server, after the gating rules (the TNC2 text): other stations' data, shown as text only */
  line: string;
}

/** The lines put on APRS-IS, to a page that looks (`igate_look`): `whole` true replaces the page's list with `lines` (the newest 200 since the daemon started, oldest first, as the page opened the box), false adds `lines` (one line as it is sent) to its end. */
export interface IgateSentMessage {
  type: "igate_sent";
  whole: boolean;
  lines: IgateSentLine[];
}

/** The login to APRS-IS (neoaprs/services/igate.py): it shows the internet's stations (`igate/enabled`), puts what the radios hear on APRS-IS (`igate/gate`, the iGate), or both, and nothing from APRS-IS is ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon started. Told whole as it changes, at most once a second. */
export interface IgateState {
  /** `igate/enabled` (Show Internet stations) as in force */
  enabled: boolean;
  /** `igate/gate` (Send what I hear) as in force: what the radios hear is put on APRS-IS while `state` is `connected` */
  gate: boolean;
  /** `off`: both ticks are off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `reason` says is missing); `connected`: logged in and verified, packets are gated; `listening`: logged in without a passcode (`gate` is off), so that nothing is gated and the stations of the internet are read only; `unverified`: the server did not accept the passcode, nothing is gated (the connection reads, as `listening` does) and the login is not tried again with another until the settings change */
  state: "off" | "connecting" | "connected" | "listening" | "unverified";
  /** the name the server gave at the login (`T2FINLAND`); empty until it has answered */
  server: string;
  /** why it is not connected, as a code the page says in its words (the log has the connection's own): `no_server` no server is set; `no_call` our call is not set or is none; `unreachable` the server cannot be reached; `offline` the server's name cannot be looked up (no connection); `not_server` it answered as no APRS-IS server, or not in time; `lost` the connection ended; `unverified` the server did not accept the password; empty while `connected`, `listening` and `off` */
  reason: "" | "no_server" | "no_call" | "unreachable" | "offline" | "not_server" | "lost" | "unverified";
  /** packets put on APRS-IS since the daemon started */
  gated: number;
  /** packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), `source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), `frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key */
  dropped: { [key: string]: number };
  /** when the latest packet was gated; null before the first */
  last_gated_at: string | null;
}

/** How this copy of the daemon was installed, which is what the steps of an update depend on (neoaprs/versions.py, neoaprs/cli/installkind.py). */
export interface InstallInfo {
  /** `windows-installer` (the frozen program of the installer), `appimage`, `macos-app` (the Python inside NeoAPRS.app), `deb` (the Debian package, in /opt/neoaprs), `uv-tool` (`uv tool install` of the wheel, which releases before 0.16 offered), `pip` (a plain environment with the wheel) or `source` (a clone of the repository) */
  kind: "windows-installer" | "appimage" | "macos-app" | "deb" | "uv-tool" | "pip" | "source";
  /** the AppImage file this runs from; empty for the other kinds */
  appimage: string;
  /** whether a service starts it: the systemd unit, the launchd agent or the Windows Run key */
  service: boolean;
  /** the architecture of the file it was installed from: `amd64` or `arm64` for a .deb, `arm64` for the macOS app; empty for the other kinds, and for a machine the release has no file for */
  arch: string;
}

/** With `on`, this page looks at the layer (its tick is on, the page is in front and the replay is closed: the page decides); with `on` false, or when the page closes, no more. While a page looks, the daemon asks the layer's source and sends the page `layer_things`. Never refused: a look at a layer whose source is `none` stands and is served once a source is chosen. */
export interface LayerLookCommand {
  cmd: "layer_look";
  layer: "aircraft" | "ships";
  on: boolean;
}

/** The own receiver's state, for its line in Settings. It says nothing of addresses or ports. */
export interface LayerReceiver {
  /** `looking` until its first answer or connection; `receiving` after an answer in the expected form (AIS: from the first AIS sentence of a connection); `no_answer` after a failure, a wrong answer or a lost connection; `connected` (AIS only) the connection is made and nothing has come yet (a receiver with no ship in range is silent); `no_ais` (AIS only) the source sent something that is not AIS first, or ended the connection without an AIS sentence */
  state: "looking" | "connected" | "receiving" | "no_answer" | "no_ais";
  /** what it gave with a position at its last answer (aircraft), or the ships held now (AIS) */
  things: number;
  /** its last answer in the expected form (AIS: the last sentence decoded); null before one */
  heard_at: string | null;
}

/** An aircraft or a ship, as its source tells it. Every field is always there; one that is not the layer's is empty or null. */
export interface LayerThing {
  /** an aircraft's type as the source names it; empty when not known */
  type: string;
  /** an aircraft's ICAO address as the source gives it, lower case (it may begin with `~`); a ship's MMSI */
  id: string;
  lat: number;
  lon: number;
  /** the time of its position */
  at: string;
  /** where the mark points; null: no direction (drawn as a diamond) */
  heading_deg: number | null;
  speed_kmh: number | null;
  /** an aircraft's flight, a ship's name; empty when none */
  name: string;
  /** an aircraft that says it is in an emergency (or squawks 7500, 7600 or 7700) */
  emergency: boolean;
  /** an aircraft's height */
  altitude_m: number | null;
  /** an aircraft's vertical speed in metres a second, above zero climbing; null when not told (a ship's is null) */
  vertical_ms: number | null;
  /** an aircraft's registration (`OH-LZA`); empty when not known */
  registration: string;
  /** an aircraft's emitter category as the source gives it, upper case (`A3`, `A7`, `B1`); empty when not known */
  category: string;
  /** an aircraft's ICAO type designator, upper case (`A321`, `EC35`); empty when not known */
  designator: string;
  /** a ship's AIS type of ship and cargo; null when not known */
  ship_type: number | null;
  /** a ship's course over ground, an aircraft's ground track; null when not told (a heading is not a course) */
  course_deg: number | null;
  /** a ship's destination as it gave it; an aircraft's: the ICAO code of the airport it is going to, upper case; empty when not known */
  destination: string;
  /** an aircraft's departure: the ICAO code of the airport it left, upper case; empty when not known */
  origin: string;
  /** the place of the airport `origin` names, from the table the program carries; empty when `origin` is empty or not in the table */
  origin_place: string;
  /** the place of the airport `destination` names, from the table the program carries; empty for a ship, and when `destination` is empty or not in the table */
  destination_place: string;
}

/** A layer's whole table, to each page that looks at it and is not behind: at once on `layer_look`, after every answer of the source, at most every 5 s for an AIS receiver, when things grow too old, and when the source in force changes (then with the new `source` and no things). */
export interface LayerThingsMessage {
  type: "layer_things";
  /** the daemon's time when the table was sent; the age of each thing's `at` is told by it, not by the page's clock */
  at: string;
  layer: "aircraft" | "ships";
  /** the source in force that the things are from */
  source: "none" | "adsbfi" | "adsblol" | "fintraffic" | "aisstream" | "radarcape" | "receiver";
  /** true when the last question failed or was not in the expected form, the connection is down, or there is no position to ask for; `things` keeps the last things then */
  away: boolean;
  things: LayerThing[];
  /** only in the first table a page gets on `layer_look`, else empty: the way each thing of `things` went in the last 30 minutes while the source was asked (it is asked on for 2 minutes after the last page stopped looking), oldest first: the last minute whole, older points at most one a minute and only where the way bends by more than 50 m */
  trails: LayerTrail[];
}

/** The way one thing went: its id, and its places as [lon, lat, time], oldest first. */
export interface LayerTrail {
  id: string;
  points: [number, number, string][];
}

/** Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a port of the machine: it is typed. With `radio`, also the sound cards its modem lists while that radio's type has a modem on a sound card (Mercury, Sound card), and the proposals leave out what the other radios and the GPS receiver hold; each row says who holds it (`held_by`). An `error` for a `radio` that is none (`radio.unknown`). */
export interface ListPortsCommand {
  cmd: "list_ports";
  /** the radio the list is for (its id): the sound cards and the proposals are its own; left out: the ports alone, with no sound card and no proposal */
  radio?: number | null;
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

/** Starts a dry run: how big the detailed map for `map/radius_km` and `map/maxzoom` round our position will be. Answered by the topic `map` (state `estimating`, then `estimate` filled in), or by an `error` when no job can start (no position, or a job is running). */
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

/** One layer of traffic in the topic `map`: where its things come from now and what the station is offered. */
export interface MapLayer {
  layer: "aircraft" | "ships";
  /** the source in force: the one chosen in Settings while it is offered, else `none` (nothing is asked, and the Layers box has no row) */
  source: "none" | "adsbfi" | "adsblol" | "fintraffic" | "aisstream" | "radarcape" | "receiver";
  /** the sources the Settings list holds, `none` first: `fintraffic` only where the map's circle reaches its waters; `aisstream` (with the operator's own key, `map/ships_key`) everywhere */
  offered: ("none" | "adsbfi" | "adsblol" | "fintraffic" | "aisstream" | "radarcape" | "receiver")[];
  /** the own receiver's state while `source` is an own receiver (`radarcape` or `receiver`); else null */
  receiver: LayerReceiver | null;
  /** why the service in force gives nothing, where the operator can mend it: `key_refused` AISStream did not take the key of `map/ships_key` (asked again after a longer wait, and at once when the key is saved; cleared by a connection that is taken); empty otherwise */
  problem: "" | "key_refused";
}

/** Why a map job failed, as a code the page says in its words, with the values of its sentence (the log has the details). */
export interface MapProblem {
  /** `no_position` the station has no position; `slow` the map server was too slow; `unreachable` it could not be reached; `no_build` no daily build was found (`days`: how far back it was looked for); `too_big` the map would be bigger than it may be (`size` and `max`, in MB); `no_space` the disk is full; `failed` anything else (the log says why) */
  code: "no_position" | "busy" | "slow" | "unreachable" | "no_build" | "too_big" | "no_space" | "failed";
  /** the values of the sentence, by name; empty for a code that has none */
  params: { [key: string]: number };
}

/** A download that did not move for a while is begun again: the page says "no progress: trying again (2 of 3)". */
export interface MapRetry {
  /** the try that is begun */
  attempt: number;
  /** the tries in all */
  tries: number;
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

/** The base map: the files, the area and detail the settings ask for, the size estimated, the job that is running, the ALOHA circles and the layers of traffic. The value of the topic `map`, told whole at most four times a second. */
export interface MapState {
  /** `none`: there is no detailed map. `ready`: there is one. `estimating` and `downloading`: a job is running (`step` and `percent` say how far). `error`: the last job failed and `problem` says why; the map files are as they were */
  state: "none" | "estimating" | "downloading" | "ready" | "error";
  /** what the running job is doing: looking for the latest build (`build`), making the world map (`world`) or the detailed map (`area`); empty while no job runs */
  step: "" | "build" | "world" | "area";
  /** how far the step is; null when it cannot say (the build has no bar) */
  percent: number | null;
  /** the size so far of the file the step is making, in bytes (it grows while the download moves); null when no file is being made yet */
  downloaded: number | null;
  /** a download that has not moved for a while is begun again: which try this is; null when all is well */
  retry: MapRetry | null;
  /** why no job can be started now: `no_position` the station has no position, `busy` a job is running; empty when one can */
  blocked: "" | "no_position" | "busy";
  /** why the last job failed; null if it did not, and while a job runs */
  problem: MapProblem | null;
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
  /** the ALOHA circles round our position, one for each radio that is on whose type shares a 1200 baud channel (Packet) and whose stations heard fill it, in the order of the boxes; none without a position */
  aloha: AlohaCircle[];
  /** the layers of traffic, the aircraft and then the ships: where each one's things come from now, what Settings offers, and an own receiver's state */
  layers: MapLayer[];
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
  /** the radio a message that came in came on, its id; null for a message of ours (its attempts say) and for one from the internet or kept before the radio was */
  radio_id: number | null;
  /** for a message of ours on its way (`sending`, `queued`), the radio its next attempt goes on: the one its first attempt went on, which it keeps until it ends unless Route changes or that radio is switched off, else the station's radio now (plan rule 3.2); null for every other message and while there is no radio it may go on. The page shows Route, the path and the radio's state of this radio */
  radio_now: number | null;
  /** `queued`: it waits, with no attempt made, for another message of ours to the same station to be acked, rejected, failed or cancelled (one message to a station is on the air at a time; one not expected to be acked, given 1 or 2 attempts, never waits); it can be cancelled, and becomes `sending` when its turn comes; `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt, or the reason in `failure`; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; `received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for) */
  state: "queued" | "sending" | "acked" | "rejected" | "failed" | "unconfirmed" | "cancelled" | "received" | "overheard";
  /** why a `failed` message failed when it is not that no answer came: `too_long_for_radio`, its frame does not fit the radio it goes out on (it may have been sent before the radio changed; sent again, it is refused with `message.too_long_for_radio` while it does not fit); null for every other message, and for a failed one that had no answer */
  failure: "too_long_for_radio" | null;
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
  /** the signal-to-noise ratio of the packet that carried it, dB: for a message that came in, its own packet's; for one of ours, the ack's (or the reject's) that settled it, null until one came; null too when that packet's radio gave none and for a message kept before readings were */
  snr: number | null;
  /** the received strength of that packet, dBm; null as `snr` is, and for the Mercury modem, which gives none */
  rssi: number | null;
  /** how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept */
  route: string;
  /** what the message is besides text (encrypted messages, a daemon started with `--encryption`): empty for a plain message; `key` an announcement of the sender's public key (`send_key`; for one that came in, the key was taken, or is the one kept already); `key_other` an announcement that differs from the key kept for the station, not taken (`forget_station_key` first); `open` an encrypted message that was read, `text` is what it says (for one of ours, what was written); `shut` an encrypted message that cannot be read here (no key from the sender, no key of ours, or not for us), `text` is the ciphertext as it came */
  seal: "" | "key" | "key_other" | "open" | "shut";
}

/** The modem program behind a radio's line, while its type is one the daemon starts a modem for (the Mercury modem, Direwolf on a sound card): the program's state, whether it keys the radio now and whether it hears a signal. */
export interface ModemState {
  /** `starting`: the program was started (or a Mercury something else runs is not yet answering on its control port); `running`: its control port answers; `waiting`: it is not running, `reason` says why */
  state: "stopped" | "starting" | "running" | "waiting";
  /** why the modem is `waiting`, as a code the page puts in its own words in the language of the viewer (the log has the English): `not_installed` this installation carries no such program; `stopped` the program ended and is started again; `network` the program listens on the network and is not run; `no_port` no port was free for it; `not_started` the program could not be started or its configuration written; `sound_card` the program could not open its sound card (or, on Windows, find it among the devices) and was ended, another is to be chosen; `keying` the program could not open its keying device (or, on Windows, found several CM108 chips) and was ended, another way of keying is to be chosen; `keying_in_use` its keying port is in use by another program (Mercury: Windows error 5, or the device is busy) and the program was ended; it is started again after a back-off for as long as the radio is on; `keying_missing` its keying port is not there and the program was ended, started again in the same way; `ports_taken` another program listens on the KISS or control port of the modem's pair (most likely a Mercury the operator started himself): no modem is started beside it, no line connects to it, and the start is tried again after a back-off; the radio's type `mercury-own` is the one for such a Mercury; `receive_stalled` the program heard nothing (its receive side stalled) again after three restarts in an hour and is not started again until the radio is; empty unless the state is `waiting` */
  reason: "" | "not_installed" | "stopped" | "network" | "no_port" | "not_started" | "sound_card" | "keying" | "keying_in_use" | "keying_missing" | "ports_taken" | "receive_stalled";
  /** the modem's mode, the same for every station of the type: `DATAC3` (Mercury), `AFSK1200` (Direwolf) */
  mode: string;
  /** the modem keys the radio now: a frame is on the air (about four seconds), or the tune tone or the keying test is on */
  keyed: boolean;
  /** another station's signal is on the channel and our frames wait: for 20 s at most (`BUSY_HOLD_MAX_SEC`), after which it is false while the channel stays busy, since nothing waits any more. The daemon judges it from the modem's spectrum (a signal as wide as a frame; a step in the noise or a carrier is none) while it reads that, else it is the modem's own fixed-threshold detector */
  busy: boolean;
  /** `tune` while the tune tone is on (`radio_tune`), `key` during the keying test (`radio_key_test`); empty otherwise. Our frames wait while either is on */
  test: "" | "tune" | "key";
  /** the signal-to-noise ratio of the latest frame decoded, in dB; null before one */
  snr: number | null;
  /** how many times the radio was keyed since the modem started */
  frames_keyed: number;
  /** the longest packet the modem carries whole, in bytes (Mercury 123): a longer message is refused, a longer beacon has its comment cut; null for AX.25's own (Direwolf) */
  max_frame: number | null;
  /** the sound card the modem runs with (`mercury/sound_card`, or the daemon's choice while that is empty); empty for the system's default device */
  sound_card: string;
  /** the frequencies the project suggests, one to five, by band, the longest first: the list of the project's file (site/frequencies.json, asked a minute after the start and when a page sends `frequencies`), else the dial the version page names, else the built-in five; the page shows them in the Mercury radio's box as they are, with the words "suggested": they are not read from the radio */
  frequencies: FrequencyRow[];
  /** how it keys the radio (`mercury/keying`, or the daemon's choice while that is empty): `vox`, `cm108`, `rts:PORT` or `dtr:PORT` */
  keying: string;
  /** the daemon reads the modem's UI interface: the spectrum scope can be shown (`radio_scope`) and the transmit gain is set live; false for a modem without the interface (the page shows no scope, and a change of the gain restarts the modem) */
  scope: boolean;
  /** the transmit gain the modem runs with, in dB (`mercury/tx_gain_db`); the tune tone follows it */
  tx_gain_db: number;
  /** the peak of the latest transmission (a frame, or the tune tone) in whole dBFS, as the modem says it; 0 or more clips in the sound card; null before one, and while the interface is not read */
  tx_peak_dbfs: number | null;
  /** the receive level as it is now, on Direwolf's own scale (0 to about 200: about 50 for most stations, under 5 too low, over 110 too high; `LIMITS.sound_card` has the zones): said every two seconds and at each packet heard; null while its Direwolf does not run, and for a modem that has none */
  rx_level: number | null;
}

/** Makes a new key pair of ours in place of the old: the stations that have the old key must be sent the new one (`send_key`) before they can read us again. The fingerprint of the new key comes with the next `status`. Answered by that `status`, or by an `error` when the key could not be kept. */
export interface NewMessageKeyCommand {
  cmd: "message_key_new";
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

/** Makes an object or an item of ours, or changes the one of that name (a changed object starts its schedule again, and is sent at once, never sooner than a minute after its last packet). `name` is 1 to 9 characters for an object and 3 to 9 for an item, printable ASCII without `!`, `_`, `|` and `~` and without a blank at either end, and not our own call or the call of a station; `lat` and `lon` the position in decimal degrees; the symbol is a table character and a code character; `comment` at most 43 characters (36 with a course or speed); `course_deg` and `speed_kmh` the course and speed, each or both or none; `path` the digipeaters, calls separated by commas, or `DIRECT` for none at all (null or empty: `beacon/path`); `qru_group` the group of QRU it belongs to (up to 8 letters and digits, not `INFO` or `NEXT`; empty for none) and `on_request` true to send it only to a station that asks for it, never on the schedule; `radios` the radios it goes out on (their ids). Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason. */
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
  /** the radios it goes out on, their ids */
  radios: number[];
}

/** Removes every message we only overheard `from_call` sending to `to_call` (the state `overheard`, that sender, that addressee: one pair of the Messages list's overheard rows) from the database in one write, from the daemon and from every page: each message's row is a `del` of the topic `messages`. The conversations are not touched: a message we sent or one sent to us is never removed by this. Answered by the `del`s, or by an `error` (no overheard message of that pair). */
export interface OverheardDeleteCommand {
  cmd: "overheard_delete";
  from_call: string;
  to_call: string;
}

/** One bulletin, announcement or group bulletin of ours: its text and where its schedule stands. The rows are the values of the topic `own_bulletins`, keyed by `slot` (`BLN1`): a bulletin that is posted, and each time it is sent, is a `set` of its row, one that is deleted (`bulletin_unpost`) a `del`. One whose schedule is over stays, with a null `next_at`, until it is deleted. */
export interface OwnBulletinRow {
  /** the addressee: `BLN1`, `BLNA`, `BLN3HAMS` */
  slot: string;
  /** the group of a group bulletin (`HAMS`); empty for any other */
  group: string;
  kind: "bulletin" | "announcement" | "group";
  text: string;
  /** how long it is sent after its first packet, in hours: 1, 2, 4, 8 or 12 for a bulletin and a group bulletin, 24, 72 or 168 for an announcement */
  hours: number;
  /** when the text was posted */
  posted_at: string;
  /** how often it was sent */
  sent: number;
  /** when it was last sent; null while it has not been sent */
  last_sent_at: string | null;
  /** when it is sent next; null when its schedule is over (a bulletin: now, after 2 and 6 minutes, then every 20 minutes, 30 while a radio it goes out on is Mercury or LoRa; an announcement: the same early, then every hour; either until `hours` after the first); a repeat after the radio's random pause, which is never longer than the wait nor past the end */
  next_at: string | null;
  /** the radios it is set to go out on (Send on), their ids, ascending, one at least, kept also while off; the radios it goes on now are those of them that are on and can send (with one radio that can send, that one; with none of them on, none) */
  radios: number[];
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
  /** the radios it is set to go out on (Send on), their ids, ascending, one at least, kept also while off; the radios it goes on now are those of them that are on and can send (with one radio that can send, that one; with none of them on, none) */
  radios: number[];
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
  /** when it is sent next: 1, 2, 4 ... minutes after the slot of the last packet, never more than the net cycle time of its path apart (30 minutes on Mercury and LoRa: the radio's floor), plus the radio's random pause, which is never longer than the wait; a time that has passed means it waits for the radio or for the call; null for one that is `on_request` */
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
  /** the station the packet is from: `source`, or for a third-party packet the source of the packet inside it */
  sender: string;
  destination: string;
  /** the digipeaters, the one that repeated it marked with `*`; for a packet from the internet everything between the destination and the colon of the line (`TCPIP*`, the q-construct `qAC`, the server `T2FINLAND`) */
  path: string[];
  /** a telemetry report is `other`; its `decoded.type` is `telemetry` */
  kind: "position" | "message" | "object" | "item" | "status" | "other" | "undecoded";
  /** how a packet that was heard on the radio reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours and for one from the internet */
  route: string;
  /** the radio the packet came on or went out on, its id (a row of the topic `radios`, a removed one too); null for a packet from the internet */
  radio_id: number | null;
  /** the signal-to-noise ratio the radio measured of the frame, dB, tied to the frame where it was read (the Mercury modem and the Dummy Mercury radio give it); null for a packet of ours, one from the internet and one of a radio that gives none (a KISS TNC) */
  snr: number | null;
  /** the received strength the radio measured of the frame, dBm; null as `snr` is, and for the Mercury modem, which gives none */
  rssi: number | null;
  /** the channel the packet came by, set once where it was made: `rf` heard on the radio (direct or by digipeaters; every packet of ours too), `rf-gated` heard on the radio as a third-party packet that an iGate put on the air, `is` received from APRS-IS over the internet (never on the air), `dummy` made up by the Dummy radio (it works as `rf` does and never goes to the internet) */
  via: "rf" | "rf-gated" | "is" | "dummy";
  /** the iGate, for a third-party packet (`via` is `rf-gated`): `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet */
  gate: string;
  /** the packet as a line of TNC2 monitor text */
  tnc2: string;
  decoded: DecodedPosition | DecodedMessage | DecodedObject | DecodedItem | DecodedStatus | DecodedTelemetry | DecodedOther | DecodedUndecoded;
}

/** Asks for what the statistics card counts from the packet log: the packets heard by the hour by radio, what went out on each radio, the packets that came by several ways and the copies sent and gated in the last hour. Answered with a `packet_stats` message to the page that asked. */
export interface PacketStatsCommand {
  cmd: "packet_stats";
}

/** The answer to `packet_stats`. The packets heard (not sent by us; none from APRS-IS while `igate/enabled` is off) by the hour of the clock over the week the log keeps, or since its oldest packet when that is younger, for each radio and the internet that heard any, the running hour last; what went out and the packets heard more than once over the last 24 hours; the copies of the last 60 minutes. Hours that are over are counted once; the answer is at most a minute behind. */
export interface PacketStatsMessage {
  type: "packet_stats";
  /** the top of the first hour counted, UTC */
  start: string;
  /** how many hours each list of `heard` has: from `start` to the running one */
  hours: number;
  /** by radio, in the order of their ids, the internet last; one that heard nothing in the span is left out */
  heard: ChannelHours[];
  /** by radio, in the order of their ids; one that sent nothing in the last 24 hours is left out */
  sent: RadioSent[];
  /** the packets the radios heard in the last 24 hours, a packet heard by several ways counted once (the same source, destination and information field within a minute of the clock) */
  packets: number;
  /** the frames those packets came in: `frames` less `packets` is how many came again by another way */
  frames: number;
  /** the copies the digipeater sent in the last 60 minutes */
  repeated_hour: number;
  /** the packets the iGate put on APRS-IS in the last 60 minutes; null while `igate/gate` (Send what I hear) is off */
  gated_hour: number | null;
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

/** What the pairs of radios passed onto this radio from one other radio since the daemon started. */
export interface PassStats {
  /** the radio the packets were heard on, by its id */
  heard_on: number;
  /** frames sent on this radio */
  sent: number;
  /** when the latest of them went out; null for none yet */
  sent_at: string | null;
  /** frames left unsent by this radio's limits: the burst on a fast radio; the budget, its share for packets other than messages and acks, a station's share of messages, the 30-minute floor, a frame already waiting, or a keyed or busy channel past 30 s on a slow one */
  held: number;
  /** frames left unsent because they are longer than this radio carries */
  too_long: number;
}

/** What changed in a topic: apply the ops in order; the copy is then at `rev`. An op says what the item is, not what to add, so an op that is applied twice ends where it should. Changes are told on a tick of 100 ms (a radio's row in `radios` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key. */
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
  /** the radio of the station that holds the port now (its id), 0 for the GPS receiver; null while none of ours does. A port another radio holds is not proposed, and the page greys it with the holder's name */
  held_by: number | null;
  /** which USB device the port sits on together with the others of one radio (an opaque token: equal for a sound card and the serial ports on one radio's own USB hub, or on one USB device; neoaprs/usbtie.py); null where it is not known (Windows, macOS, a port that is not USB, a Bluetooth device). The page orders the keying lines by it and never shows it */
  usb_group?: string | null;
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
  /** the sound cards the radio's modem lists, for a `radio` named whose type has a modem on a sound card (Mercury, Sound card) while the program is installed; empty otherwise */
  sound_cards: SoundCardRow[];
  /** the keying the daemon proposes with the card it proposes (`vox`, `cm108`, `rts:PORT` or `dtr:PORT`): the page preselects it and stores it as the radio's `keying` while that is empty; empty when no sound card is listed */
  keying: string;
  /** the radio the list was asked for (`radio` of `list_ports`: the sound cards and the proposals are its own); null for a list that named none. The ports are the machine's, the same whoever asked */
  radio: number | null;
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
  /** how far back to go: the replay offers 1, 3, 6, 12, 24 (the choices of the Stations tab's On map for) and 48, 72, 168 (2, 3, 7 days; the packet log keeps 7) */
  hours: number;
}

/** The positions of the stations over the span asked for, the answer to `position_history`, from the packet log: every position heard in it (a station's own, or the one inside a third-party packet), the live objects and items heard by their names, and what we sent under our call (our beacons, and our objects by their names). While `igate/enabled` (Internet stations) is off, no packet that came from APRS-IS is in it, whenever it was received: what was heard on the radio only, an iGate's third-party packets too, as the stations topic shows then. A station's points are thinned, the more the longer the span (REPLAY_THINNING of neoaprs/web/views.py): up to a day, a point less than 10 m from the point kept before it or less than 30 s after it is left out; up to three days, 200 m and 2 minutes; a week, 300 m and 5 minutes. The last point is always there, and so is the one where a station still was just before it moved off. The latest 1 000 000 position packets at most are read: on a feed busier than that, the span begins at the first of them. */
export interface PositionHistoryMessage {
  type: "position_history";
  /** the hours asked for */
  hours: number;
  /** where the replay begins, UTC: `hours` hours before `end`, or the oldest packet the log keeps when that is later (a daemon that has run for less than the span, or a log busier than the packets read) */
  start: string;
  /** where the replay ends, UTC: when the daemon answered */
  end: string;
  /** [time, lat, lon] for each position kept, the oldest first, by the station's call (an object's or item's name); a station with no position in the span is not in it */
  stations: { [key: string]: [string, number, number][] };
}

/** The Sent for a new post of each kind starts with, in hours: the one posted last of that kind, else 4, 72 and 4. */
export interface PostHours {
  bulletin: number;
  announcement: number;
  group: number;
}

/** The request we sent last. */
export interface QruAsked {
  /** what was asked (`INFO`, `RP70 150`) */
  text: string;
  /** when it was sent */
  at: string;
  /** the radios it went on, their ids, in the order of their boxes */
  radios: number[];
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
  /** the names of the objects heard from the server, on a radio that request went on, since it, until `settles_at` (or the last answer, before a closing line); each is an ordinary object of the stations and the map */
  received: string[];
  /** when the counting of `received` ends, 30 seconds after the closing line (a late object may still come); null before a closing line. Fewer `received` than `sent_objects` after it means objects were lost */
  settles_at: string | null;
  /** the radio its latest answer came on, its id: a request of one of its groups, and one asked again, goes on it; null when the packet named none */
  radio: number | null;
}

/** The servers that answered a request for local info, and the last request. What is older than an hour is forgotten, with the daemon's restart. Told whole as it changes. */
export interface QruState {
  /** the last request sent from here; null before one, and an hour after it */
  asked: QruAsked | null;
  /** the servers that answered in the last hour, by call */
  servers: QruServer[];
}

/** Asks a station a directed query (APRS 1.0.1 chapter 15): a message to it with the text of the query, `?APRSP` (`kind` `position`: its position packet), `?APRSS` (`status`: its status report), `?APRSD` (`heard`: the stations it hears direct, as a message), `?APRST` (`trace`: the path our query reached it by, as a message), `?WX?` (`weather`: its weather report; a general query in the specification, which many stations do not answer when it is addressed to them) or the operator's own (`custom`, with `text`: `?APRSH OH2GBA-15`, `?PING?`). The query is sent once, without a message id: no attempts follow and no ack is expected. It is kept as a row of the topic `messages` to the station, in state `sending` until it has been transmitted and then `unconfirmed`, whose `text` is the query; the page shows such a row (an `out` message with no `msg_id` whose text begins with `?`) as a note of what was asked. The answer is whatever the station sends: a packet (the station's card changes) or a message (a row `in`). Not more than one query of the same text to a station in 60 seconds. Answered with an `error` when the station is not in the station book (`station.unknown`), is no station that takes messages (`query.not_capable`: an object, an item, ourselves, a station whose position says it takes none and that never sent a message), the same query was sent less than 60 seconds ago (`query.too_soon`) or the message is refused as `send_message` refuses it (the call is not set, the radio is silent); a `custom` text that is no query is refused as invalid. */
export interface QueryStationCommand {
  cmd: "query";
  call: string;
  kind: "position" | "status" | "heard" | "trace" | "weather" | "custom";
  /** the query of `custom`, as the operator wrote it: after the spaces at its ends are taken off it begins with `?` and has something after it, is printable ASCII without `|`, `~` or `{` and at most 67 characters, the text of a message; it is sent upper-cased. Absent or null for the other kinds */
  text?: string | null;
}

/** Adds a radio of the type (`type`, a `key` of `RADIO_TYPES`): after the others, enabled, with the defaults of its kind, the name typed (empty or left out: none), and started at once. Answered with `radio_added` (its id) to the page that asked, at once, and then the `set` of its row in `radios` (the topic is told at most four times a second: the row may come a few messages later, so a page that opens the new radio waits for it), or with an `error`: `radio.unknown_type`, `radio.name_form`, `radio.name_taken`, `radio.name_label`, `setting.not_stored`. */
export interface RadioAddCommand {
  cmd: "radio_add";
  type: string;
  /** the name typed; left out or empty: none */
  name?: string;
}

/** The answer to `radio_add`, to the page that asked: the id the new radio was given. */
export interface RadioAddedMessage {
  type: "radio_added";
  id: number;
}

/** What we decided the radio's type may do (neoaprs/radiotype.py `Allowed`): a control exists only where it is true. */
export interface RadioAllowed {
  /** our frames on it may carry digipeaters: the path controls are shown for it; false: every frame goes direct */
  paths: boolean;
  /** it may repeat what it hears (its own Digipeater tick, `radio/<id>/digipeat`) */
  digipeat: boolean;
  /** a moving station's SmartBeaconing applies on it; elsewhere the timed beacon goes with the latest fix */
  smart_beacon: boolean;
  /** internet gateways hear its kind */
  gateway_heard: boolean;
  /** it is a 1200-baud shared channel: the ALOHA circle is worked out from what it hears */
  shared_channel: boolean;
}

/** The radio's own beacon timer. */
export interface RadioBeaconState {
  /** when our position last went out on it; null before one */
  last_sent: string | null;
  /** when the next timed beacon is due on it: its slot and the radio's random pause; null while none is planned (off, a moving station, the radio off) */
  next_due: string | null;
  /** the interval in force on it, in minutes: `beacon/interval_min` raised to the radio's own floor; 0 while the beacon does not go out on it (off, Send on not ticked, the radio off) */
  interval_min: number;
  /** why the latest beacon due on it did not go out (`transmit.off`, `beacon.not_sent`); null after one that did */
  problem: RadioProblem | null;
}

/** What the radio's type can do (neoaprs/radiotype.py `Can`): the controls of its box. */
export interface RadioCan {
  /** Find my radio (a serial line: `find_radio` with this radio) */
  find: boolean;
  /** its line's log can be shown (`lines`) */
  terminal: boolean;
  /** Tune (`radio_tune`) */
  tune: boolean;
  /** the keying test (`radio_key_test`) */
  key_test: boolean;
  /** the spectrum scope (`radio_scope`); whether it is shown now is the modem's `scope` */
  scope: boolean;
  /** the transmit gain (`radio/<id>/tx_gain_db`) */
  tx_gain: boolean;
  /** the station's suggested frequencies are shown in its box */
  frequencies: boolean;
  /** it can send: false for a receive-only type, which is never a message's, the beacon's, an object's, a bulletin's or the email radio, and whose line is never written to */
  transmit: boolean;
  /** its receive level is shown in its box (its modem's `rx_level`) */
  rx_level: boolean;
}

/** Changes what is given of the radio and nothing else: its `name` (empty: none), its `type` (one of its own kind), its Enable (`enabled`) or its place in the list (`position`, from 1; the others keep theirs, a tie goes by id). Stored, then in force; the radio is restarted when its type or its Enable changed what runs. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on is not switched off), `radio.name_form`, `radio.name_taken`, `radio.name_label`, `radio.type_kind`, `radio.unknown_type`, `setting.not_stored`. */
export interface RadioChangeCommand {
  cmd: "radio_change";
  /** the new type; left out: unchanged */
  type?: string | null;
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
  /** the new name; left out: unchanged */
  name?: string | null;
  /** the new Enable; left out: unchanged */
  enabled?: boolean | null;
  /** the new place; left out: unchanged */
  position?: number | null;
}

/** The operator's own values of the radio where its kind has them (`radio/<id>/beacon`, `radio/<id>/status`, `radio/<id>/ask`, `radio/<id>/local_info`, `radio/<id>/path`, `radio/<id>/digipeat`), as they are in force. */
export interface RadioChoices {
  /** Send on: the beacon goes out on this radio (with one radio on, it goes on that one whatever this says) */
  beacon: boolean;
  /** the status's Send on: the status report goes out on this radio; false by default (with one radio that can send on, on that one whatever this says; with several, while none that is on is ticked, on none); false for a radio that only receives */
  status: boolean;
  /** Ask around's Send on: a general query (`general_query`) goes out on this radio; read as `status` is */
  ask: boolean;
  /** Local info's Send on: the request to QRU that names no radio (`qru_ask`) goes out on this radio; read as `status` is */
  local_info: boolean;
  /** the digipeaters of its frames as the setting holds them (empty: the recommended path of the station's symbol, `DIRECT`: none); null for a kind that has no path */
  path: string | null;
  /** its digipeater is on; null for a kind that may not repeat */
  digipeat: boolean | null;
}

/** A device the radio holds now in the station's table of resources: no other radio, and not the GPS receiver, is given it. */
export interface RadioHold {
  /** what kind of device: a serial port, a sound card, the keying line's port, the port pair of a Mercury modem */
  resource: "serial" | "sound_card" | "keying" | "modem_ports" | "gps";
  /** the device as the table holds it: a serial port's resolved path (`/dev/ttyUSB0`, `COM3`), a sound card's id, the broadcast port of a Mercury pair (`8100`) */
  value: string;
}

/** The keying test on the radio's modem: keys it for one second, so that the operator sees it go to transmit and come back: with next to no audio (Mercury's TUNE at its quietest level) where the keying is a line (RTS, DTR, CM108), with the tune tone where the radio keys on audio (VOX); the radio's row says `modem.test: "key"` meanwhile. The same refusals as `radio_tune`. */
export interface RadioKeyTestCommand {
  cmd: "radio_key_test";
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
}

/** The receive level of a Sound card radio as its Direwolf says it ten times a second: with `on`, this page is sent `radio_level` for that radio, the level now at once and then each change, while it shows the level (the radio's box is in view); with `on` false, or when the page closes, no more. A page that is behind is skipped. Every page has the slower `modem.rx_level` of the radio's row. Refused, with `on`, for a radio that is none (`radio.unknown`) and for one whose type has no receive level (`radio.no_modem`, with its `name`: `can.rx_level` of its row is false); `on` false is never refused. */
export interface RadioLevelCommand {
  cmd: "radio_level";
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
  /** true starts the levels for this page, false stops them */
  on: boolean;
}

/** A Sound card radio's receive level as it is now, to a page that asked for it (`radio_level`): on Direwolf's own scale, as the row's `modem.rx_level`; null while its Direwolf does not run. */
export interface RadioLevelMessage {
  type: "radio_level";
  radio: number;
  level: number | null;
}

/** What the radio's type cannot do (neoaprs/radiotype.py `Limits`): constants of the type. */
export interface RadioLimits {
  /** the longest AX.25 frame the radio carries whole, in bytes (Mercury: 123); null for AX.25's own */
  max_frame: number | null;
  /** the shortest beacon interval the radio takes, in minutes (Packet 20, Mercury 30): the station's interval is raised to it on this radio */
  beacon_min_min: number;
  /** a frame holds the shared channel for seconds (HF, LoRa): what the pairs pass onto the radio is limited (`LIMITS.pass` of the page) */
  slow: boolean;
}

/** Why a radio, or its beacon, does not do what it is set to, as a code the page puts in its own words, with the values its sentence is made of (the English of the log is not told). */
export interface RadioProblem {
  /** `radio.not_connected` its line is not open (`name`: the radio's name in the log); `radio.searching` the daemon looks for its port; `radio.silent` its line is open and the radio does not answer (`since`: when the latest byte came, UTC); `radio.text_lines` its line is open and the LoRa board on it sends text lines, not KISS: nothing is sent until it is set to KISS; `radio.incoming_port` its port is the computer's incoming Bluetooth port (Windows), which reaches no device (`port`); `radio.port_in_use` another program has its port; `radio.no_answer` its Bluetooth device does not answer (switched off, asleep or out of range); `radio.not_paired` its Bluetooth device is not paired with this computer; `radio.refused` its Bluetooth device refused the connection; `radio.open_failed` its Bluetooth port could not be opened for another reason (the log says Windows' words); `radio.sends_text` its line is open and the KISS device on it sends text lines (monitor text, GPS sentences, KISS written as text) and no KISS frame; `radio.write_timeout` the last write to its port timed out (`seconds`): shown until a write goes through or a byte comes; `radio.resource_held` a device it is set to use is another's (`resource`: `serial`, `sound_card`, `keying`, `modem_ports` or `gps`; `holder`: the name of the radio that holds it, `GPS` for the GPS receiver; `held_by`: its id, 0 for the GPS receiver); `modem.<reason>` its Mercury modem is not running, `reason` as `ModemState.reason` says it; `modem.receive_deaf` its Mercury modem runs and hears nothing (its receive side stalled) and is started again soon; for its beacon `transmit.off` (RX only) and `beacon.not_sent` (`why`: the code of the reason, whose sentence the page has as the refusal `error.<why>`, and that reason's values) */
  code: "radio.not_connected" | "radio.searching" | "radio.silent" | "radio.text_lines" | "radio.incoming_port" | "radio.port_in_use" | "radio.no_answer" | "radio.not_paired" | "radio.refused" | "radio.open_failed" | "radio.sends_text" | "radio.write_timeout" | "radio.resource_held" | "modem.not_installed" | "modem.stopped" | "modem.network" | "modem.no_port" | "modem.not_started" | "modem.sound_card" | "modem.keying" | "modem.keying_in_use" | "modem.keying_missing" | "modem.ports_taken" | "modem.receive_stalled" | "modem.receive_deaf" | "transmit.off" | "beacon.not_sent";
  /** the values of the sentence, by name; empty for a code that has none */
  params: { [key: string]: string | number };
}

/** Removes the radio: it is stopped for good, and in the same write its id leaves the objects' sets, the stations' choices of it and their paths on it. Its row stays in `radios`, `removed`, so that what came by it keeps its name. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on stays), `setting.not_stored`. */
export interface RadioRemoveCommand {
  cmd: "radio_remove";
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
}

/** One radio of the station: what it is, how it is set, and how its line, its beacon and its modem are now. The rows are the values of the topic `radios`, keyed by `id` as text; a removed radio stays, marked, so that the packets and messages that name it still have its name. A radio that is added is a `set` of its row; a change of its state, counters, lines, beacon or modem is a `set` of the row, told at most four times a second; a change of the settings tells the topic whole. */
export interface RadioRow {
  /** its type, a `key` of `RADIO_TYPES` (ui/src/protocol/lists.ts), of its kind; it may change within the kind (`radio_change`) */
  type: string;
  /** the radio's id (an integer the database gave it, never given again): what every other row and command names it by */
  id: number;
  /** the kind of radio, fixed when it was added: its tag's colour and the defaults follow it */
  kind: "fm" | "hf" | "lora";
  /** the name the operator typed (at most 8 characters); empty for none: the page calls it by its kind and `number` (`Packet`, `Mercury 2`) in its own words */
  name: string;
  /** its number within its kind: 1 for the first of the kind by id among the radios not removed (`Mercury 2` is 2); a removed radio keeps its own */
  number: number;
  /** its Enable is ticked (`radio_change` with `enabled`); false for a removed radio */
  enabled: boolean;
  /** its place in the list of boxes (and of the radio a call no radio heard takes: the first that can send): the lowest first, then by id */
  position: number;
  /** it was removed: its row stays so that what came by it keeps its name; it is no longer started, chosen or offered */
  removed: boolean;
  /** its type is a Dummy radio: the traffic is made up and nothing goes on the air; its tag is dashed */
  dummy: boolean;
  /** its line: `waiting` is between two attempts to open it, or its line is open again after a write timed out and nothing has gone through or come since, `silent` the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer), nothing is sent until it does; `stopped` for a radio that is off or removed */
  state: "stopped" | "connecting" | "connected" | "waiting" | "silent";
  /** why it is not connected, while it is enabled and not connected; null otherwise */
  problem: RadioProblem | null;
  stats: TncStats;
  /** the latest 100 lines of what its line saw and did, oldest first; empty for a removed radio */
  lines: TncLine[];
  limits: RadioLimits;
  allowed: RadioAllowed;
  can: RadioCan;
  choices: RadioChoices;
  beacon: RadioBeaconState;
  status: RadioStatusState;
  /** its modem, while its type is one the daemon starts a modem for (Mercury, Sound card); null for every other type and for a removed radio */
  modem: ModemState | null;
  /** its sound card's own levels, read every two seconds while it runs and kept as read last while it is stopped or its card cannot be read; both null for a radio without a sound card of its own and before its card was read (`read` says which) */
  card: CardLevelsRow;
  /** the devices it holds now: a serial port, a sound card, a keying line, a Mercury port pair; empty while it holds none */
  holds: RadioHold[];
}

/** The scope of the radio's modem: with `on`, this page is sent the rows of its waterfall as binary frames that name the radio (*Binary frames*), first the rows kept and then the rows as they come, with `on` false, or when the page closes, no more. Several radios can be looked at at once. Nothing comes while the radio's modem is not running or has no interface (its row's `modem.scope`). Refused, with `on`, for a radio that is none (`radio.unknown`) and for one whose type has no scope (`radio.no_scope`, with its `name`: `can.scope` of its row is false); `on` false is never refused. */
export interface RadioScopeCommand {
  cmd: "radio_scope";
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
  /** true starts the rows for this page, false stops them */
  on: boolean;
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
  /** the radio the search is for (its id); null for a search that named none (radio 1) */
  radio: number | null;
  /** for `found`, the radio type that fits the TNC (a `key` of `RADIO_TYPES`, the same as `profile` for every Packet type: 1.11's `type`, which the message's own tag takes); empty otherwise */
  radio_type: string;
}

/** What went out on one radio in the last 24 hours, by what it was. */
export interface RadioSent {
  /** the radio it went out on, its id; null for what went to the internet */
  radio: number | null;
  /** our positions and statuses */
  beacons: number;
  /** our messages, bulletins among them */
  messages: number;
  /** our acks and rejects of messages */
  acks: number;
  /** our objects and items */
  objects: number;
  /** anything else of ours: answers to queries, telemetry */
  other: number;
  /** the digipeater's copies of other stations' packets */
  repeated: number;
}

/** The status report on the radio (services/rigstatus.py `on_radio`). */
export interface RadioStatusState {
  /** when our status report last went out on it; null before one */
  last_sent: string | null;
  /** when the next timed report is due on it: an interval after the slot of its last, and the radio's random pause; null while none is (the status does not go on it, the beacon or the status is off, none sent on it yet) */
  next_due: string | null;
  /** the interval in force on it, in minutes: `status/interval_min` raised to the radio's own floor (`limits.beacon_min_min` on HF and LoRa); 0 while the status does not go out on it */
  interval_min: number;
}

/** Tune on the radio's modem: with `on`, keys the radio through its keying and sends its modem's tuning tone through its sound card for ten seconds (Mercury a steady 1000 Hz, its own TUNE; Direwolf its two tones by turns), then stops by itself; with `on` false, stops it early. The radio's row says `modem.test: "tune"` meanwhile. Answered with an `error` for a radio that is none (`radio.unknown`), whose type has no modem or whose modem is not running (`radio.no_modem`, with its `name`), while the station is RX only (`transmit.off`) and while a frame is on the air or the channel is busy (`hf.held`). */
export interface RadioTuneCommand {
  cmd: "radio_tune";
  /** the radio's id, the `id` of its row in the topic `radios` */
  radio: number;
  /** true starts the tone, false stops it */
  on: boolean;
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

/** Asks what is new up to `version`: the newer one the update check found (what an update brings, from this version on), or this version itself (what the update the page's browser has seen brought: the notes of this version, or with `since` of every version after that one). The changelog of the project at the tag of `version` (neoaprs/releasenotes.py), fetched once. Answered with `release_notes`. */
export interface ReleaseNotesCommand {
  cmd: "release_notes";
  /** the newer version, as `status.update.version` names it, or this one, as `hello.version` names it; another is answered with no sections */
  version: string;
  /** the sections of the versions newer than this one; empty: this version for the newer one, and for this one its own section alone */
  since?: string;
}

/** The answer to `release_notes`: the sections of the versions asked for, the newest first; none with `problem` saying why (the notes could not be fetched, or the version is neither the newer one known nor this one). */
export interface ReleaseNotesMessage {
  type: "release_notes";
  /** the version asked for */
  version: string;
  /** the `since` asked for, empty when there was none */
  since: string;
  /** the newest first; empty with `problem` */
  sections: NoteSection[];
  /** why there are no sections, as a code: `unreachable` the notes could not be fetched, `unknown_version` the version is neither the newer one known nor this one; empty when there are */
  problem: "" | "unreachable" | "unknown_version";
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

/** A satellite whose card the page has open. A frequency, mode or path is there only where the project's list marks it sure. */
export interface SatelliteCard {
  id: number;
  name: string;
  downlinks: SatelliteTune[];
  uplinks: SatelliteTune[];
  mode: "afsk1200" | "gmsk9600" | null;
  /** the digipeater path to put in a packet (`ARISS`); empty when the list has none it is sure of */
  path: string;
  alt_km: number;
  /** the radius on the ground of the circle from which it is above the horizon */
  footprint_km: number;
  /** the points under it for one orbit ahead, every minute */
  track: SatellitePoint[];
  /** null without the station's position or with no pass within a day */
  next_pass: SatellitePass | null;
  /** empty unless it is up now */
  looks: SatelliteLookNow[];
}

/** With `on`, this page shows the satellites layer (its tick is on, the page is in front and the replay is closed: the page decides) and has the cards of `cards` open; sent again whenever the cards change. With `on` false, or when the page closes, no more. While a page looks, the daemon tells it `satellites` every 30 s and at once on this command. */
export interface SatelliteLookCommand {
  cmd: "satellite_look";
  on: boolean;
  cards: number[];
}

/** While the satellite is up: its elevation and the Doppler at a time, every 5 s for 90 s; the page tells now between them. */
export interface SatelliteLookNow {
  /** UTC, ISO 8601 with a Z */
  at: string;
  el_deg: number;
  /** the shift heard on each downlink, in their order */
  down_hz: number[];
  /** the offset to send by on each uplink, in their order */
  up_hz: number[];
}

/** A satellite on the map: the points under it from 30 s ago to 5 minutes ahead, every 30 s; the page moves the mark between them. */
export interface SatelliteMark {
  /** its catalogue (NORAD) number */
  id: number;
  /** its name as the project's list has it (`ISS`, `SONATE-2`) */
  name: string;
  points: SatellitePoint[];
}

/** The pass under way or the next one whose highest point is 10 degrees or more, within a day. */
export interface SatellitePass {
  /** UTC, ISO 8601 with a Z */
  rise: string;
  /** UTC, ISO 8601 with a Z */
  set: string;
  /** UTC, ISO 8601 with a Z */
  max_at: string;
  max_el_deg: number;
  rise_az_deg: number;
  set_az_deg: number;
}

/** Where the point under the satellite is at a time. */
export interface SatellitePoint {
  /** UTC, ISO 8601 with a Z */
  at: string;
  lat: number;
  lon: number;
}

/** A frequency of the list, and where to tune at the next pass: a downlink to hear, an uplink to send on. */
export interface SatelliteTune {
  hz: number;
  /** at the rise; null without a pass */
  rise_hz: number | null;
  /** at the highest point; null without a pass */
  max_hz: number | null;
  /** at the set; null without a pass */
  set_hz: number | null;
}

/** The satellites layer of now, to each page that looks: every satellite shown (elements no older than 14 days) and the cards that page has open. Empty before the project's file has come. */
export interface SatellitesMessage {
  type: "satellites";
  /** UTC, ISO 8601 with a Z */
  at: string;
  /** when the project's server took the orbital elements; null before a file */
  elements_at: string | null;
  satellites: SatelliteMark[];
  cards: SatelliteCard[];
}

/** The answer to a `set_config` that carried an `id`, sent to the page that asked once the settings are in force. */
export interface SavedMessage {
  type: "saved";
  /** the `id` of the `set_config` this answers */
  id: number;
}

/** Sends our public key to a station as an ordinary message (`seal` `key`), so that it can encrypt to us; our key pair is made the first time it is needed. Nothing is ever announced by itself: a station that is to read our locked messages gets our key this way, by hand, and we read its when it has sent its key the same way. Refused while the daemon was started without `--encryption` (`lock.off`). Answered as `send_message` is. */
export interface SendKeyCommand {
  cmd: "send_key";
  to: string;
}

/** Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`. When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused. */
export interface SendMessageCommand {
  cmd: "send_message";
  to: string;
  text: string;
  /** true encrypts the message with the key shared with the station (its `seal` is `open`): the text may be UTF-8, at most 34 bytes. Refused while the daemon was started without `--encryption` (`lock.off`), while the station has not announced its key (`lock.no_key`), and when the text is over 34 bytes (`lock.too_long`) */
  locked?: boolean;
}

/** Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is left out keeps its value. The answer to a request that carries an `id` is `saved` with that `id`, once the settings are in force (the `config` topic is told again too, to every page), or an `error` that carries it; a request without an `id` is answered by the topic alone. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `station/*` move our own station on the map. A radio's own setting is `radio/<id>/<key>` (a key of `radio_values`): it is checked by the field of its kind, stored with the rest in one write and restarts that radio alone where its driver says so; a radio that is none or removed is refused with `radio.unknown` (a removed one with its `name` and `removed` 1), a key its kind has not with `radio.no_setting` (its `name` and id, `radio`), `email/radio` changed to name no radio with `radio.unknown`, a device another radio holds or is set to, or the GPS receiver holds, with `radio.resource_held` (`resource`, `holder`, and the holder's id `held_by`, 0 for the GPS receiver), and the last radio that is on switched off with `radio.last_enabled` (the radio's id, `radio`), each with the key. A key of a radio's setting that does not name the radio (`serial/port`, `hf/enabled`) is refused with `setting.unknown`: the radio's own key is `radio/<id>/<key>`, its type and Enable are `radio_change`'s. A page of another device is refused with `setting.local_only` for `messages/alert_command`, `update/url`, `map/source` and `web/allowed_hosts`. */
export interface SetConfigCommand {
  cmd: "set_config";
  /** key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`) */
  values: { [key: string]: string };
  /** the page's own number for this request, which the answer (`saved`, or an `error`) carries back; left out, the page is answered by the topic `config` alone */
  id?: number | null;
}

/** The item at `key` is `value` (the whole item, new or changed). */
export interface SetOp {
  op: "set";
  /** the key of an item of a keyed topic: a station's call, a packet's id as text */
  key: string;
  value: unknown;
}

/** Sets when the operator is told about a station (see `AlertWhen`): `on_air`, `within_km` (1 to 1000, null for none) and `direct`, any of them at once; all off takes the alert away. Our own station and our own objects and items are refused. Answered by the `set` of the station's entry in the topic `station_prefs` (its path and RF only are whatever they were), or by its `del` when nothing else is set and the alert is taken away, or by an `error`. */
export interface SetStationAlertCommand {
  cmd: "set_station_alert";
  call: string;
  on_air: boolean;
  within_km: number | null;
  direct: boolean;
}

/** Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting `beacon/path` is, or `DIRECT` for a path of its own with no digipeaters at all; an empty `path` is no path of its own, as `clear_station_path` makes it. Answered by the `set` of the station's entry in the topic `station_prefs` (its `rf_only` is whatever it was), or by an `error` that names the reason. */
export interface SetStationPathCommand {
  cmd: "set_station_path";
  call: string;
  path: string;
  /** the radio the path is for (plan rule 3.3: a path belongs to the radio it was set on), its id; left out: radio 1, whose path is the entry's `path`; another radio's is the station's row's `paths` */
  radio?: number | null;
}

/** Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE` already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set` of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason. */
export interface SetStationRfOnlyCommand {
  cmd: "set_station_rf_only";
  call: string;
  on: boolean;
}

/** Asks for the readings of a station's signal in the last `hours` hours: the SNR and the RSSI its radio measured of each packet heard direct from it (`snr` and `rssi` of a packet). Answered with a `signal_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a station heard on no radio that measures is answered with no points. */
export interface SignalSeriesCommand {
  cmd: "signal_series";
  /** the station, as the `stations` topic has it: its packets are those whose source it is */
  call: string;
  /** how far back to go: 24 for a day */
  hours: number;
}

/** The readings of one station's signal, the answer to `signal_series`: one point for each packet heard direct from it in the span that carried a reading, the oldest first, the latest 1000 at most. A digipeater's copy and a third-party packet are left out: their frame is another station's signal. */
export interface SignalSeriesMessage {
  type: "signal_series";
  /** the station asked about: a page with several cards open tells the answers apart by it */
  call: string;
  /** the hours asked for */
  hours: number;
  /** [time, snr_db, rssi_dbm] for each packet with a reading, the oldest first; a reading the radio does not give is null (Mercury gives the SNR alone) */
  points: ([string, number | null, number | null])[];
}

/** Deletes a sked that this installation posted, by its id: the server takes it off the board for everybody. A sked that is not ours (another installation posted it, or the data folder is another one) is only dropped from `ours`: nothing is said, and the board is read again. An `error` (`sked.unreachable`) when the project's server could not be reached. The topic `skeds` tells the new board. */
export interface SkedDeleteCommand {
  cmd: "sked_delete";
  id: string;
}

/** A dial the project suggests for the HF radio. */
export interface SkedFrequency {
  /** the band, `40 m` */
  band: string;
  /** the dial with its mode, `7.0541 MHz USB` */
  dial: string;
}

/** A test that has ended, as the board had it: one row for each call that was on it. Checked again by the daemon as a row of the board is; it can no longer be joined or deleted. */
export interface SkedPast {
  /** the sked's id, 12 lowercase hex characters */
  id: string;
  /** the call that was on the air, upper case without an SSID of 0 */
  call: string;
  /** when it began (the field is called `from` on the wire) */
  from: string;
  /** when it ended, after `from` by 24 hours at most: the planned end, or when its poster deleted it while it ran */
  to: string;
  /** the dial with its mode, `7.0541 MHz USB` */
  dial: string;
  /** the short note, may be empty; the page shows it as text */
  note: string;
}

/** Posts a sked of ours on the board of the project's server: our call (the setting `station/call`), `from` and `to` in UTC (`to` after `from` by 24 hours at most, not past, `from` not more than 30 days ahead), a `dial` in the form of the HF box and a `note` of at most 80 characters (control and invisible characters are made spaces). It goes only on this command, and carries the call, the two times, the dial, the note and this installation's secret token. Answered by the topic `skeds`, whose rows then have it with `ours` true. An `error` when no call is set (the interlock's reason; RX only does not matter, nothing is sent by radio), the sked has ended (`sked.past`) or begins more than 30 days ahead by the daemon's or the server's clock (`sked.far`), too many were posted from here lately (`sked.rate`), the board has no room (`sked.full`), or the project's server could not be reached or would not take it (`sked.unreachable`). A board that is closed to the call is no error: the state of the topic says `closed`. */
export interface SkedPostCommand {
  cmd: "sked_post";
  /** UTC, ISO 8601 with a Z; the field is called `from` on the wire */
  from: string;
  /** UTC, ISO 8601 with a Z */
  to: string;
  dial: string;
  /** at most 80 characters once cleaned; empty for none */
  note: string;
}

/** A sked on the board: a call on the air at a dial from one instant to another. Every row was checked again by the daemon; the note is one line of at most 80 characters of letters, digits, punctuation and plain spaces. */
export interface SkedRow {
  /** the sked's id, 12 lowercase hex characters, which `sked_delete` names */
  id: string;
  /** the call that will be on the air, upper case without an SSID of 0 (`OH2GBA`, `OH2GBA-7`) */
  call: string;
  /** when it begins (the field is called `from` on the wire) */
  from: string;
  /** when it ends, after `from` by 24 hours at most; a sked that has ended by the daemon's clock is not told */
  to: string;
  /** the dial with its mode, `7.0541 MHz USB` */
  dial: string;
  /** a short note, may be empty (`Mercury, 10 W`); the page shows it as text */
  note: string;
  /** this installation posted it, so `sked_delete` takes it off the board; no other row can be deleted from here */
  ours: boolean;
}

/** The sked board: where it stands, the dials the project suggests, and the skeds to come, the nearest first. The value of the topic `skeds`, told whole as it changes (a read of the board, a post, a delete, a sked that ends). */
export interface SkedsState {
  /** `ok`: the board was read (or has not been tried yet), and a sked may be posted. `offline`: the project's server could not be reached or its answer was not a board; `rows` are the last board known, and posting is off. `off`: the check is off (`NEOAPRS_UPDATE_CHECK=0`): nothing is read or posted, `rows` is empty. `closed`: the board is closed to new skeds (by the project, or for this call); `rows` are shown without the form */
  state: "ok" | "offline" | "off" | "closed";
  /** when the board was last read from the server (or when the one kept from the last run was); null before the first */
  fetched_at: string | null;
  /** the dials the project suggests for a Mercury radio, one to five, the same as `modem.frequencies` of a Mercury radio's row (the tab does not depend on a radio's state) */
  frequencies: SkedFrequency[];
  /** the skeds to come by the daemon's clock, the nearest start first; empty when there are none */
  rows: SkedRow[];
  /** the tests that have ended in the last 30 days: those the server lists (`skeds-past.json` beside the board) and the board's own that have ended by the daemon's clock since. Rows with the same `from`, `to` and `dial` are one test; the 20 newest tests by their end come first, then by their start and dial, each test's rows by id. Kept in memory only, so empty after a start until the board is read; empty when the check is off */
  past?: SkedPast[];
}

/** The page shows the HF tests tab (and while it stays visible): the daemon reads the board now, unless it read it less than 15 minutes ago or the update check is off (`NEOAPRS_UPDATE_CHECK=0`). Nothing is answered; the topic `skeds` tells what came. */
export interface SkedsWantedCommand {
  cmd: "skeds_wanted";
}

/** A sound card as the Mercury HF modem lists it (`mercury -z`), for the Sound card choice of the Mercury radio type. */
export interface SoundCardRow {
  /** the name to give as `mercury/sound_card`: `plughw:CARD=CODEC,DEV=0` on Linux (by the card's name, which a reboot does not change); on Windows the card's recording device and its playing device, joined by `|` (one of them alone for a device with no partner) */
  id: string;
  /** what the system calls it, such as `USB Audio CODEC` */
  name: string;
  /** the same card by its number (`plughw:3,0`), as a setting made before named it; empty where the id is not by name */
  numbered?: string;
  /** whether it is the system's default device, which the empty setting means */
  default: boolean;
  /** whether it is the card the daemon proposes for the radio (the one it would choose itself, else the system's default, else the first that records and plays): the page preselects it and stores it as `mercury/sound_card` while that is empty; at most one row has it */
  pick: boolean;
  /** the radio of the station whose modem holds the card now (its id); null while none does. A card another radio holds is never the `pick` */
  held_by: number | null;
  /** which USB device the card sits on together with the serial ports of one radio: the `usb_group` of those ports (an opaque token); null where it is not known (Windows, macOS, a card that is not USB) */
  usb_group?: string | null;
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

/** An alert set on a station fired (`set_station_alert`): told to every page that is open, once. The page alerts as for a message to us (the sound, the notification, the browser tab, as its own choice says) and shows it in its toast. */
export interface StationAlertMessage {
  type: "station_alert";
  /** the station */
  call: string;
  /** what happened: it came on the air, it came within the distance, it was heard direct */
  kind: "on_air" | "within" | "direct";
  /** when the packet that fired it was heard (for `within`, when the station's position was, or when ours moved) */
  at: string;
  /** for `within`, how far the station is, km with one decimal; else null */
  km: number | null;
}

/** The public key a station announced, kept on first hearing. The entries are the values of the topic `station_keys`, keyed by call; a station that has not announced a key has no entry. A key heard from a station is a `set`, `forget_station_key` a `del`. */
export interface StationKey {
  /** 16 hex characters in four groups (`A1B2 C3D4 E5F6 0718`), the start of SHA-256 of the key, for the two operators to compare on voice */
  fingerprint: string;
  /** when the key was heard */
  heard_at: string;
}

/** What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path of its own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`. */
export interface StationPref {
  /** the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); null if none is set, and the setting `beacon/path` counts */
  path: string | null;
  /** true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet */
  rf_only: boolean;
  /** when the operator is told about the station; null if no alert is set */
  alert: AlertWhen | null;
}

/** Chooses the radio messages to a station go out on (`radio`, or null to leave it to the daemon again: plan rule 3.2, the radio that heard it lately, a local one before HF). It holds from the next attempt on, also of a message on its way, and across a restart; the station's row says it (`radio_choice`, and `radio_now` the radio a message takes now). A radio that is off is no choice: the station's row says null while it is. For a station of the book it is answered by the station's row (and the `radio_now` of each message to it on its way); a call the book does not hold is chosen for too (plan rule 3.2: the choice is kept by call), with no answer, and its station's row says it once the station is heard. The call is kept in its normal form, as a message names it (upper case, no SSID 0). Refused with an `error`: `radio.unknown` (no radio of that id that is not removed), `radio.receive_only` (a radio of a type that only receives, with its `name`), or a `call.*` code for a text that is no call. */
export interface StationRadioCommand {
  cmd: "station_radio";
  call: string;
  radio: number | null;
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
  /** what each radio heard of the station, by the radio's id as text: how many packets of the air came on it and when the latest did; a radio that heard nothing of it has no entry */
  heard: { [key: string]: HeardOn };
  /** the signal-to-noise ratio of the latest packet heard direct from the station whose radio measured one, dB (the Mercury modem and the Dummy Mercury radio do; a digipeater's copy and a third-party packet are another station's signal); null when none was */
  snr: number | null;
  /** the received strength of that packet, dBm; null when its radio gave none (Mercury gives none) */
  rssi: number | null;
  /** when that packet was heard; null until one with a reading was */
  signal_at: string | null;
  /** the channel of the packet that gave its position (the latest one wins); null for a station without a position and for our own */
  position_via: "rf" | "rf-gated" | "is" | "dummy" | null;
  /** how many of them were heard in the last hour (counted from the packets of the hour at the start and as they come; the row is told again each minute that it becomes fewer) */
  packets_hour: number;
  /** what the station runs, as the APRS device identification list names it ("Kenwood TH-D74", "APRSdroid"): by the destination call of its packets, or by the type code of a Mic-E packet; empty when unknown */
  device: string;
  /** the digipeaters of the latest packet heard on the radio, the one that repeated it marked with `*`: the packet the radio that heard the station last (`last_path_radio`) heard last */
  last_path: string[];
  /** the radio whose latest packet `last_path` is (the radio that heard the station last, radio 1 on a tie), its id; null for a station no radio heard. After a restart a station a Mercury radio heard last shows that radio's path, direct */
  last_path_radio: number | null;
  /** how the latest packet heard on the radio reached us (empty for a station known from the internet only): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in) */
  last_route: string;
  /** how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept) */
  heard_direct: number;
  /** when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`, on the radios that may carry a path; null for a station never heard direct */
  last_direct_at: string | null;
  /** when a packet of the station was last heard direct on any radio, a Mercury radio too (plan 6b: the green check, the map's ring and the "direct only" filter count any radio); null for a station never heard direct */
  last_direct_any_at: string | null;
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
  /** a message can go to the station, and the card has a Message button: false for an object or an item, for our own station and for a station known only from the internet (`heard_is` > 0 and nothing on the radio: a message goes out by radio only); true for every other station, also one whose position says it takes none (`may_not_message`) */
  can_message: boolean;
  /** the station's latest position says it takes no messages (it began with `!` or `/`, or was a Mic-E one whose comment begins with the type code `'`) and it never sent a message or an ack: the conversation says a message may not be read there */
  may_not_message: boolean;
  /** the radio the operator chose for messages to the station (`station_radio`), its id, while that radio is enabled; null for the daemon's choice (plan rule 3.2), and while the radio chosen is off */
  radio_choice: number | null;
  /** the radio a message to the station goes out on now, its id: the choice while it is in force, else the radio that heard the station most recently within six hours, a local one (Packet, LoRa) before Mercury, else the radio that heard it last, else the first radio that can send, in the order of the boxes; the email radio for the email gateway. Null for a station that takes no message and while there is no radio. A message on its way keeps its own (`radio_now` of its row). The page shows Route, the path and the radio's state of this radio */
  radio_now: number | null;
  /** the path a message or an ack of ours to the station goes by on each radio that carries no path (Mercury), by the radio's id as text: the gateway its latest packet there came by, then WIDE2-1 when a digipeater stood before the gateway, calls separated by commas, without RFONLY; a radio that carries a path, and one on which they go direct, has no entry */
  replies: { [key: string]: string };
  /** the path the operator set for the station on each radio (`set_station_path` with `radio`), by the radio's id as text: calls separated by commas, empty for direct; a radio with none set has no entry (radio 1's is `path` of the topic `station_prefs` too) */
  paths: { [key: string]: string };
  /** the bytes of text a message to the station holds on the radio of `radio_now`, where its frame leaves room for fewer than a message may have (Mercury's 123 bytes with a reply path and RFONLY); null where the whole text fits, and for a station that takes no message */
  text_max: number | null;
  /** the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed */
  track: [string, number, number][];
}

/** Asks for a station's track: the positions its row's `track` has, for a page that draws the trail or works out the speed of one station without reading the whole row. Answered with a `station_track` message to the page that asked, or an `error` `station.unknown` for a call the topic `stations` has no row of (with the internet hidden, a station known only from there). The track is as the row has it when the command is answered: a page that shows it asks again when the row changes. */
export interface StationTrackCommand {
  cmd: "station_track";
  /** the station, as the topic `stations` keys it */
  call: string;
}

/** The track of one station, the answer to `station_track`: what its row's `track` has now. */
export interface StationTrackMessage {
  type: "station_track";
  /** the station asked about: a page with several cards open tells the answers apart by it */
  call: string;
  /** the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed; empty for a station that has sent no position */
  points: [string, number, number][];
}

/** Asks for the latest packets of one station, for the station panel of the Stations tab: those it sent (its own source, or inside a third-party packet an iGate put on the air) and the messages we sent to it (a message, an ack, a directed query). Read from the packet log, so that they reach back past the 200 of the topic `packets`; the page adds the packets that come after. While `igate/enabled` is off no packet that came from APRS-IS is read, as the topic shows none. Answered with a `station_traffic` message to the page that asked. */
export interface StationTrafficCommand {
  cmd: "station_traffic";
  /** the station, as the `stations` topic has it */
  call: string;
}

/** The latest packets of one station (at most 50), the answer to `station_traffic`, the newest first. A third-party packet is looked for among the latest 20000 packets of the log, where an iGate's are. */
export interface StationTrafficMessage {
  type: "station_traffic";
  /** the station asked about */
  call: string;
  /** the packets, as the rows of the topic `packets` but for `id`, which is the packet's number in the log here (the same packet in the topic has its own); the newest first */
  packets: PacketRow[];
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
  /** minutes between our position packets on some radio: `beacon/interval_min` as it is in force, the shortest of the radios the beacon goes out on (each raised to its own floor; each radio's own is `beacon.interval_min` of its row in `radios`); 0 is off */
  beacon_interval_min: number;
  /** when the latest beacon was sent on any radio, by the timer or on request; null for none since the daemon started */
  beacon_last_sent: string | null;
  /** when the next timed beacon is due on any radio the beacon goes out on (each radio's own is its row's `beacon`); null while none is planned */
  beacon_next_due: string | null;
  /** the radio a message to a call no radio heard goes out on (its id), and a text to an addressee that is no station (CQ, ALL, QST): the first radio that can send, in the order of the boxes. Route shows it as what Automatic gives. Null while no radio that can send is on */
  unheard_radio: number | null;
  /** the radio an email to the gateway goes out on (its id), of any kind: the one radio that can send; else the one chosen (`email/radio`, the select of the E-mail tab) while it is on and can send; else the first radio that can send, in the order of the boxes. Null while no radio that can send is on, and Send of an email is off */
  email_radio: number | null;
  /** the types of radio (keys of `RADIO_TYPES`) whose program this kind of installation does not carry (a Mac carries no Direwolf): the page does not offer them, and `radio_add` refuses them (`radio.unknown_type`) */
  unavailable_types: string[];
  /** the radios a new object is ticked for (their ids, ascending), when `object_set` names none: with one radio that can send, that one; else those of the object saved last with radios named while one of them is on, else the first radio that can send */
  new_object_radios: number[];
  /** the radios a new bulletin goes on (their ids, ascending), when `bulletin_post` names none: as `new_object_radios`, by the bulletin posted last with radios named */
  new_bulletin_radios: number[];
  /** how long a new post of each kind is sent for, in hours, when `bulletin_post` names no `hours`: the one posted last of that kind */
  new_bulletin_hours: PostHours;
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
  /** the fingerprint of our own key for encrypted messages (16 hex characters in four groups), made at the start of a daemon run with `--encryption`; empty while there is none (the daemon runs without the flag, or the key could not be made), which is also how the page knows the feature is not there */
  message_key: string;
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
  /** frames the digipeater sent again for other stations on this radio, the pairs' passed frames among them */
  digipeated: number;
  /** when the latest of them went out; null for none yet */
  digipeated_at: string | null;
  /** frames the digipeater left unsent because it had already sent the most it sends in a burst (`BURST_MAX` in 10 seconds) */
  digipeat_held: number;
  /** what the pairs passed onto this radio, one entry for each radio packets came from, in the order of its id; empty while none */
  passed: PassStats[];
}

/** The value of each topic a page follows (neoaprs/web/topics.py): what `state` carries as `value`, and what `patch` replaces. */
export interface TopicValues {
  /** the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del` */
  stations: { [key: string]: StationRow };
  /** the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest */
  packets: { [key: string]: PacketRow };
  /** every radio of the station by id (as text), removed ones too (marked): what it is, how it is set, its line, its beacon and its modem. A radio added is a `set`; a change of its state, counters, lines, beacon or modem a `set` of its row, at most four times a second; a change of the settings or of the devices held tells it whole. No radio leaves it */
  radios: { [key: string]: RadioRow };
  /** the settings; told again after every save, though nothing differs: the settings form waits for it */
  config: ConfigValues;
  /** what the operator set for each station that has anything set, by call: its own path (null where none is set), whether it is RF only and its alert. `set_station_path`, `clear_station_path`, `set_station_rf_only` and `set_station_alert` each give a `set` of the entry, or a `del` when nothing is left in it */
  station_prefs: { [key: string]: StationPref };
  /** every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own */
  messages: { [key: string]: MessageRow };
  /** the public key each station announced for encrypted messages, by call: the fingerprint and when it was heard. A key heard is a `set`, `forget_station_key` a `del` */
  station_keys: { [key: string]: StationKey };
  /** the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del` */
  bulletins: { [key: string]: BulletinRow };
  /** the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations` */
  own_objects: { [key: string]: OwnObjectRow };
  /** the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one in a free slot (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`) */
  own_bulletins: { [key: string]: OwnBulletinRow };
  /** the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps, the ALOHA circle, and the layers of traffic; told whole as it changes, at most four times a second */
  map: MapState;
  /** Update now: whether this copy can update itself, and the steps of the update it is doing; told whole as it changes, at most four times a second */
  update: UpdateState;
  /** the GPS receiver and the moving station's beacon: the latest fix, its state, and when the next beacon by time is due; told whole as it changes, at most once a second */
  gps: GpsState;
  /** the receive-only iGate: whether it is connected to APRS-IS, the server's name, the packets gated and not gated; told whole as it changes, at most once a second */
  igate: IgateState;
  /** local info (QRU): the last request sent from here and the servers that answered it, forgotten an hour after; told whole as it changes */
  qru: QruState;
  /** the sked board (the page calls it HF tests): when people will be on the air, as the project's server keeps it, the dials the project suggests, and whether it can be reached or is closed; told whole as it changes */
  skeds: SkedsState;
  /** the chat of the HF tests tab, as the project's server keeps it: whether it can be read and takes lines; told whole as it changes */
  chat: ChatState;
  /** the lines of the chat by id (as text), the newest 100 the server keeps, all of them sent with the first `state`: a line read or said is a `set` of its row, one the server no longer has a `del`. Read every 15 seconds while the daemon runs */
  chat_lines: { [key: string]: ChatLineRow };
  /** asking around: the last general query of each kind sent from here (?APRS?, ?IGATE?, ?WX?) and the stations heard after it that had been quiet before it; told whole as it changes */
  general: GeneralState;
  /** how messages go to each call the station book does not hold that has a radio chosen (`station_radio`) or a path set on a radio (`set_station_path`), by call in its normal form: `station_radio` and `set_station_path` for such a call give a `set` of its entry, and a `del` once nothing is left or the station is heard (its row says it then) */
  call_routes: { [key: string]: CallRoute };
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

/** Starts Update now to `version`, which must be the version the update check announced (the `update` of `status`): the daemon fetches SHA256SUMS, its signature and the file for this copy from the GitHub release of exactly that version, checks the signature and the file's SHA-256 and installs it, and NeoAPRS restarts. The progress is the topic `update`. An `error` when this copy cannot update itself (`update.unsupported`, `update.blocked`), the version is not the one announced (`update.not_announced`) or an update is running (`update.busy`). */
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
  /** for `no_answer` why, as a code the page says in its words: `offline` the update server did not answer (is there a connection?), `bad_answer` it gave no usable answer; empty otherwise */
  reason: "" | "offline" | "bad_answer";
}

/** Update now (neoaprs/services/selfupdate.py): whether this copy can update itself, and the steps of the update it is doing. The value of the topic `update`, told whole as it changes, at most four times a second. */
export interface UpdateState {
  /** this copy can update itself (the Windows installer, an AppImage in a folder its user can write): the page offers Update now; else it shows the steps */
  supported: boolean;
  /** `idle`: no update is running. `downloading`: SHA256SUMS, its signature and then the file of the release are fetched (`percent`). `verifying`: the file's SHA-256 is held to the signed SHA256SUMS. `installing`: the file is put in place. `restarting`: NeoAPRS ends and starts again as the new version (the page loses its socket and finds the new daemon). `error`: the update failed, `problem` says how */
  state: "idle" | "downloading" | "verifying" | "installing" | "restarting" | "error";
  /** the version being installed; empty while idle */
  version: string;
  /** how much of the file has come; null when the server did not say its size */
  percent: number | null;
  /** the bytes of the file so far */
  downloaded: number;
  /** the size of the file in bytes, when the server said it */
  total: number | null;
  /** for `error`: `download` (the file or SHA256SUMS could not be fetched), `unverified` (SHA256SUMS could not be checked: its signature could not be fetched or does not hold with the project's key for this version, or the list does not name the file once; nothing was downloaded), `checksum` (the file's SHA-256 is not the one the signed SHA256SUMS gives it: it was deleted), `install` (it could not be put in place, or the installer could not be started), `no_restart` (it was installed but NeoAPRS did not restart); empty otherwise */
  problem: "" | "download" | "unverified" | "checksum" | "install" | "no_restart";
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
