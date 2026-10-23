# Documents

Every Markdown file of the repository. `tests/test_hygiene.py` fails when a document is missing here or this index lists one that is gone.

| document | what it is |
|---|---|
| `README.md` | the front page: what NeoAPRS is, how to download, run and try it |
| `docs/manual/README.md` | the manual for the person who runs NeoAPRS: what it is, the contents, a few words |
| `docs/manual/install.md` | installing on Windows, Linux and the Raspberry Pi, starting at login, updating, the update check |
| `docs/manual/start.md` | the first start, the setup guide, the data folder, how settings apply, trying it without a radio, stopping |
| `docs/manual/page.md` | the page: the panel and its tabs, the map, the station cards, the header and footer, phone, tablet and desktop, the base map |
| `docs/manual/desktop.md` | the desktop app: the window, the tray, start at sign-in |
| `docs/manual/radio.md` | the radio's port, the TNC type, the keep-alive and the silent radio |
| `docs/manual/beacon.md` | the beacon, PHG, the status, answers to queries, the fill-in digipeater |
| `docs/manual/messages.md` | sending and receiving messages, acks, retries, routes, paths, deleting |
| `docs/manual/email.md` | email through the APRS gateway |
| `docs/manual/bulletins.md` | the message board and posting to it |
| `docs/manual/objects.md` | objects and items of your own |
| `docs/manual/weather.md` | weather stations and what else NeoAPRS reads |
| `docs/manual/notifications.md` | the alert command, the alert in the browser, pop-ups |
| `docs/manual/network.md` | opening the page from another device, the access key, https, installing the page as an app |
| `docs/manual/settings.md` | every setting with its default, made from the code, and the values that are fixed |
| `docs/manual/commands.md` | the `neoaprs` command line, `neoaprs doctor`, troubleshooting |
| `docs/RADIOS.md` | which radios and TNCs work with NeoAPRS, and how to connect each (serial, USB, Bluetooth, Direwolf and soundmodems), Linux and Windows |
| `docs/development.md` | for developers: set up, the stages of `scripts/check`, CI, the wire and its generation, the page's source, the scripts, packaging and releases, the folder map |
| `docs/daemon.md` | for developers: how the daemon behaves, with the names the code and the wire use |
| `docs/ARCHITECTURE.md` | the layers and their import rules, the composition root, the database actor, the size and duplication ratchets |
| `docs/MAINTAINING.md` | what to keep up to date after a change, the download names, the steps of a release |
| `CONVENTIONS.md` | how the code, the tests, the documents and the schema are written; the words; the one table of environment variables |
| `PROTOCOL.md` | the wire protocol between the daemon and the page: the commands, the messages, the topics and the objects; generated from the models of `neoaprs/web/` by `scripts/gen-protocol.py` |
| `ROADMAP.md` | what is planned |
| `CHANGELOG.md` | what each release changed |
| `docs/README.md` | this index |
| `tests/README.md` | the suite: markers, guards, support, how to run it |
| `systemd/README.md` | one line per unit |
