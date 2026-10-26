# The NeoAPRS manual

NeoAPRS is an APRS client for a radio or a TNC. It reads your radio, keeps every packet and station in a database on your computer, and shows them in a page: a map, a table of stations, the packets as they arrive, your messages as conversations, the state of the radio link and the settings.

It sends your position (the beacon: of a fixed station at its place, or of a moving one that follows a GPS) and your messages, email through the APRS gateway, objects and bulletins of your own, and a status text. It answers messages and queries sent to you, and can repeat packets as a fill-in digipeater. A receive-only iGate, if you switch it on, puts what your radio hears on APRS-IS. A Nearby tab lists the digipeaters, voice frequencies, iGates and stations in simplex range that you have heard.

The program is a daemon with a web page. You can use it as a desktop app (a window and a tray icon) or as a service on a Raspberry Pi that you reach from a laptop or a phone.

This is the manual for the person who runs it. How NeoAPRS is built and released is in [`docs/development.md`](../development.md), and the front page is [`README.md`](../../README.md).

## Contents

| file | what is in it |
|---|---|
| [`install.md`](install.md) | installing on Windows, Linux (AppImage, .deb, install line, pip), the desktop app, starting at login, updating |
| [`start.md`](start.md) | the first start, the setup guide, the data folder, how settings apply, trying it without a radio |
| [`page.md`](page.md) | the page: the tabs, the Stations table and its menu, [the Nearby tab](page.md#nearby), the Packets tab, the Settings tab, the map (the range circle, Follow my position), the station cards you can move, the header and the footer, the language, a phone, a tablet and a desktop, the base map |
| [`desktop.md`](desktop.md) | the desktop app: a window and a tray icon |
| [`radio.md`](radio.md) | connecting the radio: ports (serial, TCP, Bluetooth, Bluetooth LE), finding the radio, the TNC types, the keep-alive and a silent radio |
| [`beacon.md`](beacon.md) | the Beacon tab: the beacon status, where the position comes from (fixed, or a GPS), the Beacon choice and Off, receive only, mobile operation with SmartBeaconing, the location and the symbol, the status, answers to queries (and the QRU server), the fill-in digipeater |
| [`messages.md`](messages.md) | the Messages tab: sending, acks and retries, the path each message chooses, deleting |
| [`igate.md`](igate.md) | the receive-only iGate: what it puts on APRS-IS, the passcode, the server, which packets it leaves out, the counts |
| [`email.md`](email.md) | email through the APRS gateway |
| [`bulletins.md`](bulletins.md) | the message board and posting to it |
| [`objects.md`](objects.md) | objects and items of your own, and the QRU server that sends them to a station that asks |
| [`weather.md`](weather.md) | weather stations, the graphs and what else NeoAPRS reads |
| [`notifications.md`](notifications.md) | being told of a new message |
| [`network.md`](network.md) | opening the page from another device, the access key, https, installing the page as an app |
| [`settings.md`](settings.md) | every setting with its default |
| [`commands.md`](commands.md) | the `neoaprs` command line (the daemon, `service`, `map`, `db`, `open`, `stop`, `replay`, `gps-replay`, `capture`, `app`), troubleshooting with `neoaprs doctor` |

The radios and how to connect each (and a GPS receiver for a moving station) are in [`docs/RADIOS.md`](../RADIOS.md).

## Words

- A **setting** is a row of the database that you change on the page or with `neoaprs db set`.
- The **radio** is what you transmit with; the **TNC** is the box that turns a packet into sound or the other way, built into some radios; the **rig** is a radio that a program such as Hamlib's rigctld can read the frequency of.
- A **path** is the list of digipeaters a packet asks to be repeated by. The **route** is what a received packet actually went by, and the **chain** is the same for a message of yours, hop by hop.
- The **timeout** of a station is how long it stays on the map after its last position: 1, 3, 6, 12 or 24 hours as you choose in the Stations tab (3 by default), the same for every station.
- The **email gateway** is the APRS-IS station `EMAIL-2`.
- A **fixed** station beacons from the location you gave; a **moving** station beacons from a GPS, and a GPS is chosen by the Beacon tab's **Position**. The **Beacon** choice switches the beacon off. **Receive only** is the daemon's setting `station/transmit`, which stops all transmitting.
