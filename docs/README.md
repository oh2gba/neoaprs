# Documents

Every Markdown file of the repository. `tests/test_hygiene.py` fails when a document is missing here or this index lists one that is gone.

| document | what it is |
|---|---|
| `README.md` | the front page: what NeoAPRS is, how to download, run and try it |
| `docs/MANUAL.md` | a pointer to docs/manual, for links to the manual's old place |
| `docs/manual/README.md` | the manual for the person who runs NeoAPRS: what it is, the contents, a few words |
| `docs/manual/install.md` | installing on Windows, macOS, Linux and the Raspberry Pi, starting at login, updating, the update check |
| `docs/manual/start.md` | the first start, the setup guide, the data folder, how settings apply, trying it without a radio, stopping |
| `docs/manual/page.md` | the page: the panel and its tabs (the Stations table, the Nearby tab, the Packets tab, the Settings tab), the map, [the Layers box](manual/page.md#layers) (tracks, the ALOHA circle, the locator grid, aircraft and ships), the station cards, the header, phone, tablet and desktop, the base map |
| `docs/manual/desktop.md` | the desktop app: the window, the tray, start at sign-in |
| `docs/manual/radio.md` | the radio's port (serial, TCP, Bluetooth, Bluetooth LE), finding the radio, the TNC type, the keep-alive and the silent radio; the Mercury radio (the Mercury modem, its sound card and keying, Tune and Test, the Spectrum) and the Dummy radios |
| `docs/manual/beacon.md` | the My station tab: the beacon status, Position (fixed or a GPS), the Beacon choice and Off, RX only, mobile operation with SmartBeaconing, PHG, the location and the symbol, the status, answers to queries, the fill-in digipeater |
| `docs/manual/messages.md` | sending and receiving messages, acks, retries, routes, paths, a station heard on a Mercury radio, encrypted messages, deleting |
| `docs/manual/igate.md` | the Internet group: stations of APRS-IS on the map, the radius and the server, and advanced use as an iGate |
| `docs/manual/email.md` | email through the APRS gateway |
| `docs/manual/bulletins.md` | the message board and posting to it |
| `docs/manual/hf-tests.md` | the HF tests tab: meeting another station on HF to try APRS, the board on the project page, planning, joining and deleting a test |
| `docs/manual/objects.md` | objects and items of your own, the QRU server |
| `docs/manual/weather.md` | weather stations and what else NeoAPRS reads |
| `docs/manual/notifications.md` | the alert command, the alert in the browser, notifications |
| `docs/manual/network.md` | opening the page from another device, the access key, https, installing the page as an app |
| `docs/manual/settings.md` | every setting with its default, made from the code, and the values that are fixed |
| `docs/manual/commands.md` | the `neoaprs` command line, `neoaprs doctor`, troubleshooting |
| `docs/manual/support.md` | getting help: the support file that holds the logs and the facts for the developer, how to make it (the page, the Start menu, the tray, the command), what is in it and what is left out |
| `docs/RADIOS.md` | which radios and TNCs work with NeoAPRS, and how to connect each (serial, USB, Bluetooth, Bluetooth LE, a sound card, your own Direwolf or soundmodem), the Mercury modem for a radio's sound card, a GPS receiver for a moving station, Linux and Windows |
| `docs/development.md` | for developers: set up, the stages of `scripts/check`, CI, the wire and its generation, the page's source, the scripts, packaging and releases, the folder map |
| `docs/daemon.md` | for developers: how the daemon behaves, with the names the code and the wire use |
| `docs/design-notes.md` | for developers: why parts of the code are built the way they are (measured numbers, protocol choices, hardware and system quirks), by module |
| `docs/direwolf.md` | for developers: every number NeoAPRS fixes for the Sound card type and its Direwolf, where each comes from, and how the program is built, started and checked |
| `docs/mercury.md` | for developers: every number NeoAPRS fixes for the Mercury modem, where each comes from and what was measured |
| `docs/pskreporter.md` | for developers: what a Mercury radio reports to PSK Reporter, the templates, the pace and where each rule comes from |
| `docs/palette.md` | the palette of the page: every colour token with its light and dark value and what it is for, held to `tokens.css` by a test |
| `docs/ARCHITECTURE.md` | the layers and their import rules, the composition root, the database actor, the size and duplication ratchets |
| `docs/MAINTAINING.md` | what to keep up to date after a change, the download names, the steps of a release |
| `docs/security-checks.md` | for developers: the security checks of the gate (`scripts/security-check`): what each is for, fetching their programs, reading a failure, how a finding is accepted and the reason it must carry |
| `CONVENTIONS.md` | how the code, the tests, the documents and the schema are written; the words; the one table of environment variables |
| `PROTOCOL.md` | the wire protocol between the daemon and the page: the commands, the messages, the topics and the objects; generated from the models of `neoaprs/web/` by `scripts/gen-protocol.py` |
| `ROADMAP.md` | what is planned |
| `CHANGELOG.md` | what each release changed |
| `docs/README.md` | this index |
| `tests/README.md` | the suite: markers, guards, support, how to run it |
| `systemd/README.md` | one line per unit |
