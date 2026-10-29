# How the daemon behaves

The details behind the [manual](manual/README.md), with the names the code and the wire use. The wire itself is in [`PROTOCOL.md`](../PROTOCOL.md); the layers
the parts are in are in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md). The policy numbers (`LOG_KEEP_DAYS`, `TNC_CHECK_SEC`)
are in `neoaprs/policy.py`.

## The TNC and its keep-alive

`neoaprs/tnc.py` is the one feed of packets; `neoaprs/source.py` is its base (state, problem, counts, the latest lines, the back-off). The profile
(`neoaprs/tncprofile.py`) is the one place that knows a device's words, with the source of each string in a comment. A profile that cannot be asked (`kiss`,
`kiss-tcp`) never has the check, the silent state or the probes.

**The check.** While the port is open and the profile can be asked, the Tnc counts the time since anything at all arrived; a damaged frame or noise counts.
After a quiet `TNC_CHECK_SEC` (600 seconds, longer by a random share of up to `TNC_CHECK_JITTER`, 20 %) it makes a check: the profile's exit (`C0 FF C0`), half a second (`CHECK_PAUSE_SEC`), a bare carriage return
(`PROMPT`), and then the profile's entry with its settling time, unless a KISS frame answered the carriage return (the TNC did not leave KISS for the exit frame, so it is in KISS already and the
entry would only cost reception). A TH-D7 that is on answers with text (`cmd:`) within about a second. Any byte in answer means
the radio is there: the state stays `connected` and the clock starts again from the latest byte.

**A line that has just been opened** (the daemon starts, or the line dropped and was opened again) has not shown yet that the radio is there. For a profile that
can be asked the Tnc makes the same check at once. Until a byte arrives it is `connected` but not `usable`, with the reason "the TNC is checking that the radio
is there". The beacon, the status, the messages, the acks and the answers to queries wait exactly as they wait while the radio is silent. A byte heard before
the check runs confirms the line and the check is skipped, and so does a port that the search chose, which has just been heard from; when what the search heard was command-mode text (the `cmd:` prompt
or a monitored packet), KISS is entered right at the open, the entry the TNC's next line would have made, so that a frame due at the start waits for the settling time instead of being typed into the TNC. Nothing is sent while a
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
- KISS is entered (the profile's entry) unless the bytes are a KISS frame already, or a piece of one (a FEND among them and no whole frame: a line delivers a frame in several reads, and command-mode
  text never has a FEND), when what follows decides;
- the Tnc is not `usable` until the settling time after that has passed, and a beacon that fell due in the night goes out then, as a KISS frame.

**Text after the entry.** A TNC that goes on typing command-mode text after the entry has settled (a radio switched on a moment ago misses the first `KISS ON` while it starts) is not `usable`, with
the reason "the TNC is in command mode", and is sent the entry again: `ENTRY_AGAIN_SEC` (10 s) after the settle, then after twice as long each time up to `ENTRY_AGAIN_MAX_SEC` (60 s), so that a TNC that never
takes it (the wrong profile) is not restarted every ten seconds for ever. The first repeat is INFO, the later ones DEBUG, and each is a line in the terminal; the schedule is `EntryAgain` in
`neoaprs/tncwatchdog.py` and starts over with every new answer (an open, a return from silence, a check) and when a KISS frame comes at last. The mode detector judges each line of text by itself, so a
comment with a letter outside ASCII or a Mic-E byte hides neither its own header nor the lines around it; a KISS frame never counts as text, because its first byte, the command, is not text.

**The log.** A check that finds the radio, each probe and each KISS entry made by a check or a probe are DEBUG only. At WARNING, once, when the silence begins:
`the radio is silent: nothing heard since 18:43 UTC, no answer to a check; probing every 30 s`. At INFO, once, when it ends:
`the radio answers again after 17 min; entering KISS`. A KISS entry on a fresh open stays INFO.

**On the wire.** `TncState` (the topic `tnc`) counts in `stats`: `keepalive_checks`, `watchdog_probes`, `port_reopens`, `digipeated` (with `digipeated_at`, when the latest went out, and `digipeat_held`, the frames the burst limit left unsent), and has
`last_watchdog_action` (`check`, `probe`, `reopen` or empty) with `last_watchdog_at`. It also has `searching` (the ports being listened to) and `lines` (the
latest 100 as `{at, text}`). The page shows the packet and byte counts as the hover title of the radio status.

**Recovery without a click.** There is no Reconnect command: every way the line can fail ends in an attempt to open it again. A silent radio is probed, and the first byte ends the silence (above). A port that goes away (a USB adapter pulled out, a COM port that disappears)
is a line lost: the Tnc is `waiting` and tries again after the back-off, and on Linux, where the radio is searched for, the next attempt after a failed open listens to the ports that match the pattern, so an adapter that comes back as another device file is found. Where the radio is not
searched for (Windows, macOS) `neoaprs/tncfollow.py` remembers which USB adapter the named port was (`serialprobe.identity_of`: vendor and product ids, and the serial number when there is one) and, when the port cannot be opened and the system no longer lists it, opens the port that adapter is on now
(`serialprobe.moved_to`: the one port with its serial number, or, for an adapter with none, the only port with its ids; two that look alike are left to the operator). The setting is not changed; the memory lasts as long as the process (a daemon started while the adapter is already renumbered
needs the port chosen once). `tests/test_tnc_recovery.py` holds these cases.

**A TCP profile.** It connects to `tcp/host` and `tcp/port`, or to the address in `serial/port`, which is then used as it stands. A TCP connection that closes,
or a serial device that goes away, is a line that dropped and is opened again after the back-off (5, 10, 20, 30 seconds). A `bt://` port is opened by
`neoaprs/btserial.py` (the RFCOMM link by itself, with the channel looked up through `neoaprs/btsdp.py`); the paired devices are listed by
`neoaprs/btpaired.py`. A `ble://` port is opened by `neoaprs/btle.py`: bleak on a thread and event loop of its own looks for the device by its address, connects, picks the GATT service
(the Mobilinkd/aprs.fi BLE KISS service, else the Nordic UART Service, or the one the URL names), listens to its notify characteristic and queues what it notifies for `read`; `write` goes
out in pieces of what the link takes. A lost link is the exception of the next read or write, so the TNC opens the port again as for a dead socket.

**The search** (`neoaprs/tncsearch.py`, `neoaprs/serialprobe.py`). On Linux the globs of `serial/pattern` are all listened to at once, and the ports that match are listed again every
`RELIST_SEC` (10 s) while the search listens: one that appeared (a radio plugged back in; the named port the search stands in for, listened to even when it does not match the pattern) is opened, one
that vanished is closed. With a profile that can be asked a carriage return is sent to a port after 10 s of silence; a port another program holds (`neoaprs/serialholders.py`) is skipped, and so is a development board
known by its USB ids (`neoaprs/serialboards.py`).

**Find my radio** (`neoaprs/services/radiofinder.py`, `neoaprs/services/radioprobe.py`), on the page's `find_radio` only. On Linux it tries the ports of the search (the pattern in force, the
skip list, the held ports and the boards left out; with the default pattern also the paired Bluetooth devices; a pattern that was narrowed, such as the tests' `NEOAPRS_SERIAL_PATTERN`,
means no Bluetooth device and no port that does not match it); on Windows and macOS (`serialprobe.can_find`, where the search that runs by itself is not made) the ports of the system's list
(`serialprobe.system_ports`: `serial.tools.list_ports`, so the COM ports with their description and hardware id, USB adapters first, boards and the skip list left out, Bluetooth serial ports last; on macOS also
the `/dev/cu.*` devices) when the pattern is the default one. A COM port of a paired Bluetooth device (`BTHENUM` hardware id) has no speed. One at a time, each at 9600, 57600, 19200, 38400, 115200, 4800 and 1200 baud (a socket or Bluetooth port once). A try listens
1 s, writes one carriage return, listens 1.5 s: a KISS UI frame is the profile `kiss`, command-mode text (`ModeDetector`) is put into KISS by the profiles that can be asked (TNC-2, D710,
Kantronics, in that order), and the first after which a carriage return gets no text is the answer. The Tnc is stopped while it runs (`hold_tnc`) and started again after it (`release_tnc`), found or not;
`radio_search` messages tell the page that asked each try and the end, and `find_radio_cancel` ends it (a closed page ends it too).

