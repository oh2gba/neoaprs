# Architecture and its ratchets

This file says what the layers are, what the limits are, and how the tests that hold them work. NeoAPRS is one process with one asyncio loop and one database thread.

## The layers

Imports run down this table, never up. `tests/test_architecture.py` reads the imports of every file in `neoaprs/` (lazy imports inside functions included) and holds the map.

The tables of this document that are that test's data (this one, the rules after it, and the lists of what is still allowed under "The ratchets" and in "The database actor") are made from it by
`scripts/doc-arch --write`, and `tests/test_docs.py` fails when one differs. Change `LAYERS` and the lists in the test, run the script, commit both.

<!-- doc-arch:layers -->
| layer | modules | may import | may not import |
| --- | --- | --- | --- |
| foundation | `clock signal coded policy callsign geo symbols kiss ax25 aprsposition aprsmice aprsmessage aprsparse aprsweather aprsthirdparty aprsextension aprsfreq aprsstorm aprslocator aprstelemetry aprsnmea gpsfix smartbeacon packet packetcodec message bulletin decay tncmode tncprofile pref route chain mapstate radiosearch serialboards versions updateasset device devicedata hourcount` | foundation | domain, adapters, persistence, services, app, delivery, and any I/O library |
| domain | `alertcommand config configlegacy configstatus configtypes configvalues interlock station stationnotes stationbook aloha ownobject ownbulletin` | foundation, domain | adapters, persistence, services, app, delivery, and any I/O library |
| adapters | `source tasks serialport serialholders serialprobe btsdp btserial btle btpaired tnc tncsearch tncwatchdog tncentry tnclines childenv rigctld gpsfeed pmtilestool worldmap updatefetch updatedownload selfreplace` | foundation, domain, adapters | persistence, services, app, delivery |
| persistence | `store migrations migrations2 backupfolder durable instancelock stopfile walcare dbfile dberror dbstats dbthread db dbopen storesql paths dblog packetsql packetlog messagesql messagelog bulletinsql bulletinlog weathersql weatherlog ownsql ownlog supportsql` | foundation, domain, persistence | adapters, services, app, delivery |
| services | everything in `neoaprs/services/` | foundation, domain, adapters, persistence, services | app, delivery |
| app | `controller app wiring` | foundation, domain, adapters, persistence, services, app | delivery |
| delivery | `neoaprs/web/*`, `neoaprs/cli/*`, `neoaprs/desktop/*`, `neoaprs/daemon`, `neoaprs/__main__` | foundation, domain, adapters, persistence, services, app, delivery | - |
<!-- /doc-arch -->

Besides the direction:

<!-- doc-arch:rules -->
* The I/O libraries that foundation and domain may not import (pyserial, `serial`, is one of them): `asyncio bleak fcntl http.client http.server os pty select selectors serial shutil socket sqlite3 ssl subprocess tempfile termios tornado urllib.request`.
* pyserial (`serial`) only in the adapters layer.
* Among the adapters only the bases every feed shares may be imported: `neoaprs.source`, `neoaprs.tasks`; and the sibling pairs: `neoaprs.btserial` and `neoaprs.btsdp`, `neoaprs.gpsfeed` and `neoaprs.serialport`, `neoaprs.serialholders` and `neoaprs.serialport`, `neoaprs.serialport` and `neoaprs.btle`, `neoaprs.serialport` and `neoaprs.btserial`, `neoaprs.serialprobe` and `neoaprs.btpaired`, `neoaprs.serialprobe` and `neoaprs.serialholders`, `neoaprs.serialprobe` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.serialholders`, `neoaprs.tnc` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.serialprobe`, `neoaprs.tnc` and `neoaprs.tncentry`, `neoaprs.tnc` and `neoaprs.tnclines`, `neoaprs.tnc` and `neoaprs.tncsearch`, `neoaprs.tnc` and `neoaprs.tncwatchdog`, `neoaprs.tncsearch` and `neoaprs.serialport`, `neoaprs.tncsearch` and `neoaprs.serialprobe`, `neoaprs.worldmap` and `neoaprs.pmtilestool`.
* bleak (the extra `ble`) only in `neoaprs/btle.py`.
* Tornado only in `neoaprs/web/`.
* pydantic only in the wire modules of `neoaprs/web/`: `neoaprs/web/beaconwire.py`, `neoaprs/web/bulletinwire.py`, `neoaprs/web/configwire.py`, `neoaprs/web/dispatch.py`, `neoaprs/web/gpswire.py`, `neoaprs/web/hostwire.py`, `neoaprs/web/hubwire.py`, `neoaprs/web/mapwire.py`, `neoaprs/web/messagewire.py`, `neoaprs/web/outbound.py`, `neoaprs/web/ownwire.py`, `neoaprs/web/packetwire.py`, `neoaprs/web/portwire.py`, `neoaprs/web/prefwire.py`, `neoaprs/web/protocol.py`, `neoaprs/web/stationwire.py`, `neoaprs/web/supportwire.py`, `neoaprs/web/tncwire.py`, `neoaprs/web/updatewire.py`, `neoaprs/web/weatherwire.py`, `neoaprs/web/wirebase.py`.
* The desktop app's toolkits (`PIL PySide6 pystray shiboken6 webview`, the extra `app`) only in the shells: `neoaprs/desktop/qtshell.py`, `neoaprs/desktop/qtwindow.py`, `neoaprs/desktop/winshell.py`.
<!-- /doc-arch -->

No import cycle at all. Every module of `neoaprs/` has a layer (a new file fails the test until you place it).

