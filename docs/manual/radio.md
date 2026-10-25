# Connecting the radio

How to connect each radio and TNC is in [`docs/RADIOS.md`](../RADIOS.md). This page says what NeoAPRS does with the port you give it.

## The port

The radio's port is the setting `serial/port`. In the Settings tab, in the TNC group (behind the arrow of its status line), it is one choice, **Port**.

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
- **The control lines** DTR and RTS are held low from the moment the port is opened, because a sound-card interface keys the transmitter on RTS.
- **A TCP type** (`kiss-tcp`) connects to the **TCP host** and **TCP port** settings when the port is empty: `127.0.0.1` and `8001` by default. Direwolf uses 8001, UZ7HO SoundModem and QtSoundModem 8100 (the program's KISS port, not its AGW port). A TCP type is refused, with the reason, while the port names a serial device.

## Finding the radio

With no port given, on Linux NeoAPRS listens to all the ports that match the settings `serial/pattern` at the same time, for as long as it takes, for the one that sends KISS frames. The default pattern is `/dev/serial/by-id/*`, `/dev/ttyUSB*` and `/dev/ttyACM*`. A device with several names is listed once, under the first glob that matches it.

- A TNC in KISS mode sends nothing until it hears a packet, so on a quiet band the search takes a long time.
- With a TNC type that can be asked (Kenwood, Kantronics), a carriage return is sent to every port after 10 seconds of silence. A TNC in command mode answers it and is then switched to KISS. With any other type, the default included, the ports are only listened to and nothing is written to them.
- A port another program holds is skipped. So is a development board, known by its USB ids: ESP32, Arduino, Raspberry Pi Pico and similar boards and debug probes, whose console resets the chip when the port is opened. The log says which ports were left out and why. A port named in `serial/port` or `--port` is never left out.
- The port it found is remembered as `serial/last_port` and tried first next time. A port that cannot be opened is followed by the search, and a line that drops is opened again after 5, 10, 20, 30 seconds.
- `serial/skip` lists ports the search never opens (a rotator's adapter, say), separated by commas. A pattern of your own, such as `/dev/brainbox_*` for Brainboxes adapters, is set with `neoaprs db set serial/pattern "..."`; a change restarts the search. Neither is on the page.

On Windows and macOS NeoAPRS listens to no port it was not told of, because it could write into a GPS or into a rig interface that keys a transmitter. The radio is the port in `serial/port` or the one remembered. A COM port that another program has open is reported as in use by another program.

## Find my radio

The button **Find my radio**, behind the arrow of the TNC group (Linux only, like the search above), finds the port, the speed and the type of TNC by itself, and puts them in the settings like any other change (the toast offers **Undo**). Nothing happens unless you press it.

- It tries the ports of the search above, one after the other (the by-id name first), and with the default pattern the paired Bluetooth devices after them. The ports a development board is behind, the ones that `serial/skip` names and the ones another program holds are left out, as they are in the search. A TCP address is never tried.
- Each serial port is opened at 9600, 57600, 19200, 38400, 115200, 4800 and 1200 baud in turn; a Bluetooth port has no speed and is tried once. Each try listens for 1 second, writes one carriage return and listens for 1.5 seconds more, so a port nobody answers on costs about 18 seconds.
- It stops at the first that answers. A TNC that sends a KISS frame (it has heard a packet) is the type `kiss`. A TNC that answers the carriage return with text is in command mode: the Kenwood TH-D7 type is tried first, then the TM-D710 and then the Kantronics, each by the steps that put that TNC in KISS (the table below), and the first after which the TNC no longer answers a carriage return with text is the type. Nothing is sent to the air.
- The radio's own line is closed while it runs and opened again after it, found or not.
- The toast at the bottom says which port at which speed it is trying and how many tries there are, with **Cancel**. When nothing answered the toast says so. A TNC that is in KISS mode says nothing until it hears a packet, so on a quiet band it may not be found: try again when the channel is busy, or choose the port yourself.

## The radio status

The TNC group of the Settings tab is one line, the radio status, with an arrow in front of it. The arrow opens the rest of the group; it is closed unless the radio is not connected.

- The state is a coloured word: connected, waiting, silent, and so on.
- One plain line follows. "Last packet 2 min ago", "Searching for the radio…" with the ports it listens to behind **Ports**, "Not connected: the reason", or for a silent radio since when it said nothing. The packet and byte counts are its hover text.
- **Reconnect**, small, at the end of the line, opens the line again.

Behind the arrow are the type of TNC, as **Radio type**, and the fields that follow it: the host and port for a TCP type, and for a serial one the port and the speed; then **Find my radio** and **Terminal**.

- **Terminal**, closed until you open it, shows the latest 100 lines of what the TNC saw and did, in monospace and in your browser's time. It follows the end unless you scroll up.

When the digipeater is on and has repeated something, the status says "digipeated N".

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
- **A silent radio.** If nothing at all comes within 2 seconds of the check, the radio is *silent*. The footer says "Radio: silent" with the time of the last byte. Nothing is sent while it is silent: the beacon that is due waits and goes out when the radio is back, messages wait without using up an attempt, and **Beacon now** is refused with "the radio is silent".
- **Coming back.** While silent, NeoAPRS probes every 30 seconds, and every fifth probe also closes the port and opens it again (a USB adapter that dropped). The first byte that arrives ends the silence: KISS is entered again, and a beacon that fell due in the night goes out then.
- These checks exist only for the types that can be asked. The types `kiss` and `kiss-tcp` are usable as soon as the line is open.

The log says `the radio is silent: nothing heard since 18:43 UTC, no answer to a check; probing every 30 s` once when the silence begins, and `the radio answers again after 17 min; entering KISS` when it ends. The internals are in [`docs/daemon.md`](../daemon.md#the-tnc-and-its-keep-alive).
