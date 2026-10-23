# Architecture and its ratchets

This file says what the layers are, what the limits are, and how the tests that hold them work. NeoAPRS is one process with one asyncio loop and one database thread.

## The layers

Imports run down this table, never up. `tests/test_architecture.py` reads the imports of every file in `neoaprs/` (lazy imports inside functions included) and holds the map. The tables of this
document that are that test's data (this one, the rules after it, and the lists of what is still allowed under "The ratchets" and in "The database actor") are made from it by `scripts/doc-arch --write`
and `tests/test_docs.py` fails when one differs: change `LAYERS` and the lists in the test, run the script, commit both.

<!-- doc-arch:layers -->
| layer | modules | may import | may not import |
| --- | --- | --- | --- |
| foundation | `clock signal callsign geo symbols kiss ax25 aprsposition aprsmice aprsmessage aprsparse aprsweather aprsthirdparty aprsextension aprslocator aprstelemetry aprsnmea packet packetcodec message bulletin decay tncmode tncprofile pref route chain mapstate serialboards versions` | foundation | domain, adapters, persistence, services, app, delivery, and any I/O library |
| domain | `alertcommand config configlegacy configtypes interlock stationbook ownobject ownbulletin` | foundation, domain | adapters, persistence, services, app, delivery, and any I/O library |
| adapters | `source tasks serialport serialholders serialprobe btsdp btserial btpaired tnc tncsearch tncwatchdog tncentry childenv rigctld pmtilestool updatefetch` | foundation, domain, adapters | persistence, services, app, delivery |
| persistence | `store migrations migrations2 backupfolder durable instancelock stopfile walcare dbfile dberror dbstats dbthread db dbopen storesql paths dblog packetsql packetlog messagesql messagelog bulletinsql bulletinlog weathersql weatherlog ownsql ownlog` | foundation, domain, persistence | adapters, services, app, delivery |
| services | everything in `neoaprs/services/` | foundation, domain, adapters, persistence, services | app, delivery |
| app | `controller app wiring` | foundation, domain, adapters, persistence, services, app | delivery |
| delivery | `neoaprs/web/*`, `neoaprs/cli/*`, `neoaprs/desktop/*`, `neoaprs/daemon`, `neoaprs/__main__` | foundation, domain, adapters, persistence, services, app, delivery | - |
<!-- /doc-arch -->

Besides the direction:

