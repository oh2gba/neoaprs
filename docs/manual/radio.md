# Connecting the radio

How to connect each radio and TNC is in [`docs/RADIOS.md`](../RADIOS.md). This page says what NeoAPRS does with the port you give it.

## The port

The radio's port is the setting `serial/port`. In the Settings tab, in the Radio group (behind the arrow of its status line), it is one choice, **Port**.

| port | what it is |
|---|---|
| a serial port | `/dev/ttyUSB0`, `/dev/brainbox_3`, `COM3` or a macOS `/dev/cu.*` port |
| `socket://host:port` | KISS over TCP (`tcp://host:port` is accepted too), such as a bridge made with `ser2net`. Direwolf serves KISS on `socket://127.0.0.1:8001`, the sound-card modems of UZ7HO and QtSoundModem on 8100. It works with every TNC type |
| `bt://AA:BB:CC:DD:EE:FF` | Linux only: a Bluetooth radio or TNC paired with the computer. `bt://AA:BB:CC:DD:EE:FF/2` names the RFCOMM channel. No `rfcomm bind` and no root |
| `ble://AA:BB:CC:DD:EE:FF` | a Bluetooth LE KISS TNC (the Mobilinkd TNC4 in LE mode, the LoRa APRS tracker, the PicoAPRS V4 in its LE mode and the like). `ble://AA:BB:CC:DD:EE:FF/nus` names the profile (`mobilinkd` or `nus`) or a GATT service by its UUID. Needs the Bluetooth LE extra: `pip install 'neoaprs[ble]'` or `uv tool install 'neoaprs[ble]'`. On macOS the address is the UUID the system gives the device |

The Port choice offers *find automatically* (empty), the ports the system lists, on Linux the paired Bluetooth devices that have a serial port (by name), and *Other...* for a path or a `socket://` or `ble://` address typed (a Bluetooth LE device is not listed: it is typed). **Refresh** asks again. Beside an automatic port it says `found: PORT` when NeoAPRS has found the radio before. On Windows and macOS pick the port from the list.

