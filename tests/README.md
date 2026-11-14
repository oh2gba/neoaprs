# The tests

`scripts/check` runs everything; `.venv/bin/pytest -q tests/test_x.py` runs one file; `-m unit`, `-m integration`, `-m safety` pick a kind. `asyncio_mode = auto`: an `async def test_*` just works.

## What is here

* `test_architecture.py`, `test_size_ratchet.py`: the layers and the size limits (`docs/ARCHITECTURE.md`), and the list of the modules that start a program, run a shell line, open a URL or hand a string to pyserial (`REACHES_OUT`); each rule is shown failing on a made-up tree.
* `test_docs.py`, `test_hygiene.py`: the documents (the index, the names they put in backticks, the manual's short paragraphs, no code names and no version number in it, the
  generated tables of the architecture and of the settings), the scripts and units tables (the unit is `neoaprs/cli/neoaprs.service`), `.gitignore`.
* `test_changelog_brief.py`: the changelog is brief (`CONVENTIONS.md`, "Documents, scripts, units"): what is under `## Unreleased` of `CHANGELOG.md`, and the section of every release after 0.18.2, is at most one summary sentence and then one line for each change, none over 25 words (the number and the release are checked against the ones `CONVENTIONS.md` names) and none naming a path into the source tree, a file of code, a module, a test, a document for developers or work a user cannot see (a refactoring, the checkers); the older sections are not read. `scripts/release` writes the version over `## Unreleased` before its gate, so the test also runs that step of the script on a made-up changelog and holds that the notes are read under the new heading, and that the section `scripts/release-notes.py` finds for a version is one the rule reads. Each rule is shown failing on a made-up section.
* `test_timelimit.py`: the time limit of a test (`support/timelimit.py`, `NEOAPRS_TEST_LIMIT_SEC`) on pytest run over test files of its own: a test that hangs ends the run with its name and the stack of every thread, one inside its limit passes, 0 is no limit.
* `test_winloop.py`: the event loop of the tests (`tests/support/winloop.py`, the hook `pytest_asyncio_loop_factories` of `conftest.py`): asyncio's own everywhere but on Windows, where a thread posts an empty packet to the loop's completion port a few times a second; an answer from another thread reaches a loop whose reader of the self pipe is dead (the state a worker of the suite hung in on Windows 11), a closed loop is not nudged, and an idle one is not kept busy.
* `test_support_files.py`: the reading of a file that a program is still writing (`support/files.py`): a missing or refused file is not ready, the text is waited for until it is whole, the loop goes on while it is.
* `test_lint_scope.py`: what ruff reads: every tool of `scripts/`, `packaging/`, `server/` and `systemd/` that begins with a python line and has no `.py` in its name is in `extend-include` of `pyproject.toml`, and the list names nothing else; shown failing on a made-up folder.
* `test_check_script.py` (POSIX only): the runner of `scripts/check` on a copy of the script with stand-ins for its stages (`NEOAPRS_CHECK_STAGES`, which the script of a tree refuses): result lines in list order, lock alone first and smoke alone last with the rest at once between them, a failing stage stops nothing and its output (even one without a final line end) is under its line, exit codes, --serial, --stage, --list, ui/node_modules installed once, an interrupted run (TERM, INT, HUP) ending what its stages started; and the real command lines of mypy, architecture, pytest, ui-tests, page, security, audit, lock and smoke against made-up python, npx and uv; the copy runs without any UV_* variable of the caller's environment (the CI's setup-uv sets some), and the file is collected on Windows too, so it names no POSIX-only name outside a function.
* `test_security_check.py` (POSIX only): the security checks (`scripts/security-check`) and the fetching of their programs (`scripts/security-tools`) with stand-ins where the script looks (the tools in a build cache of the test's own, `php` and `docker` first on the PATH) in a made-up git tree that every git command names: a finding fails with its place, the baseline lets a known finding pass and nothing beside it, an entry needs its reason, `--update` never grows unasked, a program that is not there fails with the sentence that says how to get it, the audit runs only with its flag; a file or folder named `.secrets` or `.secrets` with anything after it fails when git tracks it or does not ignore it and is never opened; the check `tokens`, with the real git, finds a made-up access token of the secrets manager wherever a push would carry it (a lock file, a picture, a binary file, a commit's message, a merge's resolution, a tag's message, another local branch, the index after the file was changed back, a file's name) whatever the developer's git settings say, reads only what the remote does not have unless `--all-history`, counts only the lines a commit adds unless `--all-history`, and never prints it; gitleaks is shown the messages and what is changed or staged and no file git does not track, and every run shows it a made-up token and fails when the rule of `.gitleaks.toml` does not find it; Psalm runs in the pinned php image where php lacks its extensions and fails where neither way is there; a settings file of shellcheck or zizmor and a `disable` comment without its reason are findings; the pins, GitHub's hosts only, and a fetch from a fake server (a wrong digest thrown away, a broken transfer tried again).
* `test_check_in_container.py` (POSIX only): the container the size of GitHub's runner (`scripts/check-in-container`, `packaging/ci/Dockerfile`) as far as it goes without docker: the threads a run takes from made-up lists of siblings (cores of two threads, cores without siblings, fewer cores than asked, cores other runs hold), the files that go in from a made-up repository (tracked, untracked, deleted, tracked though ignored, a repository inside it, a folder that is a link now; never what an ignore rule names, a private key among it, and never a file of access tokens whatever git says of it), what is refused in one sentence before docker is asked for anything (a folder that is no repository or lies inside one, a file that cannot be read, a folder that cannot be entered or that git cannot list), the tar and the shell text that unpacks it, run with bash, tar and git as they run inside (and leaving alone a repository the environment names), the command line for docker (the CPU set, the memory with no swap, no name, no port, no mount of the tree, no variable of this machine, no question to a registry), the script from end to end on a stand-in for docker (the build of a missing image, the exit code passed on, a signal that removes the container, nothing left in its temporary folder or where it was started), and that the default commands, the libraries and the Python of the image are those of the job `python` of `ci.yml`. Every git command of the file names its made-up repository (`git -C`), with no GIT_ variable and no configuration of the user's; every scratch folder is in the temporary folder, and the file fails plainly when that one resolves into the repository (set `TMPDIR`).
* `test_check_windows.py` (POSIX only): the check on a real Windows (`scripts/check-windows`) as far as it goes without the machine: the environment and what it refuses (no machine: "not set up" with the variables named; a port, a user or a name that ssh or VBoxManage would read as something else), the ssh and scp command lines (a key or a known_hosts file with a space), the PowerShell of each step with names that have quotes (the typographic ones too), spaces and dollar signs in them and the commands compared with `ci.yml`, the choice about power for a machine that is off, running or started by this run, the lock, the folders of old runs, the result lines and the exit code, the pinned zip of uv, and the script from end to end over a made-up repository against stand-ins for `ssh`, `scp` and `VBoxManage` first on the PATH (the tree that goes over keeps what an ignore rule names and every file of access tokens; a failed step is printed under its line and stops none but sync; the machine is shut down only by the run that started it; the console that the probe chooses). The machine itself, its SSH, `tar.exe` and PowerShell are tried by hand.
* `test_deploy_script.py` (POSIX only): `server/deploy.sh` in a made-up repository with a stand-in for the secrets manager and one for curl first on the PATH: what goes up is what git tracks of the folders it sends (never an untracked, an ignored or a deleted file), the ones skipped are named once on stderr, `--list` shows the same and starts no curl, the version page alone is sent without `--site`, a tracked link, submodule or name with a line end or a tab stops it, and a folder that is no checkout or an untracked file of the version page stops it with exit code 2 before the network. Every git command names its repository (`git -C`) and has no configuration of the user's.
* `test_site_check.py` (POSIX only): `scripts/site-check` against a web server of this computer in the host's place and a made-up repository: the page as committed (the last commit, not the disk) passes; a changed, a missing and a moved file, a private place that is not 403 (support files, PHP settings, the version page's logs of this month and the last, a tracked hidden file or helper under `server/neo/`) are findings; an endpoint, an uncommitted file on the server and an untracked local one are not asked; only GET is sent; an address that is not https (this computer's excepted), has a path or does not answer is exit code 2.
* `test_httpthread.py`: `support/httpthread.py`: the listening socket of a test's small HTTP server has a time limit, the connections it hands out have none, and a shutdown ends.
* `test_flaky.py` (POSIX only): the hunt for tests that fail on some runs only (`scripts/flaky`, the stage `flaky`) without docker: the four settings the runs go round, the command inside the container, what the log of a run says (the tests that failed with their first line, a run that did not reach the tests, the stack of a run that hung), the table, and the script from end to end on a stand-in for docker that answers each run by rules (settings, a hung run, a failed install, no image, no docker); and the plugin that puts the tests in a seed's order (`support/shuffle.py`) on pytest run over files of its own.
* `test_ci_workflow.py`: `.github/workflows/ci.yml` and `audit.yml` read as text: the Linux job's steps are the stages of `scripts/check` in the order of the container's list, Windows runs the commands with `--dist loadgroup`, `tests/test_package.py` and `tests/test_desktop_qt.py` are `xdist_group`s, the page job runs the page test, the simulation job's Mercury is cached under a key of what the build reads and built only on a miss, and the weekly audit is a workflow of its own that publishes nothing.
* `test_check_installs.py` (POSIX only): the clean installs in Docker (`scripts/check-installs`, `scripts/install-probe.py`): that the .deb check holds what the release's job `deb` holds, the builds and the containers from stand-ins for docker, uv and the build scripts (what each container is mounted and given, a failed container or build, no Mercury, no pin, a cached file that is not the pinned one), the pin and its checksum, and the probe of the upgrade run for real against this tree's daemon (seed, verify, a version that is not the daemon's).
* `test_tnc.py`: the TNC source on a fake radio (a TCP server on the loopback): the live capture decodes, a TNC found in command mode is switched to KISS, the
  check when a line opens, the reopen of a line that was lost, a port given as `tcp://`, the keep-alive that a TCP KISS profile does not have, no search where
  the ports are not searched, sending, the mode detector and its re-arm, and the keep-alive (a quiet line gets the check after `check_sec`, with the exit frame,
  the carriage return and KISS ON in order and nothing sent meanwhile; a `cmd:` answer keeps it connected and tells nothing; no answer makes it silent with one
  warning; no check while packets or noise flow; `check_sec` 0, a new period, enter KISS off; a stop in any step leaves nothing running; a lost line starts the
  quiet period over).
* `test_tncprofile.py`: the TNC profiles (`neoaprs/tncprofile.py`): the table and the strings of each, the entry written step by step with its pauses (the
  TM-D710's five steps, the Kantronics, the TNC-2's one), the keep-alive check that enters again with the whole sequence, the `kiss` and `kiss-tcp` profiles
  that are sent nothing but KISS frames (no entry, no check, no carriage return, no silent state, not in the search of the ports either), and the settings that
  make the port: `tcp/host` and `tcp/port`, the `tnc/enter_kiss` row.
* `test_tnc_pty.py` (POSIX only): the search for the radio among device files, on pseudo-terminal pairs behind the globs of a pattern: the probe picks the port
  that sends KISS frames, skips one it cannot open or that another program holds or that is on the skip list, takes a TNC in command mode, sends the carriage
  return, ends with a stop, the fall back from a named port, a device file that vanishes and comes back, and the settings' pattern, the remembered port and the
  search after a remembered port is gone with the whole daemon.
* `test_tnc_failures.py`: the Tnc on a line in memory and a skipped clock: an open that is refused or raises what nobody listed, the retry after the back-off, a stop while the retry opens, bytes and a loss from a port that is
  no longer the Tnc's, a write that fails, the KISS entry's steps and the port's failed write, and the repeats of the KISS entry that wait 10, 20, 40 and 60 s.
* `test_tncwatchdog.py`: the keep-alive's schedule (`neoaprs/tncwatchdog.py`) on a Tnc that is a record of what it was asked and a skipped clock: the quiet period, the check's steps, every exit of a check (no line, a write refused, a line replaced between two steps), the silent
  radio's probes and the reopen of every fifth, a Tnc that is not connected.
* `test_worldcmd.py`: `neoaprs map --world` cutting the made-up planet from a range server: the build, source and zoom, the 8 MB refusal before a tile is fetched, a failed run. `test_selfreplace.py`, `test_servicelaunchd.py`, `test_opencmd_platforms.py`,
  `test_rigctld.py`, `test_aprsmiceout.py`, `test_support_gather.py`, `test_cli_small.py`: the branches of the small pieces that the larger tests do not reach (the Windows and macOS paths with the platform said and the system's calls faked, a server that answers badly, the
  system named on each system, the hooks for what nothing caught).
* `test_silent.py`: the silent radio: a check that nothing answers makes the Tnc silent (the describe text, the lines, the log), command-mode text, a KISS frame
  or other bytes while silent end it cleanly (KISS entered afresh once for every answer, `usable` False until the settle has passed, one INFO line), the probes
  (answered at the return, answered after KISS ON, a hundred unanswered ones with one WARNING and no INFO, every 5th reopening the port and the silence kept
  across it, a lost line; the failed reopen falling to the search is in `test_tnc_pty.py`), a stop while probing leaves nothing running, a beacon due in the
  night written only after the settle as a KISS frame, and `beacon_now` and `send_message` refused over the socket with the reason; the senders' own cases are
  in `test_beacon.py`, `test_rigstatus.py`, `test_queries.py` and `test_messaging.py`.
* `test_kiss.py`, `test_ax25.py`, `test_callsign.py`, `test_geo.py`, `test_symbols.py`, `test_aprsposition.py`, `test_aprsmice.py`, `test_aprsmessage.py`,
  `test_aprsparse.py`, `test_aprsweather.py`, `test_packet.py`: the protocol stack, from the bytes of the line to the `Packet` (the parser against
  `fixtures/aprs/cases.json`, the real weather reports among them; `test_aprsweather.py` the conversions to metric, where the fields end and the comment begins,
  what is missing, the summary line and whose weather a packet is; `test_aprsfreq.py` the frequency specification (the fields of a voice frequency at the start of a comment, the object name that is a frequency, what stays text) and `test_aprsstorm.py` the
  storm data in units of the program; the signpost's braces are in `test_aprsextension.py`),
* `test_alerts_runner.py`, `test_dbcmd.py`, `test_capturecmd.py`, `test_replaypty.py`, `test_durable.py`, `test_appstate.py`, `test_addresses.py`: the ways a
  run goes wrong that the tests with real commands and processes do not reach, in the test's own process: the alert command's Windows path and its failures,
  kills and timeouts on a fake `subprocess`; `neoaprs db` on a database that is not one, an older or a newer one; `neoaprs capture` choosing a port, losing it,
  not opening it; the replay's pseudo-terminal; a folder that cannot be synced; the app's size file and log; the LAN address.
* `test_windows_program.py`: the programs started by the daemon on Windows (powershell, taskkill, explorer) are run by their full path under the system folder, never by a bare name.
* `test_allowed_hosts.py`: `web/allowed_hosts` is host names (labels of letters, digits, hyphens and underscores, at most 253 characters), IPv4 and IPv6 addresses (brackets or none) separated by commas, else `setting.not_host`; a stored value that is refused now falling to the default.
* `test_port_address.py`: the address of a port (`serial/port`, `serial/last_port`, `gps/device`): a device path or `socket://`, `tcp://`, `bt://`, `ble://` and no other scheme pyserial knows (`spy://` writes a file), refused in the setting and again where the port is made, no file made, a stored value that is refused now falling to the default.
* `test_settings_reach.py`: for every setting whose text ends in a path, a URL, a port or a command line, no generated text passes its check and is misread where it ends; a setting in no table that takes a hostile text fails it, so a new one is found.
* `test_serialport.py`, `test_serialport_pty.py`: the serial line (`neoaprs/serialport.py`, `serialprobe.py`, `serialholders.py`). The first on the fake radio
  and on stand-ins for pyserial's object, so it runs on every system: reading and writing through the threads, 8N1 with DTR and RTS set low as soon as the open allows,
  `tcp://` for `socket://`, the open in a thread and cancelled, a connection refused, Windows's access denied as in use by another program, a line that dies
  (read, write, stuck write), the list of ports, the probe of several ports at once (nudge, skip list, dying ports, cancellation) and the guard. The second
  (POSIX only) on a pseudo-terminal as a device file: pyserial's lock, a device that goes away, the holders in /proc, the globs.
* `test_route.py`: how a packet reached us (`neoaprs/route.py`): the route of the real paths (`OH2RCH-2*`, `OH2RCH-3*,TRACE2-1`, `WIDE1*,OH2RCH-2*,WIDE2-2`,
  `OH2RCH-1*,OH2RCH-3*`, `WIDE1,OH2RCH-2*`), the aliases, the text, the path to send by, the count of the routes of a station (the best one, ties, the bound of
  8) a third-party route that is never the best and the time of the latest direct packet.
* `test_config.py`, `test_stationbook.py`: the settings (each key checked, a wrong value falls back and is told) and the station book (the capture's packets and
  made-up ones: positions, the track, objects and items, us, pruning, and the stations a prune is told to keep; the latest weather of a station; the tracks made
  again from the positions the database kept: the rule of a live track, the latest 50, our own station left out).
* `test_aprsisline.py`, `test_internet_gate.py`, `test_internet_services.py`, `test_station_channels.py`, `test_migration_via.py`: how a packet reached us (`Packet.via`: rf, rf-gated, is, dummy). The parser of a line of APRS-IS (real-looking lines with qAC, qAS, qAR, qAO, qAU, qAX, qAI, Mic-E bytes, a third-party packet inside, the server's comments and the lines that are none); the one gate for packets from the internet (the handlers of both signals and every part with a method that takes a `Packet` are walked and held to `SEEN_BY_ALL` and `ON_AIR_ONLY`, a whole daemon handed packets that would each make it transmit transmits nothing, `GATEABLE`, the Dummy radio going everywhere the radio goes, a restart); each acting service handed the same packet with only the channel changed; the station book by channel (counts, times, position channel, routes of the radio only, objects, our own call, the row for the page); and migration 21.
* `test_packetlog.py`: the packet log and the station cache on a real database thread: what goes in comes out equal, the order, pruning, the rows the tables refuse (each named check).
* `test_wiring.py`, `test_controller.py`: the whole daemon on a fake radio (`support/env.py`): the capture fills the database and the book, a restart finds the
  stations, the cable pulled and put back, pruning, a change of the port in the settings restarts the Tnc (the search and the port it found being remembered are
  in `test_tnc_pty.py`).
* `test_restart_schedule.py`: the beacon and the status report across a restart (`neoaprs/services/memory.py`): the rows `beacon/last_sent_at`,
  `status/last_sent_at` and `status/last_text` in a real Store on a temporary database, a fixed clock and a stub Tnc (a start inside the interval, after it,
  with no row or a bad one, a request, a changed interval; a status restart inside the interval, after it with the same and another text, from the radio), and a
  whole daemon started twice on one data folder.
* `test_beacon.py`, `test_beacon_wiring.py`: the beacon (`neoaprs/services/beacon.py`) on a stub Tnc and a clock the test holds (the exact bytes of the frame,
  the status frame it makes for a text and its time stamp, no status after the beacon, rounding, the PHG extension (the power, height, gain and directivity
  codes, the specification's example, no PHG without a power) and DAO (the digits for known positions, a carry, the order PHG - comment - DAO, none in the
  compressed form), the compressed form read back within a metre, the first delay, the interval, the skip while the TNC is not connected, a changed interval,
  `send_now`), and inside the whole daemon on the pseudo-terminal radio (the KISS frame on the line, the `out` packet in the log, the book not taking it, an
  echo moving only `last_heard`, the cable pulled, the controller starting and stopping it).
* `test_gpsfix.py`, `test_smartbeacon.py`, `test_aprsposition_compressed.py`: the pure code of a moving station. A GPS fix from NMEA sentences (the checksummed RMC and GGA of the NMEA documentation, a stream that
  puts the GGA's altitude and satellites into the RMC's fix, a sentence without a fix clearing it, a damaged one counted) and from gpsd's TPV and SKY reports; SmartBeaconing (the rate at the speeds on both sides of
  each limit, the turn threshold, the smaller angle across north, the turn time, no turn at the slow speed, the start and the request, a made-up drive); and the compressed position byte for byte against the
  specification's worked example, read back by the module's own decoder, with the altitude and the cut comment.
* `test_gpsfeed.py`, `test_gps_service.py`, `test_beacon_mobile.py`, `test_gps_wiring.py`: the GPS and the mobile beacon. The feed on a fake gpsd and a TCP serial server (`support/gps.py`): the watch request, the fixes
  and satellites, a receiver without a fix, the reconnection, bytes cut into lines; the service (the states from `off` to `stale`, `moved`, the feed started again when the settings change); the beacon on a stub Tnc, a
  stand-in for the GPS and a clock the test holds (the exact bytes, the start, the time at three speeds, a turn, no fix and a stale one meaning no beacon, a request, a radio that is away, `?APRSP`); and inside the
  whole daemon (the book and the distances following, the ALOHA circle, the topic `gps`).
* `test_gpsreplay.py`: `neoaprs gps-replay`: the drive (the stop, the corners, the laps), the fake gpsd, the daemon's feed, GPS service and beacon on the drive, and the command as a process.
* `test_igaterules.py`, `test_aprsis.py`, `test_igate_service.py`, `test_igate_wiring.py`, `test_config_igate.py`: the receive-only iGate. The rules of the specification as a table (every rule with the packet that breaks it, the line that comes out, a third-party packet opened and judged again), the connection on a fake APRS-IS (`support/fakeaprsis.py`: the greeting, `# logresp` verified and unverified, a server that is not APRS-IS or says nothing, the keep-alive, the write queue, the reconnection), the service on that connection (`support/igateworld.py`: the counts by reason, duplicates, our position, the log and the hour line, no password in any line), the whole daemon with a replayed capture (nothing the server sends reaches the radio), and the settings. `support/guards.py` refuses the real APRS-IS (the names of its servers and the ports 14580, 10152 and 10151).
* `test_weatherlog.py`, `test_weather.py`: the weather log on a real database thread (the row both ways, only weather heard is kept, the series of a station
  from a time, the latest of each, the care, the extremes the fields can say, the log made from the packets kept: a third-party packet is the sender inside,
  what is older than the days kept, what we sent and what is no weather are left out) and the weather through the whole daemon (a report on the air reaches the
  book, the log and the page; the log made at the start only when empty; `weather_series` over the socket, every wrong command an error; the tracks of the
  packet table back after a restart: 60 positions give 50 points, objects and third-party packets by their own names, our own station none).
* `test_bulletin.py`, `test_bulletinlog.py`, `test_bulletins.py`: the message board. Which addressees are the board's, and that a record has no lifetime
  (`neoaprs/bulletin.py`); the log on a real database thread (the round trip, one row for a sender and slot, the delete, a row this program did not write left
  out); the service (`neoaprs/services/bulletins.py`) on a real log and a clock the test holds (one entry for a sender and slot, a text replaced and the count
  started again, the same text counted and the copies within 10 seconds one hearing, a third-party bulletin from the sender inside, nothing aging out after a
  year, a restart that finds the whole board, no bound of size, the delete and a bulletin sent again after it being new).
* `test_decay.py`, `test_ownobject.py`, `test_ownbulletin.py`: what we send of our own accord, without I/O. The schedules (`neoaprs/decay.py`: the hops a path
  asks for, the net cycle time of 10, 20 and 30 minutes, the decay of an object from a minute up to it, the three kill sends, the plans of a bulletin and of an
  announcement second by second); an object and an item (`neoaprs/ownobject.py`) byte for byte as chapter 11 of the specification shows them
  (`;LEADER   *092345z4903.50N/07201.75W>088/036`, `)BRENDA!4903.50N\07201.75W@088/036`), the killed form, the time stamp of the moment of sending, the position
  rounded, the course and speed, the comment limits, read back by our own parser, the names and values that are refused; a bulletin, an announcement and a group
  bulletin (`neoaprs/ownbulletin.py`) as chapter 14 shows them (`:BLN3     :Snow expected in Tampa RSN`, `:BLN4WX   :Stand by your snowplows`), read back as a
  message to a slot of the board, the slots and texts that are refused.
* `test_ownlog.py`, `test_stationbook_own.py`, `test_ownobjects.py`, `test_ownbulletins.py`, `test_own_wiring.py`, `test_migration_own.py`: our own objects and
  bulletins (`neoaprs/services/ownobjects.py`, `neoaprs/services/ownbulletins.py`, `neoaprs/services/sender.py`) on a stub Tnc (`support/stubtnc.py`), a real
  log and a clock the test holds (the log on a real database thread: the round trip, one row for a name and a slot, the delete, a row this program did not write
  left out; our objects in the station book: marked `own`, reported by us, never pruned, forgotten or given a track, replaced by what another station reports
  under the name, untouched by another station's kill; the offsets of every packet of the schedule for each path and kind, a change that starts the decay again
  and never within a minute of the last packet, the same values changing nothing, the kill sent three times and then forgotten and one that never went out
  removed at once, the interlock, the radio that is away and one packet when it is back however many were missed, the pause between two frames, a frame that
  cannot be made told once, the limits, a restart that goes on where the schedule stopped and an ended bulletin staying ended, another station taking an object
  over and a copy of ours coming back doing nothing); inside the whole daemon on the fake radio (the KISS frame, the object on the map as ours and not in the
  station cache, a digipeater's copy making no second object or board entry, a takeover, another station's kill leaving ours, a restart, the commands and the
  topics of the page); and the migration that makes the two tables (a database of the version before keeps everything, the checks of each column, a step that
  doubts changes nothing).
* `test_rigstatus.py`: the status report (`neoaprs/services/rigstatus.py`) on a stub Tnc, the real beacon, a fake rigctld on a free port (`support/fakes.py`)
  and a clock the test holds: the first status after the first poll, nothing inside the interval, after it a change sends and no change does not, a change
  within a kilohertz is none, the radio off (`RPRT -5`, a refused connection, no answer, nonsense) sends nothing and the log says so once, the template and its
  cut, the static text under the same rule, the Tnc away or refusing, `?APRSS` with the text last sent, the timer, and the `status` message of the page
  (`station_status`, `rig_state`) in the whole daemon.
* `test_status_now.py`: where the status comes from (`status/source`, and what it is while empty), and Send status now (`RigStatus.send_now`, the command
  `status_now`): inside the interval, with the radio, with the interlock, the Tnc and the length, and the reasons it gives.
* `test_versions.py`, `test_updatefetch.py`, `test_updatecheck.py`, `test_version_page.py`: the update check. The rules without I/O (which version is newer,
  what the answer of the version page means, the name of the platform); the request (`neoaprs/updatefetch.py`) against a fake version page on the loopback
  (`support/fakeversionpage.py`): the query and the User-Agent carry the version and the platform and nothing else, a page that says no, hangs or sends too much
  is none; the service (`neoaprs/services/updatecheck.py`) with a stub page: the first question and the daily ones, a newer version kept, the same or an older
  one and a failed question not, the setting and `NEOAPRS_UPDATE_CHECK` switching it off, and through the whole daemon to the `status` message of a page; and
  `server/version.php` under PHP's own web server (skipped without `php`) with a fake GitHub: the answer, the log line, the status hand-off (none for the id 0), the hour of the
  cache and the last good answer kept while GitHub fails, the note in `message.txt`. Every other test runs with the check off.
* `test_notcounted.py`: the developers' own runs are not counted: the update check sends `id=0` from a run of the source tree (a clone that simulates another kind too) and while the row `update/not_counted` is true (and no other kind of install does), keeps and gives back the installation's number, no other request to the project's server carries an id, `neoaprs db` sets and reads the row and prints the number of the installation.
* `test_usage_report.py` (POSIX only): `server/usage-report.sh --local` on made-up logs: id 0 and the ignore list left out of every count and said in a line each, the old lines without an id, a list with a byte-order mark, no logs at all, and the logs of the present and the fixed version page.
* `test_updateasset.py`, `test_updatedownload.py`, `test_selfupdate.py`, `test_selfinstall.py`, `test_selfupdate_wire.py`: Update now. The file of the release for
  each kind and architecture, its address built from the announced version alone and the hosts a download may go to, the line of SHA256SUMS; the downloads
  with a stand-in opener (progress, cancel, a file cut short or too large, a redirect away from GitHub); the job with a fake release and installer
  (`support/fakerelease.py`, its SHA256SUMS signed with a key the test makes): the steps, a SHA-256 that is wrong or missing from the signed SHA256SUMS, a cancel, the refusals, no restart; the Windows installer's command
  line (built, never run) and the AppImage renamed over the old one on temporary files, its exec and the old file put back, the simulated kinds; and through the
  daemon's socket the topic `update` and the commands `update_now` and `update_cancel`. No test reaches the network or replaces a file of the machine.
* `test_updatesign.py`: the signature of SHA256SUMS (`neoaprs/updateasset.py`): the project's public key pinned and in one place of the program; a list signed
  for its version gives the file's sum; a list that names only another file or a name twice, a signature over another list, a truncated one, an empty list, a
  line that is no checksum line, a signed list of an older release offered as the newer one and another key are each refused; through Update now each is the
  one problem `unverified` with the file never downloaded, and the project's key is the one believed by default; `NEOAPRS_UPDATE_KEY` taken only with the
  fake release; and a release's list read by the reader of the programs from before the signature (`support/fakerelease.py`, `old_checksum_for`) as before.
* `test_verify_download.py`: `scripts/verify-download.py` loaded with the test's own public key: a file of a signed release passes, a changed file, a list
  signed for another version, a file whose name carries no version without --version (the signed list of an older release), a version given that is not the list's and a missing signature do not; run as a program it believes the
  project's key alone.
* `test_alerts.py`: the message alert (`neoaprs/services/alerts.py`) with a shell line that writes its environment to a file of the test: the four variables,
  text that is data and not shell, the few names of the environment, alert off and an empty command, queries, a failing command told once an hour, a command
  that cannot start or runs out of time (killed with what it started), at most 5 at once; and in the whole daemon the first copy only, nothing for a bulletin, a
  group message, an ack, a reject, a query, another SSID or an overheard message, and a broken command that harms nothing.
* `test_queries.py`, `test_queries_wiring.py`: the queries (`neoaprs/services/queries.py`) on a stub Tnc, the real beacon and station book and a clock the test
  holds (`?APRSP`, `?APRSS` with and without a status sent, `?APRSD` with its order, its hour, its split over two messages of at most 67 bytes and `none`,
  `?APRST` and `?PING?` with the header as heard and a long path cut, the path of the asker, a query with an id, the answer once for the copies of a
  transmission, what is not a query or not to us, a third-party asker, the TNC away or refusing, the general `?APRS?` in a message to anyone and in the
  information field with its wait, once in ten minutes and cancelled by the stop), and inside the whole daemon on the pseudo-terminal radio: each query gives
  the right frame on the master, a bulletin is on the board and in the database and neither acked nor overheard, the status follows the beacon, the restart and
  the prune. The answer to an RF only asker ends with `RFONLY`, and one that cannot is not sent.
* `test_answers_budget.py`: the budget of answers (`AnswerBudget` of `neoaprs/services/answers.py`): twenty asks in a minute send ten frames at most, a whole answer or none, the QRU server and the queries spending one budget, frames that never went on the air given back, a paced answer that is stopped giving back what it did not send.
* `test_settings_reachable.py`: the settings the page leaves to `neoaprs db set` are the ones listed there, each with its reason, and none that can block a feature the page offers (transmit, the beacon, the Internet switch, the digipeater) is among them.
* `test_receive_only.py`: Receive only (`station/transmit` false, the first reason of `config.can_transmit`): on the whole daemon with a fake radio nothing reaches the line while it is off
  (a beacon, a status, an object, an ack, a query, a digipeatable packet and a message being sent are all due or asked), a new message, a retry, an object and a bulletin are refused with the
  code `transmit.off`, a message being sent keeps its attempts and does not fail and goes on when it is switched on, one beacon and no ack afterwards, the switch holds after a restart.
* `test_beacon_off.py`: the beacon Off (`beacon/interval_min` 0, a moving station too): on the whole daemon with a fake radio no beacon and no status go out whatever is due, and `beacon_now` and `status_now` are refused with the reason `the beacon is off`, while a message, its ack, the answer to a query, an object and a digipeated packet go as they do; what was held back goes when it is on. Off is not Receive only.
* `test_interlock.py`: the transmit interlock (`config.can_transmit`, `neoaprs/interlock.py`): which calls may transmit (N0CALL, NOCALL, MYCALL, a name that is
  no amateur call and the empty call may not), the empty call and position in the settings, and the whole daemon on the pseudo-terminal radio
  (`Env(operator=False)`, a fresh install): with beacon and status due, a message to send, a frame handed to the Tnc, nothing reaches the line and each refusal
  is logged once; a placeholder call gets no ack and no answer to a query; the KISS entry of the TNC goes on; with a call set a waiting beacon, an ack and a
  message go out; no position means no beacon and no own station. Every other `Env` has the operator's station in its settings (`OPERATOR`, and `ON_AIR` as a
  `Config`).
* `test_prefbook.py`: the preferences of the stations (a path or RF only for each, either of them, written through to the database and read again by the next
  start; `beacon/path` until a station has a path of its own, an empty one that is direct, the checks of a path as `beacon/path` has them; a count of attempts
  that an older version kept is ignored and a row with only that is no entry; what is told, a clearing that removes the entry when the last of the parts goes).
  RF only (`set_rf_only`: kept, read again by the next start and cleared, `RFONLY` added last to the station's own path or to `beacon/path`, none added to a
  path that has `RFONLY` or `NOGATE`, beside the other parts of the entry which goes with the last, EMAIL-2 and a name that is no call refused with the reason,
  the 8-element path that RF only cannot take).
* `test_chain.py`, `test_delivery.py`: the delivery chain of a message. The rules without I/O (`neoaprs/chain.py`: which hops of the path we sent by a heard
  path shows used, with the star on each address and on the last only, aliases replaced by the call that used them, a hop not named, the pieces of the internet
  in a third-party path left out, which attempt a copy belongs to); and the service (`neoaprs/services/delivery.py`) on messaging with a stub Tnc and a real
  database (the time and path of every attempt; a copy with the first digipeater used marks hop 1 and a later one hop 2, with the first time kept; an alias
  recorded as the call heard; a copy before and after the next attempt; a third-party copy with the gate's call, with and without hops in its path; a hop heard
  by radio and over the internet; copies of another addressee, id, text, station, an ack and a copy before the first attempt not linked; the chain kept across a
  restart; deleted with a message and with a conversation; a retry starting again). The wire is in `test_web.py` and the tables in `test_migrations.py`
  (migration 11). The markers that are no hops (`RFONLY`, `NOGATE`, `TCPIP`, `TCPXX`, the q-constructs) in the path sent and in the path heard, and in what the
  page is told for an attempt stored with one.
* `test_message.py`, `test_messagelog.py`, `test_messaging.py`, `test_messaging_wiring.py`: messaging. The rules without I/O (who a message is for, the text,
  the schedule); the message log on a real database thread (round trip, order, updates, the highest message id, deleting a conversation, pruning, the rows the
  table refuses); the service (`neoaprs/services/messaging.py`) on a stub Tnc, a real log and a clock the test holds (the exact bytes of a message and of an
  ack, the refusals, the ids and their wrap, the path of each station (`PrefBook.path_for`, which messaging is given) used by the messages, their attempts and a
  retry, and by the acks, the messages that are only overheard, the messages to a bulletin or a group (handed to the board, not overheard, not acked), the
  attempts at 0, 32, 64 and 128 seconds and the failure after them (and for 1, 3 and 10 attempts of an older message, each message keeping the number it was
  sent with, also across a restart; `send` giving 4 attempts and the email gateway 2 whatever a station's stored count or the old setting say, a message with 1
  or 2 attempts and no ack becoming `unconfirmed` and one with 3 `failed`, a late ack or reject settling an unconfirmed message, a retry from it), none dropped
  by count or age and a start that holds them all (with the warning above 10000), the daily care forgetting only the memory of old hearings, delete (any kind of
  message, a message being sent cancelled first, an unknown id, a database that refuses), delete of an overheard pair (that sender to that addressee only, no
  conversation, an unknown pair, a database that refuses), delete of a conversation (every message with the station and no other, a message being sent cancelled
  first, the overheard messages and the station's path and timeout kept, a call with no message, a database that refuses, all the messages held), ack and
  reject, retry and cancel, the radio away, a message that comes in kept once and acked once for each burst of copies (the first at once, a copy more than 10
  seconds after our last ack again, three copies in six seconds one ack, a third-party copy counted with the others, a copy after 31 minutes new; one without an
  id kept once for a repeat within 30 minutes by its text), the restart); and inside the whole daemon on the pseudo-terminal radio (`support/air.py` for the
  frames). On the pseudo-terminal: a message and our ack to an RF only station end with `RFONLY` and the chain does not hold it, a path that has `RFONLY` or
  `NOGATE` gets no second, and with 8 digipeaters a message is refused, a waiting one waits (told once) and goes when the path is shorter.
* `test_messaging_pacing.py`: the pace of messaging (`spacing_sec`): the first message goes at once and the ones written with it follow 10 seconds apart, in the
  order written, with no attempt used while they wait; a message after the pause is not delayed; messages that waited for the radio leave spaced when it is
  back. The other messaging tests set the pause to 0.
* `test_internet_hidden.py`, `test_station_radio.py`, `test_forget_all.py`: the internet hidden while `igate/enabled` is off (a page told no station and no packet from it, the station heard both ways with its radio side only, everything still in the database, switched on again without a restart, a restart with it off; `Station.radio_view`, the radio's place and the hour less the internet's) and Forget all stations (the stations, packets and weather heard go; ours, the objects and bulletins, messages, preferences and settings stay).
* `test_web.py`, `test_hub.py`: the web server over a real socket (`support/env.py` with `web=True`, `support/wsclient.py`): the hello and every topic (`TOPIC_NAMES`), the
  capture through the fake radio as patches, `list_ports`, set_config, forget_station, forget_all_stations, beacon_now, send_message, message_retry, message_cancel,
  message_delete, conversation_delete, overheard_delete (two pages see the dels, a conversation is untouched), the removed set_station_attempts and
  clear_station_attempts refused, set_station_path and clear_station_path, and the removed set_station_timeout and clear_station_timeout refused (the `messages` and `station_prefs`
  topics, an ack through the line, a bad addressee or path), the `bulletins` topic (a row by sender and slot, heard again, never aged out, a page that comes
  later) and `last_direct_at` of a station row, the files, the byte ranges of the base map, the Host check, the security headers; and the state hub with pages
  that are lists (what a patch holds, the gap of the `tnc` topic, a page that is behind), the window of packets and the publisher with its outgoing check.
  `set_station_rf_only` (the entry of `station_prefs`, the next message with `RFONLY` and a chain without it, EMAIL-2 an error with the reason).
* `test_web_access.py`: network access (`neoaprs/web/access.py`). The tests have one address only, so `away` says that no address is the loopback; then: what a
  device that has not logged in is given (the page's files, a 401 for `/access`, the base maps and the socket), a wrong key, five wrong ones and the shutting
  out and its end, the right key and its cookie (HttpOnly, SameSite=Strict, not the key) opening the socket and the map, a session kept by another `Access` with
  the same key and ended by a new key, by the switch and after a year, the per-address counts, a new key logging every other device out and giving the asker a
  session, a cross-site POST, this computer never asked (and a request through a proxy header asked), the switch turned on and off live (the key made once, the
  addresses told, the listening sockets, a page of the network cut off, the listening kept when the address is taken), a `web/bind` row read as the switch on,
  the Host names with the network on, and the address of the computer.
* `test_local_settings.py`: what a page of another device may not change or run (`LOCAL_ONLY`, `neoaprs/web/confighandlers.py`): the alert command, its Test, the update address, the map source and the allowed hosts are refused with `setting.local_only`, the rest is allowed, and `hello` says which page it is.
* `test_web_gate.py`: the gate of the page's server for every route at once, read from the running application so that a new route is asked too: a host name that is not ours is refused, a device that has not logged in is refused except on the routes of the table `FREE` (each with why) and let in with a session, a request that changes something (POST, PUT, PATCH, DELETE) or a socket's handshake with another site's Origin is refused, plain http beside the secure page is sent on or refused (the table `PLAIN`), and every answer carries the security headers.
* `test_alerttest.py`, `test_bulletindelete.py`: two commands over the socket. `alert_test` with a fake command that writes its environment (the made-up message
  in it and nothing of the daemon's, `messages/alert` off ignored, the saved command and not an older one, a failure with the exit code and the first line of
  stderr, a command that runs out of time, an empty command an `error`, a field the command does not take); `bulletin_delete` (the `del` on every page and the
  row gone from the database, a bulletin sent again new, an unknown entry an `error`).
* `test_pmtilescut.py`: the cut of the base map out of a big archive (`neoaprs/pmtilescut.py`, `pmtilesplan.py`, `pmtilesrange.py`, `pmtilesformat.py`) on made-up archives that a reader written apart
  from the program's code checks (`support/madepmtiles.py`): the tiles a box holds to a zoom and no other, for every shape of directory (the root alone, leaves, leaves of leaves, plain or gzip, runs, shared
  contents), the header, a `.part` file moved into place whole, the percent, the dry run (the size, no tile fetched), the size limit, archives that lie or cannot be cut (told in words; numbers that claim to be big
  are refused without being allocated), the grouping of the requests, a range server that fails, cuts an answer short, answers busy, gives no ranges or changes the archive, and a stop or a cancel that ends the threads.
* `test_pmtilesarchive.py`: the header of an archive read from a file, a file moved into place (a target Windows holds is tried again), whether a daily build is there.
* `test_mapfetch.py`, `test_mapwire.py`: the base map service (`neoaprs/services/mapfetch.py`) cutting the made-up planet from a range server: the files described by their headers, the
  box round the position for the radius and zoom (and clamped at the edges of the world), an estimate that writes nothing, fetches no tile and says what the download makes, the latest daily
  build looked for back a week, no position (nothing starts, the reason says so), the world map first and not again when it is there, the percent of each step
  told, a failure leaving the old files and no `.part`, a cancel ending the cut, one job at a time, an old pmtiles program in `bin/` left alone and never named, the words of an error without an address or a folder; and over the socket the topic `map`, the commands (every refusal an `error` with the reason),
  the dry run's numbers, the two files served with byte ranges, a cancel and the end of the daemon while a cut runs.
* `test_mapstall.py`: a map download that stands still (`Patience` of `neoaprs/services/mapfetch.py`) with a range server that holds its answers for tile data: the cut
  is ended and begun again with the note "trying again (2 of 3)" in the status, after the last try the job fails with the text that the server is too slow, a failure that cannot get better is not
  retried, a download that moves only in the size of its file is no stall, the size of the `.part` file reaches the status, the old map is never touched, and a
  cancel still works, also while the job waits to try again.
* `test_config_map.py`, `test_mapcli.py`: the settings of the base map (the ranges of `map/radius_km` and `map/maxzoom`, the forms `map/source` may have and the
  ones it refuses: an option, another kind of address, a word with a blank; a stored wrong value falling back) and the command line (`neoaprs map`,
  `python -m neoaprs.services.mapfetch`) as a process cutting a made-up archive from a file: a dry run for the flags, a download that makes the detailed map only, the position and the map settings read from the database of the data folder, no position (exit 1), a wrong flag (exit 2), a source that cannot be cut (exit 1, no file).
* `test_css_unused.py`: the unused-class check of the page's style sheets (`scripts/css-unused.py`, in the stage `ui-lint`): a class that a rule names and no
  source file writes is reported, as a whole word (comments, attribute selectors and declarations are no classes; a test file or `ui/src/test/` is no mention);
  a class the page builds at run time (a prefix of `PREFIXES`) and one of the map library are not, a prefix whose code or rules are gone is; and the style
  sheets of this tree are clean.
* `test_dup_check.py`: the duplication ratchet of the Python half (`scripts/dup-check`, `scripts/dup-compare.py`) with a stand-in jscpd: a clone is the pair of
  files it joins, a new or larger one fails, `--update` never makes the baseline larger.
* `test_protocol.py`: the wire models: the files `scripts/gen-protocol.py` generates (PROTOCOL.md, the JSON Schema, the TypeScript types and lists in
  `ui/src/protocol/`) are current, every message has an example that validates, every command round-trips, every command has one handler.
* `test_page_build.py`: `neoaprs/page/` (the committed build of `ui/`) is current (it builds `ui/` into a temporary folder and compares every file; skipped, and
  says so, without node or `ui/node_modules`), works from any path, lives under the daemon's Content-Security-Policy (no inline script, the map's worker is a
  file) and ships the symbol sheets and glyph files; its worker names its caches by a hash of the page's files and nothing of the page or its build reads the version of NeoAPRS.
* `test_page_snapshot.py`: the daemon serves the page it started with (`neoaprs/web/pagesnapshot.py`): the files read into memory without the hidden ones and the source maps, a folder swapped in the middle of a read read
  again, a page rebuilt on disk while the daemon runs changing nothing until it is started again, the ETag, `304`, `HEAD` and byte ranges of the snapshot, and the shipped page small enough to keep in memory.
* `test_release_script.py`: `scripts/release` run for real on a clone of a made-up repository with a bare origin, a fake `gh`, a fake `scripts/check` and a loopback server for the download links: the order of the steps, the
  dry run, the resume after a failure at each step (check, push, CI, tag, release run, the signing, the published release), `--rerun` once, the rate limit, and the refusals (branch, dirty tree, origin ahead, no notes, the version, a tag on another commit).
* `test_release_sign.py`: the step sign of `scripts/release` and `--verify` on the same made-up repository, with a fake `bws` that hands out a key the test makes (the clone's `neoaprs/updateasset.py` carries its public
  half): the draft signed and then published, the secret never in the output, the log of calls or a file, bws the only program given its access token and the secret's id; a key that is not the program's, a secret bws cannot read or none named, a secret that is no seed and a list
  that names a file twice sign nothing; a draft signed already is only published, one whose signature does not hold is signed again, a published release is never signed after the fact; `--verify` changes nothing
  and refuses a list or a signature that was changed, a signature for another version, a truncated one, a draft and a list short of a file.
* `ui/src/**/*.test.ts`: the page's own tests, run by vitest (`scripts/check --stage ui-tests`, or `cd ui && npx vitest run`): the socket client against a fake
  socket (state, patches, a missed revision, the reconnect backoff), the symbol sprites, the table's sorting and filtering, the map style, the settings form
  logic, the view composables of `App.vue` (the panel, the station picked, the Messages tab, the Email tab and its list of addressees, the Bulletins tab), the
  Email tab's rules (the 67 bytes over the addressee and the text, the commands `name L`, `name R` and `get`, the list of addressees and forgetting one, the
  gateway left out of the Messages tab, the badge rule), and every component mounted (the map against a fake MapLibre, `ui/src/test/fakemap.ts`, since the test
  browser has no WebGL); the page against the daemon is looked at by hand with `scripts/replay`.
* `test_processmeter.py`: what the daemon costs (`neoaprs/web/processmeter.py`): the CPU share as a function of two samples (including a span of none and a CPU
  clock that went back), the meter with a clock and a CPU time the test turns (the span since the previous sample, samples under a second apart sharing a
  reading), and the `status` over the socket with its share, memory and uptime.
* `test_scripts.py`: `neoaprs replay` and `neoaprs db` as processes, with a daemon on the replay over TCP (the capture fills its database and
  `neoaprs db stations` shows it), the replay on a pseudo-terminal (`--pty`, POSIX only), a file that is not there or holds no frame, and the wrappers of
  `scripts/` (`neoaprs-db`, `replay`, `capture`) run from a copy of `scripts/` in a made-up clone: they call the command with the clone's data folder, and a
  `--data` of your own wins.
* `test_install.py`: `scripts/install.sh`, the wrapper of a clone, in a copy of the tree with a HOME of its own and a `systemctl` and `loginctl` that only write
  down their arguments: it calls `neoaprs service install` with the clone's venv and data, writes the reference unit of the clone (the same in effect), enables
  lingering, changes nothing when run again, `--remove`, leaves a unit it did not write alone, and says so without a venv.
* `test_markers.py`, `test_guards.py`: the markers and the guards, each shown to fail when it should (the radio guard's own test is in `test_serialport.py`).
* `test_no_devices.py`: the no-devices switch (`neoaprs/nodevices.py`, below): the values that set it (every one but an empty one and `0`, a typo too, and the line at the start of the daemon names the value), what counts as
  this computer, the error each kind of port and address is refused with, the one line a door gets in the log, each door where it is (the serial line, the lists of ports, the fetches and the one POST, the cut of the map, rigctld, a
  gpsd and the control port of a Mercury on another computer, the alert command, the player, the Mercury program), a server of this computer asked itself and not through a proxy of the environment, every script and part of
  the harness that starts a daemon setting the switch for it (the files are read; the two that do not are listed there), and a whole daemon whose settings name a serial port, a keying line and a GPS port that
  exist as pseudo-terminals, the Mercury type with a sound card, an iGate on a real server's name and a rigctld on another address: it comes up, every part waits as it does for a device that is away, nothing is opened, started
  or connected to (every way out of the process is recorded; a socket pair, which Windows makes as a connection to the loopback, is not one), and its Dummy radios and its page work.
* `test_clock.py`, `test_signal.py`, `test_tasks.py`, `test_source.py`, `test_paths.py`: the small parts (`test_paths.py` also the data folder of Windows and
  macOS, with the platform named by the test).
* `test_portable.py`: the process layer where Windows differs, as far as Linux can show it: the one-daemon lock (a fake `msvcrt`), what `durable` syncs, the page's path rules on backslash paths.
* `test_migrations.py`, `test_store.py`, `test_dbfile.py`: the database file (the migrations, including version 1 to 2, 2 to 3, 3 to 4 (the paths carried into
  `station_pref`), 4 to 5 (`attempts_max`, 6 for every message there is) and 5 to 6 (`route`, empty for every message there is) and 6 to 7 (the `bulletin`
  table, with its named checks) and 7 to 8 (the `weather` table: every named check shown to refuse, the index, nothing made by the migration), 8 to 9
  (`station_pref.attempts`, null for every station, the table rebuilt with every row and the new CHECKs) and 9 to 10 (the state `unconfirmed` in the CHECK of
  `message`, every message and the index carried over, a doubt rolling back) against a fresh file), the settings. `test_migration_rf_only.py` has migration 12
  (`neoaprs/migrationsteps12to21.py`): a database of version 11 keeps every preference with `rf_only` off, the table refuses a bad `rf_only`, a doubt changes nothing.
* `test_migration_alert_markup.py`, `test_alert_default_line.py`: migration 27 (a stored Linux alert line that is exactly the old default is deleted, so the new default counts; own lines and the Windows default stay) and the default line itself, run in the real shell with notifier scripts: markup in a message comes out as text.
* `test_migration_message_failure.py`: migration 28 (`message.failure`, why a failed message of ours failed): every message of version 27 is kept with no failure, so an old failed one reads as one with no answer; the column takes `too_long_for_radio` and nothing else.
* `test_migration_allowed_hosts.py`: migration 29 (`web/allowed_hosts` in the checked form): a value the server took (blanks between names, a port, a dot at the end, a name twice) is written so that the check takes it and every name stays allowed; what is not a name or an address is left out and logged; a value already in the form is not touched.
* `test_migration_signal.py`: migration 30 (the signal of what is heard: `snr` and `rssi` of a packet and of a message, the last reading of a station with `signal_at`): every row of version 29 is kept with no reading; the columns take one, and the codecs read it back.
* `test_restore.py`: the way back from a database newer than this version (`neoaprs/backupfolder.py`, `neoaprs db restore`): the newest usable copy named with its date and command, a copy this version cannot open refused, the present file set aside, both locks taken, a failed restore rolled back.
* `test_cli.py`: the `neoaprs` command: no command and `run` are the daemon with the flags of `python -m neoaprs` (the daemon's parser decides them), each
  command is dispatched with the rest of the line, an unknown one is refused, the one version (`pyproject.toml` reads `VERSION`, the two scripts), the
  windowless entry that has no streams, the parser of each command, `capture` recording a TCP TNC into a file, and `map`, `db` and `doctor` as processes.
* `test_service.py`: `neoaprs service` on each system with nothing of the real machine: on Linux a HOME of its own and a fake `systemctl` and `loginctl` (the
  unit has the effect of the reference unit, `tests/fixtures/service/reference-unit.template`; without a clone no working directory; a path with a space quoted;
  again changes nothing and a changed unit restarts; a comment or the description changed does not restart; a unit with our marker is ours; a foreign file or
  link never touched; `remove`; `XDG_CONFIG_HOME`; `--linger`; the group of the serial devices; systemctl refusing or missing; `status`; `logs`), on Windows a
  stand-in for `winreg` (the Run key set to the windowless script or to `pythonw -m neoaprs`, the daemon started at once and not twice, a command that is not
  ours refused, `remove`, `status`) and on macOS a fake `launchctl` (the plist, `bootout` then `bootstrap`, a file that is not ours left alone, `remove`,
  `status`).
* `test_doctor.py`: `neoaprs doctor` on a temporary folder with the ports and the host's problems standing in: a fresh computer (warnings with their fixes, exit
  0), a folder with a database, a call and a map (all ok), a call that cannot transmit, a folder that is a file or a database that is not one or is of a newer
  NeoAPRS (fail, exit 1), an older one (warn), that it changes nothing, no port with the group, brltty and ModemManager; a daemon that holds the lock found with
  its page (a thread that answers), a page that does not answer, a run without a page, the end of a log, the decision about the group of the serial devices and
  the finding of brltty and ModemManager.
* `test_support_bundle.py`, `test_support_web.py`, `test_support_cli.py`: the support bundle (`neoaprs/cli/support*.py`) on a fake data folder (`support/supportdata.py`): the members and their order, the README and the one-screen summary, the settings with
  the secret only said to be set and the access key found in no member of the zip whatever put it there, the logs cut to their budget at a line start with the note of what was left out (rotated logs, a missing app log), the database report
  (migrations and their hashes, rows, the check, skipped over 500 MB), the packets, a database that is no database and a folder that is not there (the `.error.txt` files, the bundle still made), that the data folder is not changed (no `-wal`
  made beside the database), the Desktop folder and the file manager; `POST /support/bundle` on a daemon (the zip and its headers and the state of the running parts, the login, the Host and Origin, a bad body, the 256 KB, one at a time with 429, a failure
  as 500), `page_error` (the log line, a message that cannot forge a line, 20 a minute and the line about the rest, the ring of 100, the command's limits, over the socket), the browser named in the log, a saved setting in the log; `neoaprs support`
  (the path and the instruction, `--out`, the Desktop, `--show`, `--pause` only at a console, a folder that cannot be written), the tray item, the second line of the start, and what escapes (a thread, the program, the loop).
* `test_replay.py`: `neoaprs replay` over TCP: the real Tnc connects to it and hears the capture's four packets, nothing is sent until a client is there and the
  frames go on from where they were, `--loop`, what the daemon writes is shown, the loopback only and a taken port, and as a process (the first line is the
  address, a plain socket reads the frames, Ctrl-C ends it). The sample capture inside the package (`neoaprs/samples/thd7.kiss`) must equal the fixture, and
  `neoaprs replay` with no file plays it.
* `test_package.py`: `uv build` makes an sdist and, from it, a wheel; the wheel has the code, the page with its glyphs and symbol sheets, the placeholder and
  the unit template and nothing else, the entry points `neoaprs` and `neoaprsw` and the one version; installed into a fresh venv (`uv venv`, `uv pip install`)
  the `neoaprs` command reports the version and runs `doctor`, the package finds its page and unit template inside site-packages, and its daemon serves that
  page. Needs `uv`, and the network the first time (uv's cache after that); about five seconds with the cache warm.
* `test_main.py`: the daemon as a process (`python -m neoaprs --port socket://127.0.0.1:PORT` on a listening socket of the test, `--web-port 0` for a free port
  for the page): starts, serves the page at the address its log tells, moves the page to the next free port when its port is in use (the ten after it) and goes
  on without the page when none is free, refuses a second daemon on the same data folder with exit 2, makes its database and log, keeps the capture it is fed,
  stops on SIGTERM / SIGINT / SIGHUP within the unit's 10 s, exit code 2 on a database it cannot use.
* `test_startup_imports.py`: what is imported before the program works, read from `python -X importtime`: `--version` and `--help` load neither the web server nor Tornado, pydantic or cryptography; a plain start of the
  daemon, up to its "is running" line, loads neither the certificates' library, the secure connection's code nor the support bundle's modules; with `--encryption` the library is loaded at once, for the key.
* `test_open_stop.py`: the stop file (`neoaprs/stopfile.py`) and the commands on it: `neoaprs open` starts a detached daemon (given a fake radio on the loopback
  and `web/port` 0 in its database first, so that it never listens to the operator's serial ports or takes port 7303), waits for its page, prints the address,
  and finds the daemon again instead of starting a second; `neoaprs stop` ends it cleanly through the file (the log ends `NeoAPRS ended`, the lock is free); a
  request left in the folder does not end the next daemon; the browser is asked for the logged address (`webbrowser.open` is replaced); a daemon that exits or a
  page that never comes is reported with the log's path. The detached daemon is stopped by the fixture when a test fails.
* `test_desktop_logic.py`: the desktop app's logic with no window and no tray: which addresses stay in the window (`neoaprs/desktop/links.py`: the daemon's own
  page stays, other sites go to the browser, `file:` and `javascript:` are dropped), the tray menu as data and what its items do against a fake toolkit
  (`support/fakeshell.py`), the decision to attach to a daemon or start one (a scripted `Daemon`), what the app remembers, and which shell a computer can run
  (the importer and the WebView2 registry stood in for).
* `test_desktop_cmd.py`: `neoaprs app` end to end with the shell and the session replaced: the second app, the browser fallbacks, a page that does not come up,
  a shell that cannot start, `--quit`. `test_desktop_session.py` is the same decision against real detached daemons (fixtures of `test_open_stop.py`).
  `test_desktop_autostart.py`: start at sign-in on Windows (the stand-in for winreg of `test_service.py`) and on Linux (a configuration folder of the test's
  own). `test_desktop_single.py`: the one-app rule (the lock, the loopback port and `show` / `quit`). `test_desktop_winshell.py`: the Windows shell against
  stand-ins for pywebview, pystray and Pillow in `sys.modules`. `test_desktop_qt.py`: the Qt shell headless with the real PySide6-WebEngine
  (`QT_QPA_PLATFORM=offscreen`; skipped when the extra `app` is not installed: `uv sync --frozen --extra app`): the window, its size, the stored page data, the
  links, the tray menu, and the window that shows the loading page before the daemon answers and closes when no page comes.
* `test_desktop_splash.py`: the splash of Windows (`neoaprs/desktop/splash.py`) but its Win32 calls: the quick look at the app's arguments against the real parser's
* `test_desktop_splash_shown.py` (a Windows desktop that is shown: GitHub's Windows runner; skipped in a service's or an SSH session's hidden window station and on every other system): the loading window of `neoaprs/desktop/splash.py` made with the Win32 calls themselves: there and shown, of its size at the screen's scale, in the middle of the work area, a tool window with no button on the taskbar, without the focus, and gone when it is taken away.
  options, the look at a data folder an app holds already (no lock taken), the place at the DPI and the page's dark colours, the handle that closes it once from
  anywhere, every place the app takes it away (before a message box of its own, which the splash would cover), and the entry's way to it importing nothing heavy (`-X importtime` in a process of its own).
* `test_desktop_startup.py`: the desktop app's start: the loading page (`neoaprs/desktop/loading.py`: the page's icon and colours, nothing that moves), the session
  opened in a thread of its own, the wait for the page every 0.05 s that looks at the lock only once the page answers, and `neoaprs app` on a slow daemon and on
  one that never comes in virtual time (the wait's clock and sleep are the test's); the Windows shell's window before the page and with no page.
* `test_release.py`: the release's files as far as a test can see them: the notes `scripts/release-notes.py` takes from a changelog, the ten files the workflow
  assembles (the wheel taken out), the `macos` job, the workflow's pins by major version and its one `contents: write`, the
  installer script's promises (per user, the autostart task on by default, the uninstaller order), and the bundled pmtiles found before the PATH.
* `test_appimage.py`: NeoAPRS in an AppImage: `$APPIMAGE` counts only for an interpreter inside `$APPDIR`; the systemd unit, the detached daemon of
  `neoaprs open` and the start at sign-in start the AppImage file and not the mount (a path with a space quoted); `AppRun` with and without arguments and
  through a link (a stand-in interpreter that prints its arguments); the desktop entry; every download of `scripts/build-appimage` pinned by version and digest.
  The image itself is tried by `scripts/smoke-appimage` in CI.
* `test_cipher.py`, `test_cipher_vectors.py`, `test_keyring.py`, `test_messaging_locked.py`: encrypted messages (`--encryption`). The cipher: the key announcement and its reading, the shared key from either side, a sealed text that opens with the pair's key and with nothing else (another key, the other direction, another station, a changed character, a cut packet), the room a message has, the fingerprint. The known answers: fixed keys (the two parties of RFC 7748), the shared key, the announcement, the fingerprint and a sealed message with a fixed nonce, each a literal that is also rebuilt from the `cryptography` library alone, so that a change of the construction cannot go by. The key ring: our key made when first needed and kept in a file only the owner reads, a station's key taken on first hearing and kept, a different one refused until the old is forgotten, and the flag that governs sending. Messaging: a locked message leaves as ciphertext and is kept as what was written, every attempt sends the same bytes, the other station opens it or keeps it shut, what is overheard, and all of it after a restart.
* `test_frequencies.py`: the suggested frequencies of the HF box: the project's file understood (each entry checked, three at most), the service that asks for it a minute after the start and when a page shows the box and not more often than every 15 minutes (and never with the update check off), the last good list kept across a restart, a bad file or a missing server leaving it as it was, the fall-back to the version page's dial and to the built-in two, and the topic `hf` and `hf_frequencies`.
* `test_skeds_php.py` (POSIX only): the sked board's endpoint (`server/neo/api/v1/skeds.php`) under PHP's own web server in a folder laid out as the site is (skipped without `php`): an add kept in a file of its own and the board written beside the site's files and served as a static file, with neither the token nor its hash; a remove only with the token that posted, a wrong one counted; every refusal with its reason and status (a bad call, dial, time or token, the past, too long, too far, five for a token, ten for a call, a hundred in all, closed, a blocked call, the rate of an address with only its hash kept); an ended sked removed by rewriting its stored file's time; two writers at once under the one lock; a note with control and invisible characters cleaned and cut, an over-long body, a body without its length, a wrong content type, a path in an id; the board out of `site/` and `robots.txt`, and `server/skeds.sh` refusing a bad id or call before it asks for any login.
* `test_skeds.py`: the sked board in the daemon (`neoaprs/skeds.py`, `neoaprs/services/skeds.py`). The rules of a row and a made-up hostile board of every kind (a bad id, call, time, dial or note, markup, control and invisible characters, a row that is no object, a board nested thousands deep, floods of one call): the bad row is dropped alone and the rest stands, a board that is not one leaves the last board. The service's rhythm (a minute after the start, every 15 minutes at most however many pages ask, never with the update check off), a 404 as a board with no skeds, offline and closed, the last board and our ids kept and told at the start, what has ended dropped by the daemon's own clock, the secret token (made when first needed, kept, never sent when reading, never in the log, the bundle or `neoaprs db list`), every refusal of the server (an error with a code, or the log's and no error), and the real calls against a small server on this computer (`support/fakeskeds.py`).
* `test_skeds_wire.py`: the sked board through the page's socket: the topic `skeds` with its dials and rows and `ours`, `skeds_wanted`, `sked_post` and `sked_delete` against the fake server, the refusals with their codes, a closed board that is no error, a sked that ends leaving the topic, a command that is not right refused whole.
* `test_channelbusy.py`: the busy detectors on made-up bands (Mercury's own worked again and the automatic control: a frame, a carrier, a step, a drift, static, a narrow filter, a voice, the pause while the radio transmits), and `test_mercury_scoping.py` the control in the modem part (the spectrum reaches it through the fake UI, Mercury's lines are the state only while it is not read).
* `test_mercuryscope.py`, `test_mercuryui.py`, `test_mercury_scoping.py`, `test_hf_scope_page.py`, `test_scope_handover.py`, `test_mercury_scope_real.py`: the HF scope and the transmit level. The spectrum frame, the status, the commands, the level worked back from white noise of a known RMS, the rows of the waterfall (the passband's 307 bins, two spectra to a row, the byte, the binary frame), the rows kept of the last two minutes (bounded, in order, a gap kept as a gap, emptied, the frame of them, what making them costs) and their binary frames to the pages that asked; the hand-over to a page that begins to look (the rows kept, then every row after them, none twice and none lost with a row arriving meanwhile, a second page, one that leaves in the middle, one that is behind, the emptying told, to a page that was behind before its next row; a page that looks again on its socket sent the rows from its newest on; the daemon's clock in every history; a row of before a suspend as old as the sleep); the WebSocket client and the link to Mercury's UI against a fake server (`support/fakemercuryui.py`, which the fake Mercury program starts when its ini turns the interface on); the modem part with that program (the ini, the rows made and kept all the time, on the clock that counts a suspend, and forgotten where the channel is cleared, the gain sent live, a Mercury without the interface, the link made again, the tune tone that follows the gain and is begun again); the page's `hf_scope` and the setting of the gain; and the real Mercury on the simulated channel (the interface on the loopback only, no spectrum until asked, the level of the channel's noise within 1.5 dB, the gain, the tune peak and the refusal of a second TUNE; skipped where Mercury is not built).
* `test_mercury.py`, `test_mercury_build.py`, `test_mercury_modem.py`, `test_mercury_world.py`, `test_hf_tune.py`: the Mercury HF modem without a radio and without Mercury. What the daemon knows of it (the mode and its frame, the cap of 123 bytes, the keying, the command line and the configuration it writes, what the program prints); the build script's pins and the tarball names (the build itself is tried by the `mercury` job of the release workflow); the modem as a part of the daemon on a program that stands in for Mercury (started, given free ports, started again when it dies, a program that is not installed, the control port's `PTT` and `BUSY` lines); two and three stations on one fake air (a beacon heard after the frame's time, a message acked, two stations keyed at once losing both frames and the retry getting through, our frames waiting while a frame is on the air, an iGate); and Tune and the keying test.
* `test_reading.py`, `test_signal_kept.py`: the signal of what is heard (`neoaprs/reading.py`). Mercury's SN line taken by the next frame once and only within the pair time, so that two frames close together each get their own and a frame with none said gets none; a radio type gives only the readings it says (Mercury and the Dummy HF radio the SNR, a KISS TNC none); the Dummy HF radio's made-up SNR, the farther the weaker; a station's last reading from the packets heard direct; the readings kept in the packet log, the station cache and the message log (ours the ack's), the signal series of a station, and the daemon on the Dummy HF radio telling them on the wire.
* `test_two_radios.py`, `test_two_radios_objects.py`, `test_dummy_hf.py`: a station with two radios and the Dummy HF radio. Three daemons on an FM air and an HF air (both radios, FM alone, HF alone): a beacon goes out on both, a station is tagged with the radio it was heard on, a message and its ack take the radio the station was heard on, with the HF radio off nothing of this is there; our objects on the radio they were given, the email gateway on FM only, the beacon interval raised to the HF floor; the Dummy HF radio's distant stations, the HF pause, the answer at the pace of HF and nothing on any air.
* `test_hfchannel.py`: the HF channel for real Mercury instances (`support/hfchannel.py`), on named pipes, stepped a block at a time: exact samples on a noiseless channel, the asked SNR, a keyed station deaf, two keyed in one block a collision, delay, fading, a slow or missing reader, the same seed giving the same bytes, and the pace in a thread. The pipe tests are for Linux.
* `test_macos_app.py`: NeoAPRS as a macOS app, as far as Linux can see it: the one rule finds the shipped programs in `Contents/Resources/tools`; the launcher of `packaging/macos/launcher.c` built against
  this machine's Python and run from a made-up bundle (the arguments, `app` by default, the home, `sys.executable`, the isolation); the icon made from the Windows one; the pruning of the macOS layout of Qt
  on a made-up tree; what `scripts/build-macos-app`, `scripts/smoke-macos-app`, `scripts/build-mercury` and the bundle's files promise. The app itself is built and tried by the `macos` job of the release workflow.
* `safety/`: the database actor (`neoaprs/db.py`): order, faults, life and shutdown. Everything under it is marked `safety`.
* `fixtures/`: captured frames and streams from the radio, with the expected decode beside each; `fixtures/aprs/cases.json` holds the parser's cases, the
  third-party frames an iGate sent (an ack and a message) among them, with the inner header expected beside the decode.
* `support/`: what tests are built from (below).

## Windows

The suite runs on Windows in CI (`.github/workflows/ci.yml`; the Windows installer, the AppImage and the packages are tried by
`.github/workflows/release.yml`, not by the suite, `docs/development.md`, "Packaging and releases" and "Local and CI"). What is POSIX
only carries `posix_only` (`support/ptyline.py`: a test, or `pytestmark = posix_only` for a file) and is skipped there: pseudo-terminals and device files
(`test_serialport_pty.py`, `test_tnc_pty.py`), `/proc`, file modes, the shell scripts (`test_scripts.py` wrappers, `test_install.py`), the checks of the
repository (`test_docs.py`, `test_hygiene.py`, `test_dup_check.py`, `test_check_script.py`, `test_security_check.py`, `test_check_in_container.py`, `test_flaky.py`, `test_check_installs.py`) and the radio guard on `/dev` paths. `FakeTools` and `install_fake` skip themselves on
Windows (their programs are scripts with a shebang). The rest is written for both systems:

* a daemon started as a process gets `creationflags=NEW_GROUP` and is stopped by `stop(proc)` (`support/proc.py`): SIGTERM on POSIX, Ctrl+Break on Windows,
  where `terminate()` is a kill and the exit code is not 0;
* the alert tests use `support/alertcmd.py`, the same few commands as a shell line and as PowerShell, with the longer waits a runner needs to start PowerShell;
* a refused connection is `REFUSED` (`support/fakeradio.py`), worded by the system and slow to come on Windows, so the tests wait for the state rather than for a time;
* files are read as UTF-8 (`read_text(encoding="utf-8")`; the default on Windows is cp1252);
* the leak guard does not count the tasks the Windows loop itself keeps for a listening server.

`mypy --platform win32` runs on the Linux job, so a POSIX-only call in `neoaprs/` has to say so (`# type: ignore[attr-defined, unused-ignore]` or a `sys.platform` branch).

## Markers

Every test is exactly one of `unit` (pure code, no loop, no daemon, no socket) and `integration` (a loop, the Controller, a fake service, a child process),
given by `support/markers.py` from what the test uses, not by decorators. `safety` is added to the tests of the data layer. `expects_errors` is set by a test
that makes the code log an ERROR on purpose.

## The four guards

`support/guards.py`, wired in by `conftest.py`, run for every test:

1. **Nothing leaves this machine.** The daemon's update check is off for every test (`NEOAPRS_UPDATE_CHECK=0` in `conftest.py`, which `ProcessGuard` also
   demands of a `neoaprs` that a test starts with an environment of its own). HOME and the XDG folders are an empty folder of the test; a connect, a datagram or
   a name lookup to an address that is not on the loopback fails the test, even when the code under test swallowed the error. Not even this machine's port 4532
   or 4533 may be reached (the rigctld and rotctld of whoever runs the tests, on a real radio): a test that wants a radio starts a fake rigctld on a free port
   (`support/fakes.py`).
2. **No leak.** A test that ends with an asyncio task still running, or with the thread of a `Db` still running, fails. `support/env.py` stops the daemons of
   the `Env`s and closes the `Db`s of the stores the test opened (`support/storedb.py`).
3. **No unexpected ERROR.** A test that makes the code log an ERROR it did not say it expects fails.
4. **Never the radio.** A test that opens a path matching `/dev/brainbox_*` or `/dev/tty*` (through `serial.Serial` or `os.open`, symlinks resolved) fails: the
   tests use a fake radio on the loopback (`support/fakeradio.py`) and, for the few that are about a device file, a pseudo-terminal pair (`support/ptyline.py`,
   POSIX only).

A fifth thing that is not a guard but behaves like one: the logging (levels, handlers, switches) is put back as it was when the test ends.

## The no-devices switch

The guards live in the test's own process. A daemon or a command that a test starts as a process of its own is out of their reach, so `conftest.py` also puts `NEOAPRS_NO_DEVICES=1` into the environment, which every such
process inherits: under it the program opens no serial or Bluetooth port, starts no Mercury, plays and notifies nothing and connects to nothing but this computer, whatever its settings say (`neoaprs/nodevices.py`;
a fake on the loopback, the radio of `test_main.py` say, is still reached). The switch is on for every value but an empty one and `0`, so a value that was mistyped keeps the doors shut. A test that gives its process
an environment of its own passes the variable on with the rest of `os.environ`. In the test's own process the fixture `devices_are_fakes` of `conftest.py` lifts the switch for every test: there the guards watch the same
doors and fail the test that reaches a real device, and behind those doors stand the fakes that the tests of them use (a pseudo-terminal for a serial port, the made-up Mercury program, a socket pair for Bluetooth,
a player or an alert command of the test), which the switch would refuse as it refuses the real things. So a test of a real door needs nothing new, and a process started by a test gets the switch without asking. A
test that is about the switch asks for the fixture `under_the_switch` (`test_no_devices.py`), which keeps it on in the test's process.

## Support

`support/fakeshell.py` (`FakeFrame`, the toolkit as the desktop app's logic sees it, and a shell that `neoaprs.desktop.cmd.run` can be given by name),
`support/clock.py` (`FixedClock`), `support/stubtnc.py` (`StubTnc`, the one stub Tnc of the suite: a state, whether it takes a frame, the frames it was given as
`sent`, `infos()` and `lines()`, and how often it was asked), `support/rig.py` (`ServiceRig`: the settings, the clock and the stub Tnc that the tests of a
service that sends by a schedule start from; `OwnRig` for the own objects and bulletins), `support/maprig.py` (`MapRig`: the map download service on a range server), `support/storedb.py` (`store_at`, `log_at`: a log of the daemon on a new database file of the test), `support/fakeversionpage.py`
(`version_page()`: the page the update check asks, on a free port of the loopback, with the requests it was sent), `support/fakerelease.py` (`FakeRelease`, the
files of a release as Update now's downloads see them, and `FakeInstaller`, which writes down what it was given), `support/fakes.py` (`FakeLineServer`, a line
server on a free port of the loopback, and `FakeRigctld`/`rigctld()`: `f` answered with the frequency in Hz, `m` with the mode and the passband, `RPRT -5` for
both while `radio_on` is false), `support/weather.py` (`report` and `heard`: a weather packet as the TNC makes it, or with the weather kept as plain comment
text, with the report of OH2MUI by default), `support/env.py` (`until`: the one wait for a condition, 5 s before the test fails; `remember_stop`: a part a test
starts without an `Env` is stopped when the test is over; `Env`: the Controller on a test folder, its Tnc on a fake radio (`Env.radio`, its `link` is
`socket://127.0.0.1:PORT`; `Env(radio="pty")` is a pseudo-terminal behind a path, POSIX only, `new_pty(name)` another, `new_radio()` another fake one): `feed`,
`heard`, `play`, `unplug`/`plug`, `packets`, `stations`; with `web=True` also the page's server on a free port: `port`, `ws()`, `fetch()`),
`support/fakeradio.py` (`FakeRadio`: a TCP server on 127.0.0.1 and a free port, the same on every system, that stands in for the TNC: its `url` is the port to
open (`socket://127.0.0.1:PORT`); `feed(bytes)` is the radio talking, `await said(count, timeout)` what the code under test wrote, `drop()` closes the
connections (the line is lost), `refuse()` stops listening (a connection is refused) and `await accept()` starts again on the same port, `connected()` waits for
a client; there are no tasks in it, and what is fed while nobody is connected is kept for the next client), `support/ptyline.py` (imports on Windows, where
making a pair raises, `posix_only`, the mark of a test or a file that needs one, and the names that only POSIX has, for a test file that Windows collects and the Windows type check reads: `SIGHUP`, `SIGKILL`, `NOCTTY`, `AF_UNIX`, `is_root()`, `mkfifo`, `makedev`, `user_id`: a pseudo-terminal pair for the radio's port in the tests that are about a
device file: the fixture `ptys`, registered by `conftest.py`, makes pairs and closes them, `feed` and `heard` are the radio's side, `close_pty` is the cable
pulled, `held_by_a_program` is another process that has a port open), `support/air.py` (frames as the radio would say them and, with `await said(env)`, the
frames the daemon has written: for the tests of messages), `support/wsclient.py` (`WsClient`: a tab that keeps every message and the topics as the page would
have them: `expect`, `until`), `support/storedb.py` (`store_at`: a `Store` on its own `Db`), `support/httpthread.py` (`serve`: a test's small HTTP server on a thread, its listening socket with a time limit, so that a connection gone before it is taken cannot hold `accept` and then `shutdown` for ever), `support/madepmtiles.py` (`archive`, `planet`, `every_tile`, `tiles_of`: made-up PMTiles archives and a reader of them written apart from the program's code), `support/rangeserver.py` (`range_server`: a web server on the loopback that serves one file
with range requests and fails on demand: cut short, busy, no ranges, wrong bytes, 404, an answer held), `support/dbactor.py` (a `Db` on a table of numbers, connections that fail on demand, the leak guard for
its thread), `support/safety.py` (`FaultyConnection`: the Nth statement fails with what a full disk raises; `raw`: a second connection that sees only what is
committed), `support/migrated.py` (a file as the migrations leave it), `support/codemap.py` (what the architecture and size tests measure), `support/archdoc.py`
(the tables of `docs/ARCHITECTURE.md` made from the architecture test), `support/settingsdoc.py` (the table of settings of `docs/manual/settings.md` made from
`neoaprs/config.py`), `support/files.py` (the fixtures), `support/fakemercury.py` (a Mercury that is not one: its two ports on the loopback and one shared air, the cut at 123 bytes, the frame's time on the air with `PTT ON` and `PTT OFF` round it, no carrier sense so that two overlapping frames are both lost, the control lines and `TUNE`; also run as a program), `support/mercuryworld.py` (two or three daemons on that air or on an FM air beside it), `support/hfchannel.py` (the air between real Mercury instances) and `support/realmercury.py` (real Mercury instances and daemons for `scripts/mercury-bench` and `scripts/mercury-sim`; no test of the suite starts them).

## Waiting

A test waits for a condition with `until(...)` (`until_async(...)` for one that has to be awaited, `Env.until_usable()` for a Tnc that is connected and
settled), never for a time: a fixed sleep is the flake of a busy machine. What stays a time is named: `idle_for(seconds)` (`support/env.py`) is the window in
which a timer has had its chance to do something that the test then asserts it did not do; a plain `asyncio.sleep` is left only in what imitates a thing that
takes time (a talker, a slow open, a probe that is half way to its nudge), with a comment. `quick_start(...)` (`support/env.py`) starts an `Env` whose services
tick every 20 ms and waits until the Tnc is usable. A file that a program of the test writes is read with `read_when` or `until_written` (`support/files.py`), which wait for the text the test asserts on and not for the file's name (Windows refuses a file that the writer still holds). A wait that depends on a program the test started (the made-up Mercury, a daemon) is `until_started` (`support/env.py`, `START_SEC`), and an upper bound on real time is left out or is orders of magnitude over what the code takes: a time that is the code's own is measured on `virtual_time`, below. A test that runs over `NEOAPRS_TEST_LIMIT_SEC` (600) ends its process with its name and the stacks (`support/timelimit.py`). The tests that start the daemon as a process wait `PATIENCE_SEC` for it (`test_main.py`) and print its log
when it does not end.

A test of code that waits on timers (a pause between steps, a back-off, a quiet period) does not sit through them: `async with virtual_time() as clock:` (`support/virtualtime.py`) brings the loop's clock
forward to the next timer whenever nothing else is ready, so a 60 s wait takes no time and `clock.skipped` says how long it was. It is for fakes in memory (`support/fakeport.py`: the Tnc's line, which a test
can fail at the open or at a write, `support/faketnc.py`'s `ears`); a test with a thread or a socket that has to deliver keeps real time (`test_virtualtime.py` shows both). The Find my radio tests share their rig
in `support/finderrig.py`.

## Properties

Hypothesis is in the `dev` group. `HYPOTHESIS_PROFILE=ci` (the default) is derandomised and keeps no example database, so a run is reproducible;
`HYPOTHESIS_PROFILE=dev` explores with a random seed and 2000 examples. The properties of KISS, AX.25 and the APRS coders are `test_properties_kiss.py`,
`test_properties_ax25.py` and `test_properties_aprs.py`.

## Order

`NEOAPRS_TEST_ORDER=reverse` or `shuffle:SEED` runs the test files in another order (the tests of a file stay in theirs): a test that only passes because of
what an earlier file left behind fails in one of the two.
