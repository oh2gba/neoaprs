# Changelog

## Unreleased

- The list of ports has the other names of each port after it (the `/dev/serial/by-id` names and links of your own udev rules, such as `/dev/brainbox_3`), and is asked for once the daemon is connected, so a page that opens on the Settings tab no longer shows "Not connected to the daemon".
- The setup guide: the step's name is in its title and no longer twice on the page ("Your call", the symbol's "Code"); the position is picked on the map with **Pick on the map** on every screen, a crosshair while the map waits for the click, and a pin that can be dragged; the browser is no longer asked for its place (on a desktop it is mostly a guess).
- The TNC group of the Settings tab names the port once. **Port** is one choice: find automatically, a port the system lists (with Refresh), or Other... for a path or a `socket://` address typed; beside an automatic port the page says `found: PORT` for the port the daemon found last, which is no longer a field of its own. The search for the radio is under a heading, Search, as "Ports to search" and "Ports to skip" (left out where the daemon does not search and for KISS over TCP), after the Speed and the Keep-alive. No setting changed its name, meaning or stored value.

## 0.3.0

Alerts in the browser, for a NeoAPRS that runs on another computer, and a Notifications group in the settings.

- `neoaprs doctor` warns when Firefox is a Flatpak on KDE and its web pop-ups can go missing (the desktop portal accepts them and shows none), and prints the two `flatpak override` commands that cure it. It reads the overrides and changes nothing.
- Alerts in the page: a message to us now alerts in the browser the page is open in, which is what a NeoAPRS on a Raspberry Pi needs (the alert command runs on the Pi). A notification where the browser allows one (click it to open the conversation), else a short chime and an alert in the browser tab (the title alternates with "✉ CALL" and the icon gets a dot while the page is in the background). Once for each new message, none for a bulletin, an overheard or an own message, or when the page reconnects. The Settings tab has a group Notifications for everything about being alerted: the daemon's own alert (Alert and Command, with its Test button) under "On the NeoAPRS computer", and under "In this browser" one choice, "Alert for a new message" (off, sound, sound and pop-up, pop-up only; sound and pop-up in a page opened from another device where the browser allows pop-ups, off on the computer itself, where the alert command already notifies), kept in the browser, with Test sound and Test pop-up that each say what happened (played, pop-up sent, pop-up blocked, sound locked: click the page once). A pop-up option is disabled, with the reason, where the browser cannot show one, and the permission is asked only when one is chosen. The manual says what to do when pop-ups do not appear. The manual tells how to let the browser show notifications for an address on the network, and how to push the alert to a phone with ntfy when no page is open.

## 0.2.0

Objects and bulletins of your own, and an update check.

- Objects and items of your own: an Objects tab to make, change and kill them, placed by a click on the map or by dragging their marker, shown on the map as ours. They go out on the specification's decay schedule up to the net cycle time of their path, a kill is sent three times, and a copy that is heard back makes no second object.
- Posting to the message board: a small box on the Bulletins tab for a bulletin, an announcement or a group bulletin, sent a few times early and then at a long interval (a bulletin for 4 hours, an announcement for 3 days), shown on the board as ours with an x that stops it.
- Both obey the transmit interlock (nothing without a call, nothing while the radio is silent), keep their schedule across a restart, and are paced: never within a minute of the last packet of the same object, never a burst.
- Update check: once a day (the first a minute after the start) the daemon asks `https://oh2gba.eu/neoaprs/version.php` which version is the latest, sending its version and the kind of system (`windows`, `macos`, `linux`, `linux-appimage`, `linux-arm`) and nothing else. A newer version is shown small in the page's header after the version number, as a link to the project page. Switch it off with the settings `update/check` (Settings tab, Update check), or `NEOAPRS_UPDATE_CHECK=0` for one run; `update/url` is the address of the page. The page's source is `server/version.php`.

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
