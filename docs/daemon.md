# How the daemon behaves

The details behind the [manual](manual/README.md), with the names the code and the wire use. The wire itself is in [`PROTOCOL.md`](../PROTOCOL.md); the layers
the parts are in are in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). The policy numbers (`LOG_KEEP_DAYS`, `HIDE_AFTER_MIN`, `MAX_HIDE_AFTER_MIN`, `TNC_CHECK_SEC`)
are in `neoaprs/policy.py`.

## The TNC and its keep-alive

`neoaprs/tnc.py` is the one feed of packets; `neoaprs/source.py` is its base (state, problem, counts, the latest lines, the back-off). The profile
(`neoaprs/tncprofile.py`) is the one place that knows a device's words, with the source of each string in a comment. A profile that cannot be asked (`kiss`,
`kiss-tcp`) never has the check, the silent state or the probes.

**The check.** While the port is open and the profile can be asked, the Tnc counts the time since anything at all arrived; a damaged frame or noise counts.
After a quiet `TNC_CHECK_SEC` (60 seconds) it makes a check: the profile's exit (`C0 FF C0`), half a second (`CHECK_PAUSE_SEC`), a bare carriage return
(`PROMPT`), and then the profile's entry with its settling time. A TH-D7 that is on answers with text (`cmd:`) within about a second. Any byte in answer means
the radio is there: the state stays `connected` and the clock starts again from the latest byte.

**A line that has just been opened** (the daemon starts, or the line dropped and was opened again) has not shown yet that the radio is there. For a profile that
can be asked the Tnc makes the same check at once. Until a byte arrives it is `connected` but not `usable`, with the reason "the TNC is checking that the radio
is there". The beacon, the status, the messages, the acks and the answers to queries wait exactly as they wait while the radio is silent. A byte heard before
the check runs confirms the line and the check is skipped, and so does a port that the search chose, which has just been heard from. Nothing is sent while a
check is under way or settles (`Tnc.usable` is False), so no frame is ever typed into a TNC in command mode.

**Silent.** When no byte at all comes within `ANSWER_SEC` (2 seconds) of the carriage return and the entry, the state is `silent` (`Source.State.SILENT`). A
frame is refused with "the radio is silent". The beacon that is due waits (told once in the log), the status and the answers to queries are not sent, the
attempts of a message wait and none is used up, and `beacon_now` and `send_message` are refused with the reason.

The topic `tnc` has `state` `silent` and `silent_since`, the time of the last byte received (null otherwise). `describe` says `silent since 18:43 (17 min)` in UTC.

**Probing.** While silent the Tnc probes every `PROBE_SEC` (30 seconds), the same sequence as a check, and every `REOPEN_EVERY` (5th) probe also closes the port
and opens it again; the radio stays silent across that. The first byte that arrives, whatever it is, ends the silence cleanly:

- the Tnc is `connected`;
- the allowance to enter KISS (once for every answer: a fresh open, each return from silence, each check or probe) is given back;
- the mode detector (`neoaprs/tncmode.py`) starts over;
- KISS is entered (the profile's entry) unless the bytes are a KISS frame already;
- the Tnc is not `usable` until the settling time after that has passed, and a beacon that fell due in the night goes out then, as a KISS frame.

**The log.** A check that finds the radio, each probe and each KISS entry made by a check or a probe are DEBUG only. At WARNING, once, when the silence begins:
`the radio is silent: nothing heard since 18:43 UTC, no answer to a check; probing every 30 s`. At INFO, once, when it ends:
`the radio answers again after 17 min; entering KISS`. A KISS entry on a fresh open stays INFO.

**On the wire.** `TncState` (the topic `tnc`) counts in `stats`: `keepalive_checks`, `watchdog_probes`, `port_reopens`, `digipeated`, and has
`last_watchdog_action` (`check`, `probe`, `reopen` or empty) with `last_watchdog_at`. It also has `searching` (the ports being listened to) and `lines` (the
latest 100 as `{at, text}`). The page shows the packet and byte counts as the hover title of the radio status.

**A TCP profile.** It connects to `tcp/host` and `tcp/port`, or to the address in `serial/port`, which is then used as it stands. A TCP connection that closes,
or a serial device that goes away, is a line that dropped and is opened again after the back-off (5, 10, 20, 30 seconds). A `bt://` port is opened by
`neoaprs/btserial.py` (the RFCOMM link by itself, with the channel looked up through `neoaprs/btsdp.py`); the paired devices are listed by
`neoaprs/btpaired.py`.

**The search** (`neoaprs/tncsearch.py`, `neoaprs/serialprobe.py`). On Linux the globs of `serial/pattern` are all listened to at once. With a profile that can
be asked a carriage return is sent after 10 s of silence; a port another program holds (`neoaprs/serialholders.py`) is skipped, and so is a development board
known by its USB ids (`neoaprs/serialboards.py`).

## Stopping

`neoaprs stop` writes the file `neoaprs.stop` into the data folder. The daemon looks for it once a second (`neoaprs/stopfile.py`), deletes it and ends cleanly (`NeoAPRS ended` in the log), and the command waits until the instance lock is free. Exit 0 when it ended or none was running, 1 after `--timeout` (30 s). It needs no port and no key; whoever can write to the data folder (private to the user) could end the process as well. SIGTERM, SIGINT and SIGHUP (on Windows Ctrl+C, SIGBREAK and SIGTERM) end the daemon the same way. A detached daemon of `neoaprs open` is started as `neoaprsw.exe run` on Windows and as a child in a session of its own elsewhere, its output going to `neoaprs.log`; `open` waits for the log line `web page at` and for the page to answer.

## The beacon and the status

`neoaprs/services/beacon.py` makes the position frame; `neoaprs/services/rigstatus.py` the status. The frame is made when it is sent, from the settings then.
`Beacon.frame()` is also the answer to `?APRSP`.

The time of each beacon is kept in the row `beacon/last_sent_at`, and the time and text of the last status in `status/last_sent_at` and `status/last_text`
(`neoaprs/services/memory.py`). They are state of the daemon, not settings, so the Settings tab does not list them. A daemon that starts less than an interval
after the last beacon waits for it; with no row, or an older one, the first beacon is `FIRST_DELAY_SEC` (30 seconds) after the start.

A frame the Tnc refuses is tried again `RETRY_SEC` (5 s) later, `ATTEMPTS` (6) refusals in all, and then the interval is skipped.

The tocall is `TOCALL` in `neoaprs/__init__.py`. `APZ...` is the experimental range. A tocall of your own is registered by opening an issue at
<https://github.com/aprsorg/aprs-deviceid>; it would then replace the constant.

The status goes out by one rule, whether the text comes from the radio or the settings: the interval has passed and what it says has changed. The text is
checked when it is saved, the template with its widest fill, and the frame again when it is made. A report the TNC would not take is told once and tried again
at the next poll. From the radio, a fresh short connection to rigctld is made every 30 seconds, asking `f` (the frequency in Hz) and `m` (the mode and the
passband); an `RPRT -n` answer, a refused connection or no answer within 5 seconds means the radio is off or rigctld is away.

`status_now` sends the status at once with the same checks and answers with an `error` that says why when it cannot. The `status` message has `station_status`
(the last text sent) and `rig_state` (`on`, `off`, or `unused` while the status does not come from a radio), and carries the process's cost every 10 seconds
(`neoaprs/web/processmeter.py`, from `os.times` and `/proc/self/statm`; the working set on Windows, `neoaprs/web/winmemory.py`).

## Messaging

The commands are `send_message`, `query` (a directed query, once, with no id: `neoaprs/services/asking.py`), `message_retry`, `message_cancel`, `message_delete`, `conversation_delete` and `overheard_delete`. Messages to bulletins and
groups are the board's. Every message is a row of the table `message`, so a restart goes on where the daemon stopped.

- **The frame.** `OH2GBA>APZNEO,...::OH2RDG   :Hello Pekka{01}` is the source, the tocall, the path of the attempt (below), then `:`, the addressee padded to nine
  characters, `:`, the text, `{`, the id and `}`. Our ack of a message is the exact copy of its number: `ackMM` for `{MM`, `ackMM}` for `{MM}`, `ackMM}AA` for `{MM}AA`. When the station sent a message with a reply-ack number that its own ack has not reached it with yet, the id
  of the latest of them follows the brace.
- **The attempts.** `STATION_ATTEMPTS` (4) and `EMAIL_ATTEMPTS` (2) of `neoaprs/message.py`. The wait after attempt n is `FIRST_WAIT_SEC` (32, not 30: a retry
  exactly on the edge of the digipeaters' 30-second duplicate window could be dropped as a duplicate) doubled each time
  up to `MAX_WAIT_SEC` (960); the answer to the last is waited for 240 seconds. The count is kept with the message (`attempts_max`, in the database and on the
  wire) from the moment it is sent, so a message goes on with the number it was given. A message with `UNCONFIRMED_MAX` (2) attempts or fewer that has used them
  is `unconfirmed`, not `failed`.
- **While the TNC is away** an attempt that is due waits, none is used up, and the waits that were running are moved on by the time the radio was away.
- **The pace** is `SPACING_SEC` (10 s) in `neoaprs/services/pace.py`: our own attempts go out one at a time, at least that far apart. Acks and the answers to queries are not held back.
- **Receiving.** A message is for us when its addressee is `station/call` with its SSID exactly. `neoaprs/services/inbox.py` takes what the Tnc hears;
  `neoaprs/services/heard.py` holds the repeats already heard and when each was last acked, in memory; a copy is acked again only `ACK_AGAIN_SEC` (30 s, the digipeaters' duplicate window) or more after our last ack of it. The ack goes by the sender's path.
- **The delivery chain** (`neoaprs/services/delivery.py`). A copy of one of our own messages that the radio hears again (same addressee, id and text from our
  call; also one an iGate gated back as a third-party packet) is linked to the message and to the attempt it belongs to, the latest attempt sent before it was
  heard. Each attempt keeps when it was sent and the digipeaters it went by (the table `message_attempt`), and each hop that a copy was heard with its
  has-been-repeated bit set (the table `message_hop`: the position, the call that did it, which is the one heard when the path had an alias such as `WIDE1-1`,
  when, and whether it was a third-party copy; position 0 is such a copy whose own path names no hop, with the iGate's call). A hop used implies the hops before
  it. Both tables go with the message when it or its conversation is deleted, and a retry starts a new chain. `RFONLY`, `NOGATE`, `TCPIP`, `TCPXX`, `NOTCP` and
  the q-constructs are no hops and are left out of what is kept and told.
- **On the wire** the row of the topic `messages` has `attempts_detail`, an entry for each attempt with its hops, and a hop that is heard is a `set` of the row.
- **What is kept.** Every message while the daemon runs (the table is written as it changes). A start takes at most the latest 10000 messages and warns when
  there are more; the older ones stay in the database.
- **Deleting.** `message_delete` removes a message of any kind from the database, the daemon's records and, by a `del` of the topic `messages`, from every page.
  One that is still being sent is cancelled first, and an id the daemon does not hold is an `error`. The page has no button for it. `conversation_delete{call}`
  removes both directions of a conversation in one write (`messagesql.delete_conversation`), a `del` for each message, cancelling those being sent first; a call
  with no message is an `error`. `overheard_delete{from_call, to_call}` does the same for the overheard pair (`messagesql.delete_overheard`).
- **Reply-acks.** The page and the daemon follow WB4APR's addendum of 1999 (`aprs.org/aprs11/replyacks.txt`). The `AA` of a message is not part of the text that
  is kept, so a repeat with another `AA` is a repeat.
- **Telemetry and queries** are recognised before anything is kept: a query, and the definition of a telemetry station's channels (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`), are in the packet log only.

**Alerts** (`neoaprs/services/alerts.py`). The shell line is run by `asyncio.create_subprocess_shell`. Its environment is made by `neoaprs/childenv.py`.
`TIMEOUT_SEC` is 20 s (60 on Windows), `MAX_RUNNING` is 5, and a failure is told at WARNING once an hour (`TOLD_EVERY`). On Windows the line is a PowerShell
script run from a thread as an encoded script, so nothing of it is quoted and the text is never in it; a step that fails ends it with status 1
(`$ErrorActionPreference='Stop'`), and a run out of time is killed with everything it started (`taskkill /T /F`). The unit sets
`DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus`. The command `alert_test` runs it as saved, whatever `messages/alert` says, and answers `alert_result{ok, text}`; an
empty command is an `error`.

**The message board** (`neoaprs/services/bulletins.py`; the inbox hands over what it takes). The wire is the topic `bulletins`, `{sender/slot: BulletinRow}`. A
`set` is for a bulletin that is new or heard again and a `del` for one that is deleted. A row has `sender`, `slot`, `group`, `kind` (`announcement`, `bulletin`, `group` for a group bulletin and the messages to `ALL`, `CQ` and `QST`, or `nws` for the weather service), `text`, `first_heard`, `last_heard` and `times_heard`. The table `bulletin`
(migration 7) has one row for a sender and slot, strict, with named CHECKs. `bulletin_delete{sender, slot}` removes the row; an entry that is not there is an
`error`.

**Queries** (`neoaprs/services/queries.py`). `GENERAL_DELAY_MAX_SEC` (120), `GENERAL_EVERY_SEC` (600), `ANSWER_AGAIN_SEC` (30), `DIRECT_WINDOW` (one hour),
`MAX_DIRECT_MESSAGES` (2). For `?APRSD` the stations are those of the station book (not us, not objects), and "heard direct" is a packet with no repeated
digipeater that was not a third-party packet.

**The path of an attempt.** `Messaging` asks `PrefBook.path_for(call, attempt)` each time it sends an attempt of a message that has an id (the attempt is
`record.attempts + 1`); acks and answers ask with no attempt. The path is, in order: the station's own path (`station_pref`), else for attempts up to
`HEARD_PATH_ATTEMPTS` (2) of a message to a station other than `EMAIL-2` the heard path, else `beacon/path`; `RFONLY` is added to whichever it is. The heard path
is the pure function `route.heard_path(deliveries, now)` (`route.automatic_path` adds the attempt rule) over the station book's `Deliveries`, which keeps for
direct and for each route the times of its latest `TIMES_KEPT` (2) packets (seeded from the database with the two latest of each group,
`PacketLog.deliveries`): direct if `HEARD_PATH_MIN_PACKETS` (2) of them are within `HEARD_PATH_WINDOW_MIN` (60) minutes, else the route heard last with that many
within the window, no anonymous hop, no gate (those are counted apart), no marker, at most `HEARD_PATH_MAX_DIGIPEATERS` (3) digipeaters, reversed. The constants
are in `neoaprs/policy.py`. The delivery chain records the digipeaters of each attempt as it was sent. The station row tells the choice as `heard_path` (null: none, empty: direct), worked out
when the row is made.

**The path settings.** An empty path never means no digipeaters. `beacon/path` empty is the recommended `WIDE1-1,WIDE2-1`; the word `DIRECT` (`route.DIRECT_ONLY`,
`message.path_choice`) is no digipeaters, and stands alone (`normal_path` refuses it among calls with `path.direct_alone`). Migration 14 changed a stored empty
`beacon/path` to `DIRECT`. A station's own path: the stored `path` null is none (automatic), `''` is direct; `set_station_path` takes calls or `DIRECT`, and an empty
`path` is `clear_station_path`. An own object's or item's path: null (or empty) is `beacon/path`, `DIRECT` is none.

**The station preferences** (`neoaprs/services/prefbook.py`; the table `station_pref`). The path, the timeout (`hide_after_min`) and the RF-only flag of each
station, under the call as written, in the row `{path, hide_after_min, rf_only}` of the topic `station_prefs` (the first two null where none is set, a `path` of `""` is
direct; an entry with neither and `rf_only` false is not kept). The commands are `set_station_path` (calls, or `DIRECT`; an empty `path` clears), `clear_station_path`, `set_station_timeout`,
`clear_station_timeout` and `set_station_rf_only{call, on}`. `PrefBook.path_for` adds `RFONLY` so every frame to the station takes the same road. The daemon
only keeps and tells the timeout, except that the daily prune keeps a station with a timeout of 0 in the station book and its cache row. Messaging is given
`path_for`, the prune its `never_hidden`. `set_station_rf_only` for `EMAIL-2` is an `error`.

**The station book** (`neoaprs/stationbook.py`) counts, for each station, how many packets came direct and by each route, from the packets since the start and
the latest 2000 that the database kept. The row of the topic `stations` has `last_route`, `heard_direct`, `heard_via` (`[station heard, packets]`, the most
first, `?` for an anonymous last hop), `heard_gated`, `best_route`, `suggested_path`, `last_direct_at` (null for a station never heard direct, for us and for objects; it is the time of the station's latest packet with no repeated address in its path, not a third-party one), `can_message` and `telemetry`. `can_message` is false for an object or an item and for a station whose positions use the identifiers `!` or `/`, unless it has sent a message or an ack that we heard (overheard ones too) or a Mic-E position. It is found again at the start from the packet log, and a bulletin or a telemetry definition does not count. The route is worked out when the packet is heard (`neoaprs/route.py`) and is `route` on every packet of the topic `packets` (empty for
the ones we sent) and on every message that came in or was overheard (the column `route` of the table `message`; of two copies by different routes the first is
the one kept).

**Third-party packets** (`neoaprs/aprsthirdparty.py`). One level only: a wrapper inside a wrapper, or one whose header is not a header, stays "third-party" and
is not read. The packet keeps the gate as its `source` and the path it was heard by; `raw` and `info` are untouched, `decoded` is what the packet inside says,
read as from its inner source to its inner destination (which Mic-E needs), and `third_party` holds the inner header. The inner source and destination are calls or names APRS-IS allows (1 to 9 letters, digits
and hyphens: `OH2XYZ-L`, `OH2XYZ-20`, `WINLINK`; `callsign.normal_name`, upper case); messaging, the station book and the station's settings take such a name as the station, and a message to it is sent like one to a call. The summary ends "via OH7JHF-1
(third-party)". The gate counts as `heard_gated` and never for `suggested_path`.

## Objects and bulletins of our own

The commands are `object_set`, `object_kill`, `bulletin_post` and `bulletin_unpost`; the topics are `own_objects` and `own_bulletins`. Both services are
`neoaprs/services/repeater.py`'s ticker and send through `neoaprs/services/sender.py`, which holds back everything while the call is not set or the radio is not
usable, and puts a pause between two frames of ours.

- **Schedule** (`neoaprs/decay.py`). `FIRST_WAIT_SEC` 60, `MIN_GAP_SEC` 60, `KILL_SENDS` 3, `KILL_WAIT_SEC` 60; the net cycle time is 10 minutes for 0 or 1
  digipeaters, 20 for 2 and 30 from 3 on. `BULLETIN` is early waits of 120 and 240 s, then every 20 minutes, for 4 hours; `ANNOUNCEMENT` the same, then every
  hour, for 72 hours.
- **The interlock** is `config.can_transmit`, with the Tnc's own check. The log says `no object sent: set your call first` once.
- **Limits** are in `neoaprs/ownobject.py` (`OBJECT_NAME`, `ITEM_NAME`, `NAME_FORBIDDEN`, `COMMENT_MAX`, `COMMENT_MAX_MOTION`, `COURSE_MAX`, `SPEED_MAX_KMH`)
  and `neoaprs/ownbulletin.py` (`GROUP_MAX`, `MAX_POSTED`); the page takes them from the daemon (`LIMITS` of `ui/src/protocol/lists.ts`).
- **Tables.** `own_object` (migration 13): name, kind, position, symbol, comment, course, speed, path, whether it is alive or being killed, when it was made and
  last changed, how often it was sent since then, when last; strict, with named CHECKs. `own_bulletin`: slot, group, text, when posted, how often sent, when
  first and last. Both are written after every change and every packet.
- **On the wire** the topic `own_objects` has the values and the schedule of each (`state` `live` or `killing`, `sent`, `last_sent_at`, `next_at`) and the topic
  `stations` a row with `own` true for each live one.
- **Heard back.** The station book counts a packet from our own call as proof that we are heard and does nothing else. Replacement: when another station reports
  a live object with the name of one of ours, ours is dropped without a kill.
- **A bulletin of ours that comes back** is taken by the inbox for a copy of what we sent, so `times_heard` of nobody changes.

## Weather and the database tables

The weather is `Weather` of `neoaprs/aprsweather.py`: metric values, each `None` where the report did not have the field, and the fields as sent (`raw`). It is
`Position.weather` (the weather's fields are not the comment) and `Other.weather` for a positionless report (the packet's kind stays `other`).

**The table `weather`** (migration 8; `station`, `at`, `wind_dir`, `wind_kmh`, `gust_kmh`, `temp_c`, `humidity`, `pressure_hpa`, `rain_1h_mm`, `rain_24h_mm`,
`rain_today_mm`, `luminosity`, `raw`; STRICT with named checks, an index on station and time) is appended without waiting (`neoaprs/weatherlog.py`). `at` is
when the packet was heard. Rows are pruned after 7 days.

**At the start.** When the weather table is empty, the weather packets of the last 7 days are read from the packet table (found by what the parser decoded: a
weather packet, or a position, object or item with the weather symbol; a third-party packet is the sender inside it), decoded and written in one transaction,
and the log says how many. A table that holds anything is not made again. Then every station in the book is given its newest observation (`Station.weather` and
`weather_at`).

**On the wire.** The row of `stations` has `weather` (the metric fields, null for a station that sent none) and `weather_at`. `weather_series{call, hours}` (1
to 168) is answered to the page that asked with
`{"type": "weather_series", "call", "hours", "points": [[time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity], ...]}`, oldest first, null for a
value the report did not have. The graphs are inline SVG (`lib/chart.ts` is the arithmetic, `TrendChart.vue` one graph); there is no chart library.

**The tracks.** At the start they are made again from the latest 5000 position packets heard within 7 days (a position, or a live object or item under its own
name; the sender inside a third-party packet), oldest first, with the rule the live track has: a point joins when the station moved more than 10 m or 5 minutes
passed, the latest 50 are kept.

**The tables** of the database: `settings`, `packet`, `station` (the cache), `message`, `message_attempt`, `message_hop`, `bulletin`, `own_object`,
`own_bulletin`, `weather` and `station_pref`. `station_pref` is operator data and not part of the station cache, so it survives a rebuilt cache. Everything is
described in `neoaprs/migrations.py` and `neoaprs/migrations2.py`; how the database is written is in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md#the-database-actor).

## What the parser reads

`neoaprs/aprs*.py`, tested against captured frames (`tests/fixtures/aprs/`).

- **Weather fields** (`neoaprs/aprsweather.py`) after the position or the time: `c` or the leading `DIR/SPD` the wind direction (degrees; some stations send two
  digits) and speed (mph), `g` the gust (mph), `t` the temperature (degrees F, `t-05` below zero), `r` rain in the last hour, `p` in the last 24 hours, `P`
  since midnight (hundredths of an inch), `h` humidity (`00` is 100 %), `b` pressure (tenths of a hPa), `L` and `l` luminosity (W/m2, `l` is 1000 and over), `s`
  snow in the last 24 hours (inches, the `s` that follows the wind speed) and `#` the raw rain counter. A field that is all dots or all spaces is missing. The
  fields end at the first character that is not a field with its digits, and what follows (a software id such as `wRSW`, a comment glued to the data like
  `b10285Inkoo`) is the comment. A compressed weather position's `cs` bytes are the wind (direction `c`*4 degrees, speed 1.08^`s`-1 mph), and its fields after
  the 13 bytes are the rest.
- **Summary.**
  `position 60.4072 23.8788 /_ weather: wind 107° 2 km/h gusts 2, 10.0 °C, 85 %, 1028.4 hPa, rain 0.3 mm/h, 24 h 4.1 mm, today 3.3 mm - RX Igate & WX station`,
  only the fields that are there. Wind and gusts are km/h to 0.1, rain mm to 0.1, a direction over 360 is none.
- **Data extensions** after the symbol of an uncompressed position are taken off the comment into `Position.extensions`: `PHGphgd` (power in W, height in m,
  gain in dB, directivity and the range the specification's formula gives), `RNGrrrr` in km, `DFSshgd`, the `/BRG/NRQ` of a DF report after the course and
  speed, and the `Tyy/Cxx` of an area object with the symbol `\l`. A compressed position has none.
- A `!` position may come after up to 39 characters of text (a digipeater of the X1J kind): the text is the start of the comment.
- A timestamp with `/` is the sender's local time: kept as sent with `Position.timestamp_local` set. The MMDDhhmm of a positionless weather report is its time (`Other.timestamp`).
- **Raw NMEA** (`$GPGGA`, `$GPGLL`, `$GPRMC`, `$GPWPL`, any talker; the checksum is checked when there is one) is a position with course, speed, altitude and
  time. Its symbol is the one of the destination (`GPSxyz`, `GPSCnn`, `GPSEnn`, `SPCxyz`), else the icon of the source's SSID, else the unknown position.
  `$GPVTG` and a fix that is not valid stay "nmea", and `$ULTW` (an Ultimeter 2000) is "weather" without fields, because its format is not in the specification.
- **Telemetry** `T#sss,aaa,aaa,aaa,aaa,aaa,bbbbbbbb` is its own decoded type (`Telemetry`, packet kind `other`). The daemon keeps each station's latest report
  and the `PARM.`, `UNIT.`, `EQNS.` and `BITS.` messages addressed to it (in memory, the latest 500 stations, read again from the latest 2000 packets at a
  start) and sends the station row `telemetry` with the names, units and values `a*v^2 + b*v + c` applied (raw values when it sent no definition).
- `,` is test data ("test"), `<` station capabilities (`items`: `IGATE`, `MSG_CNT=2`...), `%` an Agrelo DF report (`bearing`, `quality`), `+` shelter data and
  `.` space weather (kept as text), `[` a Maidenhead locator beacon (a position at the centre of the square; the specification lists `[` as unused).
- A **Maidenhead locator** at the start of a status report (`>IO91sx/-` and text after a space) is `Status.locator`, and in the status text of a Mic-E packet
  `Position.locator`. The station row has it as `locator`, and it does not move the station.
- **Mic-E.** The telemetry flag
  "`" is followed by two values of two hex digits, "'" by five, and 0x1d by five bytes (all dropped from the comment). The altitude `xxx}` is read at the start of the status text (after the locator) or as a word of its own after a space.

## The update check

`neoaprs/services/updatecheck.py` asks `update/url` through `neoaprs/updatefetch.py`, `FIRST_SEC` (60) after the start and every `EVERY_SEC` (24 hours);
`neoaprs/versions.py` compares the versions and reads the answer. It keeps the answer only if it is newer than ours, and the `status` message carries it.
`check_now` is the same question on request (`update_check`, answered by `update_result`). `NEOAPRS_UPDATE_CHECK=0` switches it off for the run. The kind of
system sent is worked out by the process in `neoaprs/cli/installkind.py` and given to the controller; the `hello` message carries it so the page can say how to
update. The page loads itself again when its built-in version differs from the one in `hello`; the daemon serves `index.html` with `no-cache` and the other
files by the hash of their content.

**Update now** (`neoaprs/services/selfupdate.py`) is the update the daemon does itself on the page's `update_now`, for the Windows installer and an AppImage:
the release's file and `SHA256SUMS` of the announced version from GitHub, the SHA-256 checked, then the installer of the kind (`neoaprs/services/selfinstall.py`)
and the restart; the topic `update` tells its steps. The flow and its safety checks are in [development.md](development.md#update-now).
