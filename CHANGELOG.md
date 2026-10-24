# Changelog

## Unreleased

Buttons of one size.

- Every text button, input and select of a form or a toolbar is now the same height (32 px) on every tab, in the setup guide, the update dialog and over the map: Reconnect, Download in the map note, Close all, Message these, Done and Cancel of the map bars, the news link and Update now were smaller or larger, and a select was taller than the inputs beside it. Only Retry, Cancel, Copy, Route and the weather hours stay compact (24 px), and on a touch screen every control is still at least 40 px. The button that is the action of a row (Test sound, Test pop-up, Check now, Find my radio, Download map, Choose on map) has one least width, like Beacon now. The rule is in `CONVENTIONS.md`, and `ui/src/styles/buttons.test.ts` holds it.

Pages that keep up.

- A page left open loads itself again when the daemon it reconnects to serves another build of the page, not only another version: the daemon names its page's build in `hello` (the new field `page`, the name of the page's main script). Once for each build, as for a version.

The radio hears more.

- The keep-alive asks the TNC whether the radio is there only after 10 quiet minutes (was one minute), and after a random minute or two more. The check takes the TNC out of KISS and back, which deafens it for a few seconds; after one quiet minute it fell again and again on the next beacon of a station that sends one a minute, so a thin hour on the channel became a nearly silent one. A radio switched off is noticed within about 12 minutes. One switched off and on again while it was in KISS is put back in KISS at once: its TNC starts in command mode and types what it hears, and text after KISS frames now means that (it used to wait for the next check).

Weather graphs that bridge the gaps.

- A weather card's graphs (temperature, pressure, wind and gusts) draw each line as one smooth curve through the readings, across the hours where the station sent none, where a gap used to leave short broken pieces and lone dashes. The curve is a monotone cubic (Fritsch-Carlson): it never rises above or falls below the readings it runs between, so a pressure curve does not invent a peak. It starts at the first reading and ends at the last, and a single reading is still a dot.
- The lighter band between the wind and its gusts follows the same two curves. The rain stays bars, with no bar for an hour with no reading.

How long a station stays on the map.

- The Stations tab has a choice **On map for** in its filter row: 1, 3, 6, 12 or 24 hours after a station's last position (3 by default). It replaces the fixed 3 hours: it is one setting of the daemon, `map/station_hours` (also for `neoaprs db set`), so every browser and device shows the same, and a change applies at once with an Undo. The map, the tracks and the dimmed "timed out" rows of the table follow it. Your own station and objects never leave the map, and the daemon still keeps stations for 7 days. The old `map/hide_after_min` is not used again; the page's limits `LIMITS.station.hideAfterMin` became `LIMITS.station.hours` and `defaultHours`.

Objects.

- The Objects form no longer has a choice between Object and Item: a new one is always an object, which is what the specification recommends on RF. An item you made before is still in the list, on the map and on the air, and can be changed and killed until you delete it.

The Stations list.

- The tickbox **with position only** is gone: the stations without a position show as they do with it off.

The station card.

