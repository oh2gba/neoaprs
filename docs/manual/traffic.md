# Ships and aircraft

NeoAPRS can draw the ships and the aircraft round you on the map, beside the APRS stations. Each has a group of its own in the Settings tab:

- **Settings → Ships (AIS) → Enable** shows the ships round your position, from the open AIS data of Fintraffic's Digitraffic.
- **Settings → Aircraft (ADS-B) → Enable** shows the aircraft round your position, from the open ADS-B data of adsb.fi.

Both are off until you switch them on. They need your position: the place in the My station tab, or the fix of the GPS.

**Nothing is sent.** The ships and the aircraft are read over the internet and only drawn. They are not APRS stations: they are not in the Stations tab or the Packets tab, they are not kept in the database, and nothing of them goes on the radio or to APRS-IS. This is how NeoAPRS is built, not a setting.

## The settings

| Setting | Ships | Aircraft | What it does |
|---|---|---|---|
| **Enable** | yes | yes | draws them on the map; off by default |
| **Ship types** | yes | | a tickbox for each colour group: cargo ships, tankers, passenger ships, high-speed craft, fishing vessels, sailing and pleasure craft, tugs, pilots, rescue and other special craft, and the rest; all ticked by default |
| **Hide still ships** | yes | | leaves out the ships moored, at anchor or not moving (slower than half a knot); a ship aground, not under command or with an AIS-SART is always shown |
| **Radius** | yes | yes | how far round your position, in km: any whole number from 50 to 450 (450 by default) |
| **Track** | yes | yes | how long a line of the way each has come is drawn: none, 15 or 30 minutes, 1, 3 or 12 hours (30 minutes by default) |

A change applies at once: the data is asked for again with the new settings.

## On the map

- A ship is a hull pointed the way its bow points, or the way it moves when it does not say its heading. A still ship that gives no heading is a dot.
- Its colour says what it is: green a cargo ship, red a tanker, blue a passenger ship, yellow a high-speed craft, orange a fishing vessel, violet a sailing or pleasure craft, teal a tug, a pilot, search and rescue and other special craft, grey the rest.
- An aircraft is a silhouette of its kind (a light aircraft, an airliner, a heavy one, a helicopter, a glider, a balloon, a drone), pointed the way it flies. One that declares an emergency is red.
- When you zoom in, the full name of each ship and the flight of each aircraft are written beside it. An aircraft's height follows its flight: a flight level from 5000 ft up (**FIN1336 · FL350**), feet below it (**OH-ABC · 2500 ft**), nothing on the ground.
- A track is a thin line of the way it has come, a ship's in its colour, an aircraft's in theirs. NeoAPRS keeps the tracks only while it runs: after a restart they start again.
- Click one to open its card at the top right of the map. Its cross closes it. The card closes by itself when the ship or the aircraft is no longer in the data.

A ship's card has its type, MMSI, call sign, IMO number, navigational status (under way, at anchor, moored ...), speed in knots, course, heading, size (length × beam), draught, destination, ETA, distance and when its position was received.

An aircraft's card has its type, flight, registration, ICAO address, altitude in feet (and metres), speed in knots (and km/h), track, vertical rate, squawk, an emergency it declares, distance and when its position was received.

## The status row

Under each tickbox, while it is ticked, is a status row like the radio's:

- **receiving**, with how many ships or aircraft are shown within the radius;
- **connecting** while the first answer has not come;
- **waiting** while there is no position to ask round;
- **not reachable**, with why (no internet, the server's error). The ships and aircraft already shown stay until they are old, and the data is asked for again a little later each time.

Behind its arrow are the time of the latest answer and whose data it is.

## How often

A ship keeps a new place of its track when it has moved 30 m, an aircraft when it has moved 200 m; the last 12 hours are kept.


- The ships' positions are read every minute, and their names and voyage data every ten minutes. A ship whose position is older than an hour is not shown.
- The aircraft are read every 15 seconds. An aircraft not heard for a minute is not shown.
- When you switch a group off, its ships or aircraft go from the map at once.

## Whose data it is

The ships come from Fintraffic's Digitraffic, open data under the licence CC BY 4.0 (digitraffic.fi). The aircraft come from adsb.fi, made of what its volunteers' receivers hear. While a group is on, its credit is in the (i) of the map.
