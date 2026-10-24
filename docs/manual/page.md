# The page

NeoAPRS serves a page at `http://127.0.0.1:7303/` (the port is `web/port`). The [desktop app](desktop.md) shows the same page in a window. The colours follow the system's light or dark scheme.

The page has a **map** of the area round your station and, at its right, a **panel** with eight tabs: Messages, Stations, Email, Bulletins, Objects, Beacon, Packets and Settings. A new page opens on Messages.

## The panel and its tabs

- The tabs are in one row when they fit the width the panel has. This is measured, not a breakpoint, because the panel beside the map can be narrow on a wide screen. The tab on show is not bold or wider, so none moves when you switch.
- When they do not fit, the bar is one button, **☰ Messages** (the name of the open tab, with the number of everything that has a badge: messages and mail not seen, and new bulletins). It opens a menu of all the tabs in their order, each with its badge and the open one marked. A pick closes the menu, and so do Esc and a click outside. The arrow keys, Home and End move in it. The bar is as high in both forms, and on a phone the **Map** button stays beside it.
- The panel can be folded away and dragged to another width (from 280 px up to 80 % of the window, the map keeping at least 360 px, so on a narrow window the most is less). A remembered width that is too much for the window is shown clamped.

| tab | what it is |
|---|---|
| **Messages** | the conversations with other stations ([messages.md](messages.md)) |
| **Stations** | the table of stations, below |
| **Email** | mail through the gateway ([email.md](email.md)) |
| **Bulletins** | the message board and the box to post to it ([bulletins.md](bulletins.md)) |
| **Objects** | your objects and items ([objects.md](objects.md)) |
| **Beacon** | what your station says on the air ([beacon.md](beacon.md)) |
| **Packets** | the log, newest first, below |
| **Settings** | the TNC and everything else ([settings.md](settings.md)) |

### Stations

The table has the symbol, the call, the distance from you, the bearing as a small arrow with north up ("NE, 47°" is its hover text) and **Last heard**, the newest time of anything the station sent, with the full time as hover text. Every row is one line high and the table is one block, at most 640 px wide, in the middle of a wider panel.

- The columns Call, km and Last heard sort on a click. Your own station is on top.
- A green check mark after a call means the station was heard direct ("Heard direct", also on its card).
- The filter box has two tickboxes that wrap onto a second line when they do not fit: "hide timed out" and "direct only" (stations heard direct at some time). Both are remembered.
- A click on a row flies the map to the station and shows its card, with the marker above the card and not under it.
- At the right end of a row are three small buttons: two as on the card and a "..." that opens the row's menu (below).
  - The envelope, **Message OH2XYZ**, opens the conversation with the station (on a phone, straight into the conversation); it is there for the stations a message can go to, not for your own station, an object, an item or the email gateway.
  - The trash can, **Forget OH2XYZ**, takes the station out of the station book and asks twice like the card's Forget ("sure?", taken back after 5 seconds); your own station and your own objects have none (an object is killed on its card).
  - A click on any of them does not select the row. On a phone the row has only the envelope and the "...": Forget is in the menu.
- **The menu of a row** opens with a right-click on the row, a long press on a touch screen or the "..." button at the row's end (from the keyboard: Tab to the button and Enter, or the menu key on the row). It opens where the pointer is, kept inside the window. Up, Down, Home and End move in it; Esc, a click outside it or Tab closes it, and Esc puts the focus back where it came from. It has:
  - **Message**, as the envelope.
  - Four questions to the station, **Ask for position**, **Ask for status**, **Ask what it hears direct** and **Trace the route** (the directed queries `?APRSP`, `?APRSS`, `?APRSD` and `?APRST` of the APRS specification). They are there only where the envelope is. A toast says "Asked OH2XYZ for its status" and the conversation with the station gets a grey line, "You asked for its status".
  - The answer comes as it would to anyone: a position or a status report changes the station's card, and what it hears direct or the route comes as a message in the conversation.
  - A question is sent once, with no message number, and is never repeated. Many stations do not answer queries, and the menu says so. The same question to the same station is refused for 60 seconds (the toast says "wait 42 s").
  - **Show on map** (**Open its card** for a station with no position), which does what a click on the row does; **Copy call**; and the **QRZ page**, as on the card.
  - **Forget**, which asks twice like the trash can: the first press says "Really forget?".
  - Your own station has Show, Copy call and the QRZ page, an object or an item of yours Show and Copy call, and an object of someone else's Show, Copy call and Forget; none has the questions.
