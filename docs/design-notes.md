# Design notes

Why parts of NeoAPRS are built the way they are: measured numbers, protocol choices, and quirks of
hardware and operating systems, by module. The code keeps only a short reason at the place it
matters; the longer explanation is here. Start with [`ARCHITECTURE.md`](ARCHITECTURE.md) for the
layers and [`development.md`](development.md) for how the project is built and checked.

## neoaprs/aprsmice.py

Mic-E type codes follow the aprs-deviceid `mice` and `micelegacy` tables. The original Mic-E
telemetry is obsolete and shares its first bytes with the type codes, so it is removed and has no
type code. Status text that ends in a known two-byte suffix belongs to a radio: "`1296 MHz_3" is a
Yaesu radio stating 1296 MHz, not telemetry.

## neoaprs/aprsparse.py

A `!` position report with text in front of it (an X1J form) is deprecated in APRS 1.2, but old
digipeaters still send it, so it is read and never sent.

## neoaprs/backupfolder.py

A copy of a database is valid only if its header is SQLite's at the expected schema version with a
valid page size. The page count in the header is trusted only when it matches the change counter
(header bytes 92-96 equal 24-28); otherwise the file must merely be a whole number of pages. A
journal or WAL beside a copy means it is not whole. Header fields that differ between a copy and
its source without a difference in content are the journal mode, change counter, schema cookie,
version-valid-for number and SQLite version; byte comparison blanks them. Copy names carry a
counter, so the newest by name is the latest even if the clock went back. A restart after a
cut-short migration reuses the copy it began from, or a whole copy of the same version when the
file is unchanged since. A temporary copy file is dead once unchanged for five minutes.

## neoaprs/beaconrule.py

The floor of a radio type is about shared airtime (HF and LoRa, 30 minutes), whereas FM's 20
minutes is what the setting already enforces; only the higher floor is a radio's own and also
limits how often a live object is repeated on it.
#### Notes from comment pass 2 (list pass2-00x02)

## neoaprs/btserial.py

Channel 1 is the usual RFCOMM serial channel and some Kenwood radios use 2, so channels 1 to 3 are
tried after the ones the device lists. A device that is off or out of range fails only after the
link's page timeout, so the connect timeout is long.

## neoaprs/cardlevels.py

The card's levels are put on the card at every start of the radio's modem because the desktop's
sound system and a replug move the same controls. While the radio runs the card is read every two
seconds so the row follows the desktop mixer. Playback is the radio's only while the modem's
transmit gain is 0; otherwise the page offers the gain and the card's playback level stays as the
system has it, so the page always shows what changes the level on the air. The capture value is
always the radio's. The mixer is called on a thread, one call at a time; a failing call means no
levels and is logged once per card. `known` is true once the radio's own card was read, or at once
when there is nothing to wait for, so the page draws one control shape from the start instead of
swapping buttons for a slider.

## neoaprs/chain.py

A used hop implies that the hops before it were used. A hop of position 0 is a copy that came back
over the internet with no hop in its path.

## neoaprs/channelbusy.py

The occupancy detector's numbers were chosen by measurement (see docs/mercury.md). A frame occupies
about 562 Hz of the spectrum and a carrier about 20 Hz, so a run of three adjacent 150 Hz bands
(450 Hz) that stand over the quiet reference counts as a signal; a carrier lifts one band, a frame
three or four. The quiet reference is the lower quartile of the flattened bands, so a rise of noise
over the whole passband moves the reference with it and is no signal. Bands are averaged in power
over 0.25 s because noise bands wander by a dB or two. Each band's own slow floor is subtracted
(flattening) so that the slopes of the receiver filter are not read as a lift; the floors do not
rise while BUSY so that a frame does not lift its own floor. The release delay of 0.8 s plus 0.6 s
of smoothing after a frame matches the roughly 1.5 s that Mercury's own detector takes.

## neoaprs/childprogram.py

A child program is started with `subprocess.Popen` and its output is read by a thread, not with
asyncio subprocesses: on Windows the event loop may be the selector loop that Tornado forces, which
cannot start subprocesses. The reader thread reports the exit code and the last output lines to the
loop with `call_soon_threadsafe`. The process id is kept in a file beside the configuration so that
the next start can end a stale run left by a crashed daemon, which would otherwise hold the sound
card and the listening ports. A port that is already listened on is not free for the program, so
every foreign listener found after the program started belongs to the program. A repeated warning is
logged at INFO only the 1st, 10th, 100th, 1000th... time because a stuck sound device repeats
one line millions of times; one more line when
it has stopped for a minute says how many times it came, so that its end is in the log too. What a run said and the
callbacks of its reader belong to that run: a callback that reaches the loop after a new run started is
dropped, and a relaunch waits until a run ended in a thread is gone, since it holds the sound card. The bundled ALSA library needs ALSA_CONFIG_PATH when a shipped
alsa.conf exists, because a machine without ALSA lacks /usr/share/alsa/alsa.conf.

## neoaprs/claims.py

A claim is the value in force, whether set in the settings, remembered from the last search or
chosen by the daemon. Values are normalised by the adapter that names them, so equal text is the
same resource. A serial device is one resource whatever it is used for: the kinds in `PORT_KINDS`
(radio port, keying line, GPS port) conflict with each other, while one holder may use a device in
two ways and its claims are kept apart. A device that an enabled radio is set to belongs to that
radio whether or not its line has opened it yet; such named devices are left out of what others may
choose but are never held, so two radios stored with one port do not lock each other out. The
one-search-at-a-time rule is a lock elsewhere (the radio registry's search lock), not part of this
table.

## neoaprs/cli/servicewindows.py

NeoAPRS starts at login through the `NeoAPRS` value of the user's Run key (the list shown by Settings, Apps, Startup). It is not a Windows service because a service has no desktop and no user profile, and the COM port, data folder and page belong to the logged-in user. The command is `neoaprsw.exe run --data DIR` (the script without a console window), or `pythonw.exe -m neoaprs run --data DIR` when NeoAPRS is not installed as a script.

## neoaprs/cli/supportbundle.py

A support bundle is one deflate-compressed zip named `neoaprs-support-<CALL or nocall>-<YYYYmmdd-HHMMSS>Z.zip`. It is written under a temporary name and renamed. Secret values are removed from every member as the zip is written, in addition to the redaction of settings by name. Logs are cut to a budget by keeping the newest lines from a line start, and the first line of a cut file says how much was left out.

## neoaprs/daemon.py

The daemon is one process with one asyncio loop. SIGTERM, SIGINT and SIGHUP (SIGBREAK on Windows) and the file `neoaprs.stop` in the data folder end it; a second signal while it closes ends the process at once. Exit code 2 means the database cannot be used or another NeoAPRS holds the data folder, so a restart would not help. Only warnings, errors and migration lines go to stderr; the log is rotated and bounded. The page is served on `web/port` or the next free port of the ten after it; without a free port the daemon runs without the page. After an update or restart the new daemon keeps the previous page port when it is free. After an update of an AppImage the process runs the new file with the same arguments.

## neoaprs/db.py

The Db actor owns one SQLite connection in one thread; every statement is an operation on its FIFO queue. The guarantees are:

- Order. With one thread and a FIFO queue a read sees every earlier write. Functions run in the thread and must not wait for the event loop or for each other.
- Transactions. A failing write is rolled back and its exception reaches the caller unchanged. A function may not manage transactions or call the Db (this raises NestedUse).
- Durability. A write that has returned is committed with `synchronous=FULL`.
- Appends. `write_nowait` appends are batched for `tuning.tick` seconds and committed as one transaction, each in its own savepoint, in order. A crash loses up to one tick of them. The queue is bounded by `tuning.max_appends`: beyond it the newest append is dropped and counted, so producers never slow down. A failing batch is rolled back and retried `tuning.attempts` times, then dropped and logged; while closing it is tried once, because the stop must end within the service manager's stop timeout. An append that fails by itself (a constraint) is undone alone. Awaited operations are never dropped.
- Shutdown. `close()` runs what was queued, closes the connection and ends the thread; later calls raise DbClosed. The thread is a daemon, so a program that never closes still ends.
- Cancelling an `await` withdraws a read or maintenance operation that has not begun. A write is never withdrawn: it happens, and its outcome is logged and counted.
- `stats()` reports queue wait, run time, event-loop stall and counts.

`close()` polls `thread.is_alive` because a notice posted from another thread may fail to wake an idle loop (the Windows proactor's self-pipe). The `exited` future is never cancelled, so a second close can wait on it too.

## neoaprs/dbthread.py

The database thread serves five kinds of operation from its queue. A read runs in a read transaction with `query_only` on, so the whole function sees one snapshot. A write runs between BEGIN IMMEDIATE and COMMIT; if the function raises, the transaction is rolled back and the error goes to the caller. An append is a write nobody waits for: consecutive appends form one transaction, each in its own savepoint, so a failing append costs only itself. A maintenance operation runs outside a transaction (backup, checkpoint). A stop runs after all earlier work, closes the connection and ends the thread.

A running function may not begin, commit or roll back a transaction; an authorizer refuses it. The thread's own transaction statements carry a marker comment so that a function cannot hit their entries in the statement cache. Callers are answered on the event loop with `call_soon_threadsafe`. A failed batch is retried only while the Db is open, because the stop has to end within the service manager's stop timeout.

## neoaprs/desktop/gtkenv.py

WebKitGTK and GTK come from the system, because a bundled WebKitGTK would have to match the
computer's graphics drivers. The AppImage carries only what a desktop with WebKitGTK may still
miss: the tray's AppIndicator library with its dependencies and typelib, and the WebKitGTK 4.1
typelibs. They are found without LD_LIBRARY_PATH, which would also reach the browser and every
other program the app starts: a carried library is loaded by full path (so a later load by name
finds it), and only where the system cannot load that name itself; GI_TYPELIB_PATH gets the
carried tray typelib where the system has none, and the carried WebKit typelibs only where the
system has the WebKitGTK 4.1 library but not its typelib. A system typelib always wins.

WebKitGTK 4.0 and 4.1 leave the web content's bubblewrap sandbox off unless WEBKIT_FORCE_SANDBOX=1
is set. It is set where user namespaces are allowed, bubblewrap and xdg-dbus-proxy are present,
and bubblewrap, tried once, can start a program in namespaces. The trial is needed because a
container's seccomp or a kernel switch can refuse them, and a forced sandbox that cannot start
leaves a window whose page never loads. Where they are refused (an AppArmor rule on recent
Ubuntu, a kernel without them) the content runs unsandboxed and the window shows only the app's
own page, since every other address goes to the browser.

GI_TYPELIB_PATH, WEBKIT_FORCE_SANDBOX and PYSTRAY_BACKEND stay in the environment of programs the
app starts, on purpose: each is read from the process environment by its library at load time,
so they cannot be confined to the app. For a child they add only typelibs for namespaces the
system lacks, a sandbox this system can start, and a choice only pystray reads.

## neoaprs/desktop/renew.py

The daemon replaces the AppImage file and restarts itself, but the app is a separate process
started from the same file and would stay the old version until quit. An app that started its
daemon therefore watches its own file. Once the file differs from the one the app started from,
is the same at two looks in a row (so a file still being written is not started), and the daemon
runs the new version, the app ends as Quit would but leaves the daemon running, releases the data
folder (lock, port, window size and place) and re-executes the new file in the same process with
`--owns-daemon`, so its Quit stops that daemon. Only an app that started its daemon does this;
one attached to a service is left alone. Windows needs none of it: the installer ends and
restarts the app. If the new file cannot be started, nothing is put back, because the daemon
already runs the new file; the daemon is stopped as Quit would stop it so none is left without
its app. Before the exec the web engine's helper processes are ended and waited for: left
running they would keep the old file's mount, hold the window profile the new window opens, and
stay as zombies the new program knows nothing of.

## neoaprs/desktop/session.py

A daemon that ends to restart as a new version has not ended: while its restart note is fresh the
lock is not checked (the check holds it briefly and the new daemon would find it taken and
exit). The watch follows only a port change: an address on another host than the session's is
never followed, whatever the daemon's file says. If someone else's daemon wins the lock while the
app's own starts, the app's ends and the app does not own the one it shows.

## neoaprs/desktop/shell.py

On Windows, pywebview falls back to the old Internet Explorer engine when WebView2 is missing,
and that engine cannot show the page; so without the WebView2 runtime (looked up in the registry)
no window is offered. The web window on Linux and macOS is a trial selected by NEOAPRS_WINDOW=web.
On Linux it needs GTK 3, WebKitGTK (4.1 API, else 4.0) with typelibs, and pywebview. The tray
needs pystray with its appindicator backend; pystray fails its whole import with a ValueError
when a typelib is missing, so any import failure means no tray. The program name is given to GLib
before GTK starts so the desktop finds the window's icon by the name neoaprs.desktop.

## neoaprs/desktop/single.py

A second app finds the lock taken, reads the port from the port file and sends `show`; `quit`
is sent the same way by the uninstaller. Nothing else is understood and those two words only
raise the window or end the app, which anyone who can write to the private data folder can do
anyway, so no key is needed. The lock goes with the process however it ends, so a crash leaves
no stale app (a stale port file only refuses a connection).

## neoaprs/desktop/sizekeep.py

The saved size and place are those of the unmaximized window: a maximize does not overwrite them
(the geometry before the latest burst of events is restored), and a minimise and its restore
change nothing. The place is the frame's top left corner. Wayland does not tell an app its place,
so it is not kept there.

## neoaprs/desktop/splash.py

The real window needs .NET, WinForms and WebView2 first, which takes a while; the splash needs
only user32 and gdi32 through ctypes. It shows the name on the dark background (the page's colour
scheme is not known yet) with no border, title bar or taskbar entry, on its own message-loop
thread. The packaging entry shows it before anything heavy is imported, so the module imports
only os, sys, threading and, on Windows, ctypes. A stale port file whose pid was reused hides the
splash for one start.

## neoaprs/desktop/webdesk.py

pywebview reports the place of the window's inside, but GTK places a window by its frame (title
bar included), so on Linux the frame's place is read with get_position on GTK's own loop. When
the close button is used with no tray to restore the window, the app quits as Quit would at once
if the session exists, else when it arrives; the close itself is always cancelled so the window
loop runs until Quit has stopped the daemon.

## neoaprs/desktop/webshell.py

pystray only asks its image to write itself as ICO, so on Windows the tray image is icon.ico as it
is (no imaging library is shipped there); elsewhere it is a Pillow image of icon.png. The tray icon
file is read in the thread that makes the icon, because pystray asks later in its own thread.

On Linux the tray is the StatusNotifier of the desktop (pystray's appindicator backend, forced,
because its other backends show nothing on Wayland). A desktop without a tray host gets no tray and
the close button quits; an app started in the tray waits a minute for the host. On macOS AppKit
objects belong to the main thread, so tray calls are queued with `PyObjCTools.AppHelper.callAfter`.
On Linux, GTK's show does not raise a minimised or covered window and maximize does not bring it
back from the taskbar, whereas pywebview's restore does and keeps a maximized window maximized.
Restore alone would un-maximize a maximized window on Windows and macOS.

Nothing that ends or controls the app waits for the window engine: the session is attached in a
thread of its own, the tray has a Quit and a second app's `show` and `quit` are answered before the
page is there, since WebView2 can take half a minute to start or fail without a word. An engine not
up after a minute leaves the app in the tray with the page in the browser. A Quit before the page
stops the daemon the app started once it is up. After Quit the process ends even if pywebview's loop
never returns.

## neoaprs/desktop/winplace.py

pywebview delivers each window event on its own thread, so a `resized` to full-screen size can
arrive before the `maximized` that preceded it. An event therefore only starts a timer, and the
timer asks Windows (GetWindowPlacement). The placement is saved when the window is hidden, at quit
and once it stops changing; it is restored before the first show (hidden), again once visible, and
on opening from the tray. SetWindowPlacement moves a rectangle that is on no monitor onto one.

## neoaprs/direwolf.py

Windows: the key drops by Direwolf's own clock, and the sound card's output delay must fit in the
default 100 ms (audio_win.c) or the end of the frame is cut; TXTAIL of 200 ms leaves room for a
slow card at the cost of 100 ms extra keying. On Linux the key waits for the card (snd_pcm_drain).
The good receive-level band 30 to 70 is a choice around 50, not a measurement. Slot 0 of KISSPORT
is cleared first because it holds 8001 until then, and a new port takes the first empty slot.
`PTT CM108` looks up the HID of the output device set before it, so ADEVICE precedes it. An AIOC
keys by CM108 whatever serial ports exist (its serial port keys only on DTR with RTS low). A serial
port not tied to the card is never keyed; it may be a programming cable or another radio.
Unopenable serial port: Direwolf exits; missing or unwritable CM108 chip: Direwolf runs unkeyed,
so the daemon ends it. With several CM108 chips Direwolf keys the last one.

## neoaprs/direwolfmodem.py

On Windows the keying claim `cm108` is held for the whole station, since Direwolf keys any
CM108-class chip. The program's `Ready to accept KISS TCP client` line repeats on every client
attach and leave, so only the first of a run counts.

## neoaprs/direwolfprogram.py

Stopping: closing the standard input pipe ends Direwolf like Ctrl-C (`-Q`, quit.patch: it sends
"QRT", sets every keying output to 0 and exits 0); then SIGINT on POSIX, the only signal it cleans
up on (direwolf.c:341); then a kill (`taskkill /T /F` on Windows). A daemon that dies closes the
pipe too, so Direwolf unkeys and ends by itself. Waiting up to STOP_WAIT_SEC frees the sound card
for the next start. On Windows the pid check cannot read command lines: the image must be the
shipped program and have started no later than the pid file was written, as a pid may be reused.

## neoaprs/direwolftune.py

A calibration run stops Direwolf by closing its input, keys the radio and sends until the daemon
closes the input after TUNE_SEC or KEY_TEST_SEC, then restarts Direwolf on the same KISS port.
Tune sends alternating mark and space tones; the keying test sends PTT alone, or the mark tone for
VOX, which silence does not key. A new transmit level restarts the program once presses of the
level buttons have stopped for SETTLE_SEC, because each restart leaves the radio deaf for seconds.
Swaps run one at a time and are given up if the radio was stopped meanwhile, otherwise a stray run
would key the radio with nobody to stop it.

## neoaprs/igaterules.py

Rules for gating a frame from a receive-only radio to APRS-IS, following the APRS-IS "IGate details" and q construct pages. A frame is not gated when it is not a UI frame, carries TCPIP, TCPXX, NOGATE or RFONLY in its header, or carries a q construct or the `,I` construct (these must never appear on the air). A third-party packet has its outer header and `}` removed and the inner packet is judged again. The path is kept as heard (the last digipeater passed marked with `*`) and `,qAO,IGATECALL` is appended, qAO being the construct for an IGate that cannot gate messages back to the air. The information field goes as bytes; APRS-IS lines end at the first CR or LF, so a packet with one inside is cut there, and a line is at most 512 bytes with its CR LF. The source must be a station: a call, not a placeholder (N0CALL, NOCALL, MYCALL, SERVER, which servers drop) and not a path or network name. The station's own call is not gated, because its position goes to APRS-IS directly. The 30 seconds of duplicate suppression belong to the service.

## neoaprs/loralist.py

The CA2RXU LoRa APRS iGate reports a packet's signal only in its list of recently heard packets.
`GET /received-packets.json` on port 80 of the KISS server's host returns at most 10 entries,
oldest first, each `{"rxDate", "rxTime", "packet", "RSSI", "SNR"}`, with bytes below 32 and 127 shown
as ".". Nothing else is requested from the board: `/configuration.json` holds the WiFi and APRS-IS
passwords, and writing it restarts the board.

## neoaprs/lorasignal.py

Each LoRa firmware reports the signal in its own way. A CA2RXU Tracker and the CA2RXU iGate's KISS
and TNC2 lines report none.

- DL9SAU's tracker appends an element to the path of what it hands over in KISS: `Q`, the SNR in two
  characters and the RSSI in two (`QA7L2` means -7 dB, -112 dBm). Left in, it would show as a
  digipeater, go to APRS-IS and be repeated, so every such element is removed and the first is read.
  After eight digipeaters the element is a ninth path address, which no AX.25 frame can hold.
- esp32_loraprs sends a KISS command 7 after each data frame: two big-endian 16-bit integers, the
  RSSI in dBm and the SNR times 100.
- The CA2RXU iGate with its TNC off on USB logs each packet as
  `<--- LoRa Packet Rx (RSSI:-73 | SNR:9.50 | FreqErr:120) : text`.
- The CA2RXU iGate's APRS bridge also hands on what it took from APRS-IS: a path with TCPIP, TCPXX
  or a q-construct is the internet's, not the air's.
- The iGate's list of heard packets names a packet by its text, with every byte below 32 and 127
  written as ".".

## neoaprs/mercury.py

Mode and frames. The broadcast port is KISS over TCP: unconnected datagrams of one modem frame
each, no acknowledgement, heard by every station on the same mode and frequency. The mode is fixed
at DATAC3, the narrowest that carries a whole APRS packet (9 carriers, 562 Hz), because a station on
another mode hears nothing and nothing on the air says which mode a station uses. A frame is always
3.8 s on the air from PTT ON to PTT OFF whatever its length (measured 3.80 s: the audio is 3.41 s
plus TX delay, preamble, postamble and tail) and carries 126 bytes, 3 of them header and a two-byte
length. Mercury silently cuts a longer KISS payload, so the daemon refuses or shortens such a packet
first. From handing a frame to Mercury to the packet at the far station takes 3.68 s on average and
3.78 s at most.

Ports. The modem programs listen on the local computer only. The UI interface (spectrum, transmit
level) is on the broadcast port plus 2000 (10100 by default) to avoid Mercury's own default UI port
10000, which an operator's own Mercury may hold. The control port is 200 below the broadcast port
where the daemon chooses the ports; for a Mercury run elsewhere that is an assumption (-b and -p are
independent) that holds at the defaults.

Channel-busy detector (modem/channel_busy.c, enabled in the ini). There is no carrier sense on the
broadcast plane, so two stations keying together lose both frames. The detector takes a spectrum
every 50 ms in 150 Hz bands over 300-2700 Hz. BUSY is declared when the loudest band is the
threshold above the slowly tracked noise floor for 300 ms; CLEAR when 3 dB lower for 1500 ms. The
default threshold of 10 dB suits a quiet channel, not a real band: a heterodyne or broadcast carrier
9 dB over the band noise holds the radio at 10 dB for as long as it lasts, and a 10 dB noise step
held it for 119 s of 120. 14 dB is the highest threshold that still sees a frame at 6 dB SNR
(DATAC3 delivers from 3 dB on a flat channel and three of four from 6 dB on a poor one); a weaker
signal is not heard as a carrier, and a collision with it costs the other station a frame it could
hardly decode. The threshold is a fallback only: while the spectrum is read, channelbusy.py decides,
which a step or a carrier does not hold. A BUSY longer than 20 s holds nothing, whatever the
threshold, because the noise floor rises slowly under a signal covering the passband (60-145 s) and
traffic must not be stranded. A frame is 3.8 s on the air, the detector hangs on 1.5 s more, and
successive stations' frames may run together for a few frames, so the cap is five frames and a
margin.

VOX lead-in. A VOX radio starts to transmit only after hearing audio for its attack time, losing the
first milliseconds of a frame, including the 110 ms preamble the far Mercury acquires on. The bundled
Mercury (packaging/mercury/leadin.patch) plays 150 ms of steady tone ahead of the preamble when the
ini says `tx_leadin_ms`; the daemon sets it for VOX only.

Frequencies. The stations meet on USB dial frequencies inside the IARU Region 1 digimode segments,
in gaps between known neighbours (proposals until confirmed on the air). Mercury is centred on
1500 Hz of audio, so the signal sits 1.2 to 1.8 kHz above the dial. 10.1476 MHz, the 300 baud HF
APRS dial, is not used. The mode is spelled out as USB so that nobody tunes LSB.

Tune and keying test. They use Mercury's TUNE command on the control port: `TUNE -dB` keys the
transmitter through the keying it was started with and holds a steady tone at that level in dBFS;
`TUNE OFF` unkeys, and Mercury unkeys itself after 60 s. This tries the same keying and sound card
as frames and touches no port Mercury holds. The tone is 1000 Hz, as VARA's TUNE sends (the only
frequency the control port takes), inside the 1200-1800 Hz the modes occupy, so an antenna tuner
matches where the signal will be. The tune level is Mercury's manual default, set at the sound card
like the frames' level, so the ALC reads as on a frame. Ten seconds lets an automatic tuner settle
and a meter be read, well under Mercury's deadline. The keying test is the same command for one
second at the quietest level TUNE takes (-60 dBFS), since TUNE needs a level. A line keying (RTS,
DTR, CM108 pin) goes up whatever the tone, so the radio transmits with next to nothing on the air. A
radio that keys on audio (VOX, its own data mode) stays in receive on a silent test, so its test
sends the tune tone at the tune level. Mercury keeps the tone out of its own gain, so the tone
follows the transmit gain in the daemon. A running tone cannot be retuned (a second TUNE is
refused), so the modem part ends it and begins again.

