# Architecture and its ratchets

This file says what the layers are, what the limits are, and how the tests that hold them work. NeoAPRS is one process with one asyncio loop and one database thread.

## The layers

Imports run down this table, never up. `tests/test_architecture.py` reads the imports of every file in `neoaprs/` (lazy imports inside functions included) and holds the map.

The tables of this document that are that test's data (this one, the rules after it, and the lists of what is still allowed under "The ratchets" and in "The database actor") are made from it by
`scripts/doc-arch --write`, and `tests/test_docs.py` fails when one differs. Change `LAYERS` and the lists in the test, run the script, commit both.

<!-- doc-arch:layers -->
| layer | modules | may import | may not import |
| --- | --- | --- | --- |
| foundation | `clock signal coded policy units recent callsign geo symbols kiss ax25 aprsposition aprsmice aprsmiceout aprsmessage aprsparse aprsweather aprsthirdparty aprsisline aprsextension aprsfreq aprsstorm aprslocator aprstelemetry aprsnmea gpsfix smartbeacon packet packetcodec message bulletin decay tncmode tncprofile pref route reach chain mapstate radiosearch serialboards versions updateasset releasenotes device devicedata hourcount dummyroutes dummyframes dummyscene dummyhfscene dummyqru igaterules cipher mercury mercurycards mercuryscope channelbusy radiorules bundled` | foundation | domain, adapters, persistence, services, app, delivery, and any I/O library |
| domain | `alertcommand config configlegacy configstatus configtypes configvalues interlock station stationnotes stationbook aloha ownobject ownbulletin qrutext` | foundation, domain | adapters, persistence, services, app, delivery, and any I/O library |
| adapters | `source tasks serialport serialholders serialprobe btsdp btserial btle btpaired tnc tncport callbackport dummyline tncsearch tncwatchdog tncentry tncfollow tnclines tncreader childenv rigctld gpsfeed aprsis pmtilestool worldmap updatefetch updatedownload selfreplace mercuryhelper mercurycontrol mercurymodem mercurychannel mercuryscoping mercuryui websocketclient mercuryspeaker mercurytune httpstrust nodevices` | foundation, domain, adapters | persistence, services, app, delivery |
| persistence | `store migrations migrationlog migrationsteps1to11 migrationsteps12to21 migrationsteps22on backupfolder durable instancelock stopfile walcare dbfile dberror dbstats dbthread db dbopen storesql paths dblog packetsql packetlog messagesql messagelog bulletinsql bulletinlog weathersql weatherlog ownsql ownlog supportsql` | foundation, domain, persistence | adapters, services, app, delivery |
| services | everything in `neoaprs/services/` | foundation, domain, adapters, persistence, services | app, delivery |
| app | `controller app wiring radios` | foundation, domain, adapters, persistence, services, app | delivery |
| delivery | `neoaprs/web/*`, `neoaprs/cli/*`, `neoaprs/desktop/*`, `neoaprs/daemon`, `neoaprs/__main__` | foundation, domain, adapters, persistence, services, app, delivery | - |
<!-- /doc-arch -->

Besides the direction:

<!-- doc-arch:rules -->
* The I/O libraries that foundation and domain may not import (pyserial, `serial`, is one of them): `asyncio bleak fcntl http.client http.server os pty select selectors serial shutil socket sqlite3 ssl subprocess tempfile termios tornado urllib.request`.
* pyserial (`serial`) only in the adapters layer.
* Among the adapters only the bases every feed shares may be imported: `neoaprs.nodevices`, `neoaprs.source`, `neoaprs.tasks`; and the sibling pairs: `neoaprs.btserial` and `neoaprs.btsdp`, `neoaprs.callbackport` and `neoaprs.serialport`, `neoaprs.dummyline` and `neoaprs.serialport`, `neoaprs.dummyline` and `neoaprs.tncport`, `neoaprs.gpsfeed` and `neoaprs.callbackport`, `neoaprs.gpsfeed` and `neoaprs.serialport`, `neoaprs.mercuryfirewall` and `neoaprs.winelevate`, `neoaprs.mercuryhelper` and `neoaprs.childenv`, `neoaprs.mercurymodem` and `neoaprs.mercuryallow`, `neoaprs.mercurymodem` and `neoaprs.mercurychannel`, `neoaprs.mercurymodem` and `neoaprs.mercurycontrol`, `neoaprs.mercurymodem` and `neoaprs.mercuryfirewall`, `neoaprs.mercurymodem` and `neoaprs.mercuryhelper`, `neoaprs.mercurymodem` and `neoaprs.mercuryscoping`, `neoaprs.mercurymodem` and `neoaprs.mercuryspeaker`, `neoaprs.mercurymodem` and `neoaprs.mercurytune`, `neoaprs.mercurymodem` and `neoaprs.serialprobe`, `neoaprs.mercuryscoping` and `neoaprs.mercuryui`, `neoaprs.mercuryui` and `neoaprs.websocketclient`, `neoaprs.pmtilestool` and `neoaprs.httpstrust`, `neoaprs.serialholders` and `neoaprs.serialport`, `neoaprs.serialport` and `neoaprs.btle`, `neoaprs.serialport` and `neoaprs.btserial`, `neoaprs.serialprobe` and `neoaprs.btpaired`, `neoaprs.serialprobe` and `neoaprs.serialholders`, `neoaprs.serialprobe` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.dummyline`, `neoaprs.tnc` and `neoaprs.serialholders`, `neoaprs.tnc` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.serialprobe`, `neoaprs.tnc` and `neoaprs.tncentry`, `neoaprs.tnc` and `neoaprs.tncfollow`, `neoaprs.tnc` and `neoaprs.tnclines`, `neoaprs.tnc` and `neoaprs.tncport`, `neoaprs.tnc` and `neoaprs.tncreader`, `neoaprs.tnc` and `neoaprs.tncsearch`, `neoaprs.tnc` and `neoaprs.tncwatchdog`, `neoaprs.tncfollow` and `neoaprs.serialport`, `neoaprs.tncfollow` and `neoaprs.serialprobe`, `neoaprs.tncport` and `neoaprs.callbackport`, `neoaprs.tncreader` and `neoaprs.tncentry`, `neoaprs.tncreader` and `neoaprs.tncport`, `neoaprs.tncreader` and `neoaprs.tncwatchdog`, `neoaprs.tncsearch` and `neoaprs.serialport`, `neoaprs.tncsearch` and `neoaprs.serialprobe`, `neoaprs.updatedownload` and `neoaprs.httpstrust`, `neoaprs.updatefetch` and `neoaprs.httpstrust`, `neoaprs.updatefetch` and `neoaprs.updatedownload`, `neoaprs.worldmap` and `neoaprs.pmtilestool`.
* bleak (the extra `ble`) only in `neoaprs/btle.py`.
* Tornado only in `neoaprs/web/`.
* pydantic only in the wire modules of `neoaprs/web/`: `neoaprs/web/beaconwire.py`, `neoaprs/web/bulletinwire.py`, `neoaprs/web/configwire.py`, `neoaprs/web/dispatch.py`, `neoaprs/web/generalwire.py`, `neoaprs/web/gpswire.py`, `neoaprs/web/historywire.py`, `neoaprs/web/hostwire.py`, `neoaprs/web/hubwire.py`, `neoaprs/web/igatewire.py`, `neoaprs/web/mapwire.py`, `neoaprs/web/messagewire.py`, `neoaprs/web/outbound.py`, `neoaprs/web/ownwire.py`, `neoaprs/web/packetwire.py`, `neoaprs/web/portwire.py`, `neoaprs/web/prefwire.py`, `neoaprs/web/protocol.py`, `neoaprs/web/qruwire.py`, `neoaprs/web/replaywire.py`, `neoaprs/web/stationwire.py`, `neoaprs/web/supportwire.py`, `neoaprs/web/tncwire.py`, `neoaprs/web/updatewire.py`, `neoaprs/web/weatherwire.py`, `neoaprs/web/wirebase.py`.
* The desktop app's toolkits (`PIL PySide6 pystray shiboken6 webview`, the extra `app`) only in the shells: `neoaprs/desktop/qtshell.py`, `neoaprs/desktop/qtwindow.py`, `neoaprs/desktop/winshell.py`.
<!-- /doc-arch -->

No import cycle at all. Every module of `neoaprs/` has a layer (a new file fails the test until you place it).