- A station past its timeout is dim, listed last, with "timed out" after the time it was heard.

### Packets

The log of packets, newest first. A **Route** column says how each packet you heard reached you, and a route breaks between its words, never inside a callsign. A click on a packet tells it in a few facts: who sent it, what kind it is, the position or the text, how it reached you or the path you sent it by, and when. Under **Raw**, closed, is what the parser decoded, as JSON.

A beacon, message or answer you sent is in the log as a packet with direction `out`.

## The map

A marker for every station that has a position shows the APRS symbol with the call under it.

- Your own station is ringed. An object or an item of yours is ringed with a dashed line and can be dragged to another place.
- The track of a station that moved is a line that fades with age along its length: the newest stretch full, the oldest faint.
- A thin dashed circle round your own station is the ALOHA circle of Bob Bruninga, WB4APR: the distance within which the stations heard on the radio would fill the channel (1200 baud takes about 60 packets a minute), so a packet meant for a station beyond it is hard to receive reliably. The pointer resting on the line shows its radius.
- NeoAPRS works the circle out every minute from the stations heard in the last hour, nearest first, each by what it sends in half an hour: a moving car 15 packets, a parked one 7, a weather station 6, a digipeater 3, a home station 2, and each digipeater nearer than a station makes the packets of the stations beyond it count once more. The circle ends at the station where the sum reaches 1800. Stations an iGate put on the air from the internet do not count. There is no circle until your position is set and enough stations are heard to fill the channel.
- A marker dims in four steps on the way to the station's timeout.
- A station heard direct within the last hour has a green ring round its marker.
- A mouse resting on a marker for a quarter of a second shows a small card beside it with the call and the symbol's name, when the station was last heard, its status and comment, the distance and bearing from you, the temperature of a weather station, and how its packets reach you ("heard direct" or "via OH2RCH-2"). Only rows that have something to say are shown, and it is gone when the pointer leaves. A click still opens the full card. A touch screen has no resting pointer, so a tap opens the station as before.
- The station you pick, on the map or in a table, has the route its packets come by drawn in the page's blue. A line runs from the station through each digipeater of its latest route that has a position, to your own station, with a dot and the call on each of those digipeaters. A hop with no position is left out, so the line goes straight on. The drawing goes when the selection does.
- When the route most of its packets came by is another one, that is drawn too, dashed and fainter. Nothing is drawn for a station heard direct. When its latest packet was a copy an iGate gated back from the internet, the line is its best route by radio instead (from the iGate only when no radio route is known).

A station whose last position is older than its timeout is left off the map, marker and track, and stays in the Stations table. Selecting its row still flies the map to its last position and shows its card, and its marker for as long as it is selected.

The timeout is 3 hours (180 minutes) for every station. A station can have a timeout of its own: under **Details** on its card, **Hide from map after** takes minutes after its last position. The placeholder "3 h (usual)" is the usual time and an empty field means the usual time. "never" or 0 is never, and an x takes the station's own away. Your own station never times out. A station's own timeout can be at most 10080 minutes (a week). The daily clean-up keeps a station with a timeout of 0 whatever its age; its packets and messages are cleaned up as the others are.