Dummy radio. The Dummy HF radio makes up what is heard and sends nothing on the air. What it sends
plays through the computer's speakers as Mercury's real audio: the bundled Mercury keys nothing
(`-P none`) on its `fifo` audio backend, two named pipes the daemon paces and plays. Without named
pipes (Windows) the speaker is not started, because Mercury on the default devices would play DATAC3
aloud, open the microphone and could key a VOX radio.

Sound cards. A radio's sound card names itself as a USB codec ("USB Audio CODEC", "USB PnP Sound
Device", "All-In-One-Cable"); the computer's own card is "HDA Intel" or similar. A radio's built-in
USB sound chip names itself differently from a dongle's generic "USB Audio Device", which tells two
candidates apart. USB vendor ids of the serial adapters in radios and interfaces: Silicon Labs,
FTDI, Prolific, WCH. The C-Media CM108 and CM119 chips have a GPIO that keys the radio (DigiRig
Lite, AIOC, dongles), but not every dongle wires the pin, so a serial line wins when there is one.
With one radio the system default device is right if the radio is the only sound device.

Mercury output. Mercury prefixes each log line with a time and run time (common/hermes_log.c):
`HH:MM:SS.mmm [+s] `, preceded by a date from 1.9.22 and followed by `Z` when `log_utc` is set;
older versions and the test fake print none. When the sound card cannot be opened Mercury keeps
running, deaf and mute, so the daemon ends it. A card that goes while it runs (unplugged, a USB codec that reset) is the
same: Mercury tries it for ever, deaf and mute, so its lines saying so (mercuryhelper.py) end the run
and the radio waits for the card through the back-off of a start. Another station's program may send a station message
besides APRS (Mercury 1.9.23 and later, modem/framer.h PACKET_TYPE_STATION), handed to the broadcast
client whole under KISS command 0x03 instead of 0x00; it is not a packet and is passed over.

#### Notes from comment pass 2 (list 03)

## neoaprs/mercurycards.py

Windows lists every sound card twice, as a recording device (id beginning `{0.0.1.`) and a playing device (`{0.0.0.`), each with its own id; opening a device the wrong way fails with AUDCLNT_E_WRONG_ENDPOINT_TYPE. The two devices of one card are presented as one choice named after the card, with the id `capture|playback`. A device alone of its kind serves its own direction only and the system default device serves the other. Windows prefixes a repeated device name with a number ("2- USB Audio CODEC"), each kind separately, so the two devices of one radio can carry different numbers; unpartnered devices count as one card when they are the only two of that name without the number. On Linux the ALSA card number can change after a reboot or replug, so a `plughw:N,D` id is stored by the stable card name (`plughw:CARD=name,DEV=D`).

## neoaprs/mercurychannel.py

The modem has no carrier sense on this plane, so `hold` supplies it: no frame goes while the radio is keyed or while the channel is busy, the latter for at most BUSY_HOLD_MAX_SEC, because the modem's fixed 14 dB detector can take a carrier or a step in the noise for a signal for minutes. A PTT ON without PTT OFF for KEYED_MAX_SEC is not believed (a choice, not a measurement); a stuck transmitter is the modem's own safety timer's business.

## neoaprs/mercuryclaims.py

On Windows Direwolf keys the last of several CM108-class chips, so only one radio at a time can key by CM108 there; the claim is for the whole station. A modem given the claims table holds its port pair, sound card and keying line in it, so a second radio's modem starts on another pair; without the table it finds ports by probing. Ports are chosen once per start and kept across a restart so the TNC, which waits with a back-off, finds the modem where it left it.

## neoaprs/mercurycontrol.py

The control port serves one host at a time. Newer Mercury versions close a second connection at once, before writing a word. One such close may simply be Mercury ending; two in a row mean another program holds the port. After an empty close the line is reported up only once Mercury writes, so a port held by another program does not flap between up and down.

## neoaprs/mercuryhelper.py

The shipped Mercury listens on 127.0.0.1 only (a patch to its sources). Its ports have no password, so a listener on every interface would let any host on the LAN key the radio; `foreign_listeners` checks this. The port probe binds with SO_REUSEADDR as Mercury does, so a port in TIME_WAIT counts as free and a restarted modem finds its old pair; on Windows that option would also take a port another program listens on, so it is not set there. A port listened on in IPv6 alone is not free. Adjacent port pairs share a port (the ARQ data port of one is the control port of the next), so the claims table hands out pairs whose four ports do not overlap. A Mercury left behind by a daemon crash keeps the sound card; its process id is written beside the configuration and ended at the next start. Mercury is asked to end twice before it is killed: the second request makes it drop the transmitter at once, while a kill could leave a radio keyed through a GPIO pin or serial line. On Windows Mercury's second request exits with the keying as it stands, so it is asked once, by a Ctrl-Break to its own process group (winchild.py says why not Ctrl-C), then ended with taskkill after STOP_WAIT_SEC; only after that hard end NeoAPRS lowers a serial keying line itself, opened with both lines low, since some drivers keep a line where a killed program left it.

## neoaprs/mercurymodem.py

Mercury says "Buffer full in capture buffer!" while its demodulator does not take what it records:
it then hears nothing and nothing else tells. A run of the warning without a gap of 5 s for 30 s is
a stall, so that a burst during a busy moment is none; the modem is started again through the
restart of a program that ended, never while it keys the radio, at most every 10 minutes. A stall
right after three restarts in an hour is not cured by restarting, so the program is ended with a
reason the page shows: a deaf modem would also send over others, its busy detector hearing nothing.

The hold is the carrier sense this plane lacks. While Mercury keys the radio (`PTT ON` until
`PTT OFF`) no frame is handed to it, so frames go one at a time and the services' pace counts from a
frame that has really left. While its busy detector hears a signal (`BUSY ON` until `BUSY OFF`) no
frame goes either, for at most BUSY_HOLD_MAX_SEC, because the detector can take noise for a signal for
minutes.

The ports are chosen once for a start and kept for a restart, so that the HF Tnc finds the modem where
it left it; if something else took the pair another is chosen and the owner is told. A program
listening beyond the loopback is ended and not run again: its ports have no password, and the shipped
Mercury listens on this computer only. A Mercury that something else runs is only listened to, on the
control port 200 above its KISS port; `serial/port` is never the sign of one. As the speaker of the
Dummy radio the program keys nothing and plays through the system's player; the Tnc is not connected
to it.
On Windows Mercury writes a log file of its own beside its program unless `-L` names one, and an
install for all users cannot write there, so it is given the radio's folder; Mercury rotates the file.

## neoaprs/mercuryscope.py

Mercury's UI interface (`gui_interface/ui_communication.c`, `spectrum_publisher_thread`, and
`modem_stats_get_rx_spectrum` in `modem/freedv/modem_stats.c`) sends a binary spectrum frame every
50 ms while the waterfall is on. The frame starts with the magic 0x4D435259, then the bin count and the
sample rate as little-endian 16-bit numbers, then that many little-endian 32-bit floats.

The bins are the first half of a 1024-point FFT of the last 1024 audio samples through a Hann window:
512 bins from 0 Hz to half the sample rate (7.8 Hz each at 8 kHz), in dB on the modem's full scale
(`FDMDV_SCALE` 825: a tone of amplitude 1650 of 32768 reads 0 dB). While the radio transmits, the
buffer holds the audio Mercury plays.

The audio level is worked back from that scale. The power of a bin, 10^((dB + 112.5) / 10) over the
window's 384, is the variance the audio has in that bin, and a band's share of the total variance is
its bins' sum over the 512. White noise of RMS s reads 20 log s - 112.5 + 25.8 dB in every bin. A test
against a real Mercury checks this with the simulated channel's noise of known RMS.

A row is two modem spectra averaged in power: ten rows a second at twenty spectra a second (about
seventeen on reception). A row byte b is ROW_OFFSET_DB + b * 0.5 dB, from -110 to +17.5; measured
channel noise reads -58 to -31 dB, a frame -15 dB at its strongest, our own signal +8 dB. The floor
under the rows is the page's business (`lib/waterfallfloor.ts`).

History is kept for two minutes: the monitor card's 400 lines are 80 s, and two minutes keep a larger
box whole. The bands of `bands_db` are cut as `channel_busy_update` cuts them (bins from 300 Hz up in
bands of 19, the last one short) so that the daemon's detector sees what Mercury's sees.
`scope_clock` uses the boot clock on Linux so that a row from before a suspend is correctly old after
it; Windows' monotonic clock already counts sleep.

## neoaprs/mercuryscoping.py