- A new row, **Device**, says what the station runs ("Kenwood TH-D74", "APRSdroid", "OpenTracker"), from the destination call of its packets (with the list's wildcards) or, for a Mic-E tracker, from the type code at the ends of its comment. It is left out when the station is not in the list. The names come from the APRS device identification list of Hessu, OH7LZB (aprsorg/aprs-deviceid, CC BY-SA 2.0), a snapshot of which the program carries (`scripts/gen-devices.py` refreshes it; the daemon never fetches it) and credits in the (i) on the map and in the README. The station row of the page's protocol has the new field `device`.
- The antenna of a PHG report shows the direction it favours as a small arrow, the same as the bearing in the Stations table (a small circle for omni), with the compass point and the degrees as its hover title, in place of the degrees in the text.
- **Packets** in the details says how many of them came in the last hour: "312 · 14 in the last hour". The count is kept for each minute, read from the packet log at the start, and moves on every minute; the station row has the new field `packets_hour`.

The footer.

- The hover text of the version is a sentence in the page's language, "NeoAPRS uses 0.3 % of one processor core and 56 MB of memory, running for 3 h", not "0.3 % · 56 MB · up 3 h".

The log.

- The lines of the database migrations (for the upgrade that put the settings that are not on the page back to their defaults: one line for each, with the value it had) are on stderr too, so that `journalctl --user -u neoaprs` has them, not only `neoaprs.log`. `neoaprs db set` on a database of an older version says them on its stderr. Their logger is `neoaprs.migrations`.

The Email tab.

- **Esc** in the box to write a mail closes the list of addresses used before; with none open, it clears the address and the text being written.

The map.

- The ALOHA circle of Bob Bruninga, WB4APR, is drawn round your station: a thin dashed circle, under the markers, with its radius as the hover text ("ALOHA circle: 42 km"). It is the distance within which the stations heard on the radio would fill the channel; a packet for a station beyond it is hard to receive reliably. The daemon works it out by WB4APR's method ("The ALOHA Circle", aprs.org, 2011) once a minute from the stations heard in the last hour, nearest first, each by what it sends in half an hour (a moving mobile 15 packets, any other mobile 7, a weather station 6, a digipeater 3, any other station 2, and each digipeater nearer than a station makes the packets of the stations beyond it count once more), until the sum reaches 1800, the packets a 1200 baud channel carries in half an hour. Without a position, or with too few stations heard to fill the channel, there is no circle. The radius is the new field `aloha_km` of the topic `map`.

Nothing moves when a button answers.

- The answers of **Check now**, the alert command's **Test**, **New key** and **Test sound** / **Test pop-up** are said in the toast at the bottom, like the other notices, not beside or under the button (where they pushed the (i) aside). When Check now finds a newer version, the update window opens.

The Settings tab's TNC group.

- The group is one line, the radio status with a small **Reconnect** at its end, and an arrow in front that opens the rest: the type of TNC, the port, the speed (or the host and port of a TCP type) and the **Terminal**. It is closed unless the radio is not connected.
- **Find my radio** (Linux), a button behind the arrow, finds the radio by itself: it tries the ports of the search for the radio, and with the default search the paired Bluetooth devices, one after the other at 9600, 57600, 19200, 38400, 115200, 4800 and 1200 baud, and stops at the first TNC that sends KISS or answers a carriage return with command-mode text, which the TNC types' own steps then put in KISS. It writes nothing but that carriage return and those steps, never to the air. The port, the speed and the type go into the settings like any other change, with **Undo**. The toast shows the port it is trying, with **Cancel**; when nothing answered it says so.
- The settings `serial/pattern` and `serial/skip`, which are for `neoaprs db set` only, have no leftovers on the page any more.

- A station card has a **pin** beside its cross (on a tablet and a desktop). A pinned card stays on the map past **Esc**, **Close all**, a click on the map or on another station, and a reload of the page, in the place it stands, until its cross is clicked (the cross unpins and closes it). The pin is filled while it is on, says so to a screen reader, and has the hover title "Pin card" or "Unpin card" in all seven languages. A card opened later goes to a free place and never on a pinned one. The pinned calls and their places are remembered in the browser (localStorage), not by the daemon. The route of a pinned card is drawn only while its station is picked: Esc or a click on the map leaves the pinned cards open and marked, without their route lines.
- A card that was moved low and then grows (**Details** opened, a weather card's graphs loaded) moves up as far as it needs to be whole inside the map, and no further, and does not get a scroll bar for it; only a card taller than the map is put at its top and scrolls. Another card never moves for it.
- The card's field **Hide from map after** is gone, with its words in all seven languages: every station leaves the map 180 minutes after its last position (a station past it is still dim in the Stations table). A timeout stored for a station has no effect any more, and is cleared once at the first start of this version (migration 17): one line in the log for each station with the old value, a row that held nothing else is deleted, and the path and RF only of the station are not touched. The commands `set_station_timeout` and `clear_station_timeout` and the field `hide_after_min` of `station_prefs` are gone from the protocol, and the daily clean-up no longer keeps a station for a timeout of "never".

The Objects form.

- **Course** and **speed** are behind a closed **Moving** heading, since most objects (a meeting point, a repeater) do not move. It opens by itself for an object that already has either; an empty fold means neither is sent.

## 0.7.0

The page in seven languages, an update you can start from the page, a menu on the Stations list with APRS queries, messages that choose their own path, station cards you can move, and closer to the APRS standard.

The page in seven languages.

- The page in English, Deutsch, Español, Français, Italiano, 日本語 and Português (Brasil). It starts in the browser's language when it has it; **Language** at the top of the Settings tab changes it for this browser. The translations wait for native-speaking hams to read them: corrections are welcome.
- Numbers are written with the language's decimal point and the weekdays of the graphs by the language, from `Intl`. A refusal of the daemon is said in the page's language when the catalogue has the refusal's code, else with the daemon's English sentence.
- The zoom buttons and the label of the map are said in the page's language (the map engine has English only), and **never**, for a station's timeout, in German, French, Japanese and Brazilian Portuguese (typing the English word still works).

Updates that do themselves.

- **Update now** for the Windows installer and the AppImage: on a click, NeoAPRS downloads the file of exactly the announced version from the GitHub release and its `SHA256SUMS`, checks the file's SHA-256 (a file that does not match is deleted and nothing is installed), installs it and restarts. Windows runs the installer without a window, which starts again what was running; an AppImage is replaced under its own name, the old file kept as `.old` until the new version runs (one started with `--appimage-extract-and-run`, on a system without FUSE, starts again the same way). The progress, a Cancel while it downloads and a failure in plain words are in the window, with the steps by hand.
- The update is a window in the middle of the page (the whole screen on a phone): "NeoAPRS <version> is available", the version you have, what is new, then the steps for the way this copy was installed, in plain words, each file a button and each command with Copy. The .deb gets the package of the machine's architecture and one `apt` command; pip the release's wheel.
- A phone shows the newer version in the header too, because its map has no footer.

The Stations list.

- A row has a menu: a right-click on it, a long press on a touch screen or the **...** button at its end opens it where the pointer is. It has **Message**, four questions to the station, **Ask for position**, **Ask for status**, **Ask what it hears direct** and **Trace the route** (the directed queries `?APRSP`, `?APRSS`, `?APRSD` and `?APRST`), **Show on map**, **Copy call**, the **QRZ page** and **Forget** (asking twice). The questions are for the stations that take messages; your own station and objects have Show and Copy call (and Forget where the row has it). A phone's row has the envelope and the **...** only.
- A question is sent once, as a message with no message number, and is not repeated or waited for; the same question to the same station is refused for 60 seconds, and one to a station that is not known or takes no messages is refused. The conversation shows it as a grey line, "You asked for its status", and the page says "Asked OH2XYZ for its status" in a toast.
- Each row has, at its right end, an envelope that opens the conversation with the station and a trash can that forgets it (it asks twice), so that neither needs the card. The envelope is the one picture of "message" on the page: the header's count of messages not seen and the **Message OH2XYZ** button under an empty result have it too.
- Fixed rows drawn over each other in the table.

Station cards.

- A station card can be moved: drag it by its head (the symbol and the call) anywhere over the map, or move the focused card with Alt and the arrow keys. It stays in the map and keeps its place while it is open. Moving a card never moves another: every other open card stays exactly where it is on the screen and the moved card's place stays empty, and closing a card does not make the others close up. A newly opened card goes to the first free place in the row, never on top of a card; **Close all** and **Esc** start the row again from the left. The map keeps a marker clear of a card where it stands. Not on a phone, where the card is a bottom sheet.
- **Forget** on the card is the trash can of the other lists, "Forget OH2XYZ" on hover, with the same second press to make sure.

Messages find their way.

- A message chooses its path by itself, attempt by attempt. If you gave the station no path of its own and it has been heard recently by a good path, attempts 1 and 2 go by that path and attempts 3 and 4 by the beacon's. A good path is: heard **direct** at least twice in the last 60 minutes, else the latest named route that at least two of its packets came by in the last 60 minutes, turned round (not one with an unnamed hop, one from the internet, or more than 3 digipeaters). The choice is made when each attempt is sent, so a route learned meanwhile counts. A path of the station's own is used for every attempt; RF only still adds `RFONLY`; `EMAIL-2`, bulletins and groups go by the beacon's path. The delivery chain of a message shows the path of each attempt.
- The **Route** box of a conversation says what is used in one line: **Automatic: via OH2RDG,OH2RCH-2, then WIDE1-1,WIDE2-1**, **Automatic: direct, then WIDE1-1,WIDE2-1**, **Automatic: WIDE1-1,WIDE2-1**, or **Your path: ...** when you set one. An empty field is the automatic choice; the x gives it back; the word **DIRECT** is a path of no digipeaters. (An empty path of a station used to mean direct: stored paths are not changed, only typing an empty one now clears it.)
- A conversation opens scrolled to its newest message and stays there while it fills in; scrolling up to read older messages is left alone.

Settings.

- The Location is a row like the Call above it: the word **Location** in the label column and, in the input column, the **Choose on map** button (the whole width on a phone), the place as one line under it and **Enter coordinates** under that. The button is **Choose on map** (was "Pick on the map") in the Beacon tab, the Objects form and the setup guide's Position step, in all seven languages.
- On a phone the access key in the Settings tab has a line of its own with its button under it, and the Kind choice of the Objects form keeps room for "Object (recommended)".
- Objects: the form's position has the same Location row; **Esc** closes the form without saving, as Cancel does, unless the focus is in a field that still has text. While the map waits for a click, Esc ends that first.
- The Beacon tab's Advanced path is one choice, **Recommended (WIDE2-1)** or **Recommended (WIDE1-1,WIDE2-1)**, **Direct only (no digipeaters)** or **Custom...** (a field for the calls, applied on Enter or when it is left). An empty path is never "no digipeaters": a database whose `beacon/path` was cleared (it meant none) is changed once to Direct only, so that nothing starts to digipeat after the update. In the database an empty `beacon/path` is the recommended path and `DIRECT` is none; the path of an object or item may be `DIRECT` too.
- Settings that are no longer on the page go back to their defaults once: at the first start of this version `map/maxzoom`, `map/source`, `update/url`, `serial/pattern` and `serial/skip` lose what was stored for them (they stay settings, for `neoaprs db set`, and a value set after that is kept), and the stored rows of the settings that no longer exist (`messages/attempts`, `log/keep_days`, `update/check`, `tnc/check_sec`, `tnc/watchdog_min`, `map/hide_after_min`, `beacon/destination`, `beacon/compressed`, `beacon/dao`) are deleted. Each reset is a line in the log with the old value. `web/port` and `web/allowed_hosts` and every setting on the page are not touched.

Closer to the APRS standard.

- The **recommended path** depends on the kind of station, and there is no setting for it: it comes from the station's **symbol**. A moving or carried one (car, truck, van, bus, jeep, motorcycle, bicycle, jogger, wheelchair, boat, ship, canoe, yacht, aircraft, helicopter, glider, balloon, snowmobile, horse, farm vehicle, recreational vehicle, ambulance, fire truck, police car, rover, with any overlay) is recommended **WIDE1-1,WIDE2-1**; any other symbol is a fixed station and is recommended **WIDE2-1**, as a fixed station that reaches a wide-area digipeater directly needs no fill-in hop. The Path choice says which and follows the symbol when you change it; its (i) tells why. Beacon, status, objects, bulletins, answers to queries, `EMAIL-2` and the fallback of the automatic message path all use it.
- **Updating keeps your path.** Earlier versions stored `WIDE1-1,WIDE2-1` as the value of `beacon/path` (it was the default), so it cannot be told from a choice: the update makes that stored value empty, which is the recommended path, so a fixed station moves to `WIDE2-1` and a moving one stays on `WIDE1-1,WIDE2-1`. Any other path you have (`WIDE2-2` or `WIDE2-1` typed in, `DIRECT`) is kept as it was and shows as Custom or Direct only. Choosing Recommended now stores the empty setting, not the calls.
- The **beacon interval** is Off, every 30 minutes, every 60 minutes or every 3 hours (was Off, 15, 30, 60). The APRS net cycle is 20 minutes for a path of two hops and routine operation is 30. The daemon takes 20 minutes at the least: a stored 15 (or any value from 1 to 19) is raised to 20 with a line in the log, and a stored value that is not one of the choices (20, 45, 90) still shows as one more choice. The setup guide still gives a new station 30 minutes. The status report keeps its own least of 15 minutes.
- **Objects are the default** in the Objects form: a new one is an object unless you pick item, and the Kind choice says "Object (recommended)" with the hover text "Objects are recommended on RF; items are not."
- The fill-in digipeater repeats a third-party packet (an iGate putting a message from the internet on the air with `WIDE1-1`): only the path before the `}` counts, as APRS 1.2 says. A packet whose own path has `TCPIP` or `TCPXX` is still not repeated.
- A message from a station on the internet whose name is no radio call (a D-STAR `-L`, an SSID above 15, a name such as `WINLINK`) is shown and acked, and can be answered. Before, it was not recognised as a message, so the sender tried until it gave up.
- A repeated copy of a message to you is acked again only 30 seconds or more after the last ack (was 10): the digipeaters drop a second ack within 30 seconds anyway.
- A message is sent again 32, 64 and 128 seconds after the first attempt (was 30, 60 and 120), so that no retry comes exactly at the end of the digipeaters' 30-second duplicate window.
- The ack of a message numbered `{05}` is `ack05}`, the exact copy of the number, as the reply-ack paper says (was `ack05`).
- The fill-in digipeater sends the frame it heard byte for byte with only the path changed (it rewrote some address bits of the destination and the source), and a packet whose destination differs only in its SSID is a duplicate.
- An ack or a message number followed by blanks or a line end (`ack12  `) is understood, and so is a message whose addressee is not padded to nine characters.
- A Mic-E station whose comment starts with the type code `'` (a tracker without messaging) gets no Message button, unless it has sent a message.
- The type codes of more Mic-E radios no longer show in the comment: the TH-D75's `&` and the two-character codes of current Yaesu, Anytone and other radios and trackers.
- A snow reading with a decimal point (`s1.5`) is read, and so is the radio range of a compressed position.
- Telemetry in the forms of APRS 1.2 is read: `T#MIC` without a comma, signed values with a decimal point, fewer than five values or eight bits, and the compact base-91 telemetry `|ss11|` at the end of a position's comment (which no longer shows in the comment).
- The `!DAO!` precision extension (TH-D74 and TH-D75, APRSdroid) is read: the position is finer and the `!W12!` no longer shows in the comment.
- The answer to `?APRST` and `?PING?` is the header as the specification's example writes it, `OH2RDG>APZNEO,WIDE1*,OH2RCH-2*:`, without `Path=` in front.
- The queries `?APRSO` (your objects and items) and `?APRSM` (your messages to the asker that are not acked) are answered, at most 5 frames, 10 seconds apart.
- The manual and the (i) of the Beacon tab say what PHG means: the antenna height above the average terrain around it, the gain in dBi.

For developers.

- The words of the page are in a catalogue (`ui/src/i18n/`) that a language is a file of; English is the source, and tests hold every language to the same ids and placeholders. `ui/src/protocol/errors.json` lists the codes of the daemon's refusals and their sentences, generated from its source.
- The wire has the station row's new field `heard_path` (the heard path, null for none), the command `query`, the topic `update` and the commands `update_now` and `update_cancel`. `NEOAPRS_INSTALL_KIND` simulates an install kind for development.
- `scripts/update-e2e.py` runs Update now end to end, on Windows and on Linux, in every release run.

## 0.6.5

No new features: the wire between the daemon and the page is structured, the rules are written once, the code, the tests and the stylesheet are tidier, and the documents are readable.

The wire contract.

- An error carries the command it answers, the setting it is about, a stable code and the values its sentence is made of (`cmd`, `key`, `code`, `params`). The page goes by those and no longer reads the daemon's English; the English text stays for the log.
- The radio's state tells the ports it is searching and its latest lines as data (`searching`, `lines` as `{at, text}`). The page parses no sentence of it.
- Weather packets are found by what the parser decoded, not by a pattern in the English summary.
- The rows of every topic are built from the domain objects through their wire models, so a new field is added in one place. A golden-file test holds the JSON of every row kind.

One source of rules.

- The page takes every limit it checks against from the daemon (`LIMITS` in the generated `lists.ts`) and the rules that are code from conformance vectors (`vectors.json`) that the daemon's tests and the page's tests both assert. The settings form and the setup guide share one field check.
- The numbers the program decides (how long things are kept, the station timeout, the keep-alive time) are in `neoaprs/policy.py`, apart from the settings.

Python tidy.

- One `Radio` protocol, one way to build our frame (`our_frame`), one handler for a failed task (`TaskSet` takes a logger), all in `services/common.py` and `tasks.py`. The seeding of the station book moved from the controller to `wiring`.
- The page's server is split: the tab's socket in `web/pagesocket.py`, the choice of the port in `web/listen.py`.
- The write-ahead log is bounded by SQLite's automatic checkpoint and `journal_size_limit`; the minute's checkpoint that was never scheduled is gone.
- Dead code out: `compress_position`, `PrefBook.timeout_for`, `Store.setting_rev`, `MessageLog.highest_msg_id`, `Source.reconnect`, five `clock` helpers and others; stale docstrings corrected.

Tests and flakes.

- One stub TNC and shared rigs for the service tests (`tests/support/stubtnc.py`, `rig.py`). A wait is a condition (`until`), a window in which nothing may happen is named (`idle_for`), and fixed sleeps are gone from the serial, TNC, wiring and safety tests.
- Two flakes explained and fixed (the stop test of the daemon, the reopen test of the serial line). Coverage rose from 96 to 97 % (the alert runner, the db and capture commands, replay on a pseudo-terminal, durable writes, the Qt shell).

CSS.

- `style.css` and `responsive.css` are split by area into `ui/src/styles/` (the built CSS was byte for byte the same at the split). Dead rules are out, rules with the same selector or declarations are merged, and `scripts/css-unused.py` in the stage `ui-lint` fails for a rule of a class that no source file writes.

Page shell.

- `App.vue` went from 312 to 134 lines: it provides one typed daemon context that the panes inject, and the shell's logic lives in `useAppShell` and `useHeardIndex`. Its test is split by tab.
- One compose bar for messages, mail, bulletins and objects; one popup behaviour for the (i), the Route box and the tab menu; one disclosure box; shared symbol button and tab badge. Dead exports out.

Documents.

- The manual was split: `docs/manual/` is for the person who runs NeoAPRS (short paragraphs, plain words, one file for each subject, the secure connection and the other things it lacked included), `docs/development.md` for building and releasing, and `docs/daemon.md` for how the daemon behaves.
- The table of settings is made from the program (`scripts/doc-settings`) and a test fails when it is stale. Other tests hold the manual to short paragraphs, no code names and no version numbers. `CONVENTIONS.md` has the glossary, and the size limits and the layers are each stated once.

Dev loop.

- `scripts/gen-protocol.py` also writes `LIMITS` and the vectors; `scripts/css-unused.py` runs in `ui-lint`; `scripts/doc-settings` keeps the table of settings current.

Small fixes.

- The page's check of a call refuses what the daemon refuses: `NOCALL`, `MYCALL` and calls of an odd shape, not only `N0CALL`.
- The beacon preview rounds a position that is exactly on a half hundredth of a minute the way the daemon does.
- The Messages box scrolls into view on a phone when the keyboard comes up.

## 0.6.0

The page works on a phone and a tablet, settings apply as you change them, messages read like a chat app, email is a plain list, and several station cards open side by side.

The page on a phone, a tablet and a desktop.

- A phone (under 700 px, or held sideways) shows one view at a time: a compact header, the tab bar with a **Map** button first, and the open tab or the map on the whole screen under it, so forms and threads have the full height. A station's card is a bottom sheet you open with a tap or a swipe up and close with its cross or a swipe down; a tap on a row of the Stations tab shows the map with the card; **Pick on the map** shows the map and brings the tab back with the place; the setup guide is the whole screen.
- A tablet (700 to 1100 px) has the map and a 380 to 420 px panel side by side, in both orientations. A desktop is as before, except that a panel you have not dragged is 760 px wide from a 1280 px window (480 px below).
- The page is the height of the window, never scrolls sideways, keeps clear of the notch and the home bar, and on a touch screen every control is at least 40 px high. "The page on a phone, a tablet and a desktop" in the manual.
- The tabs by importance: Messages, Stations, Email, Bulletins, Objects, Beacon, Packets, Settings; a new page opens on Messages. When the tabs do not fit the width of the panel (measured, not a breakpoint) the bar is one button, **☰ Messages**, with the total of the badges, that opens a menu of them all.
- A quieter header and a footer: the header holds the title **NeoAPRS**, a link to the project page, and the badge of messages not seen. The footer under the open tab says "NeoAPRS 0.6.0", **Update to 0.6.1** when there is one, and the radio only when it is not ok ("Radio: not connected", "Radio: silent", ...), as a button to the radio settings.

Settings that apply as you change them.

- The Save and Revert bar is gone from the Settings and the Beacon tab. A tickbox, a list, the port list, the symbol and **Pick on the map** apply at once; a field you type in applies on Enter or when you leave it, never while you type, and only when the page finds it valid (the reason is under the field and the old value stays in force; Esc puts it back). Nothing beside the field changes or moves; a screen reader is told "Saved".
- A toast, "Beacon interval changed · **Undo**", stays for ten seconds and puts the old values back in one step. The changes go to the daemon one at a time; the latitude and longitude, and the TCP host and port, are sent together (one TNC restart).
- Turning off **Allow access from the network** on a page opened from another device asks "This device will lose the page. Turn off?" first; nothing else asks. **Beacon now** and **Send status now** wait only while a change is being saved.
- Settings, radio status: one line, "Last packet 2 min ago", with the port named once.

Messages like a chat app, email kept simple.

- Messages: from 600 px wide the conversations are at the left and the open one at the right; on a narrower tab one fills the tab, with a back arrow to the list. The conversation has a header with the call and a small **Route** button, bubbles (ours at the right), and the box to write in fixed at the bottom. A message counts as seen only while its conversation is open and visible.
- The conversation is the station: the box is the text, "67 left" and Send, with no To field and no New message button; a chat starts from a station's **Message** button, or from a call typed in the filter of the Stations tab (**Message OH2XYZ**). An overheard pair has only the bubbles. Esc deselects the conversation.
- One text to several stations: the page opens a group compose for a list of calls ("Message these 3" on the map), with the recipients as chips and **Send to 3**, which sends one ordinary message to each.
- A station that cannot do messages has no **Message** button on its card (the data type of its latest position says; a station that has sent us a message or an ack always can).
- Email: a mail list, not a chat with EMAIL-2. The oldest mail is first and the newest at the bottom, next to the box to write in (**To**, with the addresses used before as suggestions, **Text**, "N left", **Send**). A mail you sent is "To jane@example.com" with its state in words (Sending, Delivered, Not confirmed, Rejected), what the gateway sent is "From EMAIL-2"; Retry, Cancel and a trash can are on the row, and a click opens it to show the text, the route and the chain. **Check email** at the top asks the gateway for the mail it kept for you. The page no longer has the gateway's shortcuts: it sends to addresses.
- One layout for writing on every tab: the list fills the tab and the box to write in is fixed at its bottom, with the counter and the buttons at its lower right, Cancel left of the primary button (Send, Post, Save). Bulletins: the board is above the box to post; Objects: the form (New or Edit) is at the bottom, with **Pick on the map** at its left.

Station cards side by side.

- Ctrl+click (Cmd+click on a Mac) on a marker or a row of the Stations table adds that station's card, or closes it when it is open; a plain click opens one card as before. The cards stand side by side over the map, **every one the whole card**, with its graphs when it is a weather station; when there is no room the oldest closes (four at the most on a desktop, two on a tablet, one on a phone).
- While two or more weather stations are open every graph is on the same value axis and time span, so the curves can be read against each other.
- **Close all** and **Message these 3** (from two stations that can be messaged) are at the top left of the map; every open card's marker and track are marked, and **Esc** closes all the cards at once. A timed out station stays in the table, last, and a click on it shows it on the map again for as long as its card is open.
- The Stations table is one block, at most 640 px wide and centred in a wide panel; the filter and the tickboxes wrap onto a second line when they do not fit.

A plainer Beacon tab and setup guide.

- The Beacon tab is **Station** (call, Location, symbol), **Beacon**, **Antenna** and **Advanced** (closed) and **Status**. The Beacon group starts with "Last beacon: 2 min ago" and **Beacon now**, then one choice, Off, Every 15 min, Every 30 min or Every 60 min, and the Comment; the Status group starts with the status line and **Send status now**, and its interval is a choice too (Every 30 min, 60 min or 2 hours). Both buttons still ask twice ("Really send?"). A beacon or a status is at least 15 minutes apart (a shorter stored interval is raised to 15, logged), and the daemon's beacon stays Off until you switch it on.
- The Location has a large **Pick on the map** button with the place in force as one line ("60.42945 N, 24.14524 E · KP20le", "Not set"), and the latitude, longitude and locator behind **Enter coordinates**. The setup guide's Position step looks the same, and a new station gets a beacon every 30 minutes in the same save as its call.

Fewer knobs.

- **Keep-alive** is gone from the Settings tab: `tnc/check_sec` is fixed at 60 seconds, still only for the TNC profiles that can be asked (Kenwood, Kantronics).
- The Map group has the **Radius** and one button, **Download map** ("Download 493 MB?" with the real size, then "Download map again" and "Map downloaded 23 Oct"). **Estimate**, **Detail**, **Map data** and **Hide stations after** are off the page: a station leaves the map after 3 hours.
- The (i) of network access and of the alerts speak of any other computer and device, not only a Raspberry Pi in the shack.

For developers.

- `scripts/build-page` builds into a temporary folder and swaps it in with a rename (a test never sees half a page) and runs `npm ci` only when `ui/node_modules` is not what the lockfile says (never through a symlink; `--clean` forces it); the new `scripts/worktree-setup` makes a fresh worktree ready for `scripts/check`; CI runs the two duplication stages; `lists.ts` has one item to a line; `npm run protocol` uses `uv run`; the dead `e2e` marker is gone, and `scripts/check --fast` is still accepted and does nothing.

## 0.5.0

Plainer screens and fewer settings, a fill-in digipeater, a secure connection and an app to install, Bluetooth ports and a Debian package.

A plainer Beacon tab.

- Status: one group, **Status**, with one choice: *off*, *a text of my own* or *the frequency from my radio (rigctld)*, and then only the fields that choice needs (**Text** and **Every** for a text; **Rigctld**, **Text** with `{freq}` and `{mode}`, and **Every** for the radio). A new setting `status/source` keeps the choice; while it is empty it is what the other settings say (the radio while `status/rigctld` is set, else the text while there is one, else off), so an installation keeps doing what it did. Choosing the radio without an address is refused with the reason.
- **Send status now** beside the status at the top of the Beacon tab (the new command `status_now`): sends the status at once, inside the interval and although nothing changed, by the same checks as the timer's (no call set, the TNC, 55 characters with the time) and says why when it cannot; the interval counts from it.
- **Beacon now** and **Send status now** are primary buttons beside the information they act on, one row each at the top of the tab, of one size; both ask once more ("Really send?") and are off while the TNC is not connected or the settings below hold changes that are not saved.
- The symbol is a picture and its name with **Change**, which opens a picker with every symbol of the primary and of the alternate table, the usual ones first, searchable by name (`house`, `car`, `digi`, `wx`). The table and code fields are gone from the Beacon tab, the setup guide (its 12 usual symbols stay on top, **More...** opens the picker) and the Objects form. A symbol made to carry a letter or a digit has a small "Letter or digit on it".
- A small **(i)** beside the fields whose meaning is not plain (the same (i) as the Settings tab's, one component and one mechanism, `tip` in the field list) (comment, the status and its text, the radio, how often, the beacon's interval, the path, the antenna's power, height, gain and direction) opens a short note with an example; Esc, a click outside or moving on closes it.
- The preview of the packet and the status at the bottom of the Beacon tab is a closed disclosure, "Preview" (it says in its title when the values make no packet). The Objects form's map button is **Pick on the map** (was Place), on a row of its own under the latitude and the longitude, which are the same width. In the dark colour scheme a symbol picture has a light chip behind it, so that the dark outlines (bike, car, motorcycle) show.
- Less to fill in: the destination call (`APZNEO`, now a constant of the program that every frame we send carries; a stored `beacon/destination` is ignored), the compressed form and the DAO (the beacon is always the plain uncompressed position; stored `beacon/compressed` and `beacon/dao` are ignored) are no settings any more. The antenna's height, gain and direction show once a power is set; the Status group shows only what its choice needs.
- Beacon tab: **Pick on the map**, a button on a row of its own under the latitude and the longitude: the next click on the map is our station's place, to be saved like any change. Starting the pick ends a "Really send?" that waits, and arming a send ends the pick.

Plainer screens: fewer words and numbers, the rest a click away.

- The station card says what a person asks for: the symbol's picture and name, when it was last heard ("6 min ago", the full time when the mouse rests on it), the position, the distance and bearing, the speed and course (only of a station that moves), the status and the comment, and one line of how its packets reach us ("Reached us via OH2RCH-2", or "direct"). The path as it was sent, the counts of the routes, the best route, when it was first heard and the packets are under **Details**, closed. The timeout field, under Details, reads **Hide from map after** with the usual time as its placeholder ("3 h (usual)"); the close button is 32 by 32 pixels.
- The card is above the markers (the selected marker was drawn over its text on a phone), keeps clear of the map's zoom buttons, and the map moves so that the station you picked is not under the card: a station chosen in the table, or by its marker, lands above the card.
- The Packets tab: a click on a packet tells it in a few facts (who sent it, what kind it is, the position or the text, how it reached us or the path we sent it by, when) with the JSON of the parser under **Raw**; a route breaks between its words and never inside a callsign.
- The Stations table has the symbol, the call, the distance, the bearing as a small arrow (north up; "NE, 47°" is its hover text, the Brg column and its degrees are gone) and **Last heard**, and fits the panel; every row is one line high. A station heard direct has a small green check mark after its call ("Heard direct" as hover text and for a screen reader), on the card too, where the Direct lines are gone. **Last heard** is one time, the newest of anything the station sent, with the full time as hover text; the second age of its position is gone from the table and the card. The other columns (wx, packets, path) are on the card.
- The header shows the state of the radio and nothing of the machine: the CPU share and the memory are in the radio state's hover text. The number of messages not seen is one count in the header, on the handle of the folded panel and in the browser tab's title (the messages and the gateway's mail; new bulletins are not in it), and the header's mail opens the Email tab when all of them are the gateway's. On a phone the header keeps a short **Update** button when a newer version is out.
- The radio state in the header is a button: it opens the Settings tab, where the radio status is.
- The update panel's links use the page's link colour, and it no longer says "this copy: source".
- The tab bar is one row that scrolls sideways when the tabs do not fit, on a phone too (the mouse wheel turns it); the tab on show is no longer bold and wider, so no tab moves when you switch.
- One small delete button everywhere: a trash can, at least 32 by 32 pixels, titled **Delete** ("Delete (kill on the air)" for an object, "Delete (stop sending)" for a bulletin of ours), on the conversations, the bulletins, the objects and the addresses of the Email tab; one cross to close the update panel, the setup guide and the error message. The Objects **Edit** is as big as the other buttons.
- The (i) help opens downward and stays inside the page: on a phone it no longer runs off the right edge, and a click anywhere else closes it.
- The route on the map: a station whose latest packet came back from the internet through an iGate is drawn by its route over the radio, not from the iGate.

Settings that explain themselves.

- The TNC tab is gone: the TNC group of the Settings tab opens with the state of the radio link, one plain line ("Connected to /dev/ttyUSB0, last packet 2 min ago", "Searching for the radio…" with the ports behind **Ports**, "Not connected: the reason") and **Reconnect**, and a closed **Terminal** with the lines of what the TNC saw and did, in your own time and not in UTC. The counters (opened, bytes, frames, keep-alive checks) are no longer on the page; the packet and byte counts are the line's hover title, and the line says "digipeated N" while the digipeater is on and has repeated something.
- Fewer settings, more help on the Settings tab. Packets, weather observations and stations are kept 7 days (enough for the 7-day weather graphs) and the Log group is gone; the daily update check is always on and its switch is gone (**Check now** stays; `NEOAPRS_UPDATE_CHECK=0` still switches the check off for one run); the page's **Port** and **Allowed hosts** are left to `neoaprs db set web/port` and `web/allowed_hosts` (the daemon moves to a free port by itself and says which in the log). What an earlier version stored for `log/keep_days` and `update/check` is not read.
- A small (i) beside the fields that need a word of help, with plain text: the radio type (which to pick for which radio), Port (automatic or chosen; a Bluetooth radio appears after pairing), Speed, Keep-alive, **Allow access from the network** (what it is for, the access key, plain http at home), the access key and the addresses to open, Hide stations after, the map's Radius, Detail and Map data, the alerts (the NeoAPRS computer and this browser), and the update check.
- Settings tab: yes/no settings are tickboxes; the TNC choice is **Radio type**, the TCP KISS fields are **TCP host** and **TCP port**, **Off map after** is **Hide stations after**, the map's **Source** is **Map data**; the first-run guide is opened by a link at the top of the tab, not by a button beside Save; the map files are told as "Detailed map here" and "World map here", the estimate as "Download size", and a download over 200 MB asks "Download 513 MB?" first.
- Pop-ups for a page opened from another computer over plain http (the Raspberry Pi's address): the Settings tab (Notifications, In this browser) no longer says "needs https or localhost". **Enable pop-ups…** opens the steps in the page for the browser in use (Firefox, Chrome, Edge, Brave, Opera; a phone is told plainly), with the host name or the address to copy and a Reload button; Firefox as a Flatpak on KDE has its two `flatpak override` commands in a fold.

Messages, email and bulletins, simpler.

- The number of attempts is no longer chosen. A message to a station is sent at most 4 times, a message to the email gateway `EMAIL-2` at most 2 times (its acks rarely reach you: "sent, not confirmed" after that). The Attempts field is gone from the conversation's header in the Messages tab and from the Email tab, `messages/attempts` is gone from the Settings tab (and with it the Messaging group), and the commands `set_station_attempts` and `clear_station_attempts` are removed from the protocol. A count or a setting that an earlier version stored is ignored; messages already sent keep the number of attempts they were given, and Retry keeps it.
- Messages tab: under a message of ours only the delivery chain of its latest attempt is shown; the "3 attempts" line under it, which repeated the "attempt 3 of 4" above, is gone.
- Messages tab: **Stations** beside To writes one text to several stations. It lists the stations heard in the last day (stations only, those heard direct first) with a filter and a tickbox for each; the ones ticked are chips that a click removes, a call typed in To followed by a space or a comma becomes a chip too. Send makes an ordinary message for each recipient, with its own id, acknowledgement, attempts and conversation; with one recipient nothing changed. The daemon sends the attempts of all messages at least 10 seconds apart, so several messages never go out in a burst.
- The Email tab: "Fetch held mail" and the other buttons are all the same plain button, as Send is, with no small variant.
- Email tab: the shortcut fields are behind a closed **Shortcuts** heading, the placeholders are short, and a mail you sent is shown as "to jane@example.com" over its text, with the gateway's commands in words ("Shortcut me: jane@example.com", "Fetch held mail").
- Messages tab: the path and RF only of a conversation are behind a small **Route** heading, open only when the route was changed from the default; "Show overheard" has an (i); the To box says "Call"; the counter says "67 left" (also in Bulletins and Email, "3 over" when too long). On a phone the open conversation is the only row of the list left, so that the thread has the room.
- Bulletins tab: the kind and the number (a letter for an announcement) have labels.
- Bulletins tab: the kind "Group" is **Bulletin to a group** and its field is **Group name**; a small (i) beside the kind says what a bulletin, a bulletin to a group and a message are, and that particular stations are reached with a message.

A digipeater.

- A fill-in digipeater, off unless switched on (Settings tab, group **Digipeater**, `digi/enabled`; nothing else to set). A packet heard on the radio whose first unused hop is `WIDE1-1` is sent again with our call marked as used in its place (`WIDE1-1,WIDE2-1` becomes `OH2GBA*,WIDE2-1`), and one routed through our own call has that hop marked as used. Never repeated: other hops (`WIDE2-1`...), our own packets, a duplicate within 30 seconds, packets from the internet (`TCPIP`, `TCPXX`, third-party). It sends at once, at most 4 frames in 10 seconds, and only when a call is set and the radio is usable. Each one is a line in the log and is counted in the radio status line ("digipeated N").

A secure connection and an app to install.

- A secure connection (https), off unless switched on: Settings tab, Web page, **Secure connection (https)** (with **Allow access from the network**; `web/https`). NeoAPRS makes its own certificate authority and a certificate of the computer once (in `tls/` of the data folder, renewed by itself) and serves the page, with its socket, over TLS on the port after the plain one. A device other than the computer itself that asks the plain port is sent to the secure one; `localhost` keeps plain http. The authority's certificate is downloaded from `/neoaprs-ca.crt`; a guide under the switch installs it on each device, and the pop-up guide starts with the secure page.
- The page can be installed as an app (Chrome, Edge, Brave, Opera on a computer and on Android) from `localhost` or an `https://` address: it opens in a window of its own with the NeoAPRS icon, and the Settings tab, In this browser, has **Install app** where the browser offers it. A small service worker keeps the page's files and, when the daemon cannot be reached, shows the last shell, which then says "daemon offline"; the shell itself is always asked of the daemon first, so an update is never hidden. The socket, the login and the base map are never touched. Over plain `http://` from another computer browsers allow neither; a phone can still add the page to its home screen as a shortcut. "Install as an app" in the manual.

Bluetooth and a Debian package.

- A Bluetooth radio or TNC that is paired with the computer is a port of its own on Linux: `bt://AA:BB:CC:DD:EE:FF` (or `bt://AA:BB:CC:DD:EE:FF/2` with the RFCOMM channel). NeoAPRS opens the Bluetooth serial link itself, with no `sudo rfcomm bind` and no root, finds the serial channel on the radio (the TH-D74/D75 use 2, Mobilinkd 1; a radio that lists none, or refuses the one it lists, gets channels 1 to 3 in turn, and the log says which connected), and opens the link again when the radio goes out of range or is switched off, like any other port that drops. It has no speed, and the search for the radio never looks at Bluetooth devices.
- The Port choice of the Settings tab and of the setup guide lists the paired Bluetooth devices that have a serial port, by name (`Bluetooth: TH-D74`), after the serial ports. They are read from BlueZ's records (`busctl`, else `bluetoothctl`); no device is connected to for the list.
- The Bluetooth section of the radios document says how to pair once and pick the radio; the old `rfcomm bind` way stays as a fallback. Windows still uses the paired device's *Outgoing* COM port and macOS its `/dev/cu.*` port. The radios guide has entries for the BTech UV-PRO / Vero VR-N76 / Radioddity GA-5WB and the PicoAPRS V4 (both untested: users' reports and the manual). Bluetooth LE (the Mobilinkd TNC4's, the PicoAPRS's own LE mode) is not supported, as before.
- `neoaprs_VERSION_arm64.deb` and `neoaprs_VERSION_amd64.deb` on every release: NeoAPRS with its own Python 3.13 in `/opt/neoaprs` and the command `neoaprs`, for Raspberry Pi OS, Debian 12 and Ubuntu, which have no Python 3.13 of their own; `sudo apt install ./neoaprs_VERSION_arm64.deb`, then, as your own user, `neoaprs service install --linger`. It needs nothing from the system but libc, installs nothing in anyone's home and leaves your data alone; an upgrade replaces the files and restarts a running service. The update panel knows the kind (`deb` in `hello.install`) and gives its download and `apt` steps. Built by `scripts/build-deb`, byte for byte the same each time, and installed and tried with apt on a runner of each architecture by the release workflow.

## 0.4.0

Easier settings and email, a hover card and the route on the map, and updates that explain themselves.

- The list of ports has the other names of each port after it (the `/dev/serial/by-id` names and links of your own udev rules, such as `/dev/brainbox_3`), and is asked for once the daemon is connected, so a page that opens on the Settings tab no longer shows "Not connected to the daemon".
- The setup guide: the step's name is in its title and no longer twice on the page ("Your call", the symbol's "Code"); the position is picked on the map with **Pick on the map** on every screen, a crosshair while the map waits for the click, and a pin that can be dragged; the browser is no longer asked for its place (on a desktop it is mostly a guess).
- The TNC group of the Settings tab names the port once. **Port** is one choice: find automatically, a port the system lists (with Refresh), or Other... for a path or a `socket://` address typed; beside an automatic port the page says `found: PORT` for the port the daemon found last, which is no longer a field of its own. Which ports the search looks at and leaves alone is no longer on the page (the defaults suit nearly everyone; `neoaprs db set` changes them). No setting changed its name, meaning or stored value.
- Updating: the new version in the header opens a panel, "Update to 0.4.0", with a link to what is new and the steps for the way this copy was installed (Windows installer, AppImage, the install line, pip, a clone), the commands each with a copy button and the downloads linked by version. The daemon works out how it was installed and says so in `hello` (`install`: the kind, the AppImage file, whether a service starts it). The manual has an Updating section.
- A page that is open when NeoAPRS is updated loads the new version by itself: the page knows the version it was built for and loads again, once for each version of the daemon, when the daemon says another one (before, only a new protocol did, and only once for the tab). A daemon that serves an older page than itself does not make it loop. The same in the desktop app's window.
- Settings, Update check: a **Check now** button asks the version page at once and says beside it `up to date (0.3.0)`, `0.4.0 available` or why there was no answer; it works with the daily check off. The address of the version page (`update/url`) is no longer in the form; `neoaprs db set update/url` still sets it.
An Email tab that explains itself.

- The Email tab has plain actions instead of the gateway's commands: "Send an email" (the address or a shortcut, the text, and the characters left of the 67 with the address counting), a Mailbox part ("Fetch held mail") and a Shortcuts part ("Name", "Address", "Register", "Email the list", "Remove"). The command each one sends is its hover title. "Email the list" and "Remove" work only for a shortcut that was registered with the gateway before, and stay off until a shortcut is named; "Register" makes one.
- A mail whose ack never came back is "sent twice, not confirmed" with a hollow check, not failed: the gateway's acks reach a station only when an iGate puts them on the air, so a mail that went through often looks failed. What the gateway itself sends is marked "EMAIL-2 answers" in the thread.
- The gateway's commands and a new shortcut give `EMAIL-2` its count of 2 attempts the first time, as mail does, so a first "Email the list" is not sent six times.
- The manual's Email section says what the gateway is, that an iGate must be in reach, what a shortcut is and how it is made (by a message, not on a web page), and what each action sends.
- The map download no longer hangs. A download of which neither the percent nor the size of the half-made file has moved for 2 minutes is ended and begun again from the start, three tries in all, and the Settings tab says so ("no progress: trying again (2 of 3)"); after the last try the job ends with "the map server is too slow now; try again later" and the map that was there stays. The progress line shows the size downloaded so far next to the percent ("Map of the area 49% · 340 MB"), so that a slow download is seen to move, and so does `neoaprs map`. The pmtiles program is run with eight download threads instead of four.
- A lighter station card: it keeps what is known of the station, its "Off map after" timeout and the Message and Forget buttons. The path (with its suggested chip), RF only and Attempts are set in the header of the station's conversation in the Messages tab, which the Message button opens. A row with nothing to say is left out: no Course, Speed or Altitude for a house, no Status or Comment when there is none, and no row whose value would be a dash.
- Map: a mouse resting on a station's marker shows a small card after a quarter of a second with the main facts (call and symbol, when it was last heard, status, comment, distance and bearing from us, the temperature of a weather station, "heard direct" or the route it came by). A tap on a touch screen opens the station as before.
- Map: the station you pick has the route its packets come by drawn to our own station, through each digipeater that has a position (with a dot and its call), and, when the route most of its packets came by is another one, that route dashed and fainter. Nothing is drawn for a station heard direct.

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