Nothing outside the delivery layer imports `neoaprs.web` (the page's server, a package of `neoaprs/` since it is part of what a wheel carries): only the process
(`neoaprs/daemon.py`) and the commands (`neoaprs/cli/`) name it.

What each layer is for:

* **foundation**: pure code, no I/O library.
  * Time and signals: `clock`, `signal`.
  * Rules and coding: the call and SSID rules (`callsign`), geometry (`geo`), the symbol tables (`symbols`), KISS framing (`kiss`), AX.25 frame coding (`ax25`).
  * The APRS decoders (`aprs*`) and the `Packet` they produce. `aprsweather` reads the weather fields of a weather station's position or a positionless report
    into metric values, and `aprsthirdparty` the packet inside a third-party frame an iGate sent.
  * `packetcodec`: a packet as a row of the packet table, a time as text, the JSON of what the parser made.
  * `message`: a message as a value, who a message is for, what text may be sent, when the next attempt is due. `bulletin`: which addressees are the message
    board's, and a bulletin as the board keeps it.
  * `route`: how a packet reached us (the route out of the starred addresses of a path, its text, the path to send by, the count of a station's routes).
    `chain`: the delivery chain of a message we sent (its attempts, the hops of a path that a copy heard back shows used).
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
  * `serialport` is the line on every system: any pyserial port or a `socket://host:port` URL (KISS over TCP), opened in a thread with DTR and RTS held low,
    read by a thread and written by a thread of its own that hand the bytes to the loop with `call_soon_threadsafe`. No descriptor is given to the loop, which
    Windows could not wait for.
  * `btserial` is the classic Bluetooth serial port (`bt://`, an RFCOMM socket as a pyserial port, the channel looked up by `btsdp`); `btpaired` lists the paired devices. `btle` is a Bluetooth LE KISS TNC as a port
    (`ble://`): the small pyserial interface that `serialport` uses, over bleak running on a thread and event loop of its own, which notifies into a queue that `read` drains and takes `write` in pieces of the link's MTU.
    bleak is an optional extra (`ble`) and `btle` is the only module that imports it, when such a port is opened.
  * `serialholders` says which program has a device open (Linux, through /proc). `serialprobe` lists the ports of the machine and, on Linux only, searches the globs of `serial/pattern` for the radio.
  * `source` is the base every feed shares (state, problem, counts, the latest lines, the back-off). `tasks` is the set of tasks one owner starts.
  * The TNC has two parts of its own: `tncsearch` (the search for the radio among the ports) and `tncwatchdog` (the keep-alive: when an open line goes quiet,
    check that the radio is there; probe it while it is silent; reopen the port now and then).
  * `worldmap` finds the world map that ships with the program (`neoaprs/maps/basemap-world.pmtiles`, package data: in a clone, a wheel, an AppImage's or a .deb's site-packages, the Windows app's `_internal`) and picks the one to serve: the data folder's own if it is a good PMTiles file, else the shipped one.
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
    overheard), `services/heard.py` (the repeats of a message already heard and when each was last acked) and `services/delivery.py` (the attempts of each
    message and the hops heard back).
  * The message board (`services/bulletins.py`): the bulletins, announcements, group bulletins and group messages the inbox hands over, one for each sender and
    slot, kept until the operator deletes it.
  * Our own objects and bulletins (`services/ownobjects.py` and `services/ownbulletins.py`): made, changed and killed or posted and deleted by the operator,
    kept in the database and sent on the specification's schedules. Both are `services/repeater.py`'s ticker and send through `services/sender.py`, which holds
    back everything while the call is not set or the radio is not usable and puts a pause between two frames of ours.
  * The GPS (`services/gps.py`) and the moving station's part of the beacon (`services/mobilebeacon.py`): the fix of the GPS feed (`neoaprs/gpsfeed.py`, with `neoaprs/gpsfix.py` and `neoaprs/smartbeacon.py` as the pure code under it), its age, and the compressed position and the memory of the last beacon that SmartBeaconing needs.
  * The queries (`services/queries.py`): the answers to `?APRSP`, `?APRSS`, `?APRSD`, `?APRST`, `?PING?`, `?APRSO`, `?APRSM`, `?APRSH` and `?APRS?`, through the beacon's frames, our objects, our messages and the packet log, by the asker's path; `?WX?` and `?IGATE?` are recognised and not answered.
  * The QRU server (`services/qru.py`): our objects of a QRU group, sent to a station that sends the addressee `QRU` the group's name (or `INFO` for the list of groups). The inbox hands it the messages to `QRU`. It and the queries send their answers through `services/answers.py`: the asker's path, the pace between frames and the answer given once.
  * The fill-in digipeater (`services/digipeater.py`): a packet whose first unused hop is `WIDE1-1` or our call is sent again with our call as a used hop, when `digi/enabled` is on.
  * The preferences of the stations (`services/prefbook.py`): the path and RF only of each station, which messaging is given as its `paths`.
  * What the services that send share (`services/common.py`): the `Radio` they need of the Tnc, `ConfigSource` and `our_frame`, our frame to the tocall.
  * The alert (`services/alerts.py`), the base map (`services/mapfetch.py`, `services/mapcli.py`, and `services/mapauto.py`, which begins it once without a click when a place is first set), the update check (`services/updatecheck.py`) Update now (`services/selfupdate.py`, `services/selfinstall.py`) and Find my radio (`services/radiofinder.py`, `services/radioprobe.py`).
* **app**: the composition root. `app.py` makes the parts, `controller.py` is the object of the parts and brings them up and down, and `wiring.py` connects the
  signals, says how the settings become the Tnc's, and fills the station book from the database at the start.
* **delivery**: one package each.
  * `neoaprs/web/`: Tornado, the pydantic wire models (`*wire.py`), the state hub and its topics, the commands. `server.py` is the coordinator (routes, Host
    names, the switch and the key), with `pagesocket.py` (the socket of a tab) and `listen.py` (the choice of the port). `processmeter.py` is what the daemon
    costs the machine, for the status. `topics.py` is the one place that connects the daemon's signals to the page, so it is a composition root too. `supporthandler.py` is `POST /support/bundle` and `pageerrors.py` what the pages report of their own errors. The wire
    format is `PROTOCOL.md`.
  * `neoaprs/cli/`: the `neoaprs` command. `service` sets the daemon up to start at login with the system's own means, `doctor` checks the computer, `support` makes the support bundle (`supportmake` is what the daemon, the command and the tray all call; `supportgather` reads, `supportbundle` writes the zip; `uncaught` logs what escapes), and `db`,
    `map`, `replay` and `capture` are tools of the command. `neoaprs/cli/neoaprs.service` is the unit's template, package data. The one command that builds a
    service is `neoaprs/cli/mapcmd.py` (the base map's command line); `neoaprs/cli/capturecmd.py` is a composition root of its own, for the one serial port it
    wires to a file.
  * `neoaprs/desktop/`: the desktop app, `neoaprs app` and `neoaprs-app`, the page of the daemon in a window and a tray icon. `cmd.py` runs it; `session.py`
    attaches to the daemon of the data folder or starts one with the code of `neoaprs open`; `menu.py` is the tray menu as data and what it does; `links.py`
    decides which addresses stay in the window; `autostart.py`, `single.py` and `appstate.py` are start at sign-in, the one-app lock and what the app remembers.
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
| `port_override`, `pattern_override` | the serial port (`--port`) and the globs of the search for this run only; never stored |
| `store` | the `Store`, the settings in the database |
| `tnc` | the radio |
| `stationbook` | the stations as the packets tell them |
| `gps_feed`, `gps` | the GPS: `gps_feed` reads a gpsd or a serial receiver (`neoaprs/gpsfeed.py`, an adapter), `gps` is the service that keeps the latest fix and how fresh it is (`services/gps.py`) and tells the station book and the ALOHA circle when we have moved. The beacon is given `gps` |
| `beacon` | the position packet, a service: on an interval for a station that stays, on SmartBeaconing from the GPS fix for a moving one (`services/mobilebeacon.py`, `neoaprs/smartbeacon.py`) |
| `rigstatus` | the status report, a service. It reads rigctld through `neoaprs/rigctld.py`, and `queries` is given its `status_frame` |
| `alerts` | the message alert, a service. Messaging is given its `alert` |
| `packetlog`, `messagelog`, `weatherlog`, `bulletinlog`, `ownlog` | the logs of the database: the packets and the station cache, the messages, the weather observations, the message board, our own objects and bulletins |
| `prefbook` | the preferences of the stations, a service. Messaging is given its `path_for`, the prune its `never_hidden` |
| `bulletins` | the message board, a service. Messaging is given its `heard` |
| `sender` | the pause between our frames, which `ownobjects` and `ownbulletins` share |
| `ownobjects`, `ownbulletins` | our own objects and bulletins, services. `ownobjects` is given `_is_station`, which says whether a name is a station's |
| `messaging` | messages, a service |
| `queries` | the answers to queries, a service |
| `qru` | the QRU server, a service: given `ownobjects`, the station book and the paths; messaging is given its `heard` |
| `digipeater` | the fill-in digipeater, a service: it repeats a packet that asks for WIDE1-1 or for our call, when `digi/enabled` is on |
| `aloha` | the ALOHA circle, a service: the radius round our position (`radius_km`), told to the page in the topic `map`; started by the controller |
| `mapfetch` | the base map, a service: the detailed map round our position, made on request from the page with the pmtiles tool (the world map under it ships with the program; it is made only where there is none) |
| `mapauto` | the detailed map without a click, a service of `mapfetch`: the first time a place is set and there is no detailed map, it begins the same job, once for an installation (the row `map/auto`), and tries again at the next start when it could not be fetched; switched on by the daemon only (`Controller(auto_map=True)`), started by the controller |
| `radiofinder` | Find my radio, a service: on the page's request it tries the ports of the search for the radio one after the other, each at the usual speeds, and stops at the first TNC that talks KISS or can be put into KISS by a TNC profile; the radio's own line is let go meanwhile |
| `selfupdate` | Update now, a service: on the page's request it downloads the file of the announced release that updates this copy (`neoaprs/updateasset.py`, `neoaprs/updatedownload.py`), checks its SHA-256 against the release's SHA256SUMS and has the installer of the kind put it in place (`services/selfinstall.py`: the Windows installer run silently, an AppImage renamed over the old one) |
| `reexec` | the command line that runs in the place of the process once the daemon has ended, set by Update now of an AppImage (`neoaprs/selfreplace.py`) |
| `updatecheck` | the update check, a service: once a day it asks the version page, through `neoaprs/updatefetch.py`, which version is the latest, and keeps it only if it is newer than ours. `neoaprs/versions.py` has the comparison. `check_now` is the same question on request |
| `install` | how this copy was installed, worked out by the process in `neoaprs/cli/installkind.py` and given to the controller. The page's `hello` carries it, so that the page can say how to update |
| `config_changed` | the signal that every save of the settings emits |
| `web` | the page's server, which the controller makes, once the settings are read, from the factory the process gave it (`Controller(web=WebServer)`: this layer does not import `neoaprs/web/`, it knows a `Frontend` that starts and stops) |
| `db` | the `Db`, once it is open |
| `tasks` | the `TaskSet` of what the parts start on the loop |

A part gets what it needs as constructor arguments (objects of a lower layer, Protocols or plain callables), never a back-reference.

`neoaprs/wiring.py` connects them:

- What the Tnc hears goes to the packet log, the station book, the weather log, messaging (which answers a message to us with an ack and hands bulletins to the
  board and hands a message to `QRU` to the QRU server), the queries, our objects (which stop when another station reports one) and, last, the digipeater.
- Our objects go to the station book as stations of their own (`own`).
- The GPS feed's fixes go to the GPS service; when our position moved far enough the service's `moved` puts our own row at the fix and works the ALOHA circle out again.
- What the book changes or removes goes to the station cache in the database.
- The port a search found is stored as `serial/last_port` and tried first next time.
- `tnc_settings` is how the settings become the Tnc's port, speed and KISS entry, and `seed_station_book` fills the book at the start.

`neoaprs/controller.py` (`Controller`, which extends `Services`) is the start and the stop.

- **`start()`** makes the data folder, opens the database (the thread opens and migrates the file and gives it to the `Store` and the logs), and reads the
  settings. It seeds the station book from the station cache, puts our own station in it, rebuilds the tracks from the latest position packets, makes the
  weather log from the packets kept if it is empty and gives the stations their latest weather. Then it starts the message board, the Tnc **in a task** (finding
  the port can take 20 s a port, and nothing waits for it), the GPS (its feed in a task), the beacon (its timer waits 30 s before the first one), our objects and bulletins, the status, the
  preferences of the stations, messaging (it takes the latest messages from the database and starts its retry ticker), the page's server (a port in use is
  logged and the daemon goes on without the page), the update check and the daily prune task.
- **The prune** removes packets, weather observations and stations older than `LOG_KEEP_DAYS` (`neoaprs/policy.py`). Messages and bulletins are never pruned.
- **`stop()`** ends the page's server, the update check, a map job, the queries, the QRU server, messaging, the alert, the status, our bulletins and objects, the beacon, the GPS, the
  Tnc and the tasks, then closes the database, doing what was asked of its thread first.
- **`save_config(Config)`** stores the settings, puts them in force, puts our own row where they say, tells the GPS (a changed source starts its feed afresh) and the beacon (a changed interval counts at once) and restarts the Tnc when its port, speed or KISS entry changed.

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
| `neoaprs/migrations.py` | the migrations and the opening of the file, before the thread opens it, and in the tools: migration code, exempt from the size limits of the steps it pins |
| `neoaprs/migrations2.py` | the migrations from the twelfth on, frozen beside migrations.py: migration code |
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