Nothing outside the delivery layer imports `neoaprs.web` (the page's server, a package of `neoaprs/` since it is part of what a wheel carries): only the process
(`neoaprs/daemon.py`) and the commands (`neoaprs/cli/`) name it.

The ways out of the process are a list too. A module that starts a program, gives a line to a shell, puts another program in the place of this one, opens a URL or the system's browser, or hands a
string to pyserial is in `REACHES_OUT` of the test, with the kinds it does and why it may; the alert command (`neoaprs/services/alerts.py`) is the one place a shell is given a line (`SHELL_LINES`).
The list is exact, so a new place fails the test until somebody has looked at it. A plain connection to a host and a port (APRS-IS, gpsd, rigctld, the Mercury modem) is not on it.

What each layer is for:

* **foundation**: pure code, no I/O library.
  * Time and signals: `clock`, `signal`.
  * Rules and coding: the call and SSID rules (`callsign`), geometry (`geo`), the units of the air against the metric ones (`units`), the keys seen lately for a duplicate check (`recent`), the symbol tables (`symbols`), KISS framing (`kiss`), AX.25 frame coding (`ax25`).
  * The APRS decoders (`aprs*`) and the `Packet` they produce, which carries how it reached us (`via`: `rf`, `rf-gated` or `is`). `aprsweather` reads the weather fields of a weather station's position or a positionless report
    into metric values, `aprsthirdparty` the packet inside a third-party frame an iGate sent, and `aprsisline` a line of APRS-IS (TNC2 text with its q-construct) into a packet that came `via="is"`.
  * `igaterules`: which of the frames heard on the radio a receive-only iGate puts on APRS-IS, and the line each becomes (the specification's rules, the path as heard, `qAO` and the iGate's call, a third-party packet opened and judged again).
  * `packetcodec`: a packet as a row of the packet table, a time as text, the JSON of what the parser made.
  * `message`: a message as a value, who a message is for, what text may be sent, when the next attempt is due. `bulletin`: which addressees are the message
    board's, and a bulletin as the board keeps it.
  * `route`: how a packet reached us (the route out of the starred addresses of a path, its text, the path to send by, the count of a station's routes).
    `chain`: the delivery chain of a message we sent (its attempts, the hops of a path that a copy heard back shows used).
  * `reach`: how a packet from the internet got there in plain words (the iGate that heard it on the radio and the digipeaters before it, or an app that sent it, read from the q-construct of its path) and the two latest routes of a station that the map draws.
  * `device`: what a station runs, from the destination call of its packets or the type code of a Mic-E packet, by the APRS device identification list
    (`devicedata`, a snapshot made by `scripts/gen-devices.py`: CC BY-SA 2.0, from aprsorg/aprs-deviceid, which the daemon never fetches).
  * `pref`: what the operator set for a station, as a value. `mapstate`: the base map's files, estimate and job as plain values.
  * `tncmode`: a KISS stream or command-mode text, the mode detector of the TNC. `decay`: when what we send of our own accord goes out again (the
    specification's decay algorithm, the net cycle time of a path, the schedules of a bulletin and of a kill).
  * `policy`: the fixed numbers that are not settings (how long things are kept, the keep-alive time).
* **domain**:
  * `stationbook`: the stations as the packets tell them (who, where, when last, the track, the latest weather; objects and items, ours marked `own`; us). The
    tracks and the weather the database kept are seeded at the start. `station` is the station as a value, `stationnotes` what a packet says of its sender that the
    book notes (does it do messages; its packets of the last hour, which `hourcount` keeps as a count for each minute, so that a busy station costs no more than a quiet one).
  * `aloha`: the ALOHA circle of WB4APR, the distance round our position within which the stations heard on RF fill the channel (`policy.py` has the numbers). The service
    `services/aloha.py` works it out again every minute and when our position moves.
  * `config`: the settings as one immutable value, each key checked.
  * `ownobject` and `ownbulletin`: an object, an item or a bulletin of ours as a value, what it must keep to be sent, and the information field it makes.
* **adapters**: the world outside, the serial line and the TNC.
  * `serialport` is the line on every system: a device path, or a `socket://`, `tcp://`, `bt://` or `ble://` address (no other pyserial scheme) (KISS over TCP), opened in a thread with DTR and RTS set low as soon as the open allows,
    read by a thread and written by a thread of its own that hand the bytes to the loop with `call_soon_threadsafe`. No descriptor is given to the loop, which
    Windows could not wait for.
  * `btserial` is the classic Bluetooth serial port (`bt://`, an RFCOMM socket as a pyserial port, the channel looked up by `btsdp`); `btpaired` lists the paired devices. `btle` is a Bluetooth LE KISS TNC as a port
    (`ble://`): the small pyserial interface that `serialport` uses, over bleak running on a thread and event loop of its own, which notifies into a queue that `read` drains and takes `write` in pieces of the link's MTU.
    bleak is an optional extra (`ble`) and `btle` is the only module that imports it, when such a port is opened.
  * `serialholders` says which program has a device open (Linux, through /proc). `serialprobe` lists the ports of the machine and, on Linux only, searches the globs of `serial/pattern` for the radio.
  * `aprsis` is the connection to an APRS-IS server for the receive-only iGate: the greeting, the login line, `# logresp` (verified or not), the keep-alive both ways, a bounded write queue that drops the oldest line when the server is slow, the back-off. It only writes: what the server sends is read to keep the connection honest and thrown away, and nothing hands it to anything.
  * `source` is the base every feed shares (state, problem, counts, the latest lines, the back-off). `tasks` is the set of tasks one owner starts.
  * The TNC has three parts of its own: `tncsearch` (the search for the radio among the ports), `tncwatchdog` (the keep-alive: when an open line goes quiet,
    check that the radio is there; probe it while it is silent; reopen the port now and then) and `tncreader` (what the bytes of the open line say: the mode, the entry into KISS and its
    repeats, the settle time, the KISS frames handed on; the `Tnc` holds the line and the states).
    A third, `tncfollow`, is for where the radio is not searched for (Windows, macOS): the USB adapter of the named port is remembered, and a COM port that comes back with another number is opened.
  * `worldmap` finds the world map that ships with the program (`neoaprs/maps/basemap-world.pmtiles`, package data: in a clone, a wheel, an AppImage's or a .deb's site-packages, the Windows app's `_internal`) and picks the one to serve: the data folder's own if it is a good PMTiles file, else the shipped one.
  * The Mercury HF modem's UI interface: `websocketclient` is a small RFC 6455 client over asyncio streams (Tornado may be imported by `neoaprs/web/` only), `mercuryui` the link to the program's UI websocket on the loopback (opened again after the back-off, told once in the log when it cannot be reached, the spectrum feed asked for only while wanted), `mercuryscoping` the half of the modem part that owns it (the pictures of the passband five times a second while a page wants them, the transmit gain set live, the peak the status says) and `mercurychannel` the other half (`keyed`, `busy`, `snr` and the `hold` the Tnc asks about); the pure values, the spectrum frame, the commands, the meter and the bands of the busy detector, are `mercuryscope` in the foundation, and `channelbusy` holds the detectors that read those bands (Mercury's own, worked again, and the automatic control that is the channel's state while the spectrum is read: docs/mercury.md). The pages that have the scope open are `neoaprs/web/scopefeed.py`.
  * The Mercury HF modem: `mercuryhelper` is the Mercury program as a child of the daemon (the one NeoAPRS ships, found where `bundled.py` says; given free ports; started and read by a thread; stopped; a stale one of ours ended; `mercury -z` for the sound cards),
    `mercurycontrol` its control port (`PTT ON/OFF`, `BUSY ON/OFF`, `SN`) as a second connection, and `mercurymodem` the part that owns both: the configuration written from the settings, the restart after the back-off, and the hold the Tnc asks about while a frame is on the air or the channel is busy. The pure values (the mode, the frame cap, the keying, the command line, the parsers) are `mercury` in the foundation.
  * `pmtilestool` is the pmtiles program that cuts the base map out of a big archive. It is found on the PATH or in the data folder's `bin/`, fetched from the
    pinned release of go-pmtiles (SHA-256 checked) when it is not there, and run in a thread so that it works on every event loop.
* **persistence**: the database file on the database thread.
  * The actor, the migrations and the settings: `store`, `storesql`.
  * `supportsql` is the read-only statements of the support bundle. `dblog` is what the logs below share: the database they run on and the ways they ask it, each of which says no instead of raising.
  * `packetlog` (every packet and the station cache, appended without waiting) with `packetsql`.
  * `messagelog` (every message we sent and every one sent to us: an insert that is awaited, state updates appended, the attempts and the hops heard back of
    each message of ours appended; and the table `station_pref`) with `messagesql`.
  * `bulletinlog` (the message board: one row for each sender and slot, appended) with `bulletinsql`; `ownlog` (our own objects, items and bulletins with where
    each schedule stands) with `ownsql`; `weatherlog` (every observation of a weather station, appended, for the trend graphs; made once from the packets
    already kept when it is empty) with `weathersql`.
* **services**: stateful parts above the layers below, in `neoaprs/services/`.
  * The beacon (`services/beacon.py`: our position packet from the settings, on an interval and on request, through the Tnc) and, with it, the status report
    (`services/rigstatus.py`). They keep when they last sent in rows of the settings table (`services/memory.py`), so that a restart keeps the schedule.
  * Messaging (`services/messaging.py`): messages to and from other stations through the Tnc, acks, the retry schedule, the messages kept in the database. Its
    parts are `services/inbox.py` (what the Tnc hears: a message to us kept and acked, an ack or a rej settling a message, a message to another station
    overheard), `services/heard.py` (the repeats of a message already heard and when each was last acked), `services/delivery.py` (the attempts of each
    message and the hops heard back), `services/retries.py` (when each message being sent needs attention, and the ticker that makes the attempt that is due)
    and `services/acks.py` (the message ids we give and the acks we send).
  * The message board (`services/bulletins.py`): the bulletins, announcements, group bulletins and group messages the inbox hands over, one for each sender and
    slot, kept until the operator deletes it.
  * Our own objects and bulletins (`services/ownobjects.py` and `services/ownbulletins.py`): made, changed and killed or posted and deleted by the operator,
    kept in the database and sent on the specification's schedules. Both are `services/repeater.py`'s ticker and send through `services/sender.py`, which holds
    back everything while the call is not set or the radio is not usable and puts a pause between two frames of ours.
  * The GPS (`services/gps.py`) and the moving station's part of the beacon (`services/mobilebeacon.py`): the fix of the GPS feed (`neoaprs/gpsfeed.py`, with `neoaprs/gpsfix.py` and `neoaprs/smartbeacon.py` as the pure code under it), its age, and the compressed position and the memory of the last beacon that SmartBeaconing needs.
  * The queries (`services/queries.py`): the answers to `?APRSP`, `?APRSS`, `?APRSD`, `?APRST`, `?PING?`, `?APRSO`, `?APRSM`, `?APRSH`, `?APRS?` and, while the iGate gates (`connected`), `?IGATE?` (`<IGATE,MSG_CNT=0,LOC_CNT=n,UPL_CNT=n`), through the beacon's frames, our objects, our messages, the packet log and the iGate's count, by the asker's path; `?WX?` is recognised and not answered.
  * The QRU server (`services/qru.py`): our objects of a QRU group, sent to a station that sends the addressee `QRU` the group's name (or `INFO` for the list of groups). The inbox hands it the messages to `QRU`. It and the queries send their answers through `services/answers.py`: the asker's path (with RFONLY for the QRU server's), the pace between frames and the answer given once.
  * Asking QRU (`services/qruask.py`): one request to the addressee `QRU` with no id, by the path of messages with RFONLY (or the path and RF only the operator gives it), and the servers that answered it (the topic `qru`), noted from the messages to us.
  * Asking around (`services/generalask.py`): a general query (`?APRS?`, `?IGATE?` or `?WX?`) sent once at the operator's request, by the path given or `beacon/path`, RF only unless told otherwise, and the stations heard on the radio in the two minutes after it that the station book had not heard in the ten before (the topic `general`).
  * The fill-in digipeater (`services/digipeater.py`): a packet whose first unused hop is `WIDE1-1` or our call is sent again with our call as a used hop, when `digi/enabled` is on.
  * The receive-only iGate (`services/igate.py`): every packet heard on the radio goes through the rules of `igaterules` to APRS-IS (`qAO`), duplicates within 30 seconds once, the counts for the page and the log, and our own position to APRS-IS. It is given the connection (`aprsis`), the settings and a function for the position, and has no Tnc, no `Radio` and no sender: nothing from APRS-IS can reach the radio.
  * The preferences of the stations (`services/prefbook.py`): the path, RF only and the alert of each station; messaging is given the paths.
  * The keys of encrypted messages (`services/keyring.py`): our own key pair and the key each station announced; messaging seals and opens with them.
  * The alerts set on stations (`services/stationalerts.py`): watched as the station book changes (on the air after half an hour of silence, within N km of us, heard direct), each fired once for each crossing, to the alert command and, by the page's topics, to every page.
  * What the services that send share (`services/common.py`): the `Radio` they need of the Tnc, `ConfigSource` and `our_frame`, our frame to the tocall.
  * The alert (`services/alerts.py`), the base map (`services/mapfetch.py`, `services/mapcli.py`, and `services/mapauto.py`, which begins it without a click when a place is set or the guide asks, unless the map there covers the place), the update check (`services/updatecheck.py`) Update now (`services/selfupdate.py`, `services/selfinstall.py`) and Find my radio (`services/radiofinder.py`, `services/radioprobe.py`).
* **app**: the composition root. `app.py` makes the parts, `controller.py` is the object of the parts and brings them up and down (each radio on its own tickbox; the Mercury HF modem, `mercury`, with the HF Tnc: started before it, stopped with it), `radios.py` is the two radios as one for the services, and `wiring.py` connects the
  signals (both radios' packets go the same way, each stamped with its radio), says how the settings become each Tnc's (`tnc_settings`, `hf_settings`: the HF radio's port is the one the modem part chose), and fills the station book from the database at the start.
* **delivery**: one package each.
  * `neoaprs/web/`: Tornado, the pydantic wire models (`*wire.py`), the state hub and its topics, the commands. `server.py` is the coordinator (routes, Host
    names, the switch and the key), with `pagesocket.py` (the socket of a tab) and `listen.py` (the choice of the port). `processmeter.py` is what the daemon
    costs the machine, for the status. `topics.py` is the one place that connects the daemon's signals to the page, so it is a composition root too (`packetwindow.py` is the latest packets it holds for the page, and the internet's packets are shown or left out there and in the station rows by `igate/enabled`). `supporthandler.py` is `POST /support/bundle` and `pageerrors.py` what the pages report of their own errors. The wire
    format is `PROTOCOL.md`.
  * `neoaprs/cli/`: the `neoaprs` command. `service` sets the daemon up to start at login with the system's own means, `doctor` checks the computer, `support` makes the support bundle (`supportmake` is what the daemon, the command and the tray all call; `supportgather` reads, `supportbundle` writes the zip; `uncaught` logs what escapes), and `db`,
    `map`, `replay` and `capture` are tools of the command. `neoaprs/cli/neoaprs.service` is the unit's template, package data. The one command that builds a
    service is `neoaprs/cli/mapcmd.py` (the base map's command line); `neoaprs/cli/capturecmd.py` is a composition root of its own, for the one serial port it
    wires to a file.
  * `neoaprs/desktop/`: the desktop app, `neoaprs app` and `neoaprs-app`, the page of the daemon in a window and a tray icon. `cmd.py` runs it; `session.py`
    attaches to the daemon of the data folder or starts one with the code of `neoaprs open`; `menu.py` is the tray menu as data and what it does; `links.py`
    decides which addresses stay in the window and gives the window's address the fragment `#app`, by which the page knows it is the app (and shows no Server mark: page and daemon are one); `autostart.py`, `single.py` and `appstate.py` are start at sign-in, the one-app lock and what the app remembers.
    The toolkits are imported by `qtshell.py` and `qtwindow.py` (Qt, Linux and macOS) and `winshell.py` (pywebview and pystray, Windows) and by nothing else
    (`TOOLKIT_HOMES` in the test). The Qt shell connects Qt's own signals, so it is a place for `connect` too.
  * `neoaprs/daemon.py`, the process, which names `neoaprs.web.server.WebServer` as the controller's page, and `neoaprs/__main__.py`, which is `python -m neoaprs`.

  Each package of the delivery layer is that layer whole (`DELIVERY_PACKAGES` in the test): a new module of `neoaprs/web/`, `neoaprs/cli/` or `neoaprs/desktop/`
  needs no entry in `LAYERS`. The commands may import every layer.

## The composition root

`neoaprs/app.py` (`Services`) makes the parts and holds them under the names the page and the tests know. Nothing else makes a service (`SERVICE_BUILDERS` in the test).

| name | what it is |
|---|---|
| `config` | the settings, one immutable value that the controller reads at its start |
| `port_override`, `hf_port_override`, `pattern_override` | the FM radio's serial port (`--port`), the HF radio's Mercury (`--hf-port`, one that something else runs: the benches) and the globs of the search for this run only; never stored |
| `store` | the `Store`, the settings in the database |
| `tnc`, `hf` | the two radios, each a `Tnc`: the FM radio (the KISS TNC of `tnc/profile`) and the HF radio (the Mercury modem's profile, `mercury` behind it); each started while its tickbox (`fm/enabled`, `hf/enabled`) is on |
| `radios` | the two as one (`neoaprs/radios.py`): the default radio (FM while on, else HF) for a service that addresses no station, and the choice by station (`for_station`: FM unless the station was heard on HF alone) or by packet (`for_packet`: the radio it came on) for a service that answers one. Messaging, the queries, the QRU server, asking and the sender take it; the beacons and the digipeater take their own radio |
| `stationbook` | the stations as the packets tell them |
| `gps_feed`, `gps` | the GPS: `gps_feed` reads a gpsd or a serial receiver (`neoaprs/gpsfeed.py`, an adapter), `gps` is the service that keeps the latest fix and how fresh it is (`services/gps.py`) and tells the station book and the ALOHA circle when we have moved. The beacon is given `gps` |
| `beacon`, `hf_beacon` | the position packet, a service, one per radio: on an interval for a station that stays, on SmartBeaconing from the GPS fix for a moving one (`services/mobilebeacon.py`, `neoaprs/smartbeacon.py`) on the FM radio; on the HF radio by the HF rules (the one beacon interval, raised to a floor of 30 minutes while the HF radio is on, the random pause, no SmartBeaconing), its last send in a row of its own |
| `rigstatus` | the status report, a service. It reads rigctld through `neoaprs/rigctld.py`, and `queries` is given its `status_frame` |
| `alerts` | the alert command, a service. Messaging is given its `alert`, and the wiring connects the alerts of the stations to its `station` |
| `packetlog`, `messagelog`, `weatherlog`, `bulletinlog`, `ownlog` | the logs of the database: the packets and the station cache, the messages, the weather observations, the message board, our own objects and bulletins |
| `prefbook` | the preferences of the stations, a service. Messaging is given its `path_for`, the prune its `never_hidden` |
| `keyring` | the keys of encrypted messages, a service (`services/keyring.py`, the cipher in `neoaprs/cipher.py`): our own key pair in the data folder, the key each station announced in the message log's database. Messaging is given it; the flag `--encryption` of the daemon (`encryption`) allows the feature |
| `stationalerts` | the alerts set on stations, a service: given the station book, `prefbook` and the settings; the wiring connects what the book changes, what `prefbook` sets and the saves of the settings to it, and its `fired` to `alerts`; the page's topics tell every page what fired. The controller has it read the alerts after `prefbook` |
| `bulletins` | the message board, a service. Messaging is given its `heard` |
| `sender` | the pause between our frames, which `ownobjects` and `ownbulletins` share |
| `ownobjects`, `ownbulletins` | our own objects and bulletins, services. `ownobjects` is given `_is_station`, which says whether a name is a station's |
| `messaging` | messages, a service |
| `queries` | the answers to queries, a service |
| `qru` | the QRU server, a service: given `ownobjects`, the station book and the paths; messaging is given its `heard` |
| `qruask` | asking QRU and the servers that answered, a service: given the paths; it takes the packets of the radio (`ON_AIR_ONLY`) |
| `generalask` | asking around (the general queries sent from here) and who spoke after it, a service: given the station book; it takes the packets of the radio (`ON_AIR_ONLY`) |
| `digipeater` | the fill-in digipeater, a service: it repeats a packet that asks for WIDE1-1 or for our call, when `digi/enabled` is on |
| `aprsis`, `igate` | the receive-only iGate: `aprsis` is the connection to an APRS-IS server (an adapter, `neoaprs/aprsis.py`), `igate` the service that gates what the radio hears and sends our position (`services/igate.py`); started by the controller after the beacon, given `beacon.position_info` for the position; the page's topic `igate` follows it |
| `aloha` | the ALOHA circle, a service: the radius round our position (`radius_km`), told to the page in the topic `map`; started by the controller |
| `mapfetch` | the base map, a service: the detailed map round our position, made on request from the page with the pmtiles tool (the world map under it ships with the program; it is made only where there is none) |
| `mapauto` | the detailed map without a click, a service of `mapfetch`: when a place is set, or the setup guide says the map is wanted (`map_wanted`), it begins the same job for the setting's radius unless the detailed map there covers the place, remembers what it owes (the row `map/auto`), and tries again at the next start when it could not be fetched; switched on by the daemon only (`Controller(auto_map=True)`), started by the controller |
| `radiofinder` | Find my radio, a service: on the page's request it tries the ports of the search for the radio (Linux) or of the system's list (Windows, macOS) one after the other, each at the usual speeds, and stops at the first TNC that talks KISS or can be put into KISS by a TNC profile; the radio's own line is let go meanwhile |
| `selfupdate` | Update now, a service: on the page's request it downloads the file of the announced release that updates this copy (`neoaprs/updateasset.py`, `neoaprs/updatedownload.py`), checks its SHA-256 against the release's SHA256SUMS, believed only with the project's signature, and has the installer of the kind put it in place (`services/selfinstall.py`: the Windows installer run silently, an AppImage renamed over the old one) |
| `reexec` | the command line that runs in the place of the process once the daemon has ended, set by Update now of an AppImage (`neoaprs/selfreplace.py`) |
| `updatecheck` | the update check, a service: once a day it asks the version page, through `neoaprs/updatefetch.py`, which version is the latest, and keeps it only if it is newer than ours. `neoaprs/versions.py` has the comparison. The same module's `post_form` is the one POST of the program, Send feedback / logs of the Help group (`neoaprs/web/supportsend.py`). `check_now` is the same question on request; `release_notes` is what is new up to the newer version, or what the update we have had brought, the changelog at the tag of the one or of ours, fetched once (`neoaprs/releasenotes.py`) |
| `frequencies` | the frequencies the project suggests for the HF radio, a service (`neoaprs/services/frequencies.py`): a small file on the project's server (`site/frequencies.json`, `FREQUENCIES_URL` of `neoaprs/versions.py`) asked a minute after the start and when a page sends `hf_frequencies` (the HF box is shown), at most every 15 minutes and never with `NEOAPRS_UPDATE_CHECK=0`; every entry is checked, the last good list is kept in the row `update/frequencies` and told at the start. The wiring puts the project's list, else the dial the version page names, else the built-in two (`mercury.SUGGESTED`) on the modem, whose `frequencies` the topic `hf` carries |
| `install` | how this copy was installed, worked out by the process in `neoaprs/cli/installkind.py` and given to the controller. The page's `hello` carries it, so that the page can say how to update |
| `internet_packet` | the signal of the packets received from APRS-IS (`Packet.via` is `is`), entered through `hear_internet`; only the packet log, the station book and the weather log are connected to it (and the page's topics) |
| `config_changed` | the signal that every save of the settings emits |
| `config_lock` | the lock held while the settings are stored and put in force (`save_config`, `change_config`, the port the search found as `serial/last_port`): a change is made of the settings as they are then, so two that overlap keep each other's keys |
| `web` | the page's server, which the controller makes, once the settings are read, from the factory the process gave it (`Controller(web=WebServer)`: this layer does not import `neoaprs/web/`, it knows a `Frontend` that starts and stops) |
| `db` | the `Db`, once it is open |
| `tasks` | the `TaskSet` of what the parts start on the loop |

A part gets what it needs as constructor arguments (objects of a lower layer, Protocols or plain callables), never a back-reference.

`neoaprs/wiring.py` connects them:

- What the Tnc hears goes to the packet log, the station book, the weather log, messaging (which answers a message to us with an ack and hands bulletins to the
  board and hands a message to `QRU` to the QRU server), the queries, our objects (which stop when another station reports one) and, last, the digipeater.
  A packet received from APRS-IS enters through `Services.hear_internet` and goes to `internet_packet`, a signal of its own: the packet log, the station book and the weather log (`SEEN_BY_ALL`)
  are connected to both, and what answers, acknowledges, repeats or sends (`ON_AIR_ONLY`: messaging, the queries, asking QRU, our objects, the iGate, the digipeater) only to the Tnc's, each behind `AirOnly`, which drops an `is` packet
  handed to it by mistake; every entry of those services refuses one as well (`Packet.on_air`). `tests/test_internet_gate.py` walks the signals and holds them to the two lists.
  The Dummy radio's packets (`via` is `dummy`) go through the radio's signal like any other, and `packet.GATEABLE` (`rf`, `rf-gated`) is the set a consumer that sends to the internet may take.
  The iGate takes only what the radio heard: it checks `packet.via in GATEABLE` itself as well. The connection's changes go to `igate.link_changed` and the beacons that went out to `igate.beacon_sent`. Nothing connects the connection to the Tnc, and the iGate has no reference to it.
- Our objects go to the station book as stations of their own (`own`).
- The GPS feed's fixes go to the GPS service; when our position moved far enough the service's `moved` puts our own row at the fix and works the ALOHA circle out again.
- What the book changes or removes goes to the station cache in the database.
- The port a search found is stored as `serial/last_port` and tried first next time.
- `tnc_settings` is how the settings become the Tnc's port, speed and KISS entry, and `seed_station_book` fills the book at the start.

`neoaprs/controller.py` (`Controller`, which extends `Services`) is the start and the stop.

- **`start()`** makes the data folder, opens the database (the thread opens and migrates the file and gives it to the `Store` and the logs), and reads the
  settings. It seeds the station book from the station cache, puts our own station in it, rebuilds the tracks from the latest position packets, makes the
  weather log from the packets kept if it is empty and gives the stations their latest weather. Then it gives the Tnc its settings and starts the message board, the GPS (its feed in a task), the beacon (its timer waits 30 s before the first one), our objects and bulletins, the status, the
  preferences of the stations, messaging (it takes the latest messages from the database and starts its retry ticker), and only then the Tnc **in a task** (finding
  the port can take 20 s a port, and nothing waits for it; every part that handles its packets is up before the first one can come), the page's server (a port in use is
  logged and the daemon goes on without the page), the update check and the daily prune task.
- **The prune** removes packets, weather observations and stations older than `LOG_KEEP_DAYS` (`neoaprs/policy.py`). Messages and bulletins are never pruned.
- **`stop()`** ends the page's server, Find my radio and the Tnc first, then the update check, a map job, the queries, the QRU server, asking QRU, messaging, the alert, the status, our bulletins and objects, the beacon, the GPS
  and the tasks, each in a try of its own so that one that fails does not keep the others from stopping, then closes the database, doing what was asked of its thread first.
- **`save_config(Config)`** stores the settings that changed (a value written to the database by `neoaprs db set` meanwhile is left alone), puts them in force, puts our own row where they say, tells the GPS (a changed source starts its feed afresh) and the beacon (a changed interval counts at once) and restarts the Tnc when its port, speed or KISS entry changed. **`change_config(change)`** does the same for the settings that `change` makes of the ones in force, read under the one lock of the settings (`Services.config_lock`), so that two changes that overlap (the page's save and the access key the server makes) never lose each other's keys; the port the search found is stored under the same lock.

## The database actor

`neoaprs/db.py` is the only way to the file: ONE connection owned by ONE thread, and every statement of the program an operation on that thread's queue
(`neoaprs/dbthread.py`). Read its docstring; the guarantees, in one line each:

* **Order**: the queue is FIFO and there is one thread, so a read sees every write asked before it and nobody flushes or locks anything.
* **Transactions**: a write is `BEGIN IMMEDIATE` ... `COMMIT`, `ROLLBACK` when the function raises, and the error reaches the caller as it was raised; a
  function may not begin a transaction or ask the `Db` for anything (`NestedUse`).
* **Durable**: what `await db.write(...)` returned has been committed with `synchronous=FULL` (`neoaprs/dbfile.py`): the answer comes after the disk has it.
* **Appends** (`write_nowait`): the hot path of the packet log (`neoaprs/packetlog.py`): nobody waits, they are collected for a tick and committed as one
  transaction, bounded, the newest dropped and counted beyond the bound.
* **Shutdown**: `close()` does what was queued, closes the connection and ends the thread; a write is never withdrawn once it is on the queue.
* **Measured**: `stats()` gives the queue wait, the run time and the stall of the event loop as numbers.

The file is versioned and migrated by `neoaprs/migrations.py` before the thread uses it (`open_connection` in `neoaprs/dbopen.py`); a file of a newer version,
or one that is not a database, is refused with a reason, the daemon ends with exit code 2, and the unit does not restart on that code.

The homes of SQL (`SQL_HOMES` in the test): every file that imports `sqlite3` or calls `execute`, with what it is.

<!-- doc-arch:sql_homes -->
| file (`SQL_HOMES`) | what it is |
| --- | --- |
| `neoaprs/bulletinsql.py` | the statements of the bulletin table (the message board): functions of a connection that the thread runs |
| `neoaprs/db.py` | the database actor: the one connection, the one thread |
| `neoaprs/dberror.py` | the names of SQLite's connection and errors, taken from here by every class that uses the thread, so that none of them imports sqlite3 |
| `neoaprs/dbfile.py` | how a connection is set up (WAL, synchronous=FULL, the busy time) and the whole checked copy |
| `neoaprs/dbthread.py` | the thread of the actor: BEGIN, COMMIT, SAVEPOINT and the settings of its connection |
| `neoaprs/messagesql.py` | the statements of the message table: functions of a connection that the thread runs |
| `neoaprs/migrations.py` | the opening of the file, before the thread opens it, and in the tools, and the runner of the migrations (their history, the copy taken before them) |
| `neoaprs/migrationsteps12to21.py` | the migrations 12 to 21, frozen beside migrations.py: migration code |
| `neoaprs/migrationsteps1to11.py` | the migrations 1 to 11, frozen beside migrations.py: migration code |
| `neoaprs/migrationsteps22on.py` | the migrations from 22 on, frozen beside migrations.py: migration code |
| `neoaprs/ownsql.py` | the statements of the tables of our own objects and bulletins (what we send of our own accord): functions of a connection that the thread runs |
| `neoaprs/packetsql.py` | the statements of the packet log and the station cache: functions of a connection that the thread runs |
| `neoaprs/storesql.py` | the statements of the settings: functions of a connection that the thread runs |
| `neoaprs/supportsql.py` | the statements of the support bundle: functions of a read-only connection that the bundle's own thread runs (the file's version and sizes, the rows of each table, the latest packets) |
| `neoaprs/walcare.py` | the limits of the write-ahead log (journal_size_limit and the automatic checkpoint): a function of the connection, run by the thread |
| `neoaprs/weathersql.py` | the statements of the weather table (every observation of every weather station) and the read of the packets it is made from: functions of a connection that the thread runs |
<!-- /doc-arch -->

And what else touches SQL (`SQL_ELSEWHERE`; the numbers are exact and the list only shrinks):

<!-- doc-arch:sql_elsewhere -->
| file (`SQL_ELSEWHERE`) | imports `sqlite3` | calls of `execute` | why |
| --- | --- | --- | --- |
| - | - | - | no file outside the homes touches SQL |
<!-- /doc-arch -->

## The ratchets

The size limits are in `CONVENTIONS.md`. `tests/test_size_ratchet.py` measures them (`tests/support/codemap.py`). What is over a limit is listed in
`tests/size_baseline.json` with its current size as its ceiling, and the list only turns one way:

- new code is under the limits from its first commit;
- a listed unit never grows;
- one that shrank lowers its ceiling (`python -m tests.support.codemap --tighten`);
- one that is within the limit again leaves the list.

The baseline is empty.

Duplicated code is a ratchet too, in two halves.

- The Python half is `scripts/dup-check` (the stage `dup-py`): jscpd over `neoaprs/` and `tests/support/`, clones of at least 10 lines and 100 tokens, compared
  with `scripts/dup-baseline.json` by the pair of files a clone joins. A new pair, a larger one or more duplicated lines in all fail, and
  `scripts/dup-check --update` only tightens the baseline. It is empty: the Python tree has no clone at those limits.
- The page's half is the stage `dup` (`ui/.jscpd.json`: 5 lines, 50 tokens, at most 3 % over `ui/src`, the tests and the generated protocol left out).

What the layers still allow against the rule:

<!-- doc-arch:allowed -->
| import against the layers (`ALLOWED`) | why it is there |
| --- | --- |
| - | nothing is allowed against the layers |
<!-- /doc-arch -->

Wiring (`Signal.connect`) is in one place:

<!-- doc-arch:wiring -->
Places for `Signal.connect` (`COMPOSITION_ROOTS`): `neoaprs/cli/capturecmd.py`, `neoaprs/desktop/qtshell.py`, `neoaprs/desktop/qtwindow.py`, `neoaprs/web/topics.py`, `neoaprs/wiring.py`.

| connects outside them (`CONNECTS`) | how many | why |
| --- | --- | --- |
| - | - | nothing connects a signal outside the places above |
<!-- /doc-arch -->

The checks are functions of a tree (path to source), so the second half of `tests/test_architecture.py` shows each rule failing on a made-up tree: a rule that has never been seen failing is a guess.