The spectrum is requested whenever the link is open, because the channel-busy control reads every
spectrum and rules the channel state while it is fed; Mercury's own detector rules otherwise. Rows are
built from every spectrum whether a page looks or not, and are forgotten when they would misdescribe
what follows: program stopped or restarted, control line down, new UI link. The spectrum just after
Mercury lets go of the radio still holds the end of its own frame (128 ms window; Mercury's busy
detector waits 300 ms). Without a link there is no scope and the gain applies at the next start, so the
controller restarts the program when the gain changes. Mercury's status, sent twice a second, carries
the peak of the latest transmission; it reports -120 before anything was transmitted.

## neoaprs/mercuryspeaker.py

Mercury runs on its fifo audio backend (raw s32le mono, 8000 samples a second, over two named pipes),
not on a sound card. A silent ALSA `null` capture device is not paced, so Mercury would read it far
faster than real time and flood its decoder. The daemon therefore acts as the sound card's clock: it
writes 20 ms of silence into the capture pipe at the pace of a sound card and reads the transmitted
audio from the playback pipe into the system's player (`pw-play`, `paplay` or `aplay`), which knows the
desktop's sound output where the bundled ALSA library does not. Windows has no named pipes and the fifo
backend opens a plain path, so the speaker is not started there; Mercury on the WASAPI default devices
would really play to the speakers and read the microphone, which breaks the Dummy radio's promise that
nothing goes on the air.

## neoaprs/mercurystale.py

A Mercury left behind by a daemon that crashed holds the sound card, the keying line and its ports.
Its process id is in `mercury.pid` beside its configuration. On Linux and macOS the process is ended
only if its command line runs Mercury with the radio's own configuration (`-C <ini>`), so the
operator's own Mercury, an editor on such a file and another radio's Mercury are left alone. Windows
reuses process ids and gives no simple access to a command line, so there the process must be running,
its program file must be the radio's, and it must have been created no later than the pid file was
written; `os.kill(pid, 0)` is TerminateProcess there and would end the process unchecked.

## neoaprs/mercurytune.py

Mercury keeps the tune tone out of its transmit gain, and refuses a TUNE while one runs ("transmit in
progress"), so following a gain change means ending the tone and beginning it again: a second of
silence in which the radio unkeys and keys again. The hold stays on throughout. Mercury unkeys by
itself after a minute. The keying test sends almost no audio where keying is a line (RTS, DTR, CM108)
and the tune tone where the radio keys on audio (VOX; a silent test would leave it in receive).
TUNE has no length, so a TUNE OFF that cannot be written while the control port is down is owed: the
test stays on the page with its Stop, and the owed TUNE OFF is the first line written when the port is
back and at the radio's stop. Stop pressed while the port is down ends the program, which drops the keying.

## neoaprs/mercuryui.py

The UI interface is enabled in the ini the daemon writes. It is optional: a Mercury without it is
logged once and retried slowly. The spectrum is switched on when someone wants it; the modem wants it
whenever the link is open, for channel-busy control. Mercury then sends twenty frames a second.

## neoaprs/migrations.py

The database file is versioned with SQLite's user_version and brought up to date by the ordered
steps in MIGRATIONS. Before the first step on a non-empty file the file is copied whole into
backup/ as premigrate-v<from>-to-v<to>-<time>.sqlite, unless a copy that this migration already
stands on exists from an interrupted start (backupfolder.py holds that rule). After the whole
migration succeeds the older copies are removed; a failed or interrupted migration removes none. If
no copy stands and none can be made, or the disk lacks room, nothing is migrated. The copy is taken
inside one read transaction that also checks the version, so it is the file at that version page for
page, whatever another process writes meanwhile.

While a migration runs, the note `neoaprs.migrating` says so and the process holds the lock
`neoaprs.migrate.lock`. A second NeoAPRS waits while the note stays fresh, then goes on from what
the first left. `neoaprs db set` and `neoaprs db restore` hold the same lock. The operating system
drops a lock when its process ends however it ends, so a held lock belongs to a live migrating
process. The note is kept fresh by a thread, so it proves that the other process lives, not that its
migration progresses; a step stuck on a dead disk would keep it fresh forever. Real migrations take
seconds to minutes, so the wait bound of one hour never cuts one short.

Each applied step is recorded in schema_history with a checksum of its source. An applied migration
is never edited; tests pin the checksums, and the steps keep their original annotations, which is
why they name sqlite3 and not the aliases of dberror.py.

Any step failure other than a database or OS error becomes a refusal with a reason, so the daemon
exits with status 2, which the service unit does not restart. A raw exception would exit with 1
and loop on restarts, each making another full copy.

Migration 32 rewrites the packet table in place, so until it commits the write-ahead log holds the
table a second time; the disk-room check counts the database size again for versions below 32. A
copy name gets a counter suffix when the clock is not past the newest existing copy, so the newest
name is always the latest taken. Whether a file was migrated on from a copy is decided by comparing
the schema_history rows, never by a clock, since a clock may step back.

## neoaprs/nodevices.py

The switch NEOAPRS_NO_DEVICES exists for bench daemons (tests, smoke tests, screenshots, proofs on a
copy of a real data folder) that run on a machine whose radios are on the desk and whose settings
may name the serial port, sound card and keying line of a radio and the operator's APRS-IS login.
Under the switch every door out of the program is shut, each by one call into this module where it
would open: serial and Bluetooth ports (`check_port`, `refused`), the Mercury modem and its sound
cards, every connection that leaves this computer (APRS-IS, a KISS TCP server, gpsd, rigctld, a
remote Mercury, the update check, suggested frequencies, the sked board, Send logs, Update now and
the map), the default alert command and the Dummy HF radio's audio.

What stays: Dummy radios, anything on the loopback (fakes of tests and benches) and the page's own
server, except the ports a real modem of this computer listens on: Direwolf's default KISS and AGW
ports, Mercury's UI port and the ranges NeoAPRS tries for its own Direwolf and Mercury (Mercury
uses four ports per pair: broadcast, control, ARQ data, UI). A fake listens on a port the system
hands out.

A shut door behaves like a missing device: the checks raise the system's own error for a missing
file or a refused connection, so the caller waits and reports as for an unplugged radio or a server
that is down. The log has one line at the start and one line per door the first time it is refused.

The variable is read only here, each time it is asked. Every value that is not empty and not `0`
sets the switch, so `true`, `yes` or a typing slip keep the doors shut too: a mistyped value must
never be the reason a bench daemon keys a real radio. The urllib proxy handler is dropped under the
switch so that a loopback address is not sent to the proxy named by `http_proxy` or the system
settings, which would be another computer.

## neoaprs/packet.py

The duplicate key (source, destination without SSID, information field, not the path) follows the
APRS-IS server's own duplicate test and the Direwolf digipeater algorithm. Every consumer that puts
packets on APRS-IS must check `packet.via in GATEABLE` first: a packet from the internet would go
round in a circle, and the made-up traffic of the Dummy radio must never reach the real network. A
new channel is not gateable until it is added to that set on purpose.

## neoaprs/packetcodec.py

The channel of a radio packet is derived again from the frame when a row is read: rf-gated exactly
when the information field holds a third-party header; the stored column only serves SQL
statements. JSON of a decoded packet refuses NaN and Infinity because they are not JSON and SQLite's
JSON functions reject a row holding one.

## neoaprs/packetlog.py

Station writes are coalesced: a changed station is only marked dirty and written at the next flush,
because on an SD card a station heard ten times between flushes would otherwise cost ten writes of
its 1 to 3 KB row. Prune deletes run in slices of 5000 packets, one transaction each, so other
requests are served in between and the write-ahead log stays small; internet packets are the bulk
of the file and so get their own retention bound. The all-stations hourly count scans a day of the
log and is cached briefly. Track points are parsed with fromisoformat because strptime is too slow
for a week of rows.

## neoaprs/pairsetting.py

A pair's call is the station's base call with the pair's SSID (1 to 15). A save refuses a
non-pair key, a pair with a receive-only radio, a Dummy radio beside a real one, a bad value, and an
SSID that is the station's own or another enabled pair's. A pair left enabled with no SSID sent gets
the highest free SSID counting down from 15 when it has none stored or the stored one is taken
(by the station's call as it was before the save, or by another enabled pair); a free SSID that a
disabled pair still stores is avoided when possible, because that pair keeps its call when it is
switched on again. A pair the values do not name is never changed, and a pair whose SSID this save
chooses again is not counted as holding its old one.

## neoaprs/pmtilescut.py

A cut reads only the PMTiles header and the directories the box reaches into, then writes the tiles
of the box down to the requested maximum zoom as a clustered archive in which shared tile contents
are stored once. The size is known before any tile data is fetched, so a cut over the byte limit is
refused up front. Pieces next to each other in the source are fetched as one request, and so are
pieces separated by gaps as long as the gaps total at most 5 percent of the data (smallest gaps
first, as go-pmtiles does). The archive is written to a `.part` file beside the target and moved into
place when whole.

## neoaprs/pmtilesformat.py

A PMTiles v3 archive is a 127-byte header, a root directory within the first 16 KiB, JSON metadata,
leaf directories and tile data. A directory is columns of varints (tile id deltas, run length,
length, offset; an offset of 0 means "follows the previous entry"), compressed as the header says.
An entry with run length 0 points to a leaf directory. A tile id counts the tiles of the lower
zooms and then follows the Hilbert curve, so one quadtree quadrant is one range of ids; a box
therefore becomes a list as long as the curve enters and leaves it, not as the box has tiles. When
writing, the root directory alone is used if it fits beside the header; otherwise leaves of at
least 4096 entries are made, growing by a fifth per try as in go-pmtiles, until the root of their
pointers fits. Runs are cut to the part inside the box, as go-pmtiles does.

## neoaprs/pmtilesplan.py

The plan reads the root directory and, level by level, the leaf directories that reach into the box;
the entries of the tiles in the box are kept in tile id order. Each tile content gets its place in
the new tile data the first time a tile names it, so the archive is clustered and shared contents
are stored once; a content is known by its source offset, found by bisection when it comes in source
order and from a dict for the few that come back from before. The pieces to fetch are then grouped
into requests. The new header's bounds and centre are the box's in 1e-7 degrees, truncated toward
zero as go-pmtiles does; the whole world keeps the source's.

## neoaprs/pmtilesrange.py

A server must answer a range request with 206 and the matching Content-Range, for an archive whose
size does not change; any other answer is refused without reading the body. A request that fails,
is cut short or gets a "try later" status is repeated after each pause. Bytes arrive in pieces and a
stop is checked between pieces; an abort shuts waiting connections. https goes through the project's
opener and the no-devices switch, as does every redirect, which may not leave https for http. The
download threads are daemons: one still waiting for a server when the cut ends is left to end by
itself and what it delivers late is ignored.

## neoaprs/policy.py

The ALOHA circle follows the published description of the ALOHA circle on aprs.org: the radius
within which stations heard fill a 1200 baud channel (about 60 packets a minute). The window of 60
minutes is longer than the published 30 so that a home station beaconing every 30 minutes is not
missed; the speed threshold for "in motion" is chosen because a parked GPS drifts a few km/h.

## neoaprs/radiotype.py

The numbers of the kinds (radiotypes/common.py makes the `Limits` and `Allowed` of each from them):

- FM: paths and the fill-in digipeater of the VHF network, SmartBeaconing for a moving station,
  beacons from 20 minutes (the net cycle of a 2-hop path), AX.25's own frame limit.
- HF (Mercury): no path, because every station hears every frame direct and a path costs bytes of
  a 123-byte frame. No digipeater, because a repeat only fills a channel every station already
  hears. No SmartBeaconing, because a report every few tens of seconds would take the channel from
  everyone. The station's one beacon interval has a floor of 30 minutes (a 3.8 s frame on a shared
  channel). A random pause of up to 300 s comes in each slot of the interval, because fixed stations with stable
  clocks that started together would otherwise key up together every interval; FM has one of up to 30 s, and the
  status, our objects' and bulletins' repeats and the first beacon after a start have the radio's pause too
  (docs/daemon.md, "The random pause"). The size was
  measured with `scripts/mercury-measure beacons` (docs/mercury.md): at a 30-minute interval,
  stations started within a minute lose 14 percent of beacons with two stations and 43 percent with
  five without the pause; with a 300 s pause the loss is 0.8 and 2.7 percent, near the floor of
  chance (0.4 and 1.6), while a 120 s pause leaves 1.3 and 5.0. A lost beacon is made up by the
  next. Frames are up to the 123 bytes the mode carries.
- LoRa: paths, as LoRa networks use WIDE1-1 and their iGates repeat it; no digipeating by us (a
  second repeat would hold the shared channel twice as long); SmartBeaconing, whose fastest rate
  (60 s) is the trackers' own. A frame takes 2 to 4 s on the air at SF12, close to Mercury's 3.8 s,
  on one shared channel, so the beacon floor, jitter and retry pause are HF's (firmwares beacon
  every 15 minutes); the pause was measured for a 3.8 s frame, not on LoRa. Frames are up to 250
  bytes, which the boards take over KISS whole: their 255-byte buffer counts the KISS bytes around
  the frame (FENDs, command byte and escapes; the CA2RXU iGate clears its input past 255 bytes
  before the closing FEND), so a frame whose escapes would not fit is shortened or refused too
  (the KISS frame limit is 256; 250 leaves room for three escapes). On the air a packet is the
  text after a 3-byte header in a 255-byte buffer, so 252 bytes of text.

The HF retry pause (up to 20 s before each message retry) exists because two stations that
collided would otherwise retry at the same moments and collide again. A frame keys the radio for
about 4 s and the channel-busy check needs about a second to see another station start.

## neoaprs/radiotypes/dummylora.py

Every LoRa type has no digipeating by us, since the network's iGates already repeat WIDE1-1 and a
second repeat would take the shared channel twice as long, and no ALOHA circle, which is worked
out only for a shared 1200-baud channel.

## neoaprs/radiotypes/lora.py

Frequency and modem settings of a LoRa board are the board's own, and no field offers them, because
no firmware lets a program set them safely: the CA2RXU iGate's page write replaces every setting
and restarts the board, and KISS has no command for them. There is no Find, because opening the
port may restart a board and a board in KISS is silent until it hears a packet; and there is no
port search either.