- **A TCP port** has no speed, is never searched for, and nothing is sent to it that is not a KISS frame. A TCP KISS TNC has no command mode, so there is no keep-alive check. A connection that closes is a line that dropped, and it is opened again after the back-off.
- **A Bluetooth port** has no speed and is never searched for or opened to list it. A link that drops (the radio is switched off or out of range) is opened again like any other. On Windows the paired device's COM port is the way, on macOS its `/dev/cu.*` port ([`docs/RADIOS.md`](../RADIOS.md#bluetooth)).
- **A Bluetooth LE port** has no speed and is never searched for. It is not paired the way a classic device is: NeoAPRS looks for the device by its address when the port is opened, connects and uses the KISS service it finds (the log says which). A device that another program or a phone is connected to cannot be reached: LE allows one connection at a time. A link that drops is opened again like any other ([`docs/RADIOS.md`](../RADIOS.md#bluetooth)).
- **A serial port** has a speed in baud, 8N1. Empty means the type's own, which is 9600 for every serial type. The NinoTNC needs 57600; the Mobilinkd and the TH-D74/D75 ignore it. A TH-D7 on the Brainboxes adapter is 9600.
- **The control lines** DTR and RTS are set low as soon as the port is open, because a sound-card interface keys the transmitter on RTS.
- **A TCP type** (`kiss-tcp`) connects to the **TCP host** and **TCP port** settings when the port is empty: `127.0.0.1` and `8001` by default. Direwolf uses 8001, UZ7HO SoundModem and QtSoundModem 8100 (the program's KISS port, not its AGW port). A TCP type is refused, with the reason, while the port names a serial device.

## Finding the radio

With no port given, on Linux NeoAPRS listens to all the ports that match the settings `serial/pattern` at the same time, for as long as it takes, for the one that sends KISS frames. The default pattern is `/dev/serial/by-id/*`, `/dev/ttyUSB*` and `/dev/ttyACM*`. A device with several names is listed once, under the first glob that matches it.

- A TNC in KISS mode sends nothing until it hears a packet, so on a quiet band the search takes a long time.
- With a TNC type that can be asked (Kenwood, Kantronics), a carriage return is sent to every port after 10 seconds of silence. A TNC in command mode answers it and is then switched to KISS. With any other type, the default included, the ports are only listened to and nothing is written to them.
- A port another program holds is skipped. So is a development board, known by its USB ids: ESP32, Arduino, Raspberry Pi Pico and similar boards and debug probes, whose console resets the chip when the port is opened. The log says which ports were left out and why. A port named in `serial/port` or `--port` is never left out.
- The port it found is remembered as `serial/last_port` and tried first next time. A port that cannot be opened is followed by the search, and a line that drops is opened again after 5, 10, 20, 30 seconds.
- `serial/skip` lists ports the search never opens (a rotator's adapter, say, or the GPS receiver of a moving station: the search does not know which port is the GPS's, so name the radio's port or list the GPS's), separated by commas. A pattern of your own, such as `/dev/brainbox_*` for Brainboxes adapters, is set with `neoaprs db set serial/pattern "..."`; a change restarts the search. Neither is on the page.

On Windows and macOS NeoAPRS listens to no port it was not told of, because it could write into a GPS or into a rig interface that keys a transmitter. The radio is the port in `serial/port` or the one remembered, or the one **Find my radio** finds when you press it. A COM port that another program has open is reported as in use by another program.

## Find my radio

The button **Find my radio**, behind the arrow of the Radio group and under the fields of the Radio step of the setup guide, finds the port, the speed and the type of TNC by itself. In the Settings tab it puts them in the settings like any other change (the toast offers **Undo**); in the setup guide it fills in the fields, and Finish saves them. It works on Linux, Windows and macOS. Nothing happens unless you press it.

- **Linux:** it tries the ports of the search above, one after the other (the by-id name first), and with the default pattern the paired Bluetooth devices after them. The ports a development board is behind, the ones that `serial/skip` names and the ones another program holds are left out, as they are in the search. A TCP address is never tried.
- **Windows:** it tries the COM ports the system lists (`COM3`, `COM10`; the list shows what Windows calls each, such as *USB Serial Port*, *Prolific*, *Silicon Labs CP210x* or *Mobilinkd*). USB adapters come first, then the other serial ports, and a paired Bluetooth serial port last, because opening one can take seconds. Windows lists two ports for a paired radio; the one that answers is the *Outgoing* one.
- A COM port that another program has open cannot be opened and is passed over, with "in use by another program" in the log: close the other program first. Development boards and the ports `serial/skip` names are left out.
- **macOS:** it tries the `/dev/cu.*` devices in the same way.
- Each serial port is opened at 9600, 57600, 19200, 38400, 115200, 4800 and 1200 baud in turn; a Bluetooth port (also a COM port of a paired Bluetooth radio on Windows) has no speed and is tried once. Each try listens for 1 second, writes one carriage return and listens for 1.5 seconds more, so a port nobody answers on costs about 18 seconds.
- It stops at the first that answers. A TNC that sends a KISS frame (it has heard a packet) is the type `kiss`. A TNC that answers the carriage return with text is in command mode: the Kenwood TH-D7 type is tried first, then the TM-D710 and then the Kantronics, each by the steps that put that TNC in KISS (the table below), and the first after which the TNC no longer answers a carriage return with text is the type. Nothing is sent to the air.
- The radio's own line is closed while it runs and opened again after it, found or not.
- The toast at the bottom says which port at which speed it is trying and how many tries there are, with **Cancel**. When nothing answered the toast says so. A TNC that is in KISS mode says nothing until it hears a packet, so on a quiet band it may not be found: try again when the channel is busy, or choose the port yourself.

## The radio status

Each radio box of the Radio group of the Settings tab, after its Enable tickbox, is one line, the radio status, with an arrow in front of it. The arrow opens the rest of the box; it is closed unless the radio is not connected.

- The state is a coloured word: connected, waiting, silent, and so on.
- One plain line follows. "Last packet 2 min ago", "Searching for the radio…" with the ports it listens to behind **Ports**, "Not connected: the reason", or for a silent radio since when it said nothing. The packet and byte counts are its hover text.
- **Reconnect**, small, at the end of the line, opens the line again.

Behind the arrow are the type of TNC, as **Radio type**, and the fields that follow it: the host and port for a TCP type, and for a serial one the port and the speed (the Dummy has none); then **Find my radio** and **Terminal**. The Radio step of the setup guide has the same two under its fields ([start.md](start.md#the-setup-guide)).

- **Terminal**, closed until you open it, shows the latest 100 lines of what the TNC saw and did, in monospace and in your browser's time. It follows the end unless you scroll up.

When the digipeater is on and has repeated something, the status says "digipeated N".

## The Dummy radio

The type **Dummy (no radio, made-up traffic)**, the last in the list of **Radio type**, is for trying NeoAPRS without a radio, on any system. It needs no port and no speed, and nothing is opened: the program makes up the traffic itself, around your station's position (around Helsinki until you have set one). Pick it in the setup guide or in the Settings tab; a person with a real radio picks that type in the Settings tab later.

- A few stations that stay (a house, a club, a cottage), three cars and a walker on routes round the position (some with Mic-E, some with compressed positions), a weather station that reports every 5 minutes, two digipeaters with PHG that repeat the others, two objects, a bulletin now and then and a status. Something is on the air within half a minute, then a few packets a minute.
- **The stations that take messages answer.** A message to one of them is acked after a moment and answered a few seconds later with "Hello from the dummy radio", so messaging can be tried.
- **The club station Q1CLB answers local info.** Objects → Local info → Ask is answered with its categories, 70 cm repeater and Food, and a press on one with its objects ([more](objects.md#asking-for-local-info)).
- **Nothing goes anywhere.** What you send (beacons, messages) is swallowed. A digipeater is heard repeating a beacon of yours now and then, as if it had been on the air.
- The radio status says **Dummy radio: made-up traffic, nothing goes on the air**, in a muted pill.
- Every call is made up on the prefix Q (`Q1ABC`, `Q2DIG-2`, `Q3WX`), which the ITU gives to no country, so none of them is anybody's.
- Nothing of it is meant for the internet.

## The Mercury HF modem

The Radio group of the Settings tab has two boxes, **FM radio** and **HF radio**, each with its tickbox first. The FM radio is the TNC of the pages above (the type, the port, the speed; ticked by default). The
**HF radio** is APRS over HF with the Mercury modem, a separate program that NeoAPRS carries and starts and stops itself; tick it and the station is on HF beside FM, or on HF alone with the FM box unticked.

Which installs carry it and the rules of the air are in [`docs/RADIOS.md`](../RADIOS.md#mercury-hf-modem). The HF box has three fields of its own behind the arrow of its status line, and no port, speed or host.

- **Radio type** is the Mercury modem, or the [Dummy HF radio](#the-dummy-hf-radio) for trying the HF side without a radio. With the Dummy chosen the two fields below and Tune are not there.
- **Sound card** is the radio's. *Find automatically*, the first choice, lets NeoAPRS pick it (the one USB sound card that records and plays, else the system's default device) and says beside the field which it chose; the list is what Mercury finds, **Refresh** reads it again, and *Other...* takes a name typed in.
- **Keying** is how the radio is switched to transmit. *Find automatically* picks RTS of the one USB serial port of a radio or an interface when the sound card is a USB one, else VOX, and says so beside the field; or choose VOX, a CM108 sound chip, or the RTS or DTR line of one of the serial ports the list offers.
- **Test**, beside the Keying field, keys the radio for a second with next to no audio, so that you see it go to transmit and come back; the status line says *Keyed* meanwhile. It is off while RX only is ticked and while Mercury is not running.
- **Tune**, in a row of its own under the fields where the FM radio has Find my radio, keys the radio through the keying in use and sends a steady tone (1000 Hz, the modem's own tuning tone) through the sound card for ten seconds, then stops by itself; a second press, on the button that reads *Stop* meanwhile, stops it early.
  - It is the TUNE button of a rig: for an antenna tuner to find its match, for setting the audio level so that the radio's ALC does not move, and for finding which sound device is the radio (the tone is heard from the radio's monitor and seen on its meter).
  - The status line says *Tuning…* and no frame of yours goes out under the tone. Off while RX only is ticked and while Mercury is not running; refused while a frame is on the air or the channel is busy.
- The mode and the frequencies are not settings: every NeoAPRS station is on the same mode, and the frequencies are in the radios guide.
- The Beacon choice of the My station tab is one for both radios: while the HF radio is on its floor is 30 minutes, the HF beacon adds a random pause of up to five minutes, and behind the status row's arrow a line per radio says each one's last and next beacon. Over HF the beacon is a timed one: SmartBeaconing is the FM radio's, and a moving station's HF beacon says where it is now.
- Every frame goes direct: there are no digipeaters on HF, so no path is sent. With both radios a message goes out on FM when the station was heard on FM (near, quick, and HF airtime is everyone's) and over HF when it was heard on HF alone; an ack or an answer goes back the way the request came. The path and RF only controls of a conversation are there for a station heard on FM, the path of the beacon, Ask around and Local info and the Digipeater group while the FM radio is on; with the HF radio alone none of them is there, and the path settings are kept.
- A station heard over HF has the tag **HF** in the Stations tab, beside **FM** when it was heard both ways: while the HF radio is on, the FM radio's tag says FM in place of RF.
- Each box has its own status line. The HF radio's says what you can act on and nothing of the plumbing: the mode, then *Listening*, *Transmitting…* while a frame is on the air, *Channel busy, waiting* while the modem hears a signal, *Tuning…* or *Keyed* during a test, the signal-to-noise ratio of the latest frame decoded once there was one, and the last packet ("DATAC3 · Listening · SNR 3 dB · Last packet 2 min ago").
  - While the line to the modem opens it says *Connecting…*. When Mercury has stopped, or this installation carries none, the line says so; when Mercury cannot open the sound card it was given (it would run on deaf and mute), NeoAPRS ends it, the line says *the sound card could not be opened: choose another one in the Sound card field*, and Mercury is tried again after a while with the card chosen then. The address the daemon reaches the modem on is in the log, not on the page.
- A beacon's comment is cut to the modem's frame when it would not fit, with a line in the log; the longest message always fits.
- The Radio step of the setup guide has the same two boxes with their Enable tickboxes: the FM radio's fields as ever, and for the HF radio its Enable alone, since the sound card and the keying find themselves.

## The Dummy HF radio

The **Radio type** *Dummy HF radio (no radio, made-up distant stations)* of the HF box is the HF side's Dummy: for trying APRS over HF with no radio and no other station on the air, on any system. Tick the HF radio and choose it; nothing is keyed and nothing goes on the air.

- Six fixed stations hundreds of kilometres away, at real places in Finland and in Europe (Turku, Kuopio, Oulu, Stockholm, Hamburg, Warsaw), each beaconing every half hour to an hour plus the random pause every HF beacon adds, every frame direct. The first beacons come within two minutes of the start, so the map fills while you watch; after that the channel is as quiet as a real one.
- **The nearest station, Q3TKU in Turku, answers a message**: an ack about eight seconds later (a frame's time each way, as the real modem takes) and "Hello from the dummy HF radio" after it. The others take messages and stay quiet, as most do.
- **You hear what the modem sounds like.** Your own transmissions (the beacon, a message, an ack, an object) are played through the computer's sound output as Mercury's real audio: NeoAPRS starts the Mercury it carries, keying nothing, and hands it your frames.
  - On Linux what Mercury transmits goes through the system's own player (`pw-play`, `paplay` or `aplay`, whichever the machine has). On Windows nothing is played: Mercury's audio needs named pipes, which Windows has not, and the Dummy HF radio runs there without the sound.
  - A computer without a player or a recording device, or an install without Mercury, hears nothing and the Dummy works all the same; the log says why.
- The status line says **Dummy HF radio: made-up distant stations, your frames on the speakers, nothing goes on the air**, in the muted pill, and the Stations tab tags the stations HF and Dummy.
- Every call is made up on the prefix Q, as the FM Dummy's are, so none of them is anybody's, however much its letters say where it is meant to be.

## The TNC type

The setting `tnc/profile` says what kind of TNC the radio is. It decides what, if anything, is written to the TNC to put it in KISS, whether the TNC is asked if it is there, and how it is reached. A fresh install is `kiss`, which is sent nothing but KISS frames. A device that needs nothing is sent nothing.

| type | for | to enter KISS (the wait after each step) | to leave | asked if it is there |
|---|---|---|---|---|
| `kiss` (default) | Mobilinkd TNC3 and TNC4 (USB or Bluetooth serial), NinoTNC (set the speed to 57600), TNC-Pi, TNC-X, the Kenwood TH-D74 and TH-D75 with KISS switched on at the radio (`[F]` then `[LIST]` on the D75), any TNC that is in KISS when it is switched on | nothing | nothing | no |
| `kiss-tcp` | Direwolf (8001), UZ7HO SoundModem and QtSoundModem (8100): a program that serves KISS over TCP | nothing | nothing | no |
| `kenwood-tnc2` | Kenwood TH-D7, TM-D700, TS-2000; TAPR TNC-2 and the MFJ-1270B/1274/1278 and PacComm clones | `\rKISS ON\rRESTART\r` (3 s) | `C0 FF C0` | yes |
| `kenwood-d710` | Kenwood TM-D710A/E/G/GA/GE, TH-D72A/E | `TC 1` (1 s), `TN 2,0` (3 s), `HBAUD 1200` (1 s), `KISS ON` (1 s), `RESTART` (1 s), each ended by a carriage return | `C0 FF C0` | yes, and the check enters again with the whole sequence |
| `kantronics` | Kantronics KPC-3+, KPC-3, KAM | `\rINTFACE KISS\rRESET\r` (3 s) | `C0 FF C0` | yes |

- **A TNC that is not asked** (`kiss`, `kiss-tcp`): nothing is written to it but KISS frames. There is no entry, no keep-alive check and no silent state. The open line is all NeoAPRS can know of the radio.
- A TNC in command mode that sends text is told in the radio status; it is not answered. The Kenwood TH-D74 and TH-D75 have no command mode at all and cannot be asked: put them in KISS at the radio.
- **The wait after the last step** is the settle time. What the TNC says meanwhile is thrown away and no frame is sent.
- The `kenwood-tnc2` sequence is the one the Kenwood TNC-2 takes. The `kenwood-d710` sequence is the one of the tmd710_tncsetup project (Debian). Kenwood does not document what `TC 0` and `TC 1` mean, so the sequence is copied as it is, and the check of this type has not been tried on a radio. The `kantronics` entry is from the KPC-3+ manual; a reset has been reported to change the host speed on some units.
- A sound-card interface (a Digirig, a SignaLink) is not a TNC. Run Direwolf or a sound-card modem on it and use `kiss-tcp`; opening the interface's serial port as a KISS TNC would key the transmitter on RTS.
- The list of types is not a promise that a device works. The strings are from the manufacturers' manuals and from users' reports, and [`docs/RADIOS.md`](../RADIOS.md) marks which is which.

## Is the radio there?

A radio that is switched off leaves its USB adapter and port in place. A radio that is power-cycled comes back with its TNC in command mode. A TNC in KISS mode says nothing until it hears a packet. So a quiet line proves nothing, and for a type that can be asked NeoAPRS asks.

- **Keep-alive.** After 10 minutes with nothing at all on the line (and a random minute or two more, so that the check never falls on the regular beacon of a station), NeoAPRS checks that the radio is there: it takes the TNC out of KISS, sends a carriage return, and puts it back in KISS. A TH-D7 that is on answers within about a second. The check costs a few seconds of reception, which is why it runs only after a quiet spell and never while packets flow. A radio that was switched off and on again is noticed at once anyway: its TNC starts in command mode and prints what it hears as text.
- **A line just opened** has not shown that the radio is there, because the adapter is there with the radio switched off. Until a byte arrives (a packet, or the answer to the check) the radio is connected but not usable. The beacon, status, messages, acks and answers to queries wait.
- **A silent radio.** If nothing at all comes within 2 seconds of the check, the radio is *silent*. The header says "Radio: silent", and its hover text the time of the last byte. Nothing is sent while it is silent: the beacon that is due waits and goes out when the radio is back, messages wait without using up an attempt, and **Beacon now** is refused with "the radio is silent".
- **Coming back.** While silent, NeoAPRS probes every 30 seconds, and every fifth probe also closes the port and opens it again (a USB adapter that dropped). The first byte that arrives ends the silence: KISS is entered again, and a beacon that fell due in the night goes out then.
- **A port that goes away and comes back** (the USB adapter pulled out and plugged in again, a COM port that disappears) is tried again every 5 to 30 seconds, and the radio is back as soon as the port is. There is no Reconnect button to press. Where NeoAPRS does not look for the radio by itself (Windows, macOS), an adapter that comes back as another COM port or device is found by its serial number, or, when it has none, as the only adapter of its kind. If two look alike, choose the port in Settings → Radio.
- These checks exist only for the types that can be asked. The types `kiss` and `kiss-tcp` are usable as soon as the line is open.

The log says `the radio is silent: nothing heard since 18:43 UTC, no answer to a check; probing every 30 s` once when the silence begins, and `the radio answers again after 17 min; entering KISS` when it ends. The internals are in [`docs/daemon.md`](../daemon.md#the-tnc-and-its-keep-alive).
