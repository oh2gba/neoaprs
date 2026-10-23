# Changelog

## Unreleased

- Objects and items of your own: an Objects tab to make, change and kill them, placed by a click on the map or by dragging their marker, shown on the map as ours. They go out on the specification's decay schedule up to the net cycle time of their path, a kill is sent three times, and a copy that is heard back makes no second object.
- Posting to the message board: a small box on the Bulletins tab for a bulletin, an announcement or a group bulletin, sent a few times early and then at a long interval (a bulletin for 4 hours, an announcement for 3 days), shown on the board as ours with an x that stops it.
- Both obey the transmit interlock (nothing without a call, nothing while the radio is silent), keep their schedule across a restart, and are paced: never within a minute of the last packet of the same object, never a burst.

## 0.1.0

The first release.

- A map of the stations you hear (OpenStreetMap data cut to your area with the pmtiles tool, a world map under it), with APRS symbols, trails, a Stations table, station cards and the packet log.
- Messages with acks, reply-acks and retries, the route of each message, a path, a timeout and an attempts count for each station, alerts on the desktop, bulletins and group messages, queries (`?APRSP`, `?APRSS`, `?APRSD`, `?APRST`, `?APRS?`), and email through the APRS gateway.
- The beacon (PHG, DAO, compressed form), the status report from a Hamlib rigctld or a text, and a transmit interlock: nothing is sent until a call is set.
- Weather stations with readings and 24 hour and 7 day graphs.
- Radios and TNCs: Kenwood TH-D7, TM-D700, TS-2000 and TNC-2 clones, TM-D710 and TH-D72, TH-D74 and TH-D75, Mobilinkd TNC3 and TNC4, NinoTNC, TNC-Pi, TNC-X, Kantronics KPC-3+, and any radio with a sound card through Direwolf or a soundmodem (KISS over TCP). A keep-alive check notices a radio that is switched off and finds it again.
- The desktop app: the page in a window with a tray icon, on Windows (WebView2) and on Linux and macOS (Qt), as an optional extra.
- The search for the radio leaves development boards alone (ESP32, Arduino, Pico and other boards, debug probes), whose USB console resets the chip when the port is opened; a port chosen by name is always opened.
- A setup guide for the call, the position, the symbol, the radio and the map; `neoaprs doctor` says what keeps the radio from working.
- `neoaprs replay` plays a capture as a TNC, to try NeoAPRS without a radio.
- Network access: one switch in the Settings (Web page, Allow access from the network) opens the page to other devices on the network with no restart, behind an access key that is shown in the Settings; this computer is never asked for it.
- A SQLite database for everything NeoAPRS keeps, with migrations and a backup copy before each one.
- Downloads: the Windows installer `NeoAPRS-Setup-0.1.0.exe`, the Linux AppImage `NeoAPRS-0.1.0-x86_64.AppImage`, the wheel and sdist, and `install.sh` for Linux, macOS and the Raspberry Pi, with `SHA256SUMS` and build provenance. `neoaprs service install` starts it at login (systemd, the Run key of Windows, launchd).