<!-- doc-arch:rules -->
* The I/O libraries that foundation and domain may not import (pyserial, `serial`, is one of them): `asyncio fcntl http.client http.server os pty select selectors serial shutil socket sqlite3 ssl subprocess tempfile termios tornado urllib.request`.
* pyserial (`serial`) only in the adapters layer.
* Among the adapters only the bases every feed shares may be imported: `neoaprs.source`, `neoaprs.tasks`; and the sibling pairs: `neoaprs.btserial` and `neoaprs.btsdp`, `neoaprs.serialholders` and `neoaprs.serialport`, `neoaprs.serialport` and `neoaprs.btserial`, `neoaprs.serialprobe` and `neoaprs.btpaired`, `neoaprs.serialprobe` and `neoaprs.serialholders`, `neoaprs.serialprobe` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.serialholders`, `neoaprs.tnc` and `neoaprs.serialport`, `neoaprs.tnc` and `neoaprs.serialprobe`, `neoaprs.tnc` and `neoaprs.tncentry`, `neoaprs.tnc` and `neoaprs.tncsearch`, `neoaprs.tnc` and `neoaprs.tncwatchdog`, `neoaprs.tncsearch` and `neoaprs.serialport`, `neoaprs.tncsearch` and `neoaprs.serialprobe`.
* Tornado only in `neoaprs/web/`.
* pydantic only in the wire modules of `neoaprs/web/`: `neoaprs/web/beaconwire.py`, `neoaprs/web/bulletinwire.py`, `neoaprs/web/configwire.py`, `neoaprs/web/dispatch.py`, `neoaprs/web/hostwire.py`, `neoaprs/web/hubwire.py`, `neoaprs/web/mapwire.py`, `neoaprs/web/messagewire.py`, `neoaprs/web/outbound.py`, `neoaprs/web/ownwire.py`, `neoaprs/web/packetwire.py`, `neoaprs/web/portwire.py`, `neoaprs/web/prefwire.py`, `neoaprs/web/protocol.py`, `neoaprs/web/stationwire.py`, `neoaprs/web/tncwire.py`, `neoaprs/web/weatherwire.py`, `neoaprs/web/wirebase.py`.
* The desktop app's toolkits (`PIL PySide6 pystray shiboken6 webview`, the extra `app`) only in the shells: `neoaprs/desktop/qtshell.py`, `neoaprs/desktop/qtwindow.py`, `neoaprs/desktop/winshell.py`.
<!-- /doc-arch -->

No import cycle at all; every module of `neoaprs/` has a layer (a new file fails the test until you place it); nothing outside the delivery layer imports `neoaprs.web` (the page's server, a package of `neoaprs/` since it is part of what a wheel carries): only the process (`neoaprs/daemon.py`) and the commands (`neoaprs/cli/`) name it.

What each layer is for:

* **foundation**: pure code, no I/O library: time and signals; the call/SSID rules, geometry, the symbol tables, KISS framing, AX.25 frame coding, the APRS decoders (`aprsweather` reads the weather fields of a weather station's position or a positionless report into metric values), the `Packet` they produce, `packetcodec` (a packet as the row of the packet table, a time as text, the JSON of what the parser made), `message` (a message as a value, who a message is for, what text may be sent, when the next attempt is due), `bulletin` (which addressees are the message board's and a bulletin as the board keeps it), `mapstate` (the base map's files, estimate and job as plain values), `route` (how a packet reached us: the route out of the starred addresses of a path, its text, the path to send by, the count of a station's routes) and `aprsthirdparty` (the packet inside a third-party frame an iGate sent), `chain` (the delivery chain of a message we sent: its attempts, the hops of a path that a copy heard back shows used), `pref` (what the operator set for a station, as a value) `tncmode` (a KISS stream or command-mode text: the mode detector of the TNC) and `decay` (when what we send of our own accord goes out again: the specification's decay algorithm, the net cycle time of a path, the schedules of a bulletin and of a kill).
* **domain**: `stationbook` (the stations as the packets tell them: who, where, when last, the track, the latest weather; objects and items, ours marked `own`; us; the tracks and the weather the database kept are seeded at the start), `config` (the settings as one immutable value, each key checked), `ownobject` (an object or an item of ours as a value, what it must keep to be sent, and the information field it makes) and `ownbulletin` (the same for a bulletin, an announcement or a group bulletin).
* **adapters**: the world outside: the serial line and the TNC. `serialport.py` is the line on every system: any pyserial port or a `socket://host:port` URL (KISS over TCP), opened in a thread with DTR and RTS held low, read by a thread and written by a thread of its own that hand the bytes to the loop with `call_soon_threadsafe` (no descriptor is given to the loop, which Windows could not wait for); `serialholders.py` says which program has a device open (Linux, through /proc); `serialprobe.py` lists the ports of the machine (`available_ports`) and, on Linux only, searches the globs of `serial/pattern` for the radio. `source.py` is the base every feed shares (state, problem, counts, the latest lines, the back-off) and `tasks.py` the set of tasks one owner starts. `pmtilestool.py` is the pmtiles program that cuts the base map out of a big archive: found on the PATH or in the data folder's `bin/`, fetched from the pinned release of go-pmtiles (SHA-256 checked) when it is not there, and run in a thread so that it works on every event loop. The TNC has two parts of its own: `tncsearch.py` (the search for the radio among the ports) and `tncwatchdog.py` (the keep-alive: when an open line goes quiet, check that the radio is there; probe it while it is silent; reopen the port now and then).
* **persistence**: the database file on the database thread: the actor, the migrations, the settings (`store.py`, `storesql.py`); `dblog` (what the logs below share: the database they run on and the ways they ask it, each of which says no instead of raising); `packetlog` (every packet and the station cache, appended without waiting) and `packetsql` (their statements); `messagelog` (every message we sent and every one sent to us: an insert that is awaited, state updates appended, the attempts and the hops heard back of each message of ours appended; and the table `station_pref`, what the operator set for each station) and `messagesql`, `bulletinlog` (the message board: one row for each sender and slot, appended) and `bulletinsql`, `ownlog` (our own objects, items and bulletins with where each schedule stands: appended) and `ownsql`, `weatherlog` (every observation of a weather station, appended, for the trend graphs; made once from the packets already kept when it is empty) and `weathersql`.
* **services**: stateful parts above the layers below, in `neoaprs/services/`: the beacon (`services/beacon.py`: our position packet from the settings, on an interval and on request, through the Tnc; with the status report's `services/rigstatus.py` it keeps when it last sent in rows of the settings table, `services/memory.py`, so that a restart keeps the schedule), messaging (`services/messaging.py`: messages to and from other stations through the Tnc, acks, the retry schedule, the messages kept in the database; `services/inbox.py` what the Tnc hears (a message to us kept and acked, an ack or a rej settling a message, a message to another station overheard), `services/heard.py` the repeats of a message already heard and when each was last acked; `services/delivery.py` the attempts of each message and the hops heard back; the inbox, the record and the delivery chain are parts of messaging, which makes them) the message board (`services/bulletins.py`: the bulletins, announcements, group bulletins and group messages the inbox hands over, one for each sender and slot, kept until the operator deletes it), our own objects and bulletins (`services/ownobjects.py` and `services/ownbulletins.py`: made, changed and killed or posted and deleted by the operator, kept in the database and sent on the specification's schedules; both are `services/repeater.py`'s ticker and send through `services/sender.py`, which holds back everything while the call is not set or the radio is not usable and puts a pause between two frames of ours), the queries (`services/queries.py`: the answers to `?APRSP`, `?APRSS`, `?APRSD`, `?APRST`, `?PING?` and `?APRS?`, through the beacon's frames, by the asker's path), the fill-in digipeater (`services/digipeater.py`: a packet whose first unused hop is `WIDE1-1` or our call is sent again with our call as a used hop, when `digi/enabled` is on) and the preferences of the stations (`services/prefbook.py`, the path and the timeout of each station, which messaging is given as its `paths`).
* **app**: the composition root: `app.py` makes the parts, `controller.py` is the object of the parts and brings them up and down; `wiring.py` connects the signals and says how the settings become the Tnc's.
* **delivery**: `neoaprs/web/*` (Tornado, the pydantic wire models in `neoaprs/web/*wire.py`, the state hub and its topics, the commands, `neoaprs/web/processmeter.py` (what the daemon costs the machine, for the status); `neoaprs/web/topics.py` is the one place that connects the daemon's signals to the page, so it is a composition root too; the wire format is `PROTOCOL.md`) `neoaprs/cli/` (the `neoaprs` command: `service` sets the daemon up to start at login with the system's own means, `doctor` checks the computer, `db`, `map`, `replay` and `capture` are tools of the command; `neoaprs/cli/neoaprs.service` is the unit's template, package data), `neoaprs/desktop/` (the desktop app, `neoaprs app` and `neoaprs-app`: the page of the daemon in a window and a tray icon; `cmd.py` runs it, `session.py` attaches to the daemon of the data folder or starts one with the code of `neoaprs open`, `menu.py` is the tray menu as data and what it does, `links.py` decides which addresses stay in the window, `autostart.py`, `single.py` and `appstate.py` are start at sign-in, the one-app lock and what the app remembers; the toolkits are imported by `qtshell.py`/`qtwindow.py` (Qt, Linux and macOS) and `winshell.py` (pywebview and pystray, Windows) and by nothing else, `TOOLKIT_HOMES` in the test; the Qt shell connects Qt's own signals, so it is a place for `connect` too), `neoaprs/daemon.py`, the process, which names `neoaprs.web.server.WebServer` as the controller's page, and `neoaprs/__main__.py`, which is `python -m neoaprs`: the command. Each package of the delivery layer is that layer whole (`DELIVERY_PACKAGES` in the test): a new module of `neoaprs/web/`, `neoaprs/cli/` or `neoaprs/desktop/` needs no entry in `LAYERS`. The commands may import every layer, and the one place of them that builds a service is `neoaprs/cli/mapcmd.py` (the base map's command line); `neoaprs/cli/capturecmd.py` is a composition root of its own, for the one serial port it wires to a file.