The three LoRa types are `lora-tcp` (the default: a CA2RXU iGate on the network, whose list of
heard packets gives each packet's signal), `lora-serial` (a device, `bt://` or `ble://`) and
`lora-console` (a CA2RXU iGate's USB log, which only receives).

## neoaprs/radiotypes/soundcard.py

The sound card and keying settings are the same as the Mercury modem's, so one card is one
resource whichever type uses it.

## neoaprs/radiotypes/tnctext.py

The receive-only text radio (a Yaesu FTM on its data port, or a TNC in monitor mode) prints what it
hears as text instead of KISS. Its line, the search of an empty port (which only listens), the
claims, the Terminal and the reopen are those of any serial TNC. It is allowed no path, digipeater
or SmartBeaconing, is no e-mail radio and no shared channel; its fields are the port and the speed.
What it hears goes to the map, the log, the station book and the iGate as from any radio.

## neoaprs/reading.py

A signal reading is tied to its frame where the frame is made. Mercury says the SNR before it hands
the frame over, so a reading waits for the next frame for at most one second: Mercury's broadcast
port hands a frame over within 0.1 s of its SN line, and the next frame is 3.8 s away. Mercury's
SNR is scaled to 3 kHz. A LoRa board says the reading after the frame: the esp32_loraprs firmware
sends KISS command 7 right after it (a wait of 0.5 s, not measured), and the CA2RXU iGate says it in
its list of heard packets (a wait of 2 s, not measured; a LoRa frame takes 1 to 9 s on the air).

## neoaprs/recent.py

The table is pruned only once it has grown past its limit (2000 keys, more than a channel carries in
the 30 s window), so a busy channel costs bounded memory and a quiet one costs no pruning.

## neoaprs/selfreplace.py

Replacing a running AppImage keeps the old file beside the new one as `<file>.old` until the new
version has started, and puts it back if the new one cannot be started.

An AppImage started with `--appimage-extract-and-run` (a system without FUSE) runs from an unpacked
folder, and the runtime removes the flag before the program sees it. The new file is therefore
executed with `APPIMAGE_EXTRACT_AND_RUN=1`, or its runtime would try to mount it and fail. A
mounted image is executed again without it, since unpacked it takes some 430 MB of the temporary
folder.

The mount lives as long as a descriptor does: the runtime hands the program the read end of a pipe,
and the process serving the mount ends, unmounts and removes the folder when writing to the pipe
fails. So "was this mounted?" must be asked while the descriptors are still open; the exec closes
them (they are marked close-on-exec, not closed earlier), so the mount this program runs from stays
until the new file has replaced the process, and also if it cannot be started. Where descriptors
cannot be listed (no /proc) they are closed at once.

The runtime unpacks one file into one folder shared by all runs and removes it when its program
ends, even while another process (the daemon) still runs from it. `NO_CLEANUP` makes the new
runtime leave the folder; this process's own runtime still removes it at its end. A value of
`NO_CLEANUP` the operator set is kept, which is why the value NeoAPRS sets is its own word. Around
the exec the variable is removed so the new file unpacks into its own folder, which only its own
runtime removes; for a restored old file it is set again because that file shares its folder with
the app, whose runtime removes it.

## neoaprs/sendonrule.py

A change of the radios keeps in force what would otherwise stop. Only a radio that comes on (can
send now, could not before: added, switched on, given a type that sends) can stop something. The
change is read alone, with each radio's ticks as they were before (a new radio counts as unticked,
so its default tick does not stand in for what it would stop), so a save that also unticks
something is not undone, and a save that changes ticks alone keeps nothing.

For the e-mail radio: while no choice is stored or the stored one is not on, the radio the mail
went on stays; but if that one is of a type internet gateways do not hear and a radio that comes on
is one they hear, the first such radio that comes on takes over.

A new object or bulletin is ticked for: the one radio that can send, if there is one; else the radios
the one saved last went on while one of them is on; else the first radio that can send, in box
order. While none is on: the radios of the last save that are still the station's, else the first
radio of the station that can send though it is off, and radio 1 only while the station has none (a
new installation: the thing goes out once a radio is there).

## neoaprs/serialboards.py

Development boards and debug probes are known by their USB ids and the search for the radio never
opens them: their USB console resets the chip, or drops it into its boot loader, when a program
opens or closes the port (the kernel and pyserial toggle DTR and RTS), so opening one to see
whether a radio answers resets whatever runs on it. None of these is a TNC or a radio's USB port;
a board that is one is chosen by its name (`serial/port`), which is never filtered. The generic
USB-serial bridges (FTDI 0403, Silicon Labs 10c4, WCH 1a86, Prolific 067b) and the TNCs' own ids
(ST's serial port 0483:5740, used by the Mobilinkd TNC4) are not listed. Vendor 16c0 is shared by
other makers, so only the Teensy's serial product is listed. 303a:1001 is Espressif's USB
Serial/JTAG console, and the vendor also covers the native USB of the S2, S3 and C3.

## neoaprs/serialport.py

A line is a serial port (`/dev/ttyUSB0`, `COM3`), a TCP socket (`socket://host:port`, KISS over TCP
such as Direwolf on 8001; `tcp://host:port` is accepted for it), on Linux a Bluetooth serial port
paired with the system (`bt://AA:BB:CC:DD:EE:FF`), and on any system a Bluetooth LE KISS TNC
(`ble://...`).

`SerialPort` reports what happens as signals and never reopens by itself: the TNC that owns it
decides when to try again. The control lines are set low as soon as the open allows, because a
sound-card interface keys the transmitter on RTS. The open runs in a thread (a Bluetooth COM port
can take seconds to say no) and each open line has a reader thread and a writer thread, so nothing
waits on the event loop and no descriptor is given to the loop, which Windows could not do for a
serial handle; the loop gets the bytes by `call_soon_threadsafe`, in order. The pyserial socket
close sleeps (and a Bluetooth link closes slowly), so a socket line is closed in a thread.

A TCP line quiet for a minute is probed every 15 s, four times, so a board that lost power is found
gone in two minutes. pyserial opens a file for a `spy://` address, so the settings' scheme check is
repeated before it is handed over.

## neoaprs/serialprobe.py

Windows makes two COM ports for a paired Bluetooth device: the device's own, whose BTHENUM hwid
ends in the device's address, and the computer's incoming one, whose address is twelve zeros. The
incoming one reaches no device and takes no data, so it is not offered and a radio set to it waits
with `radio.incoming_port` until its settings change, as `MAC_LEFT_OUT` does on a Mac.

The search writes to the ports it listens to (a carriage return, to wake a TNC in command mode),
and a port that is not a TNC may be a GPS, a rotator or an interface that keys a transmitter. The
automatic search therefore runs only where ports are USB serial adapters under `/dev` (Linux). On
Windows and macOS the radio is the named or remembered port, which the operator picks from the
list or finds with Find my radio, run on a click over the system's list: the COM ports on Windows
(a paired Bluetooth serial port is one), the `/dev/cu.*` devices on macOS.

The search listens for ten seconds before writing a CR: a TNC in command mode answers it, one in
KISS mode ignores it. Each port is nudged once per search. Listening ports are listed again every
ten seconds, so a port that appeared is opened and nudged and one that vanished is closed. Listing
again instead of ending after a time matters because a search with no limit is what the Tnc asks
for, and a restarted search would see the same ports and leave a new port, or the named port the
search stands in for, unheard while another port keeps talking. The latest 16 KiB a listening port
heard are kept for the validity test, which bounds memory against noise.

A port is never opened or written to when another process has it open, when another radio of the
station holds or is set to it, or when it is on the skip list. A device that appears under several
names (a `/dev/serial/by-id` link and its ttyUSB node) is one claim, compared by resolved name; a
KISS TCP address is a connection, not a device, so two radios may each have one to one server.
Find my radio tries USB adapters first, then other serial ports, then Bluetooth serial ports, which
are slow to answer and have no line speed. The settings name the serial devices of every enabled
radio, so a device a radio is set to is left out of every other radio's search, whether or not
that radio has opened it yet; radios that are off count too for the keying choice, which a modem
keeps while it runs, so a radio switched on later does not find its TNC's port keying another.
On macOS a device has a call-in (`tty.*`) and a call-out (`cu.*`) node, and the call-out is opened.

## neoaprs/services/alerts.py

With `messages/alert` on and `messages/alert_command` set, the command runs through the shell
(PowerShell on Windows) with these variables in its environment:

- `NEOAPRS_KIND`: `message` or `station`.
- `NEOAPRS_TITLE`: the notification title, "APRS message from OH2XYZ" or "APRS alert: OH2XYZ".
- `NEOAPRS_FROM`: the sender's call, or the station's.
- `NEOAPRS_TEXT`: the message text, or what happened ("OH2XYZ is on the air").
- `NEOAPRS_AT`: when it was heard, ISO 8601 in UTC (2026-10-21T12:00:00Z).
- `NEOAPRS_MSG_ID`: the sender's message id; empty if none and for station alerts.

The text travels in the environment, never in the command line, so a stranger's text is never read
as shell. The command is killed with everything it started after the timeout (20 s; 60 s on Windows,
because a cold PowerShell on a busy machine can take longer than 20 s to show a toast). A failure
is logged as a warning once an hour, then at DEBUG; nothing raises. At most five alerts run at
once, so a flood of messages does not start a flood of programs. The PowerShell script goes in on
standard input (`-Command -`), because an encoded command or an execution policy bypass looks like
malware to Windows Defender; `-OutputFormat Text` keeps stderr from being XML. The prelude is the
Windows counterpart of `set -e`, and the postlude passes on the status of a failed program.

## neoaprs/services/answers.py

The frames of an answer go out by the asker's path on the radio the request came on, the first at
once and the rest SPACING_SEC apart. A server may delay the first frame so its answer does not
collide with digipeaters repeating the request; the answer then counts as given at once, so copies
of the request arriving meanwhile are not answered again. The same station asking the same query
within the duplicate window is answered once. All answers together are held to two of the longest
answers (ten frames) in 60 s, so a station asking under a new call each time cannot get more; an
answer that does not fit whole is not sent. Nothing is sent under the transmit interlock or while
the radio is unusable. A frame stamped in the future (the clock was set back) is dropped from the
budget instead of holding the window shut.

## neoaprs/services/asking.py

A directed query is a message whose text is the query, sent once without a message id, because
queries are not acked and not retried. It is kept as an unconfirmed outgoing message whose text
begins with `?`. The same query to the same station is refused within QUERY_EVERY_SEC; a query
refused for any other reason does not count.

## neoaprs/services/beacon.py

A fixed station beacons every `beacon/interval_min` minutes (raised to the radio's own floor); a
moving station on a radio with SmartBeaconing asks SmartBeaconing at every tick instead, using a
GPS fix no older than the stale limit. With no fresh fix nothing is built or sent and the home
position is never substituted. The beacon goes out only on the radios selected by
`beaconrule.beacon_radios`. An interval of 0 turns the timer off, but a send on request still
sends; transmitting as a whole is the interlock's (`station/transmit`). A moving station on a radio
without SmartBeaconing (HF) sends its fix but is planned by interval.

Each timed beacon goes after the radio's random pause in its slot, and the next slot counts from the slot. The
first beacon is `first_delay_sec` and the pause after start, unless the last one of an earlier run (kept in
the radio's memory row) is less than an interval old, so a restart does not send another. A beacon
due while the radio is disconnected or silent stays due and goes out at the first tick the radio is
usable, one beacon however many intervals passed. A refused frame is retried every few seconds,
six times; then the interval is skipped (a moving station is tried again after 60 s). A connected
radio that is unusable is settling after KISS ON, so the wait is quiet.

## neoaprs/services/beaconframe.py

Frames are built from the settings for any radio and differ between radios only by the radio's
digipeater path and by a comment cut to fit its frame. The position is always the uncompressed
form with the PHG extension when `beacon/power_w` is set. A moving station sends the GPS fix of
now, and with no fresh fix there is no frame; the home position is never substituted. The status
report is never cut; one too long for a radio is no frame for that radio. A position frame too long
for a radio with a fixed frame size has its comment cut, logged once per radio and cut. The
position field for the receive-only iGate transmits nothing, so the interlock is not asked. A radio
may still arrive as the old `services/common.Radio` shape, which is wrapped as an AirRadio; with
the legacy flag any radio that has an `rtype` is treated as old-shape, so its choices come from the
station's settings rather than its own.

## neoaprs/services/bulletins.py

The inbox hands over every message to a board addressee; none is acked. A sender repeating its slot
with new text replaces the entry and resets the hearing count; the same text only counts, and
copies arriving within ten seconds of the last hearing are one hearing. Entries leave only when the
operator deletes them. Only what was heard on the radio is recorded.

## neoaprs/services/delivery.py

A copy of our own message heard again (same addressee, id and text, from our call; by RF or wrapped
by an iGate as third-party) is linked to the latest attempt sent before it, and the hops its path
shows are kept for that attempt, the first hearing of each staying. Acks, rejects and copies of
messages we did not send are not linked.

## neoaprs/services/digipeater.py

The fill-in digipeater sends a heard packet again, once, if its path asks for us. The first unused
hop of the path decides. `WIDE1-1` is replaced by our call marked as used:
`OH2XYZ>APRS,WIDE1-1,WIDE2-1` goes out as `OH2XYZ>APRS,OH2GBA*,WIDE2-1`. Our own call with our SSID
is marked as used where it stands. Any other first hop is not ours, and a path with no unused hop
is finished. Never repeated: our own packets, a packet already showing our call as used, a packet
whose path says it came from the internet (TCPIP, TCPXX; NOGATE and RFONLY are repeated), and a
duplicate. A duplicate is the same source, destination without SSID and information field heard or
sent within the duplicate window, whatever the path (WB2OSZ's digipeater algorithm). A third-party
packet counts only by the path before the `}` (APRS 1.2, chapter 17). Only the path is re-encoded;
every other byte of the heard frame is kept.

Nothing goes while the interlock refuses or the radio is unusable. A fill-in is useless when late,
so it bypasses the sender's pacing; at most a burst limit of frames goes out per window and the
rest are dropped. The TNC's channel access still decides when a frame is on the air.

The digipeater is a table of rows "heard on radio A, sent on radio B"; only A to A rows are made
here, for each enabled radio whose type may digipeat (not HF) and whose own `digipeat` is on. The
duplicate check, burst limit and counts are per outgoing radio. Rows between two radios are in
services/passrows.py.

## neoaprs/services/frequencies.py

The file is a few hundred bytes. Requests are limited to one per interval whoever asks. The server
may be replaced by a local one for tests through an environment variable.

## neoaprs/services/generalask.py

A general query makes every station that hears it transmit on a shared channel, hence the
per-radio wait between queries of a kind. RFONLY is appended by default so iGates keep the query
off APRS-IS. A press is all or nothing: if any ticked radio is inside its wait, or a path makes no
frame on one, nothing is sent. Newcomers are stations heard within the counting window after the
query that were not heard on that radio in the quiet period before it; a beacon in the window
counts too, and a newcomer is counted once however many radios heard it. State is lost on stop.

## neoaprs/services/gps.py

State is off, connecting (no connection or fix yet), no_fix, fix, or stale. `current()` never
substitutes the home position. `mobile_fix()` returns the latest fix even when stale, so a lost GPS
leaves the map row where the station was last seen. A save of the gps settings restarts the feed in
a task so the save does not wait for a gpsd that does not answer. `moved` is emitted when the fix
is far enough from the map row, at a limited rate.

## neoaprs/services/igate.py

The service has no radio: it takes the connection, the settings and functions giving our position
bytes and location. It knows of the radios only whether an enabled radio is a Dummy type. With a
passcode it gates what the radio hears; without one, or one the server rejects, it logs in
read-only. The connection filter is the map radius around our position, resent when the station
moves more than a set distance or the radius changes. Packets are also not gated while the
connection is unverified, nor when the same source, destination without SSID and information
field was gated within the duplicate window (servers drop such copies anyway; the window can be 0).
A fixed station sends its position when the login is verified and periodically after; a moving
station also sends each beacon at a limited rate. Building it needs no transmit interlock since
nothing is transmitted.

## neoaprs/services/inbox.py

A message to us is kept as received and, if it has an id, acked at once. The same id and text from
the same station within the duplicate window is not kept again, and is acked again only after the
ack-again interval. A packet from our own call (a digipeater's or iGate's copy) is handed to the
host, which links it to the sent message.

Text such as `ack12` or `rej3` is an ack or reject only if it quotes a message of ours to that
station; otherwise it is ordinary text. A query is never kept, but a query carrying an id is acked
so the sender does not retry. Telemetry definitions (PARM., UNIT., EQNS., BITS.) are neither kept
nor acked.

Reply-acks: the `AA` of `{MM}AA` settles our message with that id and is acked as `ackMM}AA`. A
`{MM}` message tells us the sender knows reply-acks, so its id is carried as the `AA` of our next
message to that station until the station answers one of ours.

A message to the addressee QRU is a request for a QRU server. If the server takes it, it is
answered there, never acked (an ack from our call would match nothing at the asker) and not kept;
otherwise it is overheard. A QRU server's answer to our own request is neither kept nor acked.
A message to a bulletin, announcement, group, ALL, CQ, QST or weather-bulletin addressee is no
conversation and is never acked: it goes to the board, or is overheard if there is none.

A message is to us when its addressee equals our call including the SSID (no SSID equals -0). A
third-party packet counts as its inner sender's, also when that name is not an AX.25 call. The
first copy of a message to us is also passed to the alert hook.

Encrypted messages: a text announcing the sender's key is kept as `key`; a sealed text is opened
with the shared key and kept with the plaintext (`open`, ciphertext as `wire`), or as received if
it does not open (`shut`). Both are acked. An overheard sealed message is `shut` and an overheard
key announcement `key`.

## neoaprs/services/messageradio.py

An outgoing message keeps the radio of its first attempt until it ends, so its attempts and their
acks stay on one channel even if the station is heard on another radio meanwhile. The message
leaves that radio when the operator chooses another radio for the station (the Route setting, or
the e-mail radio setting for mail) or the radio is disabled. The choice compared is the one in
force: a choice naming a disabled radio counts as none. The next attempt is then fitted to the new
radio. After a restart the kept radio is the one the last attempt went on, unless a choice moved
it. A radio that only stood in for the station's own (it never heard the station and no Route names
it) is kept only until a radio that heard the station is enabled again.

## neoaprs/services/messaging.py

Outgoing: the addressee and the printable-ASCII text are checked, the message gets the next id (two
characters, 1296 in all, skipping ids still in use), is kept as "sending" and transmitted at once
as a UI frame. Every frame carries its number as a reply-ack, `{MM}`, or `{MM}AA` when the station
sent a message whose ack has not reached it yet; each attempt is built when sent, so a retry
carries the latest. Attempts follow the message schedule (4 attempts, 2 for the e-mail gateway);
the last is waited for a final period, then the message is "failed", or "unconfirmed" if only 1 or
2 attempts were allowed (a late ack still settles it). A message to a bulletin or group, or a
directed query, is sent once without an id and kept as "unconfirmed".

An encrypted message is sealed once when written, with the key shared with the station. The record
keeps the text and the sealed wire form; every attempt sends the same bytes, so the addressee's
duplicate check sees one message. It is refused when encryption is off, the station has no
announced key, or the text exceeds 34 UTF-8 bytes.

Only one message to a station is on air at a time: later ones wait with no attempt until it is
acked, rejected, failed or cancelled, so they arrive in order and a silent station is not sent
several at once. The one on air is the one with an attempt, else the oldest. Messages expecting no
ack (1 or 2 attempts) neither wait nor hold others. The database keeps a waiting message as
`sending`; the page is told `queued`.

While the TNC is disconnected, the radio is silent or transmit is off, a due attempt waits without
being used up, and running waits are moved on by the time away. A new message or retry is refused
at once when transmit is off; acks for received messages are not sent.

Incoming: an ack is `ackMM`, or `ackMM}` for `{MM}` and `ackMM}AA` for `{MM}AA`, as the reply-ack
form requires. A message to another station that is only heard is kept as "overheard" (once per
duplicate window). A bulletin or group message goes to the board and is never acked; a query or
telemetry definition is not kept.

Every message is held in memory as well as in the database and none leaves on its own. A start
loads the latest messages up to a limit and warns if there were more.

A station may have its own path (preference book); otherwise attempts 1 and 2 use the recently
heard path, else the beacon path. Every message and ack to a station uses it, with RFONLY after it
for an RF-only station. A path that would exceed 8 digipeaters with it is no path: a new message
is refused, an attempt waits, an ack is not sent.

## neoaprs/services/mobilebeacon.py

The mobile beacon's information field is a compressed position (`=` and 13 bytes: position, symbol,
course and speed from the GPS fix) then the comment: the altitude `/A=aaaaaa` if the fix has one,
then the station comment cut to the 40 characters a compressed report may carry. There is no PHG
extension, as a compressed position cannot hold one.

## neoaprs/services/ownbulletins.py

A bulletin has no message id, so nobody acknowledges it. The schedule sends it a few times early,
then at a long interval (the specification: bulletins "a few times an hour for a few hours",
announcements "less frequently but perhaps for several days"). Repeats keep at least the floor of
each radio they go on. The packet goes on every radio of the bulletin in one round, each radio
with its own path. The sender holds back frames while the call is not set, the radio is unusable
or inside the spacing; what was missed goes out once when it is back. After the last send the
entry stays on the board as ended. Send counts and times are stored, so a restart resumes the
schedule. The inbox treats a packet from our own call as a copy of what we sent, so the heard
bulletin board never holds ours.

## neoaprs/services/ownobjects.py

The schedule is the decay algorithm of the specification's Packet Timing: a new or changed object
goes out at once (at least a minute after its last packet), then after 1, 2, 4 ... minutes, never
further apart than the net cycle time of its path, or the beacon floor of a shared-airtime radio.
A kill sends the killed form three times, then the object is forgotten; one never sent is simply
removed. An object marked on-request is shown on the map but only sent as an answer to a query,
so killing it is removal too.

An object goes out on its radios as the set is in force, in one round. Its path is used on each
radio that may carry one (none on HF); the wait is the longest of those radios. A new object
without named radios uses the last saved set; a changed one keeps its own. A kill goes on its radios
in force plus every radio that took a live frame of it in this run (kept in memory only).

Another station reporting an object of our name takes it over (the specification's "Replacement"):
ours is dropped silently. The station book ignores a packet from our own call that comes back
(digipeater copy, TNC echo), so there is no second object. Stations simulated by the Dummy radio
take nothing over.

## neoaprs/services/passback.py

A passed message is remembered for 600 s, longer than the sender's own retry schedule of about 6
minutes, so an ack heard on the far radio can be sent back once.

## neoaprs/services/passlimits.py

A fast radio has a burst limit of 4 frames sent again per 10 seconds, shared by the fill-in and the
pairs. A slow radio takes at most 4 frames from the pairs per 300 seconds (four frames are 15.2 s
of keying in 300 s on Mercury); at most 2 of them are of kind "other" (positions, status, objects,
telemetry), the rest being messages and acks; at most 2 messages come from one source (acks and
rejs are not counted); and a frame of kind "other" is taken once per source within the radio's
floor. Frames handed to a slow radio are at least one frame time apart, because Mercury keys only
at PTT ON.

## neoaprs/services/passrows.py

A packet heard on one radio of a pair goes out once on the other when its path names the pair's
call. Each radio has its own table of what it heard and sent, the limits of the target radio apply,
one frame may wait for a slow radio, the ack of a passed message goes back once, and counts are kept
per pair and direction in the radio's stats. A pair passes only while it is enabled, both radios
are senders and may pair (both transmit, both Dummy or both real), the station call parses and the
pair's call is neither the station call nor another enabled pair's. Nothing is logged at WARNING,
as the operator cannot act on a held frame; the first of each reason per direction is logged at
INFO.

The rows cannot guard one case: a frame of the station's own (an ack, a message attempt) handed to
a slow radio right after a passed frame. Those follow the services' own pace; the handover gap
holds back only what the rows send.

## neoaprs/services/prefbook.py

Operator preferences per station: a path of its own, RF only, and an alert. Each part is optional;
a station with none has no entry. Entries are read once at start and written through. An empty
path means DIRECT, which differs from none set (the path lately heard, else the radio's own path).
RF only appends RFONLY to every path used for the station; the e-mail gateway is on the internet
and can never be RF only.

A path is set per radio. The entry's own path is radio 1's; the paths of other radios are kept
through a separate path log, and without one they cannot be set. A radio whose type has no path
setting gets the gateway's reply path instead. Forgetting an entry forgets radio 1's path, never
the paths of the other radios.

The path for a message is, in order: the station's own path on that radio; for early attempts the
path lately heard; the radio's own path (the type's recommended path when empty). RFONLY is
appended for an RF-only station; a path that would then exceed 8 hops is refused.

## neoaprs/services/qru.py

A station sends a message to the addressee `QRU` (any server in range answers) with the text:

    INFO          which groups are served near me? (`?` alone, or `?INFO`, `?RP70 100`, also work)
    INFO 250      the same within 250 km instead of the default range
    RP70          the objects of the group RP70 near me
    RP70 250      the same within 250 km
    NEXT          the next objects of the group last asked for

The answer goes by the asker's path with RFONLY added, as frames without a message id, the first
one a few seconds after the request, because the digipeaters are still repeating the request and
an answer sent at once collides with them. INFO is answered with
"de OH2GBA-10:RP70(3) FOOD(1) Max 5@50km" (a long list takes two messages, the first ending in `+`).
A group is answered with its objects in range, nearest first, at most five, then
"Sent 3 RP70 Objects Max 5@50km de OH2GBA-10", or "Sent 5 of 12 RP70 Objects, NEXT for more. de ..."
when more are left. Nothing is answered where nothing is in range.

A message to QRU is a broadcast: it is never acked and never kept as ours. The inbox hands it over
only while some group is served. Only a request heard on the radio is answered; an internet or
gated one is not, since the asker is out of radio range. An object belongs to a group by its group
name and may be on-request (never beaconed on the decay schedule). "In range" is measured from the
asker's latest position in the station book; an asker with no known position gets every object.

The format follows the QRU servers of APRSIS32 (aprsisce.wikidot.com/doc:qru) and YAAC, and the
replies quoted in SA7SKY's queries sheet. Not implemented: the group size limit and the QRU beacon.

## neoaprs/services/qruask.py

A local-info request is a broadcast message to the addressee QRU: no message id, sent once, never kept as a
message. It uses the path of messages to QRU with RFONLY added, so iGates keep it off APRS-IS and only servers
in radio range answer; the operator may give another path and drop RFONLY. It is refused under the transmit
interlock and while the radio is away. The same request goes out once per ASK_EVERY_SEC (a server answers one
station once in that time anyway) and any two requests are ASK_GAP_SEC apart because the channel is shared; a
request inside either wait is refused with the seconds left.

Servers answer with messages: a list of groups with object counts, and after the objects a closing line saying
how many were sent. A group list ending in `+` continues in the next message of the same server within
CONTINUE_SEC. Servers are remembered for KEEP_FOR after being heard.

Arrival is counted from the objects heard from the server's call between the request and ARRIVAL_GRACE_SEC after
the closing line, each name once. The server sends them while digipeaters still repeat the request, so one can
be lost in a collision. A list or closing line without a message id within ANSWER_WINDOW_SEC of a request is an
answer, and the inbox does not keep it as a conversation.

Local info has its own Send on (each radio's "local_info" tick). A request naming no radio goes once on each
ticked radio that takes frames now; one naming a radio goes on that one. Waits are per radio and a request is
all or nothing: if any target radio is inside a wait or a path makes no frame, nothing goes out. A server keeps
the radio its latest answer came on, among the radios asked; objects count as arrived only when heard on a radio
the request went on (a packet naming no radio counts for every request).

## neoaprs/services/queries.py

Directed queries are answered only when the message is addressed to our exact call (a base call is not ours when
ours has an SSID):

- ?APRSP: our position packet. ?APRSS: our status as last sent, nothing if none was sent.
- ?APRSD: a message "Directs= CALL CALL": calls heard direct in the last hour on the radio the query came on,
  latest first, at most two messages, "Directs= none" if empty. A radio that carries paths uses its own routes;
  one that carries none (HF, where every frame is direct) uses any station heard in the hour.
- ?APRST and ?PING?: the query's header as heard, e.g. "OH2GBA>APZNEO,OH2RCH-2*:".
- ?APRSH CALL: "CALL HEARD: 1 3 2 . . 4 5 6", packets of that station in each of the last 8 hours, latest first,
  a dot for none, "CALL NOT HEARD" if never seen. The station's position object that the specification adds is
  omitted: an object named like a station is never allowed among our own objects and clients would show it twice.
- ?APRSO: our live objects and items, each once, at most ANSWER_FRAMES_MAX. ?APRSM: our messages to the asker that
  no ack has settled, each once as sent, the latest ANSWER_FRAMES_MAX; their records do not change.
- ?APRSO and ?APRSM frames go out SPACING_SEC apart, the others at once.

The general query ?APRS? is a `?` packet, not message text; a message with that text is not answered. It may
carry a footprint, `?APRS?V34.02,-117.15,0200` (degrees, radius in miles; the V is optional). The station answers
only when its current position is inside the footprint; an unreadable footprint is not answered. The answer is the
position packet, then the status report if there is one, after a random delay of 0 to GENERAL_DELAY_MAX_SEC, and
not again within GENERAL_EVERY_SEC. Answers go by the asker's path as plain frames: not messages, never retried.

?IGATE? follows the same rules with its own interval, but only while the iGate is connected (on, logged in and
verified). The answer is a station capabilities packet (data type `<`), for example
`<IGATE,MSG_CNT=0,LOC_CNT=3,UPL_CNT=812`. MSG_CNT is always 0 because nothing is gated from APRS-IS to the radio.
LOC_CNT counts stations heard direct within DIRECT_WINDOW (as ?APRSD lists them, not the station itself or
objects). UPL_CNT is the number of packets put on APRS-IS since start. Other counts that Dire Wolf sends are not
sent. A message with the text ?IGATE? is not answered.

?WX? is recognised and never answered: there is no weather report to send, and a queried station without relevant
information need not respond (APRS 1.0.1 chapter 15).

## neoaprs/services/radiofinder.py

Ports come from the serial probe. On Linux: the globs of the search pattern, minus boards the search leaves alone,
the skip list and ports another program holds, plus paired Bluetooth devices when the pattern is the default. On
Windows and macOS: the ports the system lists, USB adapters first. A port already open elsewhere fails to open
and is passed over. A KISS TCP address is never tried. The TNC's own line is closed during the search and
reopened after it. A port without a speed (Bluetooth, the COM port of a Bluetooth device) is tried once. Each try
takes listen time plus answer time when nothing answers, so a serial port costs 7 tries, about 18 s.

With several radios the search is for one radio: that radio's line is held and released. Serial devices claimed
by another radio or the GPS receiver are skipped, and re-checked once the search has its turn. Searches run one at
a time; a waiting search takes its turn through the shared lock.

## neoaprs/services/radioprobe.py

A KISS TNC says nothing until it hears a packet, so a silent line is tried with a carriage return: a TNC in
command mode answers with text and is put into KISS by each profile that can be asked, in turn, until a following
carriage return is no longer answered with text.

## neoaprs/services/radioset.py

The module holds `AirRadio`, `RadioPick` and the frame fitting so every service may import it while it imports
none of theirs. `fit` is the one place that makes our frame for a radio: the path where the radio may carry one,
the comment cut to what it carries whole. Protocol members are read-only so a plain attribute, a property or a
frozen field satisfies them. A byte cut from the information shortens the KISS frame by at least one, so cutting
the excess is enough. An ack to a message goes out on the radio it came on while that can send; otherwise on the
radio a message to the station uses (the email radio for the gateway), so a station heard only on a receive-only
radio is still acked and stops repeating. A question is answered only on the radio it came on, and only if that
radio sends: the copy a sending radio hears is the one taken.

## neoaprs/services/repeater.py

A subclass keeps its things by key and defines `_due` (None: not sent again) and `_transmit` (True when sent,
False when the radio would not take it, SendError when the values make no frame). A thing whose frame cannot be
made is logged once and waits; the others are not held up. A thing on several radios goes out in one round: each
radio that has not taken it and takes a frame now is given it. The round is done when every present radio has
taken it; a radio that is away does not hold it up, nor does a connected one that takes no frame for
ROUND_HOLD_SEC after the first took it. Radios that took the round are kept in memory by id; a restart sends on
all again.

A repeat waits a random pause in its slot (`_paused`): one share drawn per wait and kept until the round ends, so a
tick or a look at `next_at` draws nothing; a share, not seconds, so that a radio that comes up later or changes type
scales it, and nothing is kept while no radio is up. The next slot counts from the slot of the round that ended in
its pause window (`pause.anchor`), so a schedule's count of packets is what its plan says. Keys loaded at the start
(not in `_fresh`) wait from the start, as stations on one power strip start them together.

## neoaprs/services/retries.py

While a message's radio is unusable, or transmitting is off, a due attempt waits and is not used up; when the radio
is back the waits of its messages move on by the time it was away. Acks that waited for a radio go when it takes
frames again. The time away is measured from the tick that first found the radio away to the last tick that still
did, not to the tick that finds it back: the radio returned at some unseen moment in between, so a clock jump in
that gap counts as time with the radio back, an error of one tick.

## neoaprs/services/rigstatus.py

The status source is `rig`, `text` or `off`; empty means `rig` while a rigctld address is set, else `text` while a
station status is set, else `off`. With `rig` every POLL_SEC a fresh short connection to Hamlib rigctld asks for
the frequency and mode and the template is filled in ({freq} as `14.074 MHz`, {mode} as rigctld names it). A radio
that is off, a refused connection or no answer means nothing is sent, and the log says so once, not at every poll.

A report goes out when the status interval has passed since the slot of the last one (or none was sent), after the
radio's random pause, whether or not the content changed; a one-second timer checks the slots with the latest
reading, so that a pause shorter than the poll counts. The time and text of the last report are stored and read at start, so a restart sends nothing
inside the interval. The last text is what `?APRSS` answers with. `send_now` sends at once with the same
interlock, length and radio checks, and the interval then counts from it on each radio.

Targets are the radios with the "status" tick (unticked by default; one sending radio is used whatever the ticks).
The text is read once per poll and is the same on every radio. Each radio sends at the interval raised to its own
floor (30 minutes on HF and LoRa), counted from its last send there. A radio with no send yet counts from the
station's latest report, so a radio ticked later joins at the next interval. A radio that is not connected, silent
or does not take the frame is retried at every poll, as the beacon is; a report longer than the radio carries is
not sent there. A receive-only radio is never a target. No automatic report goes while the beacon is off
(`send_now` still sends); a held-back one goes at the first poll after the beacon is on if the interval has passed.
A report that cannot go is logged once per reason and retried at the next poll. A single-radio call shape (a radio
that is not a registry, with frames from a beacon) is still accepted, sending at the plain interval.

## neoaprs/services/selfinstall.py

Windows: the installer runs silently and detached from the `update` folder in the data folder, after earlier
installers are deleted. It ends the app and the daemon first (so the Restart Manager is not asked); its `[Run]`
entries restart what was running (the app if it held the data folder, else the daemon) on the same data folder.
The daemon notes its page's port before the installer starts so the new daemon serves it again. A daemon that ran
with encryption is restarted with it.

AppImage: the new file is made executable and renamed over the running file; the old one stays as `<file>.old`
(hard link, else copy) until the new version has started. The daemon then ends and starts the file again with its
arguments, keeping the process so a service manager sees no end, on the same port.

Other kinds get no installer and the page shows the steps. The macOS app is among them: replacing a running app
bundle that imports modules lazily, and restarting through launchd, is untested.

A simulated install kind gets a rehearsal: every step but the last; the file is deleted instead of installed. The
fake release folder (a server on the loopback) replaces GitHub only with a simulated kind or the update-test flag,
and only for http(s) on 127.0.0.1 or localhost. Only with that fake server may a test key replace the project's
public key, since a test cannot sign with the project's; from GitHub only the project's key is accepted.

## neoaprs/services/selfupdate.py

SHA256SUMS is trusted only if its signature holds with the project's key for exactly that version. Every signature failure is
the single problem `unverified`, since the operator's options are the same and the log has the cause; a signature that could not
be fetched (connection failure, or any answer other than 404) is `download`, like SHA256SUMS itself. After `restarting` the
daemon should end; if it is still running `RESTART_GRACE_SEC` later the update failed (`no_restart`).

## neoaprs/services/skeds.py and neoaprs/skeds.py

The sked board is the static file `skeds.json` of the project's server. The daemon trusts nothing in it: each row is validated
(12-digit lowercase hex id, an amateur call, ISO times with the end after the start by at most 24 hours, a dial, a note of at
most 80 characters of letters, marks, digits, punctuation, symbols and plain spaces), a bad row is dropped alone, a board holds
at most 100 rows and ten per call, and rows already ended or beginning over a month ahead are dropped. Posting happens only on
the operator's press and carries the sked token (16 random bytes made on first use, kept in the row `update/sked_token`; secret,
distinct from the installation number and never sent when reading); the server keeps its hash with the sked, so only this
installation can delete it. A refusal the operator can act on (rate, full, past, too_far) is an error with a code; others are
logged and the job completes as far as possible (a closed board or blocked call is state `closed` until the next read).

## neoaprs/soundmixer.py

Only volume controls are touched, never a switch, so mute and Auto Gain Control stay as the system has them. The first of
PLAYBACK_NAMES and of CAPTURE_NAMES that the card has is used; "Mic" is not a playback name because its playback volume is the
monitor on some chips. The percent is the raw value within the control's range, as `amixer` prints it. ALSA prints a line at every
look at an unplugged card, so the library's error handler is replaced by one that discards the messages.

## neoaprs/stopfile.py

`neoaprs.stop`: the stop command writes it; the daemon polls once a second, deletes it and ends as on SIGTERM. Whoever can
write to the (user-private) data folder can kill the process anyway, so the file gives no extra power. A stale one is deleted at
the next start.

`neoaprs.restarting`: left by a daemon that ends to start again as a new version (an AppImage update); the new one deletes it,
and the desktop app waits for the new daemon while it is fresh.

`neoaprs.restart-port`: the port the page was served on. A daemon that starts while the note is fresh serves the page there
again, so an open browser page keeps its address even if the configured port was taken or freed meanwhile. The Windows
installer's restart leaves only this note, because the installer ends the app and the app must not wait. It is a note rather
than a command-line argument because the command line belongs to the operator or a service manager and repeats at every start,
whereas the note is read once. It is believed for 15 minutes because the Windows installer replaces every file between the
daemon's end and its start.

`neoaprs.migrating`: written every few seconds while the database is migrated and deleted at the end. Waiters (`neoaprs open`,
the desktop app) wait while it is fresh; one left by a kill goes stale by itself. The migration also holds the lock
`neoaprs.migrate.lock` (released by the system whenever its process ends), so a second NeoAPRS waits to migrate the same file.

## neoaprs/tnc.py

A write that times out (pyserial's SerialTimeoutException: the device took no data within the
write timeout, as the incoming Bluetooth port of Windows does) is its own reason. The line is opened
again with the usual back-off, but the row says `waiting` with `radio.write_timeout` until a write
goes through, a byte comes, or the port has stayed open for the watchdog's probe interval with no
failed write (a quiet radio that is sent nothing): a bare reopen proves nothing. Frames still go to the port meanwhile,
since only a write that goes through can show that it works, and a quiet channel is no evidence.

A Kenwood TH-D7 TNC starts in command mode: it prints heard packets as TNC2 text and answers a carriage return with "cmd:".
`ModeDetector` tells that from a KISS stream, and the Tnc switches the radio to KISS ("KISS ON", "RESTART") once per answer it
gets. A silent line that starts to speak is entered into KISS unless the bytes are a KISS frame or part of one, so that no frame
is typed into a TNC in command mode. A fresh open of a line to a TNC that can be asked is not usable until the radio has shown
that it is there, because a USB adapter is present with the radio off. With the checks off nothing is asked and the line is
usable as soon as it is open. A profile that cannot be asked is sent nothing but KISS frames.

## neoaprs/tncfollow.py

Where the radio is not searched for among the ports (Windows, macOS), a replugged USB adapter may return as another COM port
or /dev/cu device. The adapter behind the named port is remembered by serial number, or by vendor and product ids when unique,
and the new port is opened if the named one cannot be. The memory is made after the line is open, in a task, because reading the
system's port list in a thread can be slow and nothing may be awaited while an open port has no owner.

## neoaprs/tnchealth.py

A usable TNC line is reported as `connected` even before its first KISS frame, since a Kenwood or
Kantronics TNC is silent in KISS mode until it hears a packet. A connected line whose Mercury runs
and hears nothing (its stall watch) has the problem `modem.receive_deaf` until the warning stops or
the modem is restarted.

## neoaprs/tncsearch.py

The search listens to every port that matches the pattern at once, and the port whose bytes look like the radio's is the answer.
It runs as a task of the Tnc that asks, so the Tnc's stop ends it. With several radios the station's table of claims is shared:
the search leaves out every serial device another radio or the GPS receiver holds, or another enabled radio is set to; the table
is read again at every listing and whenever a port has spoken, and a search that has such a port open closes it. A named port
held by another radio is not opened at all (the radio waits); the port that radio 1's search only remembered is searched past
instead. A named port that another radio's search has open is let go by that search at once. The port found is held for its
radio before the next radio's search may start, until the Tnc stops.

One radio searches at a time (the registry's search lock). A turn is bounded: after its nudge and one listing a search gives
the turn up at its next listing while another radio's search or Find my radio waits, closes its ports and waits again, so that a
radio that never finds its port keeps no other from its own. Over all its turns one search writes its carriage return to a port
once.

## neoaprs/tncwatchdog.py

The keep-alive exists because a quiet serial line proves nothing about the radio. A switched-off Kenwood TH-D7 leaves its USB
adapter and port in place, a TNC in KISS mode sends nothing until it hears a packet, and a power-cycled radio comes back in
command mode. So the absence of the radio has to be asked for.

When nothing has been heard for the quiet period plus a random part (TNC_CHECK_JITTER, so that checks never keep step with a
station that beacons at a fixed rate), the watchdog makes a check, only for a profile that can be asked. A check sends the
profile's KISS exit frame, pauses, sends a bare carriage return (a TH-D7 that is on answers with text, "cmd:", within about a
second) and then the profile's entry (KISS ON). Any byte in answer means the radio is there and the clock restarts from the
latest byte. A check costs a few seconds of reception, hence the quiet period. A line just opened has not shown that the radio
is there (the Tnc is not usable, `confirmed` is false), so its first check is made at once.

If no byte comes within `answer_sec` of the carriage return and KISS ON, the radio is called silent. The same sequence is then
a probe, made every `probe_sec`; the first byte that comes ends the silence. Every fifth probe also reopens the port, for a USB
adapter that dropped. Nothing above DEBUG is logged for a check or probe; the Tnc reports once when the silence begins and
once when it ends.

`EntryAgain` covers a TNC that keeps typing command-mode text after the entry into KISS has settled (a radio switched on a
moment ago misses the first KISS ON while it starts). The entry is sent again `ENTRY_AGAIN_SEC` after the settle, then after
twice as long each time up to `ENTRY_AGAIN_MAX_SEC`, so that a TNC that never takes it (the wrong profile) is not restarted every
ten seconds for ever. The first repeat is logged at INFO, later ones at DEBUG.

## neoaprs/updateasset.py

SHA256SUMS.sig is the base64 of a 64-byte Ed25519 signature made with the project's private key, which only the release script
reads; PUBLIC_KEY is the public half and the program's only copy. What is signed is the line `NeoAPRS SHA256SUMS v<version>`
followed by the list as it is. Binding the version there, not in the list, keeps the list readable by
`sha256sum --check --strict`. The version checked is the one requested, never one read from the download, so a signed list of an
older release offered as a newer one fails.

## neoaprs/updatecheck (services/updatecheck.py)

The question carries the version, platform and a random installation number and nothing else. The number is 0 for a run from the
source tree or while the settings row `update/not_counted` is true; otherwise it is made on first use and kept in the row
`update/install_id` (daemon state, not a setting) and is derived from nothing on the machine, so the project can count
installations without identifying them. The check is always on; `NEOAPRS_UPDATE_CHECK=0` switches it off for one run and is
rechecked an hour later. An unreachable or unintelligible page is a debug log line and the next try is the next day.

## neoaprs/updatefetch.py

The update check sends the program's version, platform and the installation number (if any) in the query; a failure of any kind
gives None and the check is asked again the next day. `get_feed` (the map's traffic layers) asks for gzip, unpacks it within a
bound, and returns the status, the body and the `Retry-After` wait; a `user:password@` in the address is sent as basic
authentication to that host only, and the log names only the host because an own receiver's address may carry more. A POST
returns the status and body even for a refusal, and None only when the server could not be reached.


#### Notes from the second comment pass (web, first part)

## neoaprs/usbtie.py

A USB radio or interface (Digirig, IC-7300, FTX-1) carries its sound chip and serial chips behind a small hub of its own; an
all-in-one chip is one USB device with both. A port elsewhere on the USB is not the card's, and keying it would key nothing or
another radio.

The grouping rule: a USB device is grouped with the others on its hub when the hub is not the computer's own root hub and
carries only devices with a sound card or a serial port, exactly one with a sound card; otherwise the device is a group alone.
A hub that also carries a keyboard, a memory stick, another hub or a second sound card is no radio's. A lone serial cable and a
lone sound dongle on an otherwise empty hub look like a radio's hub and are grouped; nothing in the tree tells them apart, and the
cable is then the likely keying anyway.

`together` gives each port and card an opaque token, equal within a group, which the page uses to order keying lines; it is never
shown or logged. The keying chosen automatically comes from ports on the card's own USB device or beside it on its hub, whatever
else the hub carries (`tied`); the stricter group orders only the Keying list.

## neoaprs/web/access.py

A session token is `expires.nonce.mac`, where the mac is an HMAC-SHA256 of the preceding parts under the
access key. Nothing is stored, so sessions survive a restart and a new key ends them all. The key itself
is never put in a cookie and is compared in constant time. A session bought over https carries an extra
`s` part and the secure port accepts only those, because a cookie bought over plain http may have been
read off the network. Wrong keys are counted per address: five within a minute shut that address out for
five minutes.

Settings in `LOCAL_ONLY` name a program or an address the daemon runs or fetches from. A page on another
device (a phone, or a cookie read off the network) may operate the radio but not the computer; on a
headless computer these settings are changed with `neoaprs db set`. `map/aircraft_host` and
`map/ships_host` are deliberately not listed: those receivers sit beside headless Raspberry Pis, and the
daemon fetches a single file from them and shows only what the file's format allows.

## neoaprs/web/hub.py

Pages follow every topic from the start. Each is first sent the whole value (`state`), then patches.
Changes are flushed on a tick, so what changed in a topic between two ticks is one patch with at most one
operation per key. A keyed topic records which keys changed and builds each item when the patch is made,
so an item that changed ten times is sent once and a vanished one becomes a `del`. A whole topic sends a
`replace`. A topic may set a minimum interval between patches.

The hub keeps no queue per page. A page whose socket holds more than an eighth of the write-buffer
cut-off is skipped and the topic is marked stale for it. Once its socket has been read down, it is sent
the whole state. A page that never reads is cut off by the socket itself. Failures from a builder are
logged with a traceback the first time and as one line after that, because the same odd packet can break
the same builder at every change; the failed change is dropped, not retried.

## neoaprs/web/pagefiles.py

The base map route uses an entity tag built from the file's size and modification time. Tornado's own
hash reads the whole file on the event loop, caches the result for the life of the process (so a
refetched map would keep the old tag) and gives no tag for files above 64 MB. PMTiles readers use byte
ranges; the octet-stream type is not compressed, so a range is a range of the file. The route is behind
the login because the map is data.

Content types of the page's own file kinds are fixed in a table, because the Windows registry may map
`.js` to `application/javascript` or `text/plain`, and with `nosniff` a browser then runs no script.
Plain http from another device is redirected with 307, not a permanent redirect, because the secure
page can be switched off again.

## neoaprs/web/pagesocket.py

The Origin check alone is not enough under DNS rebinding, since an Origin that matches the Host proves
nothing when both are the attacker's; the Host is therefore checked in `prepare()`. Sockets use
permessage-deflate (RFC 7692) because the station table is large, repetitive JSON; Tornado keeps a
deflate state of a few hundred kilobytes per direction per socket, so connections are capped.

## neoaprs/web/scopefeed.py

A page that starts looking first gets the rows the modem keeps (the last two minutes), then every row
newer than the newest it was sent or passed over, so no row repeats or is lost while the history is
written. A page that is behind when it asks gets no history. When the modem forgets its rows, looking
pages get an empty history. A page that looks again on the same socket gets only the rows from the two
it already holds, when the modem still has them. Every history carries the daemon's clock so the page
can place times.

## neoaprs/web/secureside.py

The secure port is the first free port after the plain one. The certificate is checked when settings
change and hourly (every five minutes while wanted and failing); a new computer address or a
certificate near its end makes a new one, loaded for connections made afterwards.

## neoaprs/web/server.py

Host header check (DNS rebinding): an attacker's page controls its own name and, after moving it to
this address, is "same origin" with the daemon. An IP address cannot be moved this way, so any IP is
accepted; a name must be the computer's own or listed in `web/allowed_hosts`. The hosts file is read
for extra loopback addresses of the computer's name (Debian and Raspberry Pi OS use 127.0.1.1) so a
local browser opening the page by name connects; the name is not resolved, so no name server is asked.

## neoaprs/web/topics.py

While `igate/enabled` is off the internet is hidden, nothing is deleted: a station known only from
APRS-IS is absent from the stations topic and one heard both ways shows its radio side only. The
packet window then shows the latest 200 non-internet packets. A change of that setting, or of the
radios in force (id, kind, type, Enable, place, removed, email radio choice, own calls), sends the
stations topic whole. Our own position moves every station's distance, so the stations topic is
resent whole, at most every 30 seconds while the GPS moves; our own row follows every GPS step.
Rate limits of topics: radios, map and update at most four times a second; gps and igate once a
second. Two messages are no topic: `station_alert`, sent to every open page, and `layer_things`,
sent to the pages looking at that layer.

## neoaprs/winchild.py

On Windows every child program is put into one job object of the daemon, made with kill-on-close, so
that a daemon that dies however it dies takes its Mercury and Direwolf with it instead of leaving them
holding the sound card, the ports and the install folder's files.

Mercury is asked to end with Ctrl-Break, never Ctrl-C. A Ctrl-C does not reach a program that inherited
"ignore Ctrl-C", which the daemon has when its Run entry starts it in a new process group, and clearing
the attribute before starting Mercury made the asking process take the Ctrl-C itself and end: on a Windows
machine the ask must never end the daemon. Ctrl-Break to the child's own process group (it is started with
CREATE_NEW_PROCESS_GROUP and a hidden console) reached the child every time; sigbreak.patch gives it
Mercury's unkeying handler. The daemon never touches a console of its own: a runner's session and a
console program started by a double click are alone on a console that shows, and letting go of it would
take the window from the person looking at it. A disposable asker does it (neoaprs/winask.py: the program
itself with `--winask` or `-m neoaprs.winask` and the child's id, started hidden): it lets go of its own
console, attaches to the child's, sends the Ctrl-Break and exits with a code that says what happened.

## neoaprs/winmm.py

Direwolf opens a WinMM device by number. A number or name that matches nothing leaves it on the
system's default device (audio_win.c, device selection), which could key the wrong radio or use the
computer's speakers, so the daemon finds the numbers itself and anything other than exactly one
input and one output of the card is no start. WinMM names a device through the ANSI calls Direwolf
uses (`waveInGetDevCapsA`, `waveOutGetDevCapsA`) in at most 31 characters: the WASAPI friendly name,
such as "Microphone (USB Audio CODEC)", cut short. That the two are the same name was verified on a
Windows machine, not from source. A Sound card radio's card is the single id the HF modem's list
gives it (the pair of its WASAPI recording and playing devices), so one card is one claim for any
radio type. Windows may put a number before a name ("Speakers (2- USB Audio CODEC)"); the match
falls back to ignoring it.


#### Notes from the second comment pass over scripts/ and packaging/

## scripts/build-direwolf

Direwolf is built from the pinned source (version, commit, URL and SHA-256 are the pins in
neoaprs/direwolf.py and nowhere else), either for Linux or cross-compiled for Windows with MinGW-w64
(`packaging/direwolf/mingw-w64.cmake`). On Linux the program has RUNPATH `$ORIGIN/lib`, is stripped, and
carries libasound and libudev beyond glibc plus the ALSA configuration; the build container is Ubuntu 22.04
because its glibc is the floor of the AppImage and the .deb. The Windows program is linked statically and
imports only system DLLs; it cannot be run on the build machine, so its import table is read and its
banner bytes are searched instead.

The CMake build leaves out the unit tests, DNS-SD announcement, gpsd, hamlib and libgpiod: NeoAPRS has its
own GPS and an FM interface keys on RTS, DTR, a CM108 pin or VOX. Six patches in `packaging/direwolf/` are
applied in order and each is verified in the source afterwards, so a new pin that moves the lines fails the
build and not an operator: loopback.patch binds every listener (KISS, AGW, UDP audio) to 127.0.0.1 because
those ports have no password; flush.patch flushes each output line because Windows buffers a pipe;
quit.patch adds `-Q` (end of standard input ends the program like Ctrl-C and sets keying outputs to 0);
txlevel.patch adds `-G` (transmit level); rxlevel.patch adds `-R` (receive level every so many ms of audio);
confpath.patch lifts the 99 character limit on the `-c` path. quit, txlevel and rxlevel change the same
option string, hence their order.

The program proves what it holds: its banner names the pinned release with `cm108-ptt` as the only optional
part, and on Linux a run on its UDP audio input listens on 127.0.0.1 only and ends with "QRT" and exit 0
within a few seconds of its input closing (its cleanup sleeps one second). Python 3.10 (the container's)
`communicate` flushes a closed stdin and raises, so the run sets `stdin = None` after closing it.

## scripts/build-gi

The AppImage's web window carries PyGObject (`gi`), built from its pinned source for the pinned CPython of
scripts/build-appimage with Meson (Ubuntu 22.04's own Meson is older than the 0.64 PyGObject asks for) and
`-Dpycairo=disabled`. From Ubuntu 22.04's packages it also takes the tray's AppIndicator library with the
libraries it needs, its typelib, and the typelibs of WebKitGTK 4.1, each package with its version and
copyright file. WebKitGTK and GTK themselves are never carried; they are the system's. The tarball's single
folder `neoaprs-gtk/` holds `site-packages/gi/`, `lib/` (the libraries listed in
`neoaprs/desktop/gtkenv.py` LIBRARIES), `girepository-tray/`, `girepository-webkit/` (WebKit2-4.1,
JavaScriptCore-4.1, Soup-3.0) and `NOTICES/`. scripts/build-appimage puts `gi/` into the image's
site-packages and the rest under `usr/lib/neoaprs-gtk/`.

Every download is pinned by version and SHA-256 (the pin is the trust, not the server) and fetched once into
$NEOAPRS_BUILD_CACHE. The link of `_gi` and of each carried library is checked with readelf: what they need
must be glibc, GLib, girepository-1.0, libffi, GTK 3 and its stack, or each other, which any desktop with
WebKitGTK has. The build runs on the container's Python 3.10 and for x86_64 only, as the AppImage does.

## scripts/build-mercury

Mercury is built from the pinned source (pins in neoaprs/mercury.py only) for Linux, macOS or, cross-compiled
with MinGW-w64, Windows. Linux build: RUNPATH `$ORIGIN/lib`, stripped, with libasound and the ALSA
configuration beside it; macOS links the system's CoreAudio only (the deployment floor is the app's floor,
macOS 14; the upstream universal build is not used because it needs macOS 26); Windows `mercury.exe` is
stripped, links the C runtime's thread library and the compiler runtime statically and imports system DLLs
only. The CI job runs on ubuntu:22.04 because its glibc is the floor of the AppImage and the .deb.

Make flags: NeoAPRS keys the radio itself (VOX, CM108 over /dev/hidraw, RTS or DTR), so Mercury links no
hamlib, hidapi or OpenSSL on Linux and macOS (`HAVE_HAMLIB=0 HAVE_HIDAPI=0 WS_TLS=0`). On Windows hidapi stays
(Mercury compiles its own copy, `radio_io/hidapi-w64`) because that is how a CM108 chip is keyed there. The
Makefile asks pkg-config for hamlib, hidapi and OpenSSL and sets their flags whatever `HAVE_*` says, so the
flag variables are also given empty on the command line, which beats the Makefile's assignments including
`+=`. The Makefile puts `-lpulse` into FFAUDIO_LINKFLAGS in a Linux-only branch; the variable is given whole
on the command line instead of patching those lines with sed, which would break silently. The RUNPATH goes
through EXTRA_LDFLAGS, the Makefile's hook for the caller's linker flags (`$$` is make's `$`; the quotes keep
the shell from expanding `$ORIGIN`). The caller's CFLAGS, CPPFLAGS, LDFLAGS and LD_LIBRARY_PATH are dropped
because the Makefile copies them into every link. The Windows program follows Mercury's own `windows` target
(`OS=Windows_NT`, MinGW compiler as CC and AR; DirectSound and WASAPI, Winsock); `-s -static` strips it and
guarantees that no MinGW DLL is requested whatever the thread model. Its two make steps run in sequence
(`internal_deps`, then `mercury.exe`) because the link must wait for the objects.

Patches in `packaging/mercury/`, each verified in the source after applying so that a moved line fails the
build and not an operator: loopback.patch binds the two TCP listeners and the UI websocket to 127.0.0.1
(the ports have no password; no INADDR_ANY may remain); leadin.patch adds the ini key `audio:tx_leadin_ms`
(a tone ahead of the preamble for a radio on VOX; off by default); dsound.patch makes the DirectSound backend
load dsound.dll on first use so the program starts on a Windows without the Media Feature Pack; flush.patch
flushes stderr after each log line (Windows buffers a pipe); ffcpu.patch defines `_ffcpu_features`, which the
audio library declares and leaves to the program, so it links with a compiler whose default machine has
SSE4.2; sigbreak.patch gives Ctrl-Break the handler of Ctrl-C on Windows, the event NeoAPRS asks Mercury
to end by. On Linux `pulse_stub.c` replaces the PulseAudio backend: ALSA is the one sound system of the bundle,
and both PulseAudio and PipeWire offer an ALSA device.

The link is checked with ldd (only libasound, glibc and its helpers). The last step starts the program as the
daemon does (`-V`) and, on Linux, once on its fifo backend to see that its four ports (the UI websocket
included) listen on 127.0.0.1 only. The sound cards are not listed with `-z` because that would open the
control device of every card of the machine, the radios' among them. A Windows program cannot be run on the
build machine, so its import table is read and the release workflow's Windows job starts it and reads the
system's socket table. A Mac program is not stripped, since that would break the signature the linker gave it.

## scripts/check-in-container

The suite runs in a container shaped like GitHub's Linux runner: the Ubuntu named in `packaging/ci/runner.json`,
its compiler's default machine (x86-64-v3) and C library, the CI jobs' libraries and tools, git, PHP, the
pinned uv and node, and the user `runner`. The image (`packaging/ci/Dockerfile`) is built when missing or
when the Dockerfile changed (its tag is the Dockerfile's digest) and holds no project file. Its programs need
a processor with x86-64-v3; the system's loader (`ld.so --help`) is asked first, because it also knows
whether the system saves the wider registers, which /proc/cpuinfo flags do not say. Images of other
Dockerfiles are never removed by a run, only counted; `--prune` removes those no container uses.

The tree goes in as it is on disk: tracked files plus untracked files that are not ignored
(`git ls-files -co --exclude-standard`), packed before anything starts and unpacked inside as a repository of
one commit so that tests which ask git see what they see after a CI checkout. Files named by an ignore rule
stay on the machine, and so does any file whose name begins `.secrets` (in any folder); a key under another
name is kept out by a line in .gitignore. No environment variable of the host is passed on, the working tree
is never mounted, and `.venv` and `node_modules` are the container's own. uv's, npm's and the build cache
(Mercury's source archive) are the volumes `neoaprs-ci-uv`, `neoaprs-ci-npm` and `neoaprs-ci-build`.

The runner is four threads (two cores with their siblings as the kernel lists them) and 16 GB without swap;
`--starved` is two threads of one core and 7 GB. The threads are given as a CPU set, because a quota would
leave `pytest -n auto` starting a worker for every thread of the machine. Concurrent runs take cores no other
run holds (found through a label on each container, under a lock so two starts cannot pick the same cores),
and each container has its own loopback. Inside, NEOAPRS_UPDATE_CHECK=0, NEOAPRS_NO_DEVICES=1 and UV_FROZEN=1
are set; with UV_FROZEN `uv lock --check` does not compare uv.lock with pyproject.toml, which is why the
`lock` stage of scripts/check removes the variable. UV_LINK_MODE=copy because uv's cache is on another file
system. Exit codes: the command's (of the first that fails), 125 when docker failed, 2 when the machine is not
set up.

## scripts/check-installs

The release's clean installs are tried in Docker before a tag: the wheel in a fresh environment, the .deb with
apt in a clean Debian (bookworm-slim) and a clean Ubuntu (24.04, pinned by digest, as the release workflow's
`deb` job has it on its arm64 runner), the AppImage on a computer without NeoAPRS, and an upgrade. The files
come from the same build scripts the release workflow runs (`uv build --wheel`, build-mercury, build-deb,
build-appimage) for this machine's architecture only. Each check runs in a container with nothing of NeoAPRS
and none of this tree: built files and test scripts are mounted read-only, no device, no port, and nothing a
container makes reaches the host. The wheel and the AppImage use the image of scripts/check-in-container (the
Ubuntu of GitHub's runner with the Qt web engine's libraries, uv and Python 3.13); the Debian run also proves
that Mercury needs no system library.

The upgrade starts from the .deb pinned in `packaging/ci/old-release.json` (fetched once into the build
cache and checked against the pinned SHA-256; an unpinned release is a failure, not a skip) or from
`--update-from` (a .deb, or a commit built from `git archive` without Mercury). It installs the old build,
starts its daemon with both radios, a station and a message, installs the new build over it (`--reinstall`
when the version number is the same, because apt would leave it), and requires the daemon to come up as the
new version with everything present, every file of the package in place and the database at this build's
schema version. A Mercury built on a machine with a newer glibc than the container cannot run there; the
check then reports one SKIPPED line and the run is not called all green; the release workflow's `deb` job,
which builds on the older system, proves that part. Daemons run with NEOAPRS_NO_DEVICES=1 and
NEOAPRS_UPDATE_CHECK=0.

The trial AppImage of the web window (`--only appimage-web`, never a release) is built without Mercury from
this tree and the gi tarball of `scripts/build-gi --docker`, and started by `scripts/smoke-appimage-web` in
each container of WEB_CASES as a desktop of that system has it: with WebKitGTK 4.1 the window must come; on
Ubuntu 22.04 with only the 4.0 API the window must come; with no WebKitGTK the log must name the package and
the app continue with the tray. A window run also prints what `scripts/webkit-probe.py` counted (software GL,
the worst case).

## scripts/dup-compare.py

The duplication ratchet of the Python half compares a jscpd JSON report with a committed baseline. A clone is
identified by the pair of files it joins, not by line numbers, which move whenever code above them changes.
The baseline holds, per pair of files, how many clones and lines they cover, plus the total of duplicated
lines. The check fails when a pair is new, when a pair has more clones or lines, or when the total of
duplicated lines is larger. It compares line counts, not the percentage, because a percentage rises when
clean code is deleted and falls when clean code is added, so it can hide a new clone. The percentage is only
printed.

## scripts/errorcodes.py

The refusals of the daemon that carry a code are found in its source: for each code, the values (`params`) it
passes and the English sentence it writes, as a template of the page's message syntax (`{name}` is a value,
`{{` a literal brace, `{*}` a part of the sentence that is not one of the values). scripts/gen-protocol.py
writes this as ui/src/protocol/errors.json; the page's catalogue (ui/src/i18n/en.ts) is held to it by a test,
so a code the daemon gains must have a sentence on the page and the sentence is the daemon's. A refusal is a
call with a code in its second argument (`CodedError(text, "setting.range", value=...)`,
`SettingError(key, code, {...}, text)`, `UserError(text, code, params={...})`, `Reason(text, "radio.silent")`)
or in `code=` (`conn.error(text, code=...)`). The sentence is its f-string with the leading `<command>: ` or
`<setting>: ` removed (the page places the reason itself); an expression that is one of the values becomes
`{name}` and `{x!r}` becomes `'{name}'`.

## scripts/flaky

Every run is `uv sync --frozen --extra app --extra ble` followed by `scripts/check --stage pytest`, the first
and the last line of the CI's job `python` that scripts/check-in-container holds; the lock, ruff, mypy and
layer checks are not what is hunted. Four settings go round, each in a quarter of the runs (run n uses
settings[n % 4]): the runner's size or half of it (`--starved`: two threads, 7 GB, where tests that count on
time show themselves), and the tests in file order or in the order of a seed (tests/support/shuffle.py; the
seed is the run number, passed in PYTEST_ADDOPTS, which the stage forwards). pytest's output is made wide
enough not to cut a failure's message. Each container has cores no other holds and its own loopback, so runs
cannot meet on a port; the image is built once before any run. A run ended for its time is listed with the
stack `faulthandler_timeout` printed, and a run that did not reach the tests with the last lines of its log.
Exit code 0 when every run passed, 1 when a test failed or a run hung or did not run, 2 when docker or git is
missing. The default limit of 45 minutes is above the CI job's 30 because the first run on a cold cache also
has the install to do.

## scripts/install-probe.py

What the upgrade check of scripts/check-installs asks of an installed NeoAPRS, inside its container: the
daemon of the old release is given something to keep (`seed`), and the daemon of the new build, installed
over it, must have all of it (`verify`). It runs with the Python that has neoaprs installed (the .deb's
`/opt/neoaprs/bin/python3 -I`, which has Tornado's WebSocket client), next to scripts/smoke.py, whose fake TNC
and daemon start it reuses. `seed` starts the daemon on the data folder with a fake KISS TNC (the FM radio) and
the settings of a station with an HF radio (the Dummy HF radio; both on), waits until stations are heard,
sends one message, records what it saw and stops the daemon the way a service manager does. `verify` starts
the new daemon on the same folder and requires every station, the message and the settings, the new version in
the hello, and a clean stop (exit code 0, `NeoAPRS ended`, a database that passes its integrity check). Only
the page WebSocket's long-standing interface is used (topics `stations`, `messages`, `config`, commands
`set_config`, `send_message`, the `hello`, and for radios the topic `radios` and the radio commands). Nothing is sent to a
radio and nothing leaves the loopback (NEOAPRS_NO_DEVICES).

## scripts/mercury-bench

The bench exercises APRS over the Mercury HF modem with no radio, for a developer by hand against the Mercury
the checkout carries (`scripts/build-mercury --install`, or `--mercury PATH`). Two real Mercury instances are
cross-wired through named pipes (Linux only; Mercury's `fifo` audio backend: what one plays the other hears)
and two NeoAPRS daemons, each on its own data folder with the Mercury radio type attached to its own Mercury,
are driven through the pages' sockets: a beacon of A heard by B (direct, whatever A's path setting says), a
message from A acked by B with the time it took, and the longest message acked too (over HF every message
fits the frame). Nothing is keyed and nothing leaves the loopback. Mercury's fifo backend delivers a frame's
samples as fast as the pipe takes them while the sender holds PTT for the frame's time, so a straight pipe
lets the far side decode and answer while the near side still transmits, and the answer is lost (half
duplex). The bench therefore pipes the audio through a pacer of its own: 8000 samples of 32 bits a second,
with silence between frames as a sound card would deliver, so that a frame is decoded when it ends and the
answer comes when the sender listens again. The pacer also adds noise at about -66 dBFS under the signal:
Mercury's busy detector takes its noise floor from what it hears, and on digital silence the floor is zero
so every frame reads BUSY for a minute.

## scripts/mercury-measure

The script measures the numbers NeoAPRS fixes for the Mercury HF modem (docs/mercury.md has the table), with real
Mercury instances on the suite's simulated channel (`tests/support/hfchannel.py`); nothing is keyed and nothing
is on the air. Each measurement prints a table and, with `--report FILE`, writes JSON so a number in the docs
can be made again. Linux only (named pipes). Measurements:

- `frame`: one frame's levels and times: peak and RMS of what Mercury plays, time on the air (PTT ON to PTT
  OFF), hand-in to the far station's KISS port, the busy detector's lag and hang time, the SNR the far station
  reports. The busy detectors take their noise floor from the noise, so the channel carries noise.
- `decode`: frames delivered of N sent at each SNR, on a flat channel or a Watterson preset (good, moderate,
  poor, flutter). A point of 50 frames takes about four minutes (a frame is 3.9 s on the air and the next waits
  for the channel to clear); points run one after another, so several runs with different `--first-port`
  values make a table quickly. The far side decodes within a few hundred milliseconds of the end of a frame.
- `vox`: frames delivered when the first milliseconds of every transmission are muted (a VOX's attack), before
  the channel's fading as a radio that starts late does, with Mercury's own frame start (`--leadin-ms 0`) or
  with the lead-in tone NeoAPRS's Mercury plays ahead of the preamble.
- `acks`: two daemons on the channel send N messages one after another; the time to each ack is compared with
  the retry schedule.
- `busy`: the busy threshold (`busy_threshold_db`, 10 dB by default) tried at 10, 12 ... 24 dB, one transmitter
  and one receiver per threshold on the same channel. First what a frame does to each (does its BUSY ON come,
  and how soon) at SNRs from -3 to 20 dB on white noise (the noise stays where it is, 20 dB under a frame at
  gain 0: a frame's level is the link's gain and the floors need not follow a step); then what no frame does:
  how long each reads BUSY in 90 s of white noise, noise filtered as a radio's audio is, with carriers 6, 9, 12
  and 15 dB above the noise of their band, and after steps of 10 and 20 dB in the noise (the floors settle for
  20 s first). About 20 minutes.
- `autobusy`: the automatic channel-busy control against Mercury's fixed 14 dB: the same spectra, read from real
  Mercury instances, judged by Mercury's detector as it runs (its BUSY lines) and by the detectors of
  `neoaprs/channelbusy.py` replayed on the bands of every spectrum, in scenes of noise (steady, filtered,
  carriers, a step, a slow rise, static, wandering, a voice) with frames at 20 to -3 dB SNR sent before them
  (AUTO_SNRS, `--frames` times each). The quiet part, where the scene's event takes place and no frame is sent,
  follows. Two batches of six receivers, about 7 minutes each. `--record FILE` keeps what the receivers saw;
  `--replay FILE` judges a recording again with no Mercury at all, so detectors can be changed and tried in
  seconds. The gap between two frames lets the hang and tail of the one before end.
- `beacons`: no Mercury. Fixed stations on one beacon interval, each started at a random moment of the first
  interval (a daemon start is a random phase already) and adding a random pause of up to J seconds after every
  interval (`radiotype.HF_BEACON_JITTER_SEC`); over `hours` of simulated time, how many beacons are lost to an
  overlap (two frames within FRAME_SEC of each other are both lost, as Mercury's broadcast plane has no carrier
  sense), for each J. Also the case the pause is for: every station started in the same minute (a net that
  switched on together, or clocks that agree). Without the pause an overlap of phases lasts the whole round,
  so many short rounds measure it.

Frames are 100 bytes so that every frame is its full size whatever the payload.

## scripts/mercury-sim

The simulation runs N real Mercury instances joined by one simulated channel (`tests/support/hfchannel.py`):
every station hears the sum of the others with noise at a chosen signal-to-noise ratio, a keyed station hears
nothing and two keyed at once collide. Each station has a NeoAPRS daemon on its own data folder. Linux only
(named pipes, Mercury's fifo backend); nothing is keyed and nothing leaves the loopback. A scenario driven
through the pages' sockets is checked against what an HF net must do: every beacon heard by every other
station; the longest message around the ring acked by each; two simultaneous keyings losing both frames, with a
message between them going through afterwards; a lost ack (the sender retries, the receiver acks again, the
message is kept once); a Mercury that dies and comes back; a daemon restarted with a message on its way; a weak
link; a poor fading channel at 0 dB (CCIR 520-2 Watterson: two paths 2 ms apart, 1 Hz Doppler spread, noise at
the signal's level; some beacons are lost, a message gets through on retries, and the busy detectors, whose
noise floor rises slowly, hold the radios until the modem's hold cap); the first stations also on FM (a KISS
hub is their FM air); the FM radio away while HF talks; and the first station gating what it hears to a fake
APRS-IS. The daemon may be the checkout's or an installed one (`--daemon /usr/bin/neoaprs`), and Mercury the
checkout's or any (`--mercury`). The default run (five stations, two also on FM) takes about five minutes.
`--fading poor --snr 6` runs the scenario on a fading channel, where expectations may fail. Two runs at once
need different `--first-port` values (ten ports per station).

Constants. Station i has the KISS port FIRST_PORT + 10 i and the control port 200 above it, the distance the
daemon expects of a Mercury it did not start. The weak link gain leaves 3 dB at the channel's default 30 dB,
where DATAC3 still decodes every frame on a flat channel (`scripts/mercury-measure decode`: all frames down to
-2 dB, none at -6). The longest message is 98 bytes direct with its number and addressee, under the frame's
123. The late-block share limit (how many of the channel's 20 ms blocks may start a block late or more) is
there because a busy machine stalls the thread now and then: a quiet machine has none or one in 18,000, a
GitHub runner was seen at 1.6 per mille and passed at under 1 twice, and a frame survives a late block, which
only delays it; a second's stall would be fifty. Over the poor channel at 0 dB codec2's table has DATAC3
deliver 74 of 100 single frames, so some of the beacons are lost and some heard. A command is given a short
time to be refused before it counts as taken, because the daemon answers a refusal at once. `when_free` waits
for the radio to take a frame: the daemon refuses `beacon_now` and `send_message` while Mercury keys the radio
or hears a signal (the plane's one carrier sense), as an operator sees the busy lamp; a BUSY that lasts holds
nothing after the modem's cap, so the wait is that long at most. `send_taken` resends when the daemon refuses
all the same (the channel went busy, or a frame of the station's own went out, between the look and the send).

## scripts/release

`scripts/release VERSION` makes a release in one command and can be run again after any failure: what is done is
detected and skipped. It requires master, the repository's GitHub switches on (secret scanning and push
protection, Dependabot alerts, code scanning, immutable releases, actions pinned by commit; read back through
`gh api` and refused by name when one is off), a clean tree up to date with origin, and notes under
`## Unreleased` in CHANGELOG.md. It then writes VERSION and the changelog section, builds the page to compare it
with the committed one only when ui/ changed since the last tag, runs scripts/check, commits, pushes, waits for
the CI run of that commit, tags `v<VERSION>` on that commit and pushes the tag, waits for the release run (which
leaves a draft), signs SHA256SUMS, uploads SHA256SUMS.sig, checks it with the program's public key, publishes
the release, and checks that it is published (not a draft, its 15 files, the signature holding, every download
link answering). With `--deploy` it uploads the version page (server/deploy.sh, which needs the operator's
Bitwarden session; without it the command is printed). When a fix came after the release commit and no tag is
made yet, HEAD is the release (its CI run, the tag on it) if it has the same VERSION and changelog section; a
tag is never moved. `--dry-run` prints the steps, what is done and what would refuse, and changes nothing;
GitHub is asked only for the switches (read only) and origin with `git ls-remote`. `--rerun` reruns the failed
jobs of a failed CI or release run once (a flaky test). `--interval` is seconds between looks at GitHub
(default 15), and the first wait after a rate-limit answer, doubling over five tries. `--verify` only checks the
published release.

The signing key is the secret whose id NEOAPRS_SIGNING_SECRET_ID names, read with `bws secret get` (bws takes its
token from BWS_ACCESS_TOKEN and its server from BWS_SERVER_URL) into memory; it is never printed, written to a
file or put in a command line. bws is the only program given BWS_ACCESS_TOKEN and NEOAPRS_SIGNING_SECRET_ID:
scripts/check, git and its hooks, gh and server/deploy.sh run without them, so that no install script of
`npm ci`, a test, tool or hook can read the key. The script uses the operator's own `gh`, as the anonymous API
of a sandbox hits GitHub's rate limit at once. The 15 files of a release are the installer, the AppImage, the
macOS disk image and the two packages, the five again under fixed names, the source tarball (for packagers),
the wheel and install.sh (for copies installed before 0.16, whose update runs it), SHA256SUMS and
SHA256SUMS.sig. A 403 on a switch is a missing permission and no rate limit, so it is not waited out.

## scripts/security-check

The checks read what git tracks, never the developer's own folders. The programs are the pinned ones that
scripts/security-tools fetches into the build cache; php is the system's. A missing program fails its check
with the way to get it, because a check that could not run is never a pass. Checks:

- `secret-files`: no tracked path has a part named `.secrets` (or starting with it) and none lies in the tree
  unignored; names only, nothing is opened.
- `tokens`: nothing of the form of the secrets manager's access token is on its way to GitHub. The script looks
  itself, with no program and no exceptions, in every commit of a local branch or tag that the remote lacks
  (changes, a merge's resolution, message), in tag messages, in the staged index and in every tracked file, as
  bytes. It names the commit and file, never what it found.
- `gitleaks`: no other secret in this branch's commits, their messages, or the changed or staged tracked
  files; `.gitleaks.toml` lists the made-up values, each with its reason.
- `php-lint`: `php -l` over every tracked `*.php` of server/.
- `psalm`: taint analysis of server/ (server/psalm.xml); only `Tainted*` reports count. Without the XML
  extensions it runs in the pinned php image with docker, read-only and without network.
- `shellcheck`: level `warning` over the tracked shell scripts of server/, scripts/ and packaging/, against the
  baseline; a tracked settings file or a `disable` without a reason is a finding.
- `zizmor`: the workflows, offline, severity `medium` and up, against the baseline; a tracked settings file is
  a finding.
- `audit`: osv-scanner over uv.lock and ui/package-lock.json; `osv-scanner.toml` lists advisories set aside.

The baseline `scripts/security-baseline.json` holds what shellcheck and zizmor are known to find, each entry
with a count and a reason; a finding not in it, or one more of a kind that is, fails. It is rewritten with
`--update`, never larger unless `--allow-growth`. `tokens` normally reads commits the remote lacks;
`--all-history` reads every commit, the remote's branches too. The token form searched for is deliberately
looser than the real one, because nothing else in the tree has it, and the pattern also allows a NUL after
every character so the text is found as UTF-8 and as UTF-16. git is run with a plain environment (no `git
replace`, no log settings), because a push sends the commit as stored.

## scripts/security-tools

Each tool that scripts/security-check runs (gitleaks, shellcheck, zizmor, osv-scanner, Psalm) is a file of the
tool's own GitHub release at one pinned version, downloaded from GitHub's hosts only and kept only when its
SHA-256 is the one written in the script (the digest GitHub shows for the release file; the pin is the trust,
not the server). Programs go to `security-tools/` in the build cache (`$NEOAPRS_BUILD_CACHE`, default
`~/.cache/neoaprs-build`), one folder per tool and version, so a new pin is a new folder; nothing is installed
on the system or put on the PATH, and security-check asks this module where each program is. The pins are for
Linux x86_64 only. Psalm's file is a PHP archive: the system's php runs it and needs its XML extensions
(Debian and Ubuntu: `php-xml`), which this script does not fetch. Where php lacks them, security-check runs
the archive in the official php image with docker; PHP_IMAGES pins that image by php minor version with the
digest of the tag `<minor>-cli`, which is what `docker pull php:<minor>-cli` prints as `Digest:`. A minor
version without an entry has no image and the check fails saying so. A transfer that ends before the size the
server announced is an OSError, so it is retried and not taken for another file. Moving a pin: write the new
version, address and digest, then run security-tools and security-check to see what the new version finds
(docs/security-checks.md). The script needs the network and the standard library only, so that it runs before
there is a venv.

## scripts/site-check

`site-check URL` compares the live project page with what is committed and asks the private places whether
they are private. It is not a stage of the gate (it needs the network); run it after `server/deploy.sh --site`
and from time to time. Every file the last commit (HEAD) has under `site/` is fetched over https and its
SHA-256 compared with the committed one's (and `/` with `index.html`); what is edited on this computer and not
committed is not the measure. A missing, changed or redirected file is a finding. Then the places that must
answer 403 are asked: the stored support files and their log, PHP's settings, the version page's logs and
cache, and every `.htaccess` and every PHP file git has under `server/neo/` that is not an endpoint in
`PUBLIC_PHP` (a helper is never called from the web). A file that is on the server and not committed cannot be
found by asking, so the list of what is committed is the list compared. A link or submodule is no file;
`server/deploy.sh` refuses them. Only https is used, except an address on this computer (127.0.0.1, localhost)
which the tests use; only GET requests are sent. Exit 0 when the page is what is committed and every private
place answers 403, 1 for any finding (one line each on stdout), 2 when it could not ask at all.
version.php and latest.php are one folder up in the repository and are not under `neo/`.

## scripts/update-e2e.py

The end-to-end test of Update now uses the real files of a release. The old version is installed (the Windows
installer, run silently) or put in a folder (the AppImage) and its daemon runs on its own data folder against
a fake KISS TNC. A fake version page announces the new version and a fake release server on the loopback serves
its file, SHA256SUMS and SHA256SUMS.sig as GitHub does (`v<version>/<file>`), signed with a key the test makes
and passes as `NEOAPRS_UPDATE_KEY`. Over the page's WebSocket the test asks the update check, sends
`update_now` and follows the topic `update`; the new daemon must come up by itself on the same data folder. The
daemon gets `NEOAPRS_UPDATE_TEST=1` and `NEOAPRS_UPDATE_FROM`; nothing leaves the loopback and no radio or serial
device is used. Versions are read from the file names and B must be newer than A. The test runs an installer and
replaces files: run it on a CI runner, never on a developer's own computer, with a Python that has Tornado
(docs/development.md, "Update now").

Asserted for both kinds: A's hello says A and the install kind; the update check finds B; update_now never goes to
`error`; SHA256SUMS, its signature and B's file were fetched; a daemon comes up on the same data folder, says B,
connects to the same fake TNC, keeps the packets and the settings; the log has A's start, A's end and B's start
and ends with `NeoAPRS ended`; B's page is served on the port A used, where an open page waits (not the
settings' port, which the test holds while A starts), and the restart notes are gone once B runs.

Windows: B's installer ran silently (its log in `update/` of the data folder), A's daemon ended with 0, the
installed neoaprs.exe and Windows' program list say B, `update/` holds B's installer and log alone, nothing else
changed (start at sign-in, Start menu, desktop, default data folder), and no NeoAPRS program or installer is
left running. AppImage: the file in place is B (SHA-256), executable, with no `.old` or `.part` beside it, the
same process went on as B and nothing was written to the home folder; B runs as A ran (mounted when A was
mounted, unpacked when A was unpacked, read from the daemon's `$APPDIR`). `--extract-and-run` starts the file as
a system without FUSE does.

`--app` (AppImage only): the desktop app replaces the bare daemon, as a user runs the file. A starts as
`app --data DIR`, which starts its own daemon, on Qt's offscreen platform (no tray icon or window on a screen,
but the app's logic, window page and watches run). Without FUSE the app is started with
APPIMAGE_EXTRACT_AND_RUN=1, since the runtime drops the flag and the daemon it starts would try to mount the file.
The page's port is the one in `neoaprs-web.url`. Before the update, read from /proc: A's app runs its window and
started its own daemon; one app and one daemon run on the data folder, each mounted or unpacked as started; the
app's pid, port and lock files are its own. After: once B's daemon runs, A's app ends as Quit would but leaves
the daemon and runs B's file in place (neoaprs/desktop/renew.py, `--owns-daemon`); the app's program is B's and
runs as A's did, exactly one app and one daemon are left, and every mount in the temporary folder belongs to a
running program (a mount of A beyond 30 s is reported); the home folder holds only NeoAPRS's own files, and
what Qt and the web engine wrote is reported. At the end `app --quit` ends the app and the daemon within its
time with exit code 0, the daemon's log ends with its clean end, and no process or mount is left. An unpacked
run shares one folder that the first runtime to end removes: its "Failed to clean up cache directory" is
reported, not failed.

`--known-old`: A is a release of 0.20.1 or before with known restart quirks, reported but not failed (its
AppImage starts B unpacked though A was mounted, and its restart names no port). With `--app` it also covers an
A of 0.20.2 or before whose app does not start again as B (it has no renew.py; found by
`app --owns-daemon --quit` on an empty folder, which it refuses). Held is that the daemon came back as B, the
app goes on, and Quit still ends both. Exit code 0: all is well; 1: the first thing that was not, said on stderr;
the work folder keeps the logs.

Other facts the code relies on. The first release whose Update now asks for SHA256SUMS.sig is a constant; an
older one (0.18.2) is updated by the checksum alone. The FM radio's port is the flat key of every version before
the radios were separate (kept as radio 1's), its own key afterwards; on a fresh folder a newer version has no
radio 1, so it is added by its command line. A daemon listens on the port of its settings and the ten after it
when that one is taken (neoaprs/web/listen.py). 

## scripts/webkit-probe.py

The probe counts how the map moves in a web engine window: one window on the daemon's page, then for SECONDS the
map is zoomed with the wheel and dragged with the mouse (events dispatched on the map canvas, nothing added to
the page), and frames are counted with requestAnimationFrame. It prints one JSON line: frames and frames per
second, whether WebGL2 is available, the engine's user agent, the time from the script's start to the first
paint of the page, and the engine. `--engine web` (default) is pywebview on WebKitGTK as the trial AppImage's
window has it (run with that image's Python or one with pywebview and gi); `--engine qt` is the Qt window
(QWebEngineView) with a Python that has PySide6-WebEngine. It needs a display; nothing leaves the loopback but
what the page asks for.