Without a base map the map area says "No base map" with a Download button over a blank background, and the stations are drawn all the same ([The base map](#the-base-map)).

## A station's card

A click on a marker opens a card over the map. It is above the markers, clear of the map's zoom buttons, and the map moves so that the station's marker is not under it. It has the facts a person asks for:

- the symbol's picture and name, and a small QRZ link beside the call (the base call's page on qrz.com, the SSID off, in a new tab; for a station, yours included, not for an object or an item);
- a green check mark beside the call when the station was heard direct;
- when the station was last heard ("6 min ago", the full time on hover);
- its position, how far and in which direction it is from you;
- its speed and course (only a station that moves has them) and the altitude;
- the status and the comment;
- one line of how its packets reach you ("Reached us via OH2RCH-2", or "direct").

A row with nothing to say is left out: a station that stands still has no speed whatever course it gave, a station that sent no altitude has none, and so on. An altitude of 0 that the station did send is shown.

The buttons are **Message**, which opens the Messages tab on the station, and **Forget**, the trash can at the right ("Forget OH2XYZ" on hover), which asks twice (it says "sure?" after the first press, and takes it back after 5 seconds). The station's own timeout, **Hide from map after**, is under Details.

**Message** is there only for a station that can do messages. There is none for an object or an item, and none for a station that sent its positions with `!` or `/` (the identifiers of a station without messaging) or Mic-E positions whose comment starts with `'` (a tracker without messaging), unless it has sent a message or an ack that you heard (overheard ones too). Positions with `=` and `@`, other Mic-E positions, and a station of which nothing is known yet all have it.

NeoAPRS finds this again at its start from the packet log. The bulletins and telemetry definitions of a station do not count as a message.

**Details**, closed, has the rest:

- the data extensions, the locator and the telemetry the station sent;
- when it was first heard;
- the path of its latest packet as it was sent;
- how its packets reach you ("Heard: 12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3", "from the internet" for third-party packets);
- the best route with the path to send by;
- the number of packets.

The path and **RF only** are set in the header of the conversation in the Messages tab, not on the card ([messages.md](messages.md#a-path-for-each-station)).

A weather station's card has its weather panel at the top ([weather.md](weather.md)). The card of an object of yours has **Edit** and **Kill** ([objects.md](objects.md)).

### Several cards

A click on a marker or on a row of the Stations table opens that station's card and closes the others. With **Ctrl** held (**Cmd** on a Mac) the click adds the card to the open ones, or closes it when it is open already. This is for comparing, for instance several weather stations.

- The cards are side by side in a row over the map, from its left, the oldest at the left and the newest at the right. **Every card is the whole card**, with its graphs when it is a weather station: opening more cards makes none of them smaller.
- While two or more weather cards are open each graph is on the same value axis and the same time span on all of them. A single card keeps its own axis.
- When the row is wider than the map has room for, the oldest card closes: up to four on a desktop, two on a tablet, one on a phone (a tap replaces it). Each card has its own cross.
- **Drag a card by its head** (the symbol and the call, not the buttons and the QRZ link) to move it anywhere over the map, with the mouse, a finger or a pen. The card stays inside the map, and the map does not move while you drag. **Alt** with an arrow key moves the card that has the focus (with **Shift** in bigger steps). The card on a phone is a bottom sheet and cannot be dragged.
- **Moving a card never moves another.** When you start to move one, every other open card stays exactly where it is on the screen, and the place the card left stays empty. Closing a card does not make the others close up either.
- A card that you open later goes to the first free place in the row, from the left, where it covers no other card (the empty place of a card you moved, or room to the right of the cards); with no free place in the row it goes to a row above. It is never put on top of a card (you can put one there yourself). All the open cards count against the room above, wherever they stand: the oldest closes when there are too many.
- A card keeps its place as long as it is open, and places are not remembered: **Close all** and **Esc**, and then a new card, start the row again from the left. A card that grows (its **Details** opened, a weather card's graphs) is kept inside the map.
- When you pick a station whose marker is under a card, wherever the card stands now, the map moves so that the marker is clear of it.
- With two or more open, **Close all** and **Message these 3** are at the top left of the map beside the zoom buttons. The count is of the open cards that are stations that can be messaged, not yourself. The second button opens the Messages tab with a [group compose](messages.md#one-text-to-several-stations) for those stations.
- The marker and the row of every open card have the selected look, and the track of every open card is highlighted. The route to your station is drawn for the newest card only.
- A card added from the table does not fly the map to the station (a plain click does).
- A station past its timeout stays in the table, and a click on it, with Ctrl or without, shows its marker and track on the map for as long as its card is open.
- **Esc** closes all the cards at once and clears the selection. Not while a field has text in it: in the filter box of the Stations table the first Esc clears the text and the next closes the cards. And not while the setup guide or the update panel is open: they take the key.

## The header and the footer

The **header** is one calm line. It holds the title **NeoAPRS**, a link to the project page (https://oh2gba.github.io/neoaprs/, in a new tab; it looks like the title, with an underline on hover), and at its right the number of messages not seen as a small badge with an envelope. That is the messages and the gateway's mail not seen, one count that the handle of the folded panel and the title of the browser tab have too. A click opens the Messages tab, or the Email tab when all of them are the gateway's.

While no call is set an amber **no call set** button is beside the title, which opens the setup guide. Your call is not in the header; it is in the Settings tab and in every message you send.

The **footer** is one small muted line under the open tab of the panel (under the panel, not under the map; on a phone under the tab; not while the panel is folded). It is always the same height, so nothing moves when a message comes or goes.

- At the left is the name and version of the program. Its hover text says what the daemon costs the machine, every 10 seconds: its share of one CPU core in percent, its memory and the uptime ("NeoAPRS uses 0.3 % · 42 MB · up 3 h").
- When the update check has found a newer version, an **Update to** button follows it, which opens the window of the update: what is new, **Update now** where NeoAPRS can update itself, and the steps by hand ([install.md](install.md#updating)). On a phone the map has no footer, and the header has a small badge with the new number instead.
- At the right is the state of the radio, only when it is not ok, in the warning colour, as a button that opens the Settings tab where the radio is. "Radio: searching…" (looking for the port), "Radio: entering KISS…", "Radio: not connected" (it waits between two tries, or is stopped; the TNC's problem is the tooltip), "Radio: waiting…" (no word from the TNC yet), "Radio: silent" (the line is open and the radio does not answer; the tooltip says "nothing heard since 18:43 (5 h)" in the browser's time), "Connecting…" (the page's connection is being opened) and, in red, "Daemon offline".
- When the radio is connected the footer says nothing of it. The port and when a packet was last heard are in the radio status at the top of the TNC group of the Settings tab.

## The page's language

The page speaks English, Deutsch, Español, Français, Italiano, 日本語 and Português (Brasil). It starts in your browser's language when it has it, else in English. **Language**, at the top of the Settings tab, changes it for this browser. The translations have not all been read by native-speaking hams yet: corrections are welcome. The daemon's own words (the log, the radio's terminal, the packet summaries, the names of the radio types) and the manual stay English.

## What the page remembers

The panel's width and tab, the map's view, the table's "hide timed out" and "direct only", which messages and bulletins were seen, the addresses used for mail, the choice of browser alert and the language are kept in your browser's local storage, and nothing else is. Each device keeps its own.

## A phone, a tablet and a desktop

The page chooses its layout from the size of the window.

| size | window | what it looks like |
|---|---|---|
| **phone** | under 700 px wide, or shorter than 500 px and under 1000 px wide (a phone held sideways) | One view at a time. A compact header, the tab bar under it (the tabs as one **☰** button when they do not fit), and the rest of the screen is the open tab with the footer under it, or the map. The first button of the tab bar is **Map**: it shows the map on the whole screen, and a tab of the bar brings its tab back (the view is remembered). A station's card is a bottom sheet: folded to its head and the first facts, a tap or a swipe up on its grip opens it, a swipe down folds it and a swipe down on the folded sheet closes it. It has a close button too (held sideways it is a sheet at the left). A tap on a row of the Stations tab shows the map with the card; **Message** and **Edit** on the card and the mail count of the header bring the tab. **Choose on map** shows the map with a bar ("Tap the place on the map", **Cancel**), and the tab comes back with the place filled in. The setup guide is the whole screen. One card at a time |
| **tablet** | 700 to 1100 px | The map and the panel side by side, the panel 380 to 420 px wide (40 % of the window between those; no handle, a finger cannot drag it), with the fold button. Both orientations are side by side: a portrait tablet (768 by 1024) keeps a map 388 px wide, which is enough for a pinch and a card, and the panel keeps its full height. Up to two cards |
| **desktop** | from 1100 px | The map and, at its right, the panel with the handle you drag. A panel you have not dragged is 760 px wide from a window of 1280 px (wide enough for the two columns of the Messages tab and the eight tabs with their badges), 480 px below that; a width you dragged is kept. Up to four cards side by side, as many as the width of the map has room for |

- On every size the page is the height of the window (it follows the toolbars of a phone), does not scroll sideways, and keeps clear of the notch and the home bar.
- On a touch screen every button, tab, field and row is at least 40 px high and a field has a 16 px font, so that a phone does not zoom the page in when one is focused.
- The installed app uses the same layout.

**One box to write in.** On the tabs Messages, Bulletins, Email and Objects the list or the board fills the tab and scrolls, and the box to write in is fixed at the bottom of it. It has the fields and under them one line with the counter ("67 left") and the buttons at the right: the secondary one (Cancel) left of the primary one (Send, Post, Save), which is the last.

On a phone the box stays above the home bar, and the field being typed in is scrolled into view when the keyboard comes up. The form of an object scrolls inside the box on a short screen, its buttons always in sight. A list of suggestions or the note of an (i) in the box opens upward.

## The base map

The base map is two files in the data folder that the daemon serves to the page:

- `basemap.pmtiles`, the OpenStreetMap map of the area round your station: a square of `map/radius_km` (10 to 1000 km, default 150) in every direction, down to zoom 12.
- `basemap-world.pmtiles`, the world to zoom 5 (about 15 MB), drawn under it so that there is something to see outside the area and when zoomed out. It ships with NeoAPRS.

You make the detailed map in the Settings tab, in the Map group. It has the **Radius** and one button, **Download map** ("Download map again" when there is a detailed map, with a line such as "Map downloaded 23 Oct" beside it). The same is `neoaprs map` on the command line.

1. The first press works out the size ("Checking size…"), and the button then asks "Download 493 MB?" with the real size.
2. The second press makes the world map, if there is none, and then the detailed map. A bar shows the percent of the step and the size so far ("Map of the area 49% · 340 MB").
3. **Cancel** ends the job. The half-made file is removed and the map that was there stays.

A change of the radius takes the question back. One job runs at a time. The button waits for a change of the radius that is being saved and for the station to have a position.

- The files are cut out of the daily build of build.protomaps.com (or the source in `map/source`) with the `pmtiles` program of [go-pmtiles](https://github.com/protomaps/go-pmtiles) (BSD-3-Clause), each into a `.part` file that is moved into place when the program has finished. It is run with eight download threads.
- A download that stands still, with neither the percent nor the size of the `.part` file moving for 2 minutes, is ended and begun again from the start after 10 seconds, three times in all. The page says so ("no progress: trying again (2 of 3)"). When the last try stands still too, the job ends with "the map server is too slow now; try again later", and the map that was there stays.
- The program is the one on the PATH, else `bin/pmtiles` (`bin/pmtiles.exe` on Windows) in the data folder. When there is neither, the release for this system (Linux and macOS on x86_64 and arm64, Windows on x86_64) is downloaded from GitHub into `bin/`, and only if its SHA-256 is the one NeoAPRS has pinned.
- `map/maxzoom` (6 to 15, default 12: 10 shows towns, 12 streets, 14 houses) and `map/source` are not on the page. The estimate and the download use the stored values (`neoaprs db set map/maxzoom 14`). `map/source` is empty for the latest daily build (today's, else back up to a week), a web address (`https://...`) or the path of a PMTiles file, such as a planet file of your own. A deeper zoom of the page draws the last one magnified.
- By hand: put `pmtiles` on the PATH and run `pmtiles extract https://build.protomaps.com/YYYYMMDD.pmtiles data/basemap.pmtiles --bbox=WEST,SOUTH,EAST,NORTH --maxzoom=12`, and the same with `--maxzoom=5` and no `--bbox` into `data/basemap-world.pmtiles`. A file made that way is shown all the same, its area and zoom read from its header.

The names of places and roads are drawn with Noto Sans glyph files (Regular and Medium, made by the Protomaps `basemaps-assets` project, SIL Open Font License 1.1).

### Credits

The (i) on the map shows the credits: "© OpenStreetMap contributors, Protomaps" (the base map data is OpenStreetMap's, ODbL, in the Protomaps tile format) and the symbol set. MapLibre GL JS (BSD-3-Clause) and PMTiles (BSD-3-Clause) are in the page.

The symbols are the aprs.fi high-resolution symbol set by Heikki Hannikainen, OH7LZB (<https://github.com/hessu/aprs-symbols/>). The set is released to the APRS community for use by any APRS application, for free, with a request to give a pointer to the source, which is done in the (i) on the map and in a file beside the sheets. Where each symbol comes from and under what terms (many public domain or CC BY-SA, the old APRS set's originals without licence information, three company logos) is in a file beside the sheets. The sheets are unchanged.