## The composition root

`neoaprs/app.py` (`Services`) makes the parts and holds them under the names the page and the tests know: the data directory, the clock, the settings (`config`, one immutable value the controller reads at its start), the `Store` (`store`), the radio (`tnc`),
the station book (`stationbook`), the beacon (`beacon`, a service), the status report (`rigstatus`, a service: it reads rigctld through `neoaprs/rigctld.py`, and `queries` is given its `status_frame`), the message alert (`alerts`, a service: messaging is given its `alert`), the preferences of the stations (`prefbook`, a service: messaging is given its `path_for`, the prune its `never_hidden`), the message board (`bulletins`, a service, and its log `bulletinlog`: messaging is given its `heard`), our own objects and bulletins (`ownobjects` and `ownbulletins`, services, with their log `ownlog` and the `sender` they share: `ownobjects` is given `_is_station`, which says whether a name is a station's), messaging (`messaging`, a service) and the message log (`messagelog`), the weather log (`weatherlog`), the queries (`queries`, a service), the fill-in digipeater (`digipeater`, a service: it repeats a packet that asks for WIDE1-1 or for our call, when `digi/enabled` is on), the base map (`mapfetch`, a service: the detailed map round our position and the world map under it, made on request from the page with the pmtiles tool of `neoaprs/pmtilestool.py`), the update check (`updatecheck`, a service: once a day it asks the version page, through the request of `neoaprs/updatefetch.py`, which version is the latest, and keeps it only if it is newer than ours; the page's status message carries it; `neoaprs/versions.py` has the comparison and the reading of the answer; `check_now` is the same question on request, the Settings tab's Check now), how this copy was installed (`install`, worked out by the process in `neoaprs/cli/installkind.py` and given to the controller; the page's `hello` carries it, so that the page can say how to update), the packet log (`packetlog`), the `TaskSet` (`tasks`), the `Db` (`db`) once it is open, the serial port given for this run only (`port_override`, from `--port`; never stored), the globs the search listens to for this run only (`pattern_override`, used by the tests instead of `serial/pattern`), the signal that every save of the settings emits (`config_changed`) and the page's server (`web`), which the controller makes, once the settings are read, from the factory the process gave it (`Controller(web=WebServer)`: this layer does not import `neoaprs/web/`, it knows a `Frontend` that starts and stops).
`neoaprs/wiring.py` connects them: what the Tnc hears goes to the packet log, the station book, the weather log, messaging (which answers a message to us with an ack and hands bulletins to the board), the queries and our objects (which stop when another station reports one), our objects go to the station book as stations of their own (`own`), what the book changes or removes goes to the station cache in the database, and the port a search found is stored as `serial/last_port` and tried first next time;
`tnc_settings` is how the settings become the Tnc's port, speed and KISS entry. `neoaprs/controller.py` (`Controller`, which extends `Services`) is the start and the stop: `start()` makes the data folder, opens the database (the thread opens and migrates the file and gives it
to the `Store`, the packet log, the message log, the bulletin log, the log of our own objects and bulletins and the weather log), reads the settings, seeds the station book from the station cache, puts our own station in it, rebuilds the tracks from the latest position packets, makes the weather log from the packets kept if it is empty and gives the stations their latest weather, starts the message board (it takes the bulletins from the database), then the Tnc **in a task** (finding the port can take 20 s a port, and nothing waits for it), then the beacon (its timer waits 30 s before the first one), then our objects and bulletins (they take theirs from the database, our objects into the station book, and their tickers wait for the radio), then the preferences of the stations (read from the database), then messaging (it takes the latest messages from the database and starts its retry ticker), then the page's server (a port in use is logged and the daemon goes on without the page) and the daily prune task
(packets, weather observations and stations older than 7 days; messages and bulletins are never pruned); `stop()` ends the page's server, a map job, the queries, messaging, our bulletins and objects, the message board, the beacon, the Tnc, the tasks, then closes the database, doing what was asked of its thread first; `save_config(Config)` stores the settings, puts them in force, tells the beacon (a changed interval counts at once) and restarts the Tnc when its port, speed or KISS entry changed.

