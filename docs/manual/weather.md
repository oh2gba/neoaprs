# Weather and what else NeoAPRS reads

## Weather stations

A weather station sends its readings in a position packet with the weather symbol `_`, or in a positionless weather report. NeoAPRS shows them in metric units: wind and gusts in km/h (to 0.1), temperature in degrees C, rain in mm, pressure in hPa, humidity in per cent, the wind direction in degrees.

A field the report did not have is left out. A report whose fields are all missing is no weather. An object or item with the weather symbol carries weather too.

The **card** of a weather station (the weather symbol, or a station that has sent weather) opens with its weather panel at the top:

- the readings: the temperature large, the wind as an arrow turned to where it goes with its speed, the direction it comes from and the gusts, humidity, pressure, rain over the hour, over 24 hours and since midnight, and luminosity and snow when sent;
- how long ago they were heard;
- under them, the graphs of the temperature, the pressure, the wind (with its gusts as a lighter band) and the rain (as bars), over the last 24 hours or 7 days. The switch is remembered;
- a line under the pointer that says the value and the time of the nearest observation.

Each line of a graph is one smooth curve through the readings, across the hours where the station sent none (a monotone cubic: it never rises above or falls below the readings it runs between, so a pressure curve does not invent a peak). It starts at the first reading and ends at the last, a single reading is a dot, and the band between the wind and its gusts follows the same two curves. The rain is bars, none for an hour with no reading.

The graphs are drawn by the page in its own colours. The page asks for them when the card opens, when the switch changes and when a new observation comes.

While two or more weather cards are open, every graph is on the same value axis and time span, so the stations can be compared ([page.md](page.md#several-cards)).

On the map, a weather station keeps its symbol, and the small card that appears when the pointer rests on its marker shows its temperature.

## What is kept

Every weather packet heard is kept for the graphs, with the time it was heard (not the time it carries). A report that reaches you by two digipeaters is two observations. Observations older than 7 days are removed once a day.

At the start, when no observations are kept yet, NeoAPRS reads the weather packets of the last 7 days from the packets it has and makes the observations from them. Then every station is given its newest observation.

The track of a moving station is kept in memory, so at the start it is made again from the packets: the latest 5000 position packets heard within 7 days, oldest first. A point joins the track when the station moved more than 10 m or 5 minutes passed, and the latest 50 are kept. Your own station has no track.

## What else is read

Besides positions, objects, items, messages, statuses and weather, NeoAPRS reads these, and the station card shows each on a line of its own:

- **Data extensions** after the symbol of an uncompressed position: `PHG` (power, height, gain, directivity and the range the specification's formula gives), `RNG` (range in km; a compressed position may carry the range too), `DFS`, the bearing and quality of a direction-finding report, and `Tyy/Cxx` of an area object.
- **A voice frequency** at the start of the comment of a position, an object or an item, or of a status text, as the frequency specification writes it (`145.775MHz T118 -060 R40k`, or an object named by its frequency such as `145.775-A`): the station card shows it on a line of its own with the tone, the offset and the range, and it does not show in the comment. NeoAPRS only shows it; nothing is sent to a radio.
- **Storm data** of a hurricane, tropical storm or tropical depression object (`/HC/150^200/0980>090&030%040` after the course and speed), shown in the card's details in words, with the radii in kilometres.
- **A signpost** (an object or item with the signpost symbol and `{55}` at the start of its comment) shows its characters on the map and in the card's details.
- **Extra precision.** The `!DAO!` at the end of the comment of a TH-D74, a TH-D75 or APRSdroid (`!W12!`, `!wAB!`) makes the position finer, to a metre or so, and does not show in the comment.
- **Raw NMEA** sentences (`$GPGGA`, `$GPGLL`, `$GPRMC`, `$GPWPL`, from any talker such as `$GN`; the checksum is checked when there is one). They give a position with course, speed, altitude and time. Its symbol comes from the destination, else from the source's SSID.
- **Telemetry.** NeoAPRS keeps the latest report of each station (a `T#` packet, or the compact `|...|` telemetry at the end of a position's comment) and the names, units and equations the station sent for it, and shows the values with the equations applied (raw values when it sent no definition).
- **A Maidenhead locator** at the start of a status report is shown with the station (the grid and the centre of the square). It does not move the station.
- **Mic-E** positions, including the altitude and the telemetry flags in their comment.
- A timestamp with `/` is the sender's local time. It is shown as sent ("09 23:45 local"), never converted.
- **Other packets:** test data, station capabilities, shelter data, space weather and a Maidenhead locator beacon (a position at the centre of the square).

How the parser reads each form is in [`docs/daemon.md`](../daemon.md#what-the-parser-reads).
