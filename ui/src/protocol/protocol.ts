// The types of the wire protocol between the daemon and the page, written from the models of neoaprs/web/protocol.py by scripts/gen-protocol.py: never edited by hand.
// `Command` is what the page sends (tagged by `cmd`), `Message` what the daemon sends (tagged by `type`), `TopicValues` the value of each topic the page follows.

export type Command = PingCommand | AskStatusCommand | CheckUpdateCommand | SubscribeCommand | UnsubscribeCommand | ForgetStationCommand | TncReconnectCommand | ListPortsCommand | SetConfigCommand | BeaconNowCommand | StatusNowCommand | SendMessageCommand | MessageRetryCommand | MessageCancelCommand | MessageDeleteCommand | ConversationDeleteCommand | OverheardDeleteCommand | SetStationPathCommand | ClearStationPathCommand | SetStationTimeoutCommand | ClearStationTimeoutCommand | SetStationRfOnlyCommand | WeatherSeriesCommand | AlertTestCommand | BulletinDeleteCommand | ObjectSetCommand | ObjectKillCommand | BulletinPostCommand | BulletinUnpostCommand | MapEstimateCommand | MapFetchCommand | MapCancelCommand;

export type Message = HelloMessage | StatusMessage | PongMessage | ErrorMessage | PortsMessage | StateMessage | PatchMessage | WeatherSeriesMessage | AlertResultMessage | UpdateResultMessage;

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

/** Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path` (or the `del` of the entry when it had no timeout either), or by an `error`. */
export interface ClearStationPathCommand {
  cmd: "clear_station_path";
  call: string;
}

/** Takes a station's own timeout away, so that it has the fixed 180 minutes again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `hide_after_min` (or the `del` of the entry when it had no path either), or by an `error`. */
export interface ClearStationTimeoutCommand {
  cmd: "clear_station_timeout";
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
}

/** A status report. */
export interface DecodedStatus {
  type: "status";
  /** the status text; after the locator when there is one */
  text: string;
  timestamp: string | null;
  /** a Maidenhead locator with a symbol at the start of the report (a report that has one has no timestamp) */
  locator: LocatorValues | null;
}