A part gets what it needs as constructor arguments (objects of a lower layer, Protocols or plain callables), never a back-reference. The services (`neoaprs/services/`) are built by the composition root only (`SERVICE_BUILDERS` in the test).

## The database actor

`neoaprs/db.py` is the only way to the file: ONE connection owned by ONE thread, and every statement of the program an operation on that thread's queue (`neoaprs/dbthread.py`). Read its docstring; the guarantees, in one line each:

* **Order**: the queue is FIFO and there is one thread, so a read sees every write asked before it and nobody flushes or locks anything.
* **Transactions**: a write is `BEGIN IMMEDIATE` ... `COMMIT`, `ROLLBACK` when the function raises, and the error reaches the caller as it was raised; a function may not begin a transaction or ask the `Db` for anything (`NestedUse`).
* **Durable**: what `await db.write(...)` returned has been committed with `synchronous=FULL` (`neoaprs/dbfile.py`): the answer comes after the disk has it.
* **Appends** (`write_nowait`): the hot path of the packet log (`neoaprs/packetlog.py`): nobody waits, they are collected for a tick and committed as one transaction, bounded, the newest dropped and counted beyond the bound.
* **Shutdown**: `close()` does what was queued, closes the connection and ends the thread; a write is never withdrawn once it is on the queue.
* **Measured**: `stats()` gives the queue wait, the run time and the stall of the event loop as numbers.

