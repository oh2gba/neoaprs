# Ships and aircraft

NeoAPRS can draw the ships and the aircraft round you on the map, beside the APRS stations. Each has a group of its own in the Settings tab, with one tickbox:

- **Settings → Ships (AIS) → Enable** shows the ships within 450 km of your position, from the open AIS data of Fintraffic's Digitraffic.
- **Settings → Aircraft (ADS-B) → Enable** shows the aircraft within 450 km of your position, from the open ADS-B data of adsb.fi.

Both are off until you switch them on. They need your position: the place in the My station tab, or the fix of the GPS.

**Nothing is sent.** The ships and the aircraft are read over the internet and only drawn. They are not APRS stations: they are not in the Stations tab or the Packets tab, they are not kept in the database, and nothing of them goes on the radio or to APRS-IS. This is how NeoAPRS is built, not a setting.

## On the map

- A ship is a hull pointed the way its bow points, or the way it moves when it does not say its heading. A still ship that gives no heading is a dot.
- Its colour says what it is: green a cargo ship, red a tanker, blue a passenger ship, yellow a high-speed craft, orange a fishing vessel, violet a sailing or pleasure craft, teal a tug, a pilot, search and rescue and other special craft, grey the rest.
- An aircraft is a silhouette of its kind (a light aircraft, an airliner, a heavy one, a helicopter, a glider, a balloon, a drone), pointed the way it flies. One that declares an emergency is red.
- When you zoom in, the full name of each ship and the flight of each aircraft are written beside it.
- Click one to open its card at the top right of the map. Its cross closes it. The card closes by itself when the ship or the aircraft is no longer in the data.

A ship's card has its type, MMSI, call sign, IMO number, navigational status (under way, at anchor, moored ...), speed in knots, course, heading, size (length × beam), draught, destination, ETA, distance and when its position was received.

An aircraft's card has its type, flight, registration, ICAO address, altitude in feet (and metres), speed in knots (and km/h), track, vertical rate, squawk, an emergency it declares, distance and when its position was received.

## The status row

Under each tickbox, while it is ticked, is a status row like the radio's:

- **receiving**, with how many ships or aircraft are within 450 km;
- **connecting** while the first answer has not come;
- **waiting** while there is no position to ask round;
- **not reachable**, with why (no internet, the server's error). The ships and aircraft already shown stay until they are old, and the data is asked for again a little later each time.

Behind its arrow are the time of the latest answer and whose data it is.

## How often

- The ships' positions are read every minute, and their names and voyage data every ten minutes. A ship whose position is older than an hour is not shown.
- The aircraft are read every 15 seconds. An aircraft not heard for a minute is not shown.
- When you switch a group off, its ships or aircraft go from the map at once.

## Whose data it is

The ships come from Fintraffic's Digitraffic, open data under the licence CC BY 4.0 (digitraffic.fi). The aircraft come from adsb.fi, made of what its volunteers' receivers hear. While a group is on, its credit is in the (i) of the map.