/** A telemetry report (`T#005,199,000,255,073,123,01101001`). The definitions of the channels are messages of the station, applied by the daemon: see `telemetry` of the station. */
export interface DecodedTelemetry {
  type: "telemetry";
  /** the sequence number; null for the `MIC` of a Mic-E unit */
  sequence: number | null;
  /** the five analog values as sent (0 to 255) */
  analog: number[];
  /** the eight digital values as a text of 0 and 1 */
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

/** A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed. */
export interface ErrorMessage {
  type: "error";
  /** what could not be done and why, in a sentence; for a setting it begins with the key */
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

/** Removes a station from the station book (and its cache in the database) until it is heard again. Not our own station. Answered by the `del` of the row, or by an `error`. */
export interface ForgetStationCommand {
  cmd: "forget_station";
  call: string;
}

/** The first message of a connection; `status` and the `state` of every topic follow it at once, so a page need not ask for them. */
export interface HelloMessage {
  type: "hello";
  /** the version of these messages: a page built for another one says so and loads itself again */
  protocol: number;
  /** the version of the daemon: a page built for another one loads itself again, once for each version */
  version: string;
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
  /** `basemap.pmtiles` (the detailed map) or `basemap-world.pmtiles` (the world to zoom 5) */
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
  /** `basemap-world.pmtiles`; null if it is not there */
  world: MapFileInfo | null;
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
  /** `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; `received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for) */
  state: "sending" | "acked" | "rejected" | "failed" | "unconfirmed" | "cancelled" | "received" | "overheard";
  /** how many times it has been transmitted (at most `attempts_max`: 0, 30, 60, 120, 240, 480, 960 ... seconds after the first, no wait longer than 960) */
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

/** Kills an object or an item of ours: the killed form is sent three times (at once, after a minute and after three) and then it is forgotten, and it leaves the map now. One that was never sent is removed at once. Answered by the `del` of its row in `stations` (and in `own_objects` once the kill is sent, or at once), or by an `error` (no such object of ours). */
export interface ObjectKillCommand {
  cmd: "object_kill";
  name: string;
}

/** Makes an object or an item of ours, or changes the one of that name (a changed object starts its schedule again, and is sent at once, never sooner than a minute after its last packet). `name` is 1 to 9 characters for an object and 3 to 9 for an item, printable ASCII without `!`, `_`, `|` and `~` and without a blank at either end, and not our own call or the call of a station; `lat` and `lon` the position in decimal degrees; the symbol is a table character and a code character; `comment` at most 43 characters (36 with a course or speed); `course_deg` and `speed_kmh` the course and speed, each or both or none; `path` the digipeaters, calls separated by commas (null: `beacon/path`). Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason. */
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
  /** the digipeaters it goes by, calls separated by commas; null: the path of the setting `beacon/path` is used */
  path: string | null;
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
  /** when it is sent next: 1, 2, 4 ... minutes after the last packet, never more than the net cycle time of its path apart; a time that has passed means it waits for the radio or for the call */
  next_at: string | null;
}

/** One packet heard or sent. The rows are the values of the topic `packets`, keyed by `id` as text: the daemon holds the latest 200, a packet that comes is a `set` and the one that falls out of the 200 a `del`. The page shows them newest first (the highest id). */
export interface PacketRow {
  /** counts up in the order the packets came in this run of the daemon; not kept in the database */
  id: number;
  /** UTC, ISO 8601 with a Z */
  heard_at: string;
  /** heard on the air, or sent by us */
  direction: "in" | "out";
  /** who sent the frame we heard; for a third-party packet the iGate (see `via`) */
  source: string;
  destination: string;
  /** the digipeaters, the one that repeated it marked with `*` */
  path: string[];
  /** a telemetry report is `other`; its `decoded.type` is `telemetry` */
  kind: "position" | "message" | "object" | "item" | "status" | "other" | "undecoded";
  /** how a packet that was heard reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours */
  route: string;
  /** the iGate, for a third-party packet: `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet */
  via: string;
  /** one line, as the log has it */
  summary: string;
  /** the packet as a line of TNC2 monitor text */
  tnc2: string;
  decoded: DecodedPosition | DecodedMessage | DecodedObject | DecodedItem | DecodedStatus | DecodedTelemetry | DecodedOther | DecodedUndecoded;
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

/** A serial port the system lists, or a Bluetooth device paired with it (Linux). Nothing was opened or connected to find it. */
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
}

/** The whole value of the topic is `value`. */
export interface ReplaceOp {
  op: "replace";
  value: unknown;
}

/** Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`. When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused. */
export interface SendMessageCommand {
  cmd: "send_message";
  to: string;
  text: string;
}

/** Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `serial/*`, `tcp/*` and `tnc/profile` restart the TNC, `station/*` move our own station on the map. `tnc/check_sec` counts at once, with no restart. */
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

/** Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting `beacon/path` is; an empty `path` is a valid path of its own, direct with no digipeaters at all, which is not the same as none set. Answered by the `set` of the station's entry in the topic `station_prefs` (its `hide_after_min` is whatever it was), or by an `error` that names the reason. */
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

/** Gives a station a timeout of its own: how long after its last position it stays on the map, in minutes; 0 is never. The page hides a station whose last position is older than that (a station without one of its own is hidden after 180 minutes), and the daily prune does not remove a station with a timeout of 0 from the station book. `call` is a station's call as it is in the topic `stations` (the name of an object or an item too). Answered by the `set` of the station's entry in the topic `station_prefs` (its `path` is whatever it was), or by an `error` that names the reason. */
export interface SetStationTimeoutCommand {
  cmd: "set_station_timeout";
  call: string;
  minutes: number;
}

/** A topic as it is now: its revision and its whole `value`, which replaces what the page had. Patches for the changes made meanwhile follow. */
export interface StateMessage {
  type: "state";
  topic: string;
  /** how many changes the topic has had since the daemon started */
  rev: number;
  value: unknown;
}

/** What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path and no timeout of its own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`. */
export interface StationPref {
  /** the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); null if none is set, and the setting `beacon/path` counts */
  path: string | null;
  /** the minutes after the station's last position that it leaves the map (the page does the hiding); 0 is never; null if none is set, and the default of 180 minutes counts */
  hide_after_min: number | null;
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
  /** how many packets of this station were heard */
  packets: number;
  /** the digipeaters of the latest packet, the one that repeated it marked with `*` */
  last_path: string[];
  /** how the latest packet reached us: `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in) */
  last_route: string;
  /** how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept) */
  heard_direct: number;
  /** when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`; null for a station never heard direct */
  last_direct_at: string | null;
  /** how many packets came as third-party packets: an iGate put what it heard on the internet on the air; counted, but never a route to send by */
  heard_gated: number;
  /** [the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted */
  heard_via: [string, number][];
  /** the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted */
  best_route: string;
  /** the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned) */
  suggested_path: string | null;
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
  /** the PHG, RNG, DF or area data of the station's latest position; null when it had none */
  extensions: ExtensionValues | null;
  /** from our position, null for us and for a station without a position */
  distance_km: number | null;
  /** the direction from our position, degrees from north; null as the distance is */
  bearing_deg: number | null;
  /** our own station: the row of the call in the settings, at the position in the settings */
  is_me: boolean;
  /** an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row */
  own: boolean;
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

/** A station's latest telemetry report with the definitions the station sent as messages (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`) applied. */
export interface TelemetryValues {
  /** the sequence number; null for the `MIC` of a Mic-E unit */
  sequence: number | null;
  /** the five analog channels */
  channels: TelemetryChannel[];
  /** the eight digital channels */
  bits: TelemetryBit[];
  /** the project title of the `BITS.` message; empty when there is none */
  project: string;
  comment: string;
}

/** Opens the radio's line again with the settings as they are now (the port, the speed, entering KISS): the TNC is stopped and started in the background. The new state is told in `tnc`. */
export interface TncReconnectCommand {
  cmd: "tnc_reconnect";
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
  /** one line for the status bar: the port, the speed and what the TNC does; while `silent` it says since when, in UTC */
  describe: string;
  /** while `state` is `silent`, when the latest byte came; null otherwise */
  silent_since: string | null;
  stats: TncStats;
  /** what the watchdog did last: `check` (the radio asked whether it is there, after a quiet period), `probe` (the same, while the radio is silent) or `reopen` (the port closed and opened again); empty if it has done nothing since the daemon started */
  last_watchdog_action: "" | "check" | "probe" | "reopen";
  /** when the watchdog did that; null if it has done nothing since the daemon started */
  last_watchdog_at: string | null;
  /** the latest 100 lines of what the TNC saw (TNC2 text and what it understood of it) and did (`NeoAPRS: ...`), oldest first, each begins with the time HH:MM:SS */
  lines: string[];
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
  /** times the keep-alive checked that the radio is there (after `tnc/check_sec` of nothing heard) */
  keepalive_checks: number;
  /** times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds) */
  watchdog_probes: number;
  /** times the port was closed and opened again (every 5th probe of a silent radio) */
  port_reopens: number;
  /** frames the digipeater (`digi/enabled`) sent again for other stations */
  digipeated: number;
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
  /** what the operator set for each station that has anything set, by call: its own path and its own timeout, each null where none is set, and whether it is RF only. `set_station_path`, `clear_station_path`, `set_station_timeout`, `clear_station_timeout` and `set_station_rf_only` each give a `set` of the entry, or a `del` when nothing is left in it */
  station_prefs: { [key: string]: StationPref };
  /** every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own */
  messages: { [key: string]: MessageRow };
  /** the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del` */
  bulletins: { [key: string]: BulletinRow };
  /** the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations` */
  own_objects: { [key: string]: OwnObjectRow };
  /** the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`) */
  own_bulletins: { [key: string]: OwnBulletinRow };
  /** the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps; told whole as it changes, at most four times a second */
  map: MapState;
}

/** Stop following these topics. A topic that was not followed is ignored. */
export interface UnsubscribeCommand {
  cmd: "unsubscribe";
  topics: string[];
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