The file is versioned and migrated by `neoaprs/migrations.py` before the thread uses it (`open_connection` in `neoaprs/dbopen.py`); a file of a newer version, or one that is not a database, is refused with a reason, the daemon ends with exit code 2, and the unit does not restart on that code.

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
| `neoaprs/walcare.py` | the minute's care of the write-ahead log: a function of the connection, run by the thread |
| `neoaprs/weathersql.py` | the statements of the weather table (every observation of every weather station) and the read of the packets it is made from: functions of a connection that the thread runs |
<!-- /doc-arch -->

And what else touches SQL (`SQL_ELSEWHERE`; the numbers are exact and the list only shrinks):

<!-- doc-arch:sql_elsewhere -->
| file (`SQL_ELSEWHERE`) | imports `sqlite3` | calls of `execute` | why |
| --- | --- | --- | --- |
| - | - | - | no file outside the homes touches SQL |
<!-- /doc-arch -->

## The ratchets

The limits: a module of `neoaprs/` (the page's server and the commands are in it) has at most 400 lines, a class 300, a function 60, and a function has a cyclomatic complexity of at most 12. `tests/test_size_ratchet.py` measures them (`tests/support/codemap.py`); what is over a limit is
listed in `tests/size_baseline.json` with its current size as its ceiling, and the list only turns one way: new code is under the limits from its first commit, a listed unit never grows, one that shrank lowers its ceiling
(`python -m tests.support.codemap --tighten`) and one that is within the limit again leaves the list. The baseline is empty.

Duplicated code is a ratchet too, in two halves. The Python half is `scripts/dup-check` (the stage `dup-py`): jscpd over `neoaprs/` and `tests/support/`, clones of at least 10 lines and
100 tokens, compared with `scripts/dup-baseline.json` by the pair of files a clone joins; a new pair, a larger one or more duplicated lines in all fail, and `scripts/dup-check --update` only tightens the baseline.
It is empty: the Python tree has no clone at those limits. The page's half is the stage `dup` (`ui/.jscpd.json`: 5 lines, 50 tokens, at most 3 % over `ui/src`, the tests and the generated protocol left out).

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
