# The NeoAPRS manual

NeoAPRS is an APRS client for a radio or a TNC. It reads your radio, keeps every packet and station in a database on your computer, and shows them in a page: a map, a table of stations, the packets as they arrive, your messages as conversations, the state of the radio link and the settings.

It sends your position (the beacon) and your messages, email through the APRS gateway, objects and bulletins of your own, and a status text. It answers messages and queries sent to you, and can repeat packets as a fill-in digipeater.

The program is a daemon with a web page. You can use it as a desktop app (a window and a tray icon) or as a service on a Raspberry Pi that you reach from a laptop or a phone.

This is the manual for the person who runs it. How NeoAPRS is built and released is in [`docs/development.md`](../development.md), and the front page is [`README.md`](../../README.md).

## Contents

| file | what is in it |
|---|---|
| [`install.md`](install.md) | installing on Windows, Linux (AppImage, .deb, install line, pip), the desktop app, starting at login, updating |
| [`start.md`](start.md) | the first start, the setup guide, the data folder, how settings apply, trying it without a radio |
| [`page.md`](page.md) | the page: the map, the cards you can move, the tabs, the Stations table and its menu, the language, a phone, a tablet and a desktop, the base map |
| [`desktop.md`](desktop.md) | the desktop app: a window and a tray icon |
| [`radio.md`](radio.md) | connecting the radio: ports, Bluetooth, the TNC types, the keep-alive and a silent radio |
| [`beacon.md`](beacon.md) | the Beacon tab: the beacon, the status, answers to queries, the fill-in digipeater |
| [`messages.md`](messages.md) | the Messages tab: sending, acks and retries, the path each message chooses, deleting |
| [`email.md`](email.md) | email through the APRS gateway |
| [`bulletins.md`](bulletins.md) | the message board and posting to it |
| [`objects.md`](objects.md) | objects and items of your own |
| [`weather.md`](weather.md) | weather stations, the graphs and what else NeoAPRS reads |
| [`notifications.md`](notifications.md) | being told of a new message |
| [`network.md`](network.md) | opening the page from another device, the access key, https, installing the page as an app |
| [`settings.md`](settings.md) | every setting with its default |
| [`commands.md`](commands.md) | the `neoaprs` command line, the service, troubleshooting with `neoaprs doctor` |

The radios and how to connect each are in [`docs/RADIOS.md`](../RADIOS.md).

## Words

- A **setting** is a row of the database that you change on the page or with `neoaprs db set`.
- The **radio** is what you transmit with; the **TNC** is the box that turns a packet into sound or the other way, built into some radios; the **rig** is a radio that a program such as Hamlib's rigctld can read the frequency of.
- A **path** is the list of digipeaters a packet asks to be repeated by. The **route** is what a received packet actually went by, and the **chain** is the same for a message of yours, hop by hop.
- The **timeout** of a station is how long it stays on the map after its last position.
- The **email gateway** is the APRS-IS station `EMAIL-2`.