**The Dummy radio** (`neoaprs/dummyline.py`, `neoaprs/dummyscene.py`, `neoaprs/dummyframes.py`, `neoaprs/dummyroutes.py`, `neoaprs/aprsmiceout.py`) is the TNC profile `dummy` (transport `dummy`, no port, no speed). The Tnc opens a `DummyPort` in the place
of a serial line: a task that asks a `Scene` every half second what has come due and hands the frames to the Tnc as KISS bytes, so that the KISS decoder, the AX.25 decoder and the parser work as for a radio. The scene is pure
(a clock is given to it) and seeded: fixed stations (`Q1ABC`, `Q1CLB`, `Q8QTH`), cars (`Q4CAR-9` and `Q6CAR-1` in Mic-E, `Q5VAN-7` compressed), a walker (`Q7WLK-7`), a weather station (`Q3WX`, every 5 min), two digipeaters with PHG
(`Q2DIG-2`, `Q7DIG-1`, which repeat the first frame of the others with themselves starred in the path), two objects and a bulletin and a status from the club and the house, all round `station/lat` and `station/lon` (Helsinki when none is set)
and at most 8 km from it. The stations that send `=` positions answer a message: an ack after 1.5 s, "Hello from the dummy radio" 3.5 to 6 s later, once for each message. What the Tnc writes is decoded by the port and shown to the scene and then dropped:
a position of ours is played back as repeated by `Q2DIG-2` (the first always, then 6 in 10). Every call is on the ITU prefix Q, which no country has. `Source.is_dummy` is true for the Dummy (the Tnc says it by its profile's transport, there is no flag of its own): every packet the Tnc hears or sends is made in `Tnc._handle` and `Tnc._transmit`, like a radio's, with the channel `dummy`, and
whatever sends packets to the internet (an iGate) takes the packets of the channels in `packet.GATEABLE` only. The iGate also puts nothing of ours (its timed position, a moving station's beacon) on APRS-IS while `Igate.made_up()` (set by `app.py` to `Tnc.is_dummy`) says the radio is the Dummy.

## Stopping

`neoaprs stop` writes the file `neoaprs.stop` into the data folder. The daemon looks for it once a second (`neoaprs/stopfile.py`), deletes it and ends cleanly (`NeoAPRS ended` in the log), and the command waits until the instance lock is free. Exit 0 when it ended or none was running, 1 after `--timeout` (30 s). It needs no port and no key; whoever can write to the data folder (private to the user) could end the process as well. SIGTERM, SIGINT and SIGHUP (on Windows Ctrl+C, SIGBREAK and SIGTERM) end the daemon the same way. A detached daemon of `neoaprs open` is started as `neoaprsw.exe run` on Windows and as a child in a session of its own elsewhere, its output going to `neoaprs.log`; `open` waits for the log line `web page at` and for the page to answer.

## The beacon and the status

`neoaprs/services/beacon.py` makes the position frame; `neoaprs/services/rigstatus.py` the status. The frame is made when it is sent, from the settings then.
`Beacon.frame()` is also the answer to `?APRSP`.

The time of each beacon is kept in the row `beacon/last_sent_at`, and the time and text of the last status in `status/last_sent_at` and `status/last_text`
(`neoaprs/services/memory.py`). They are state of the daemon, not settings, so the Settings tab does not list them. A daemon that starts less than an interval
after the last beacon waits for it; with no row, or an older one, the first beacon is `FIRST_DELAY_SEC` (30 seconds) after the start.

A frame the Tnc refuses is tried again `RETRY_SEC` (5 s) later, `ATTEMPTS` (6) refusals in all, and then the interval is skipped.

**Beacon off.** `beacon/interval_min` 0 is off, for a fixed and a mobile station alike (`Config.beacon_on`; the page's Beacon choice is Off or an interval, or Off or On for a moving station, where any other value is On and unused). While it is off the beacon's timer and SmartBeaconing send nothing, `send_now` (`beacon_now`) is refused with `BEACON_OFF` ("the beacon is off", the reason of the coded error `beacon.not_sent`), and `RigStatus` sends no status, neither on its poll nor for `status_now` (`status.not_sent` with the same reason). Nothing else changes: messages, acks, answers to queries, own objects and bulletins and the digipeater do not look at it, so it is not receive only. A status held back goes out at the first poll after the beacon is on again if it differs from the last one and the interval has passed. `station/transmit` is the other switch: `can_transmit`'s first reason, which stops every frame and is not on the page (the header still marks it).

The tocall is `TOCALL` in `neoaprs/__init__.py`. `APZ...` is the experimental range. A tocall of your own is registered by opening an issue at
<https://github.com/aprsorg/aprs-deviceid>; it would then replace the constant.

The status goes out by one rule, whether the text comes from the radio or the settings: the interval has passed and what it says has changed. The text is
checked when it is saved, the template with its widest fill, and the frame again when it is made. A report the TNC would not take is told once and tried again
at the next poll. From the radio, a fresh short connection to rigctld is made every 30 seconds, asking `f` (the frequency in Hz) and `m` (the mode and the
passband); an `RPRT -n` answer, a refused connection or no answer within 5 seconds means the radio is off or rigctld is away.

`status_now` sends the status at once with the same checks (and while the beacon is off it sends nothing) and answers with an `error` that says why when it cannot. The `status` message has `station_status`
(the last text sent) and `rig_state` (`on`, `off`, or `unused` while the status does not come from a radio), and carries the process's cost every 10 seconds
(`neoaprs/web/processmeter.py`, from `os.times` and `/proc/self/statm`; the working set on Windows, `neoaprs/web/winmemory.py`).

## The GPS and the moving station

`gps/source` says where the position comes from: `off`, `gpsd` or `serial`. It alone decides whether the station moves: `off` (Fixed on the page) is a fixed station at the stored location (the beacon on `beacon/interval_min`, with PHG), `gpsd` or `serial` a moving one whose beacon follows the GPS (`Config.mobile`; `GpsState.mobile` on the wire is the same). The feed (`neoaprs/gpsfeed.py`, a `Source` like the TNC, with a state, a problem line and the back-off of `Backoff`) runs while the
source is not `off`, and never raises into the loop.

- **gpsd** (`gps/host`): one TCP connection, opened with a timeout of 5 seconds, over which `?WATCH={"enable":true,"json":true}` is sent. gpsd answers with a JSON object a line: `GpsdFixes` (`neoaprs/gpsfix.py`) makes a
  fix of each TPV report with mode 2 or 3 (`speed` is metres per second, `track` degrees, the altitude `altMSL`, else `alt`, else `altHAE`: APRS wants it above sea level) and the satellites of the latest SKY report
  (`uSat`, else the ones marked used). A line that is not JSON is counted in the rejected. A connection that is refused, lost or hung up is opened again after 5, 10, 20, 30 seconds.
- **serial** (`gps/device`, `gps/baud`): a `SerialPort` (`neoaprs/serialport.py`, so `socket://host:port` works for a receiver behind a TCP serial server) whose bytes are cut into lines for `NmeaFixes`. The RMC gives
  position, speed and course, the GGA altitude and satellites, in one fix a second; a GGA alone is a fix with no speed when no RMC came in the last 3 seconds. A sentence that says there is no fix (RMC status V, GGA
  quality 0) clears the stream's fix; a bad checksum is counted and changes nothing. 4096 bytes without a line end are thrown away.

`Fix.at` is the time the daemon received the fix, by its own clock, not the receiver's: a receiver that has just started may not know the date, and the age of a fix is judged by the clock of the program. The feed keeps the
latest fix even after the receiver says it has none; the service decides what to do with an old one.

`services/gps.py` (`Gps`, made with the feed in `neoaprs/app.py`, started by the controller before the beacon) keeps the fix and its age. `state` is `off`, `connecting` (the line is not up, no fix yet), `no_fix`, `fix` or
`stale` (older than `GPS_STALE_SEC`, 120 seconds, `neoaprs/policy.py`); `problem` is the feed's line, or that the fix is old. `current()` is the fix to beacon with, and only while it is fresh. A save of `gps/*` stops the
feed and starts it again with the new numbers in a task, and the old fix is forgotten.

While the station is mobile, the service emits `moved` when the fix is the first, or at least 5 seconds and 10 metres from where our row was last put (`GPS_PLACE_EVERY_SEC`, `GPS_PLACE_MOVED_M`). The composition root connects it
to `wiring.place_me`, which puts our own row in the station book at the fix with its course, speed, altitude and time (`StationBook.set_me`), and to the ALOHA circle, which is worked out again. The page's topic `stations`
is told whole at most every 30 seconds for it, because every other row's distance and bearing move with us. A GPS that is lost leaves our row at the latest fix, however old; the stored location of the settings (`station/lat`, `station/lon`, which the page hides while a GPS is chosen and keeps) is for a
station that is not mobile, and for a mobile one before its first fix. With the source `off` there is no GPS and the row stays at the settings' position.

**The mobile beacon.** `Beacon` (`neoaprs/services/beacon.py`) asks SmartBeaconing at every tick instead of waiting for `beacon/interval_min`, which a mobile station uses only as On (not 0) or Off (0): a beacon is asked for only while it is on. `neoaprs/smartbeacon.py` is the
decision, pure code: `decide(settings, last, now, speed_kmh, course_deg, request)` gives a `Decision(reason, next_due)` where `reason` is `request`, `start` (no beacon yet in this run), `time` (the last beacon plus the
rate of the speed now has passed: `slow_sec` up to `slow_kmh`, `fast_sec` from `fast_kmh`, `fast_sec * fast_kmh / speed` between) or `turn` (above `slow_kmh`, the course differs from the course at the last beacon by
more than `turn_min_deg + turn_slope / speed_in_mph`, and `turn_min_sec` have passed since it), or None. The algorithm is HamHUD's SmartBeaconing by Tony Arnerich KD7TA and Steve Bragg KA9MVA, in kilometres per hour;
the numbers are not settings but a preset (`PRESETS` in `neoaprs/smartbeacon.py`) that the setting `beacon/travel` chooses (`Config.smart`): `car` (the default, Dire Wolf's SmartBeaconing numbers), `bicycle`, `foot` and `boat` (NeoAPRS's own choice):

| `beacon/travel` | `fast_kmh` | `fast_sec` | `slow_kmh` | `slow_sec` | `turn_min_deg` | `turn_min_sec` | `turn_slope` |
|---|---|---|---|---|---|---|---|
| `car` | 100 | 60 | 8 | 1800 | 30 | 15 | 255 |
| `bicycle` | 30 | 60 | 4 | 1800 | 35 | 20 | 255 |
| `foot` | 7 | 120 | 1.5 | 1800 | 45 | 60 | 100 |
| `boat` | 40 | 60 | 3 | 1800 | 20 | 30 | 255 |

The table is read at each tick, so a changed preset is in force at once. `services/mobilebeacon.py` has `MobilePlan`, the memory of the last mobile beacon
(when, its course, why; the page reads it), and `mobile_info`, the information field.

The information field is `=` and the compressed position (`compressed_position` in `neoaprs/aprsposition.py`: the 13 bytes `/YYYYXXXX$csT`, the latitude and longitude as base-91 numbers rounded to the nearest of 380926 and
190463 steps a degree, the course in steps of 4 degrees and the speed as `1.08**s - 1` knots, `T` for a current RMC fix compressed by software; the blank form ` sT` when the speed or the course is missing), then the
altitude as `/A=aaaaaa` (feet) and the station comment. A compressed report may carry 40 characters of comment in all (`COMPRESSED_COMMENT_MAX`), so the comment is cut at the end to fit, not refused; there is no PHG.
The frame's other parts (the tocall, the path, the symbol) are those of the fixed beacon.

With no fresh fix there is no frame: `frame()` raises `NoFix`, a `BeaconError`, `send_now` is refused with `problem` "no beacon: ..." and the answers to `?APRSP` and `?APRS?` are not made (the log says why), nothing is
sent by the timer, `next_due` is None, and the log says once that the beacon waits for the GPS and once when it is back. The home position is never put in the fix's place. When the fix is back the beacon goes on
by the clock: a gap longer than the rate is a `time` beacon at once, not a `start`. A frame the Tnc refuses is tried again after `RETRY_SEC`, six refusals in all, and then 60 seconds later with the fix of then
(`MOBILE_GIVE_UP_SEC`); a radio that is away is waited for as with the fixed beacon. `send_now` (the page's Beacon now, reason `request`) builds the frame from the fix as it is and starts the times from it; `?APRSP` is
answered with the position as it is and does not.

**The page.** The topic `gps` (`GpsState` in `neoaprs/web/gpswire.py`, built by `gps_state` in `neoaprs/web/views.py`) is told whole, at most once a second, when the service's `changed` is emitted (a fix, a state or a
problem that changed), after every packet of ours and every save of the settings. `next_beacon_at` is the beacon's `next_due`, told only for a mobile station with a fresh fix. The settings are in the topic `config`.

`neoaprs gps-replay` plays a drive as a gpsd ([development.md](development.md#trying-mobile-operation-without-a-vehicle)).

## The iGate and the APRS-IS view

One connection to APRS-IS does both: with a passcode the iGate gates what the radio hears, and with or without one it reads the stations of the internet round us and shows them. The group of the Settings tab has the switch and the passcode only.

While `igate/enabled` is off the internet is hidden, not deleted: the topics `stations` and `packets` (`neoaprs/web/topics.py`) leave out a station known only from APRS-IS (`Station.internet_only`) and every packet that came by `is`, and show a station heard both ways by `Station.radio_view`: no internet count, time or hour, and the place and track the packets that were not from the internet gave (`Station.radio`, kept for a station once it is heard from the internet too, and made again from the packets at the start). The status, weather, telemetry and the like are whatever the latest packet of any channel said. A change of the setting tells both topics whole, so the pages follow without a restart.

`igate/enabled` (off by default), `igate/server` (`rotate.aprs2.net:14580`, not on the page) and `igate/password` (the APRS-IS passcode of `station/call`, digits, a secret; `-1` is refused because it only reads; empty is the read-only login, which the page does not mention) set it up. NeoAPRS never works a
passcode out: the page links to the request page of the author, `PASSCODE_URL` in `ui/src/lib/igatestatus.ts`, which is told the base call.

**The rules** are `neoaprs/igaterules.py` (pure code; the module's head says where each rule comes from: https://www.aprs-is.net/IGateDetails.aspx, https://www.aprs-is.net/q.aspx, WB2OSZ's "Successful APRS IGate Operation"). A UI frame
heard on the radio is gated unless its path has `TCPIP`, `TCPXX`, `NOGATE` or `RFONLY`, its information field starts with `?`, it carries a q construct or `,I` (never on the air), its source is no station (a placeholder, `WIDEn`,
`TRACEn`, ...) or is our own call, its field has a CR or LF inside, or the line would be more than 512 bytes. A third-party packet (`}`) is opened (at most three deep) and the packet inside is judged again from the first rule; with
`TCPIP` or `TCPXX` in the inner path it is not gated at all, else the RF header and the `}` are dropped. The line is `SOURCE>DEST,PATH,qAO,OURCALL:INFO`: the path as heard (`Frame.path_text`, the star after the last digipeater the frame has been
through, hops not yet used kept), `qAO` because the iGate is receive only (the specification: "Use qAO instead if the IGate is receive-only"), the information field as the bytes it is, a CR LF at its very end cut off. Not in the
specification, and ours: a copy of the same source, destination (without its SSID) and information field is not gated again within `DUPLICATE_SEC` (30 s; Dire Wolf stopped doing this at the request of a server author, so the number can be 0),
and our own call as the source is not gated, because our own position goes by a path of its own.

**The connection** is `neoaprs/aprsis.py` (`AprsIs`, a `Source`): connect (10 s), the server's comment line as greeting (anything else is "not an APRS-IS server"), `user CALL pass PASSCODE vers NeoAPRS VERSION filter r/LAT/LON/150` with TCP_NODELAY,
`# logresp CALL verified|unverified, server NAME`. The filter is the circle of `FILTER_KM` (150) round our position (`range_filter`, the position to a hundredth of a degree), the constant that the port 14580 needs to send anything; it is
sent again as a comment line `#filter r/...` on a connection that is up when it changes (`set_filter`; one set between the login line and the answer to it goes out when the answer comes). Without a passcode the login is `pass -1`, the
read-only login, and the server's `unverified` is no fault. A passcode that was given and refused sets `unverified` (the state `unverified` on the page, the problem "the server did not accept the password"): nothing is gated and the login is
not repeated with it, but the connection stays up and reads exactly as the read-only one does. A silence of 3 minutes from the server is a lost connection; a comment line goes to the server when nothing was written for 2 minutes; a write the
server does not take in 30 s is a lost connection too. Lines are written by a task from a queue of at most 500 lines (`slow_dropped` counts the oldest ones dropped when the server is slow). The reconnection is `Backoff`. The passcode is in the login
line and in no log line, line of the Source, error or problem.

**What the server sends** is read by the same connection: a comment line (`#`) is the keep-alive and ignored, every other line goes through `aprsisline.parse_is_line(line, now)` and the packet (`Packet.via` is `is`) to the connection's signal
`heard`, which `neoaprs/wiring.py` connects to `Services.hear_internet` and to nothing else (the one gate for packets from the internet, below). A line that does not parse is counted (`unreadable`) and forgotten, never raised, and a handler
that fails does not end the connection; `read` counts the packets handed on. The connection holds no reference to anything that can transmit, and the service's `on_packet` is not on this path at all, so a packet of the internet cannot be gated back.
Each packet of the internet is one line of the log at DEBUG (those of the radio are at INFO, `wiring._log_packet`), so that a busy circle does not fill the log; the hour line says how many were read and how many were no packet.

**The service** is `neoaprs/services/igate.py` (`Igate`): `on_packet` (connected to the Tnc's packets by `wiring.py`, in `ON_AIR_ONLY`) gates packets that were heard (`direction in`) and whose channel is in `packet.GATEABLE` (a packet of the Dummy radio or from the internet is counted as `not_air` and never sent), counts `gated`, `dropped` by reason (`tcpip nogate query source own
newline long frame duplicate offline not_air`) and `last_gated_at`, and `changed` tells the topic `igate`. Without a passcode, or with one the server refused, `on_packet` does nothing and counts nothing (it only listens). It has no Tnc, no `Radio`, no sender and no way to send a frame; the connection has none either, and nothing connects it to the radio
(`tests/test_igate_service.py` and `tests/test_igate_wiring.py` hold this). Our position goes as `OURCALL>APZNEO,TCPIP*:` and the information field of the beacon (`Beacon.position_info`, which asks no transmit interlock and works with the beacon off): at the
login and every 30 minutes for a fixed station that has a position, and for a moving station (`gps/source` is not `off`) with every beacon that goes on the radio (`Beacon.sent`), at most one a minute. The log: the login and its result at INFO, each packet
gated at DEBUG, and one line an hour at INFO, "igate: 812 packets gated in the last hour, 40 not gated: 31 TCPIP, 6 duplicate, 3 query".

**The filter follows the station.** The service gives the connection `range_filter(lat, lon)` of `stationbook.me_position` (the position of the settings, or the GPS fix of a moving station) when the connection is configured and at every tick; it is
sent again when the position is more than `FILTER_MOVE_KM` (10) from where the last one was set, and the first time a position is known if there was none at the login. The state of the topic `igate` is `off`, `connecting`, `connected` (verified),
`listening` (logged in without a passcode: the page says "Connected, listening only") or `unverified` (the passcode was refused: the page says so, and that NeoAPRS only listens). Our own position is sent to APRS-IS only on a verified login.
Tests: `tests/test_aprsis.py` (the login with its filter, the read-only login, the lines read, the lines that are none), `tests/test_igate_service.py` (the filter that moves, the states, nothing gated while listening) and `tests/test_igate_wiring.py`
(a whole daemon on a fake server: stations of the internet in the book and the log, nothing written to the radio, nothing sent back to the server).

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
- **Receiving.** A message is for us when its addressee is `station/call` with its SSID exactly. Blanks, CR and LF after an ack or a message number do not
  count (`ack12  `, `Hello{12}  `), and an addressee field shorter than nine characters is ended by its first colon (`:KH2Z:hi`). `neoaprs/services/inbox.py` takes what the Tnc hears;
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
- **Telemetry and queries** are recognised before anything is kept: a query, and the definition of a telemetry station's channels (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`), are in the packet log only. A
  query that carries a message id (the specification gives it none; some radios number it) is acked, so that the radio does not retry it; the answer is the queries' as ever.

**Alerts** (`neoaprs/services/alerts.py`). The shell line is run by `asyncio.create_subprocess_shell`. Its environment is made by `neoaprs/childenv.py`.
`TIMEOUT_SEC` is 20 s (60 on Windows), `MAX_RUNNING` is 5, and a failure is told at WARNING once an hour (`TOLD_EVERY`). On Windows the line is a PowerShell
script run from a thread as an encoded script, so nothing of it is quoted and the text is never in it; a step that fails ends it with status 1
(`$ErrorActionPreference='Stop'`), and a run out of time is killed with everything it started (`taskkill /T /F`). The unit sets
`DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus`. The command `alert_test` runs it as saved, whatever `messages/alert` says, and answers `alert_result{ok, text}`; an
empty command is an `error`. `Alerts.station` runs the same line, under the same switch and limits, for an alert set on a station that fired, with `NEOAPRS_KIND=station`, the title `APRS alert: <call>` and no message id
(a message has `NEOAPRS_KIND=message` and the title `APRS message from <call>`); the default line shows `NEOAPRS_TITLE`.

**The alerts of the stations** (`neoaprs/services/stationalerts.py`; the part `Alert` of `Pref`, the columns `alert_on_air`, `alert_within_km`, `alert_direct` of `station_pref`). The command `set_station_alert{call, on_air, within_km, direct}`
(`within_km` 1 to 1000 or null) sets the whole alert, all off takes it away; our own call and our own objects are refused (`alert.own`). `StationAlerts` is connected to `StationBook.changed`, `PrefBook.changed` and the saves of the settings
(wiring.py), and keeps for each alerted station when it was last heard, last heard direct, and whether it was near; the start (and a new or changed alert, and a switch of `igate/enabled`) takes them from the book
as it is, so nothing fires for what was already true. It fires `on_air` for a packet after `QUIET` (30 min) of silence or the first one, `direct` for a packet heard direct after 30 min without, and `within` when the
distance from our position comes to N km or less from more than N plus a tenth (at least 0.5 km), from a packet of the station or a move of ours. While `igate/enabled` is off the station's radio side is watched.
`fired` goes to `Alerts.station` and, by the page's topics, to every open page as `station_alert{call, kind, text, at, km}`, once; a line at INFO says it.

**The message board** (`neoaprs/services/bulletins.py`; the inbox hands over what it takes). The wire is the topic `bulletins`, `{sender/slot: BulletinRow}`. A
`set` is for a bulletin that is new or heard again and a `del` for one that is deleted. A row has `sender`, `slot`, `group`, `kind` (`announcement`, `bulletin`, `group` for a group bulletin and the messages to `ALL`, `CQ` and `QST`, or `nws` for the weather service), `text`, `first_heard`, `last_heard` and `times_heard`. The table `bulletin`
(migration 7) has one row for a sender and slot, strict, with named CHECKs. `bulletin_delete{sender, slot}` removes the row; an entry that is not there is an
`error`.

**Queries** (`neoaprs/services/queries.py`; how an answer is sent is `neoaprs/services/answers.py`, which the QRU server uses as well). `GENERAL_DELAY_MAX_SEC` (120), `GENERAL_EVERY_SEC` (600), `ANSWER_AGAIN_SEC` (30), `DIRECT_WINDOW` (one hour),
`MAX_DIRECT_MESSAGES` (2), `ANSWER_FRAMES_MAX` (5), `HEARD_HOURS` (8). `?APRSH CALL` reads the times the station was heard in the last 8 hours from the packet log on the database thread
(`PacketLog.heard_since`, a packet of direction `in` whose source is the call) and answers with a message `CALL HEARD: 1 3 2 . . 4 5 6`, the last 60 minutes first, `CALL NOT HEARD` for a station that is neither in the log of those
hours nor in the station book; the object with the station's position that APRS 1.0.1 adds is left out. `?WX?` and `?IGATE?` are `Other` of kind `query` like `?APRS?`; `?WX?` is logged at DEBUG and never answered. `?IGATE?` is taken as `?APRS?` is (the random wait, footprint and all, with a `GENERAL_EVERY_SEC` of its own),
but only while the iGate (`Queries(igate=...)`, the `Igate` of the composition root) is `connected`, and asked again before the answer goes: one capabilities packet `<IGATE,MSG_CNT=0,LOC_CNT=n,UPL_CNT=n`
(`capabilities_info`), MSG_CNT always 0 (receive only), LOC_CNT the stations heard direct within `DIRECT_WINDOW` (those of `?APRSD`), UPL_CNT `Igate.gated`. For `?APRSD` the stations are those of the station book (not us, not objects), and "heard direct" is a packet with no repeated
digipeater that was not a third-party packet. `?APRSO` sends each live object and item of ours once as it is now, `?APRSM` each message of ours to the asker that no
ack has settled (`sending`, `failed`, `unconfirmed`) once more with its number, at most `ANSWER_FRAMES_MAX` of either; the first frame goes at once and the rest
`SPACING_SEC` (10 s) apart. The messages' records do not change.

**The path of an attempt.** `Messaging` asks `PrefBook.path_for(call, attempt)` each time it sends an attempt of a message that has an id (the attempt is
`record.attempts + 1`); acks and answers ask with no attempt. The path is, in order: the station's own path (`station_pref`), else for attempts up to
`HEARD_PATH_ATTEMPTS` (2) of a message to a station other than `EMAIL-2` the heard path, else `beacon/path`; `RFONLY` is added to whichever it is. The heard path
is the pure function `route.heard_path(deliveries, now)` (`route.automatic_path` adds the attempt rule) over the station book's `Deliveries`, which keeps for
direct and for each route the times of its latest `TIMES_KEPT` (2) packets (seeded from the database with the two latest of each group,
`PacketLog.deliveries`): direct if `HEARD_PATH_MIN_PACKETS` (2) of them are within `HEARD_PATH_WINDOW_MIN` (60) minutes, else the route heard last with that many
within the window, no anonymous hop, no gate (those are counted apart), no marker, at most `HEARD_PATH_MAX_DIGIPEATERS` (3) digipeaters, reversed. The constants
are in `neoaprs/policy.py`. The delivery chain records the digipeaters of each attempt as it was sent. The station row tells the choice as `heard_path` (null: none, empty: direct), worked out
when the row is made.

**The path settings.** An empty path never means no digipeaters. `beacon/path` empty is the recommended path of the station's symbol (`route.recommended_path`: `WIDE1-1,WIDE2-1` when `symbols.is_mobile` of the symbol, else `WIDE2-1`;
`Config.beacon_path_calls` is the one place that works it out for the beacon, the status, objects, bulletins, queries, acks and the fallback of a message); the word `DIRECT` (`route.DIRECT_ONLY`,
`message.path_choice`) is no digipeaters, and stands alone (`normal_path` refuses it among calls with `path.direct_alone`). Migration 14 changed a stored empty
`beacon/path` to `DIRECT`; migration 15 changed the stored `WIDE1-1,WIDE2-1` (the old default, which every save wrote, so it cannot be told from a choice) to empty. A station's own path: the stored `path` null is none (automatic), `''` is direct; `set_station_path` takes calls or `DIRECT`, and an empty
`path` is `clear_station_path`. An own object's or item's path: null (or empty) is `beacon/path`, `DIRECT` is none.

**The station preferences** (`neoaprs/services/prefbook.py`; the table `station_pref`). The path, the RF-only flag and the alert of each
station, under the call as written, in the row `{path, rf_only, alert}` of the topic `station_prefs` (the path null where none is set, a `path` of `""` is
direct, the alert null where none is set; an entry with no path, `rf_only` false and no alert is not kept). The commands are `set_station_path` (calls, or `DIRECT`; an empty `path` clears), `clear_station_path`
and `set_station_rf_only{call, on}`. `PrefBook.path_for` adds `RFONLY` so every frame to the station takes the same road. Messaging is given
`path_for`. `set_station_rf_only` for `EMAIL-2` is an `error`. A station has no timeout of its own: every station leaves the map as many hours after its last position as the setting `map/station_hours` says (1, 3, 6, 12 or 24, 3 by default; the page does that, the daily prune keeps
packets and stations 7 days). Migration 17 cleared the timeouts that earlier versions stored (the column `station_pref.hide_after_min` is always null and not read).

**The station book** (`neoaprs/stationbook.py`) counts, for each station, how many packets came direct and by each route, from the packets since the start and
the latest 2000 that the database kept. The row of the topic `stations` has `last_route`, `heard_direct`, `heard_via` (`[station heard, packets]`, the most
first, `?` for an anonymous last hop), `heard_rf_gated`, `best_route`, `suggested_path`, `last_direct_at` (null for a station never heard direct, for us and for objects; it is the time of the station's latest packet with no repeated address in its path, not a third-party one), `can_message` and `telemetry`. `can_message` is false for an object or an item and for a station whose latest position uses the identifier `!` or `/` or is a Mic-E one whose comment starts with the type code `'` (a tracker without messaging, aprs-deviceid), unless it has sent a message or an ack that we heard (overheard ones too). It is found again at the start from the packet log, and a bulletin or a telemetry definition does not count. The route is worked out when the packet is heard (`neoaprs/route.py`) and is `route` on every packet of the topic `packets` (empty for
the ones we sent) and on every message that came in or was overheard (the column `route` of the table `message`; of two copies by different routes the first is
the one kept).

The routes the map draws are not the counted ones. A station keeps the route of its latest packet of any channel and the one before it that came another way (`route_marks` of the row, at most two, the newest first; `neoaprs/reach.py`), each with where the station was when the packet was heard (the position it reported, else the one it had), and the way of its latest packet from the internet (`internet_reach`): the q-construct of the APRS-IS path says whether an iGate heard it on the radio (`qAR`, `qAO`, and the indirect `qAr`, `qAo`; the starred addresses before it are the digipeaters) or a client sent it into the network (`qAC`, `qAS`, `qAX`, `qAU`, or `TCPIP*` without a q-construct), which never was on the air. A path that says neither is not read. Both are read again from the latest packets at the start; the counted routes (`heard_via`, `best_route`, `suggested_path`) are unchanged and still serve the automatic path of a message.

**Third-party packets** (`neoaprs/aprsthirdparty.py`). One level only: a wrapper inside a wrapper, or one whose header is not a header, stays "third-party" and
is not read. The packet keeps the gate as its `source` and the path it was heard by; `raw` and `info` are untouched, `decoded` is what the packet inside says,
read as from its inner source to its inner destination (which Mic-E needs), and `third_party` holds the inner header. The inner source and destination are calls or names APRS-IS allows (1 to 9 letters, digits
and hyphens: `OH2XYZ-L`, `OH2XYZ-20`, `WINLINK`; `callsign.normal_name`, upper case); messaging, the station book and the station's settings take such a name as the station, and a message to it is sent like one to a call. The summary ends "via OH7JHF-1
(third-party)". The packets of the station inside count as `heard_rf_gated` and never for `suggested_path`; the gate itself, when the book has it as a station, counts each such packet it put on the air as `gated` (a gate that is only ever heard wrapping other stations' packets is no row and is not counted), and a capabilities packet of its own that holds the token `IGATE` sets `igate`. The page's Nearby tab lists a station with either as an iGate.

## How a packet reached us: `via`

Every `Packet` (`neoaprs/packet.py`) says how it reached us in `via`, set once where the packet is made and frozen with it (the column `packet.via`, `via` of the rows of the topic `packets`):

| `via` | what it is | made by |
|---|---|---|
| `rf` | heard on the radio, direct or by digipeaters; every packet of ours that went out | `tncmode.packet_of` |
| `rf-gated` | heard on the radio as a third-party packet (`}`) that an iGate took from the internet and put on the air: the sender inside is the station, the iGate is `Packet.gate` | `tncmode.packet_of`, when the frame holds a third-party header |
| `is` | received from APRS-IS over the internet; it was never on the air | `aprsisline.parse_is_line` |
| `dummy` | made up by the Dummy radio (`Tnc.is_dummy`), which lets a person try the program with no radio; it works everywhere a packet of the radio does | `tncmode.packet_of` with `dummy=True` |

A packet is `rf-gated` exactly when it came on the radio as a third-party packet (the constructor refuses the other combinations); the codec reads the header again from the frame, so a row whose column differs is made right on the way out. A packet from the internet has no AX.25 frame: its `raw` is the line as the server sent it, its `path` everything between the destination and the colon (digipeaters, the q-construct `qAC`/`qAS`/`qAR`/`qAO`..., the server or iGate after it), its `info` what follows the first colon.

**The APRS-IS line parser** (`neoaprs/aprsisline.py`, foundation, pure code) is the one way such a packet is made: `parse_is_line(line, now)` takes a line of TNC2 text (bytes as the socket gave them, or text) like `OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi`, reads the header (a call or a name APRS-IS allows for the source and the destination, at most 32 path elements), reads the information field with the ordinary dispatcher (a third-party packet inside is opened as on the air, and stays `is`) and returns `Packet(via="is")`. It raises `IsLineError` for a line that is none; `error.comment` is true for the server's own `#` lines, which are no fault (`is_comment(line)` tells beforehand). `q_construct(path)` gives the code and the call after it, `heard_by_radio(path)` whether the q-construct says an iGate heard it on the radio (`qAR`, `qAO`).

**The one gate for packets from the internet.** The program has two signals of packets: the Tnc's (`tnc.packet`, the radio, and ours that go out) and `Services.internet_packet`, entered only through `Services.hear_internet(packet)`, which refuses anything but a packet with `via` `is` heard (not sent). `neoaprs/wiring.py` connects:

- `SEEN_BY_ALL` (the packet log, the station book, the weather log) to both signals, and the page's topics (`packets`) follow both;
- `ON_AIR_ONLY` (messaging with the inbox, the QRU server, the board and the delivery chain behind it, the queries, asking QRU, our objects, the digipeater) to the Tnc's only, each behind `AirOnly`, which drops an `is` packet handed to it by mistake, counts it and says so once in the log;
- and every entry of those services refuses one again (`Packet.on_air`), so that no message from the internet is kept, acknowledged or answered, nothing from it is repeated, taken as a take-over of our objects, or sent. Nothing connects the alert, the status or the beacon to a packet at all. The iGate is among `ON_AIR_ONLY` (it takes the radio's packets to put them on APRS-IS) and checks `packet.via in GATEABLE` itself as well; a packet that fails it is counted as `not_air`.

`tests/test_internet_gate.py` builds the daemon and walks the handlers of both signals and every part that has a method taking a `Packet` (two levels down), so that a part added later fails there until it is classified; it holds the connection to APRS-IS, whose `heard` signal reaches `hear_internet` alone, and hands a whole daemon the packets that would each make it transmit, by `hear_internet` and through a fake server; `tests/test_internet_services.py` hands each acting service the same packet with only the channel changed.

**What each channel does to the station book.** A station keeps, for each channel, the count of its packets and the time of the latest (`heard_rf`, `heard_rf_gated`, `heard_is`, `heard_dummy`, `last_rf_at`, `last_rf_gated_at`, `last_is_at`, `last_dummy_at`; `packets` is the sum) and the channel of its position (`position_via`, the latest packet that carried a position wins). Everything that means "on the air near us" counts the radio only: the routes (`heard_direct`, `heard_via`, `last_route`, `last_path`, `best_route`, `suggested_path`, `last_direct_at`), the station's `gated` count and `igate`, the ALOHA circle (`last_on_air_at`: the radio's packets and the Dummy radio's, not an iGate's, not the internet's), `?APRSD` and `?APRSH` (the SQL leaves `is` packets out), the routes read from the log at the start, and `can_message`: a station known only from the internet (`internet_only`: `heard_is` and none of the others) cannot be messaged, as nothing is sent but by radio. A station heard both ways has both. The packets of the last hour, the time last heard and the sort order count every channel. An object or item reported over the internet is known from the internet alone, if no packet of the radio reported it. Our own call over the internet is not proof that the radio was heard, and changes nothing.

**What may go to the internet.** `packet.GATEABLE` (`frozenset({"rf", "rf-gated"})`, in `neoaprs/packet.py` beside `Packet.via`) is the set of channels an internet-facing consumer may take. The iGate, or anything else that sends to APRS-IS, must check `packet.via in GATEABLE` first: a packet from the internet (`is`) would go in a circle, and what the Dummy radio makes up (`dummy`) must never reach the real network. A new channel is not gateable until it is put there on purpose (`tests/test_packet.py`, `tests/test_internet_gate.py`).

**The tables.** Migration 21 adds `packet.via` (CHECK, default `rf`; a stored AX.25 frame whose information field begins `}SRC>DST:` with names that are calls or names APRS-IS allows is told to be `rf-gated` from the stored `raw` alone, every other row stays `rf`) and, to the station cache, `heard_rf`, `heard_rf_gated`, `heard_is`, `heard_dummy`, `last_rf_at`, `last_rf_gated_at`, `last_is_at`, `last_dummy_at` and `position_via`. A cached station is taken to have been heard on the radio: its `packets` become `heard_rf` and its `last_heard` becomes `last_rf_at`, except for the packets of it stored as `rf-gated`, which move to `heard_rf_gated` (at most as many as it has) with the time of the latest of them; the position of a station whose packets were all gated is `rf-gated`, any other `rf`. That is as near as the cache knows: it is an approximation for stations from before this version, and the counts are exact from then on.

## Objects and bulletins of our own

The commands are `object_set`, `object_kill`, `bulletin_post` and `bulletin_unpost`; the topics are `own_objects` and `own_bulletins`. Both services are
`neoaprs/services/repeater.py`'s ticker and send through `neoaprs/services/sender.py`, which holds back everything while the call is not set or the radio is not
usable, and puts a pause between two frames of ours.

- **Schedule** (`neoaprs/decay.py`). `FIRST_WAIT_SEC` 60, `MIN_GAP_SEC` 60, `KILL_SENDS` 3, `KILL_WAIT_SEC` 60; the net cycle time is 10 minutes for 0 or 1
  digipeaters, 20 for 2 and 30 from 3 on. `BULLETIN` is early waits of 120 and 240 s, then every 20 minutes, for 4 hours; `ANNOUNCEMENT` the same, then every
  hour, for 72 hours.
- **The interlock** is `config.can_transmit`, with the Tnc's own check. The log says `no object sent: set your call first` once.
- **Limits** are in `neoaprs/ownobject.py` (`OBJECT_NAME`, `ITEM_NAME`, `NAME_FORBIDDEN`, `COMMENT_MAX`, `COMMENT_MAX_MOTION`, `COURSE_MAX`, `SPEED_MAX_KMH`, `QRU_GROUP_MAX`, `QRU_RESERVED`)
  and `neoaprs/ownbulletin.py` (`GROUP_MAX`, `MAX_POSTED`); the page takes them from the daemon (`LIMITS` of `ui/src/protocol/lists.ts`).
- **Tables.** `own_object` (migration 13): name, kind, position, symbol, comment, course, speed, path, whether it is alive or being killed, when it was made and
  last changed, how often it was sent since then, when last; strict, with named CHECKs. `own_bulletin`: slot, group, text, when posted, how often sent, when
  first and last. Both are written after every change and every packet.
- **On the wire** the topic `own_objects` has the values and the schedule of each (`state` `live` or `killing`, `sent`, `last_sent_at`, `next_at`) and the topic
  `stations` a row with `own` true for each live one. A row also has `qru_group` and `on_request` (below).
- **The QRU server** (`neoaprs/services/qru.py`). `own_object` has `qru_group` (migration 18: `''` or 1 to 8 upper-case letters and digits, not `INFO` or `NEXT`) and `on_request` (0 or 1). An object with
  `on_request` is never due on the schedule (`next_at` is null), is not sent when made or changed, and a kill of it removes it at once. The inbox hands a message to the addressee `QRU` that is not an ack or a rej
  to `Qru.heard` (given by the composition root to messaging); `heard` returns False, and the message is kept as overheard, unless some live object has a group and the text reads as a request (`INFO [km]`, `?`, `NEXT`
  or a group name with an optional distance in km, with a `?` before the word allowed: `?INFO`, `?POST 20000`); when it takes the message it answers by the asker's path with RFONLY added (`Answers.deliver(rf_only=True, first_after_sec=FIRST_WAIT_SEC)`: the first frame, objects or list, goes `FIRST_WAIT_SEC` (5) after the request so that the digipeaters have finished repeating it and the answer does not collide with them at the asker, the others `SPACING_SEC` apart after it) and never acks the id (a request is a broadcast: an ack from our call matches nothing at the asker). Only a request with `Packet.via` `rf` or `dummy` is taken: one from the internet never reaches it (`AirOnly`), and one an iGate took from it (`rf-gated`) is refused. `RANGE_KM` (50), `MAX_INFO_MESSAGES` (2), `NEXT_KEEP` (1 hour), and `ANSWER_FRAMES_MAX` and
  `ANSWER_AGAIN_SEC` of the queries. The asker's position is the station book's.
- **Asking QRU** (`neoaprs/services/qruask.py`, the words in `neoaprs/qrutext.py`). The command `qru_ask` (`text`: `INFO`, `NEXT` or a group, and a distance in km, 1 to `ASK_KM_MAX`) sends one message to `QRU` as `QruAsk.ask`
  does: no message id, not kept in `messages`, never sent again, by the path of messages (`PrefBook.path_for("QRU")`) with RFONLY added (more than 8 digipeaters with it is refused), and refused as any message is: `transmit.off` in RX only, the interlock's
  reason without a call, the radio's reason when it is away. The same request goes on the air once per `ASK_EVERY_SEC` (60) and any two `ASK_GAP_SEC` (10) apart: another within that time is `qru.too_soon` with `seconds`. The page greys Ask for the same minute and shows the refusals in the row of the Local info section. `QruAsk.on_packet`, connected as `ON_AIR_ONLY`, notes the messages to us that read as a server's list of groups
  (`de CALL:GROUP(n) ... Max O@Dkm|mi`, a first message ending in `+` goes on in the next within `CONTINUE_SEC`) or its closing line (`Sent N GROUP Objects ...`). Such a message to us, with no id and within `ANSWER_WINDOW_SEC` (300) of a request of ours, is an answer (`QruAsk.answers`, given to messaging as `qru_answer`): the inbox does not keep it as a message (the packet log has it). Any other message of the same station is kept as usual.
  `QruAsk` also notes the objects heard (`ObjectReport` or `ItemReport`, alive) from any call since the first request; a server's `received` are the names heard from its call between the request its closing line answers (`request`, which Ask again sends; for a `NEXT` it is the group with the distance of the group's own request) and `ARRIVAL_GRACE_SEC` (30) after the line (`settles_at`): fewer than `sent_objects` is a lost object. The topic `qru` (`QruState`) has the last request
  and the servers (call, groups with counts, limit, range and unit, when, the last closing line, `sent_objects`, `request`, `received`, `settles_at`), told whole, and a note is forgotten `KEEP_FOR` (1 hour) after it was heard (a timer of the service). The objects the servers send are objects like any.
  The Dummy radio's club station Q1CLB (`neoaprs/dummyqru.py`) is a server for `RP70` and `FOOD`.
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
described in `neoaprs/migrations.py` (the runner) and its steps, `neoaprs/migrationsteps1to11.py`, `neoaprs/migrationsteps12to21.py` and `neoaprs/migrationsteps22on.py`; how the database is written is in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md#the-database-actor).

**The settings reset** (migration 16, `neoaprs/migrationsteps12to21.py`). The settings that are not on the page any more cannot be changed back by their operator, so once, at the first start of this version, their stored rows are
deleted and the defaults count: `map/maxzoom`, `map/source`, `update/url`, `serial/pattern` and `serial/skip` (they stay settings, for `neoaprs db set`), with one INFO line in the log for each whose value was not
the default (`map/maxzoom reset to the default: 14 → 12`). The rows of the keys that are no settings (`messages/attempts`, `log/keep_days`, `update/check`, `tnc/check_sec`, `tnc/watchdog_min`,
`map/hide_after_min`, `beacon/destination`, `beacon/compressed`, `beacon/dao`) are deleted without a line. `web/port`, `web/allowed_hosts`, every setting on the page, the old rows `tnc/enter_kiss` and `web/bind` and the
daemon's own state rows are not touched. Like every migration, it runs after a copy of the file is made in `backup/`, and a value set after it is kept.

**The station timeouts** (migration 17, `neoaprs/migrationsteps12to21.py`). The field "Hide from map after" of the station card is gone and every station follows the one choice of the Stations tab (`map/station_hours`, 3 hours by default), so once, at the first start of this version, the own
timeouts stored in `station_pref.hide_after_min` are cleared, with one INFO line in the log for each station (`OH2RDG: the own timeout of 45 minutes removed, the time on the map of the Stations tab counts`); a row that held nothing else is deleted, and
the path and RF only of a station are not touched. The commands `set_station_timeout` and `clear_station_timeout` and the field `hide_after_min` of `station_prefs` are gone from the protocol.

**The alerts of the stations** (migration 22, `neoaprs/migrationsteps22on.py`). `station_pref` is rebuilt with the columns of the alerts (`alert_on_air` and `alert_direct` 0 or 1, `alert_within_km` 1 to 1000 or null), every row kept with no
alert, and a row may now say only an alert. The setting `messages/alert_command` is deleted where it is exactly the old default of Linux or of Windows (which titled every notification "APRS message from"), so that the
new default, which shows `NEOAPRS_TITLE`, counts, with one INFO line in the log; a command of the operator's own is not touched.

## What the parser reads

`neoaprs/aprs*.py`, tested against captured frames (`tests/fixtures/aprs/`).

- **Weather fields** (`neoaprs/aprsweather.py`) after the position or the time: `c` or the leading `DIR/SPD` the wind direction (degrees; some stations send two
  digits) and speed (mph), `g` the gust (mph), `t` the temperature (degrees F, `t-05` below zero), `r` rain in the last hour, `p` in the last 24 hours, `P`
  since midnight (hundredths of an inch), `h` humidity (`00` is 100 %), `b` pressure (tenths of a hPa), `L` and `l` luminosity (W/m2, `l` is 1000 and over), `s`
  snow in the last 24 hours (inches, the `s` that follows the wind speed, a decimal point allowed: `s1.5`) and `#` the raw rain counter. A field that is all dots or all spaces is missing. The
  fields end at the first character that is not a field with its digits, and what follows (a software id such as `wRSW`, a comment glued to the data like
  `b10285Inkoo`) is the comment. A compressed weather position's `cs` bytes are the wind (direction `c`*4 degrees, speed 1.08^`s`-1 mph), and its fields after
  the 13 bytes are the rest.
- **Summary.**
  `position 60.4072 23.8788 /_ weather: wind 107° 2 km/h gusts 2, 10.0 °C, 85 %, 1028.4 hPa, rain 0.3 mm/h, 24 h 4.1 mm, today 3.3 mm - RX Igate & WX station`,
  only the fields that are there. Wind and gusts are km/h to 0.1, rain mm to 0.1, a direction over 360 is none.
- **Data extensions** after the symbol of an uncompressed position are taken off the comment into `Position.extensions`: `PHGphgd` (power in W, height in m,
  gain in dB, directivity and the range the specification's formula gives), `RNGrrrr` in km, `DFSshgd`, the `/BRG/NRQ` of a DF report after the course and
  speed, and the `Tyy/Cxx` of an area object with the symbol `\l`. A compressed position has none but the radio range of its cs bytes `{s` (2 x 1.08^s miles,
  as `range_km`).
- **Local information** (the frequency specification, `neoaprs/aprsfreq.py`): the free text of a position, an object, an item, a Mic-E packet or a status begins with `FFF.FFFMHz` (or
  `FFF.FF MHz`, any case, one `/` or blank in front of it; `A96.000MHz` and `1.296GHz` for the microwave bands), optionally followed by fields of four bytes in any order, each once: a tone
  `Tnnn` (CTCSS to transmit), `Cnnn` (both ways), `Dnnn` (DCS), `Toff` or `1750`, where a lower-case first letter (`t`, `c`, `d`, `l750`) is narrow modulation; an offset `+nnn` / `-nnn` in
  10 kHz (`-000` is simplex); `Rnnm` / `Rnnk`; `FFF.FFFrx`. The fields end at the first word that is none. It is `Position.frequency` / `Status.frequency` (a `Frequency`, the range in km, the
  tone in whole hertz as sent: `T107` is 107.2) and leaves the comment. A frequency anywhere else (`QRV 145.500MHz`) or with three decimals and a blank (`145.500 MHz`) is text. An object or
  item named `FFF.FFxyz`, `FFF.FFF-z` or `FFF.FFFyz` (a name with at least one character after the frequency) is the frequency itself, and its comment begins with the fields; a frequency in
  such an object's comment too is then its receive frequency. The station keeps the frequency it gave last (`Station.frequency`): a position without one leaves it, a status text with one
  replaces it, and an object or item has what its latest report says.
- **Storm data** (APRS101, chapter 12) at the start of the comment of a position or object with the symbol `\@` or `/@` (after the course and speed of the storm, which are the position's):
  `/TS`, `/HC` or `/TD`, then `/www` and `^GGG` (knots), `/pppp` (hPa), `>RRR`, `&rrr` and `%ggg` (nautical miles), each optional but in this order, as `Position.storm` (km/h, hPa, km).
- **A signpost** (`\m`, an object or an item) has `{xxx}`, one to three characters, at the start of its comment: `Position.sign`. The `{nn}` of an area object (`\l`) is not read.
- **`!DAO!`** (APRS 1.2, chapter 5) anywhere in the comment of a position, an object, an item or a Mic-E packet is taken out of the comment and makes the
  latitude and longitude finer: `!W12!` (datum letter in capitals) adds a digit of thousandths of a minute to each, `!w5L!` (lower case) a base-91 value of
  0 to 0.0099 minutes, a blank nothing; the last one counts. A compressed position (finer already) and an ambiguous one are not moved.
- A `!` position may come after up to 39 characters of text (a digipeater of the X1J kind): the text is the start of the comment. The specification has deprecated
  this since 2012; it is still read, for old digipeaters.
- A timestamp with `/` is the sender's local time: kept as sent with `Position.timestamp_local` set. The MMDDhhmm of a positionless weather report is its time (`Other.timestamp`). A timestamp is the
  latest instant that is not more than an hour ahead of our clock (`FUTURE_TOLERANCE`); one that is no time at all (the 32nd, the 60th minute) leaves the position without a time instead of losing it.
- **Raw NMEA** (`$GPGGA`, `$GPGLL`, `$GPRMC`, `$GPWPL`, any talker; the checksum is checked when there is one) is a position with course, speed, altitude and
  time. Its symbol is the one of the destination (`GPSxyz`, `GPSCnn`, `GPSEnn`, `SPCxyz`), else the icon of the source's SSID, else the unknown position.
  `$GPVTG` and a fix that is not valid stay "nmea", and `$ULTW` (an Ultimeter 2000) is "weather" without fields, because its format is not in the specification.
- **Telemetry** `T#sss,aaa,aaa,aaa,aaa,aaa,bbbbbbbb` is its own decoded type (`Telemetry`, packet kind `other`), with the forms of APRS 1.2: `T#MIC` with or
  without a comma, values of any width, signed and with a decimal point (`-7.3`), 1 to 5 values, and 1 to 8 bits after the fifth. The base-91 telemetry
  `|ss11...|` in the comment of a position or a Mic-E packet (the sequence and 1 to 5 channels of two bytes each, then the bits) is taken out of the comment into
  `Position.telemetry` and counts as the station's latest report. The daemon keeps each station's latest report
  and the `PARM.`, `UNIT.`, `EQNS.` and `BITS.` messages addressed to it (in memory, the latest 500 stations, read again from the latest 2000 packets at a
  start) and sends the station row `telemetry` with the names, units and values `a*v^2 + b*v + c` applied (raw values when it sent no definition).
- `,` is test data ("test"), `<` station capabilities (`items`: `IGATE`, `MSG_CNT=2`...), `%` an Agrelo DF report (`bearing`, `quality`), `+` shelter data and
  `.` space weather (kept as text), `[` a Maidenhead locator beacon (a position at the centre of the square; the specification lists `[` as unused).
- A **Maidenhead locator** at the start of a status report (`>IO91sx/-` and text after a space) is `Status.locator`, and in the status text of a Mic-E packet
  `Position.locator`. The station row has it as `locator`, and it does not move the station.
- **Mic-E.** The telemetry flag
  "`" is followed by two values of two hex digits, "'" by five, and 0x1d by five bytes (all dropped from the comment). The radio's type code is dropped
  as aprs-deviceid's tables have it: a leading `>` with an optional trailing `=`, `^` or `&` (Kenwood TH-D72, TH-D74, TH-D75), `]` with an optional `=`
  (TM-D700, TM-D710), and a leading `` ` `` or `'` with one of the table's two-byte suffixes (`_%` FTM-400DR, `|3` TinyTrak3, `[1` APRSdroid ...); a suffix
  not in the table stays in the text. The leading `'` says the radio does no messages (`can_message`). The altitude `xxx}` is read at the start of the status text (after the locator) or as a word of its own after a space.
- **The device a station runs** (`neoaprs/device.py`, the station row's `device`): the name the APRS device identification list (`neoaprs/devicedata.py`, a snapshot of Hessu's `tocalls.yaml`, CC BY-SA 2.0, made by `scripts/gen-devices.py` and never fetched by the daemon) gives for the destination call of the station's latest packet (an exact tocall before a wildcarded one, the more characters written out the better; `?` is any character, `n` a digit), or for a Mic-E packet the type code at the ends of its comment. The station row also has `packets_hour`, the packets of the last hour (counted for each minute, read from the packet log at the start).
- **The ALOHA circle** (`neoaprs/aloha.py`, `neoaprs/services/aloha.py`, the field `aloha_km` of the topic `map`): once a minute the stations heard on RF in the last hour (not objects, not ours, not the ones an iGate put on the air) are walked from the nearest to the farthest, each adding what it sends in 30 minutes by its kind (a moving mobile 15, any other mobile 7, a weather station 6, a digipeater 3, any other 2, times a factor that starts at 1 and rises by one after each digipeater) until the sum reaches 1800, the packets a 1200 baud channel carries in 30 minutes; the distance of that station is the radius. None without a position or when the sum is not reached. The numbers are in `neoaprs/policy.py`.

## The update check

`neoaprs/services/updatecheck.py` asks `update/url` through `neoaprs/updatefetch.py`, `FIRST_SEC` (60) after the start and every `EVERY_SEC` (24 hours);
`neoaprs/versions.py` compares the versions and reads the answer. It keeps the answer only if it is newer than ours, and the `status` message carries it.
`check_now` is the same question on request (`update_check`, answered by `update_result`). `NEOAPRS_UPDATE_CHECK=0` switches it off for the run.
`release_notes` (the command of the same name) is the changelog read at a tag (`neoaprs/releasenotes.py`): at the newer version's, the sections from ours up to it; at our own, our section, or with `since` every section after that version up to ours (what the page shows once after an update, from the version its browser last saw). Each tag's changelog is fetched once and kept; no other version is fetched. The question carries
the number of the installation as `id`: 16 random bytes as 32 lowercase hex characters, made the first time a question is asked and kept in the row `update/install_id` (state of the daemon, not a setting),
so that the project can count installations; nothing derived from the machine goes into it. The kind of
system sent is worked out by the process in `neoaprs/cli/installkind.py` and given to the controller; the `hello` message carries it so the page can say how to
update. The page has no version of NeoAPRS built in: it learns the daemon's from `hello` (the Update check row, the update check) and compares only the protocol and its build (the field `page` of `hello`, the name of the page's
main script). When either differs it loads itself again once; when that does not help it shows a notice in its language ("This page and NeoAPRS do not match ...", with a Reload button), keeps the socket closed and does not run
(`ui/src/lib/reload.ts`). A new version of NeoAPRS that changed nothing in `ui/` therefore changes nothing in the page.

**The page is the one the daemon started with** (`neoaprs/web/pagesnapshot.py`, `neoaprs/web/pagefiles.py`). At its start the daemon reads every file of `neoaprs/page/` (not a hidden one or a source map) into memory, 26 files and 3.4 MB
(`tests/test_page_snapshot.py` holds it under 16 MB; beyond that the page would be copied to a folder named by the build under the data folder and served from there), and answers every request from that, with the ETag (a hash of the content) and `Last-Modified` of
the file, `HEAD`, byte ranges and `Cache-Control` as before: `index.html` and the files copied from `ui/public` with `no-cache`, the hashed files of `assets/` for good. A page rebuilt on disk, a branch switched or a
package upgraded while the daemon runs changes nothing until the daemon is started again, so the page a browser gets and the daemon it talks to are always a pair, and `hello`'s `page` is the build of that pair. A folder swapped
by a build in the middle of the read (the build renames two folders) is read again, up to three times. What a browser may still hold of an older pair is its service worker's copy of the page, which a reload replaces: the worker asks the daemon for the shell first.

**Update now** (`neoaprs/services/selfupdate.py`) is the update the daemon does itself on the page's `update_now`, for the Windows installer and an AppImage:
the release's file and `SHA256SUMS` of the announced version from GitHub, the SHA-256 checked, then the installer of the kind (`neoaprs/services/selfinstall.py`)
and the restart; the topic `update` tells its steps. The flow and its safety checks are in [development.md](development.md#update-now).

## The log and the support bundle

What a person who has a problem sends is one file, the support bundle, and the log is most of it. The log is `neoaprs.log` in the data folder, rotated at 20 MB and kept in five files (`neoaprs.log` and `.1` to `.4`); the desktop app's is `neoaprs-app.log` (1 MB, three files).
Every line has the time in UTC, the level and the text. Only warnings, errors and the lines of the migrations go to stderr, and so to the journal.

**What the log has to be read by:**

- The start is two lines: `NeoAPRS 0.9.0 starting, data in ...` and `running on <system and version>, <machine>, Python X.Y.Z, installed as <kind>, pid N` (the kind is `neoaprs/cli/installkind.py`'s).
- A page that connects is `page connected from 127.0.0.1: Firefox 140 on Linux` (`neoaprs/web/browser.py` names the browser from the socket's `User-Agent`; one it does not know is `unknown browser (...)` with the start of the header on one line).
- A setting saved from the page is a line for each key that changed: `settings: station/comment = new (was old)`. A secret setting (`web/key` and any key with key, secret, password or token in its name, `neoaprs/configtypes.py`) is only `(set, 14 characters)` or `(empty)`. A value that is changed with `neoaprs db set` is not in the log.
- An error of the page itself arrives as the command `page_error` and is a warning: `page error (vue) on page index-HASH.js: MESSAGE | FIRST LINE OF THE STACK`, with the message and the line cut to one line (a page is not trusted with the form of the log). At most 20 for a connection are logged in a minute; the rest are counted in one line, `7 more page errors not logged this minute`, when the minute is over or the page leaves. The latest 100 (with the address of the page) are kept in memory for the bundle (`neoaprs/web/pageerrors.py`).
- What nothing caught is logged with its traceback (`neoaprs/cli/uncaught.py`): the event loop's exception handler (`event loop: Task exception was never retrieved (task: ...)`), the exceptions that end a thread, and the one that ends the daemon (`CRITICAL`). The tasks the parts start are in a `TaskSet`, which logs a failure as `<part> task <name> failed`.

**The bundle** (`neoaprs/cli/supportmake.py`) is a zip, `neoaprs-support-<CALL or nocall>-<YYYYmmdd-HHMMSS>Z.zip`, of text files: `README.txt`, `summary.txt` (the one screen: version, install kind, system, data folder, whether the daemon runs and for how long, the call, the position mode, the beacon, the TNC profile, port, speed, state and problem, the GPS, the web page's bind and switches, the database version and size, and the warnings and errors of the whole kept log, each message once as `COUNT× LAST-TIME LEVEL MESSAGE` with its numbers, times, addresses and durations ignored when comparing, errors first, then the newest, 25 at most, without the web server's 403/404 lines for `basemap*.pmtiles`, `/favicon.ico` and `/fonts/*.pbf`, which a line under the list counts),
`logs/` (`neoaprs.log` and the rotated ones, newest first, the newest lines kept within 12 MB in all, cut at a line start and with a first line that says how much was left out; the app's log; on Linux `journal.txt`, the last 3000 lines of `journalctl --user -u neoaprs`, best effort within 5 seconds),
`settings.json` (every setting, the secrets redacted by name), `state.json` (only from a running daemon: the `tnc` topic with its latest lines, the GPS, the beacon, the status report's radio, the map, the update, the serial ports with who holds them, the process's memory, threads and tasks, the database actor's counters),
`doctor.txt` (the checks of `neoaprs doctor`, run in the process), `database.txt` (the version, each migration with whether its source hash matches, the rows of each table, the sizes of the file, the log and the shared memory, `PRAGMA quick_check` unless the file is over 500 MB), `packets.txt` (the last 1000 packets and the last 200 that did not decode, as TNC2 lines with the parser's summary or error), `page.json` and `page-errors.json` (from the page). It is deflate-compressed and written under a temporary name that is renamed.

Nothing is changed: the database is opened read-only (as immutable when no daemon has it open, so that no `-wal` or `-shm` file is made beside it), the logs are read. A part that fails is a file `<name>.error.txt` with the traceback, and the summary says what it could not read; the bundle is made all the same. The access key's value (and the key typed without dashes) is taken out of every file as the zip is written, whatever put it there. What is left out: the access key, the key and certificates of the secure connection, the message store, the database file, the base map; the README says so, and that the log and `packets.txt` hold the packets heard and sent, which are public.

**Four ways to a bundle:** the page's Help button (`POST /support/bundle`), `neoaprs support` (from the data folder, without the daemon, so no `state.json`; to the Desktop or `--out`), the Windows Start menu entry **NeoAPRS support logs** (`neoaprs.exe support --show --pause` in a console) and the tray item **Collect support logs** of the desktop app (the same, in a thread, to the Desktop, shown in the file manager, logged as `support bundle made: PATH, N KB`).

**`POST /support/bundle`** takes `{"page": {...}}` (at most 256 KB, stored as `page.json`) and answers the zip as `application/zip` with `Content-Disposition: attachment`. It is behind exactly what the page and `/ws` are: the Host gate, no plain http while the secure page is served, the session of the access key from another device (`401` without it), and no `Origin` of another site. It is made in a thread after the state has been read on the loop; one at a time (`429` and `Retry-After` for a second request), `400` for a body that is not a JSON object with a `page` object, `500` with a line to look in the log when the bundle could not be made. The log says `support bundle made for the page: NAME, N KB`. The route reads its body in pieces so that 256 KB is its limit alone; the rest of the server takes 64 KB.
