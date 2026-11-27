# The satellites layer

For contributors: where the map's satellites come from, the rules of the orbit data's provider, where the list lives and how a satellite is added. The operator's side is in [manual/page.md](manual/page.md#satellites).

## The data flow

1. **The list** is `server/neo/private/satellites-list.json` in this repository: for each satellite its catalogue (NORAD) number, a short name, its APRS downlink and uplink frequencies, its mode and its digipeater path, each value with `"sure": true` or `false`, and a `source` line that says where the values were found. `server/deploy.sh --site` uploads it to `private/` on the project's host, which Apache never serves.
2. **The endpoint** `server/neo/api/v1/satellites.php` answers a GET with `private/satellites/satellites.json`: the list (without `source`) and, for each satellite, its orbital elements as OMM fields, or `null` when CelesTrak has none. When its last download is older than 24 hours it downloads CelesTrak's group `amateur` as CSV and merges again; a changed list is merged with the last download at once. The host has no cron: the first request after a day pays for the download.
3. **The daemon** (`neoaprs/services/satellites.py`) fetches that file while a page has the layer's tick on and the file is missing or a day old, at most once a day, an hour apart after a failure. It keeps the file as `satellites.json` in the data folder and uses it while the server cannot be reached. Nothing is fetched or computed while no page looks; `NEOAPRS_UPDATE_CHECK=0` fetches nothing (the tests and `scripts/demo-daemon`), and `NEOAPRS_SATELLITES_URL` points the daemon at a server on this computer (CONVENTIONS.md).
4. **The maths** is in the daemon, with the `sgp4` package: `neoaprs/satellites.py` gives the point under a satellite, the look angles and range rate from the station, the footprint, the Doppler shift and the passes; `neoaprs/satellitelist.py` reads the file and drops every value the list does not mark sure and every satellite whose elements are older than 14 days; `neoaprs/satelliteview.py` makes what a page is told.
5. **The page** sends `satellite_look` with the ids of its open cards and gets `satellites` every 30 s and at once when its cards change (PROTOCOL.md): every satellite with points from 30 s ago to 5 minutes ahead, which the page moves the mark between, and for each open card the next pass, the samples of the elevation and Doppler while it is up, the frequencies to tune, the track ahead and the footprint's radius.

## The provider's rules

CelesTrak (https://celestrak.org/usage-policy.php and https://celestrak.org/NORAD/documentation/gp-data-formats.php): download each update once (new data comes at most every 2 hours), ask for compressed data, stop asking after any answer that is not 200, and keep to the limit of errors. The endpoint makes one request a day, sends `Accept-Encoding: gzip`, follows no redirect, and after a failure asks again only after 2 hours. Installations never ask CelesTrak themselves.

TLE lines cannot hold catalogue numbers above 99999 (AO-129 is 101098), so the elements are CelesTrak's CSV, whose columns are the OMM fields.

## Adding a satellite

1. Find its catalogue number (CelesTrak's `amateur` group lists most; a satellite outside the group needs its own request in the endpoint first).
2. Add an entry to `server/neo/private/satellites-list.json`. Mark a value `"sure": true` only when the operator's own page or a recent report of packets heard confirms it, and say where in `source`. A frequency heard confirms the downlink, not that the digipeater repeats; a path is sure only from the operator. A value that is not sure is never shown.
3. Run `tests/test_satellites_php.py` and `tests/test_satellites_service.py` (the fixture of the elements is `tests/fixtures/satellites/amateur.csv`, fetched once on 27 Nov 2026), and `server/deploy.sh --site`. No release is needed: installations take the new list with their next daily file.
