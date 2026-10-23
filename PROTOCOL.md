# The protocol between the daemon and the page

*This file is generated from the models in `neoaprs/web/protocol.py` and the `neoaprs/web/*wire.py` modules by `scripts/gen-protocol.py`: change the models (their docstrings and field descriptions are the
text below) or the prose in the script, not this file. `tests/test_protocol.py` fails when it is out of date.*

One WebSocket per browser tab at `ws://host:7303/ws`. JSON text frames both ways. Every time is UTC ISO 8601 with a `Z`. A station is referred to by its call and a packet by its id, never by
a position in a list.

The conversation: the page opens the socket and is sent `hello` (the version of this protocol, the version of the daemon, how it was installed, the topics), then the **state** of every topic (`state`: its revision
and its whole value), and `status`. From then on it is sent what changes (`patch`). Everything else is a **command** from the page (`ping`, `set_config`, `forget_station`, ...), answered by
the change it makes in a topic, or by `pong`, `status` or `error`. All the state of the daemon that the page shows is small, so a page follows every topic from the start; it may stop following one
(`unsubscribe`) and ask for it again (`subscribe`, which is answered with `state`).

```
page                                     daemon
  |  <-------------------------------------  hello {protocol, version, install, topics}
  |  <-------------------------------------  state {topic, rev, value}          (one for each topic: stations, packets, tnc, config, station_prefs, messages, bulletins)
  |  <-------------------------------------  status {version, started_at, packets, stations, call, lat, lon, ..., cpu_percent, rss_mb, uptime_sec}   (every 10 s too)
  |  <-------------------------------------  patch {topic, rev, ops}            (as it changes, on a tick of 100 ms)
  |  -- set_config {values} ------------->
  |  <-------------------------------------  patch {topic: "config", ops: [replace]}   or  error {text}
```

## Connection, the host and the headers

The daemon listens on `web/port` of the settings (default `127.0.0.1:7303`; port 0 is a free one, which the log tells: `web page at http://127.0.0.1:PORT/`). While the setting `web/network` is on it
listens on every interface instead, and a request from any address but this computer's must carry the session cookie that the access key (`web/key`) bought; a request from this computer asks for
nothing. The page's files are free (they hold the key screen); the socket and the base map answer `401` without the cookie. `GET /access` answers `204` to a device that is let in and `401` to one that is
not; `POST /access` with `{"key": "k7m2-x9pq-4hrt"}` logs a device in (`204` and the cookie `neoaprs_session`, HttpOnly and SameSite=Strict, valid for a year; `403` for a wrong key; `429` for five wrong ones
in a minute from an address, which is then refused for five minutes); `POST /access/new` makes a new key, which ends every session but the asking device's. A session is an HMAC under the key, so it
needs no storage and ends with the key. A port that is in use leaves the daemon running without the page.

Every request, the socket's too, must carry a `Host` header that is an IP address, `localhost`, the name of this computer or a name in the setting `web/allowed_hosts` (several, separated by commas);
any other is answered `403` with a line that says what to do (a page of another site whose name was moved to this address cannot talk to the daemon). A socket from a page of another site (an
`Origin` that is not the `Host`) is refused too.

The files: `/` and what is under it come from `page/` (`scripts/build-page` makes it; while there is none, a line says so), `/basemap.pmtiles` and `/basemap-world.pmtiles` are the files of those names in the data folder
(the detailed map and the world under it), served with byte ranges (a `404` with a line of text while one is not there: the `map_fetch` command makes them), `/ws` is the socket. Nothing whose name begins with a dot is served, and no source map. Every answer
carries the security headers: a Content-Security-Policy that allows the page's own scripts, workers, styles and its own socket and nothing else, `X-Frame-Options: DENY`, `Referrer-Policy:
no-referrer`, `X-Content-Type-Options: nosniff` and `Cross-Origin-Resource-Policy: same-origin`. An error is a line of text. The shell `index.html` is sent `Cache-Control: no-cache`, the hashed
files of `assets/` `public, max-age=31536000, immutable`.

At most 256 connections are open at once (32 from one address that is not the loopback). A message from the page is at most 64 KiB (a bigger one closes the socket with 1009). A page whose socket
holds more than 4 MiB it has not read is sent no patches and is sent the topic whole when it has read down; one that holds 32 MiB is cut off. The socket is compressed when the browser offers
`permessage-deflate`.

## Following the state of the daemon

The state of the daemon that a page shows and that changes is held in named *topics* (`neoaprs/web/hub.py`; what changes each is in the table of `neoaprs/web/topics.py`). The value of each topic is in *Topics*
below; its type is the one in `TopicValues` of `neoaprs/web/protocol.py`. There are two kinds: a topic of **one whole value** (`tnc`, `config`), which changes by `replace`, and a **table of items** by
key (`stations` and `station_prefs` by call, `packets` and `messages` by id as text, `bulletins` by `sender/slot`), which changes by `set` and `del` of one item.

### `subscribe` and `unsubscribe`

All topics are followed from the start. `unsubscribe` stops following some (a topic that was not followed is ignored), `subscribe` follows them again and is answered with `state` for each (a
topic that is followed already is sent whole again: a page may ask at any time). A name that is no topic is refused with an `error` that names it; the others in the command are not affected.

### `state`

`state` is a topic as it is: its `rev` (the revision) and its whole `value`, which replaces what the page had. It is the first message of every topic, the answer to `subscribe`, and what a page is
sent when it was too slow to be sent patches and has read down its socket.

### `patch`

`patch` is what changed: `rev`, the revision the copy is at when the ops are applied in order, and the ops: `replace` (the whole value), `set` (the item at `key` is `value`) and `del` (the item
is gone). An op says what the item *is*, not what to add, so an op that is applied twice ends where it should. A change of the daemon is told on the hub's **tick** of 100 ms: what changed between
two ticks is one patch for a topic, with at most one op for each key, so a burst of 200 packets is one message. The topic `tnc` changes with every line the TNC sees and is told at most four times a
second. A page that sees a revision other than the one before plus one has missed something and asks again with `subscribe`.

Revisions count up in each topic and start again at 0 when the daemon starts. The packets of a topic `packets` are numbered by the daemon in the order they come in this run (`id`); the 200 the
daemon starts with are the latest the database holds. The messages of a topic `messages` are numbered by the database (`id`) and kept across runs; the daemon holds all of them
(a database with more than 10000 gives the latest 10000 at a start); none leaves on its own.

## Validation

Every frame the page sends is checked against the `Command` union before anything is done. The models are strict: a number is a number (not `"5"`), a flag is `true` or `false` (not `1`), a
field the model does not know is an error, text has a maximum length, `NaN` and `Infinity` are not JSON. A frame that does not fit is answered with `{"type": "error", "text": "<command>: <field>:
<what is wrong>"}`, for example `forget_station: call: is missing`, and nothing at all is executed. A frame that is not JSON, or not an object, or names no known command is answered the same
way. The values of `set_config` are checked by the settings (`neoaprs/config.py`), all before any is stored: the first that is wrong is the answer, `set_config: station/lat: 95 is not between -90
and 90`.

With `NEOAPRS_VALIDATE_OUT=1` in the daemon's environment every message it sends is checked against the `Message` union too (`state` and `patch` also against the type of the topic's value, and
each `set` against the type of the item), and a message that does not fit is logged once for each type (the test suite runs with this on, and fails on any mismatch).

TypeScript types for both unions are in `ui/src/protocol/protocol.ts`, the JSON Schema in `ui/src/protocol/schema.json`, the lists the daemon owns in `ui/src/protocol/lists.ts`.

## Adding a topic

1. **The value.** Add a field to `TopicValues` in `neoaprs/web/protocol.py`, typed with models (add them to a `neoaprs/web/*wire.py` module if the value is new), and describe it in `Field(description=...)`: the
   description is the row of the table under *Topics*. Run `scripts/gen-protocol.py`: it writes this file, `ui/src/protocol/schema.json`, `protocol.ts` and `lists.ts`.
2. **The row.** Add a `Topic` in `Topics.__init__` of `neoaprs/web/topics.py` (`build` makes the whole value from the daemon's state, `item` one item of a table, `interval` the least time between two
   patches) and connect the signals that make it stale: they call `hub.changed(name, key)`. A view in `neoaprs/web/views.py` makes the plain dicts.
3. **The page.** Follow the topic in the page's store and add its value to the fixtures of the page's tests.
4. **The tests.** `tests/test_web.py` drives the topic over a socket with `Env(web=True)`; every message is checked against the models while it runs.

## Client to server

32 commands, each a JSON object with `"cmd"` as the first field. Types: `integer` and `number` are JSON numbers, `time` is UTC ISO 8601 with a `Z`.

### `ping`

Answered with `pong`.

### `status`

Answered with `status` at once (the daemon also sends one every 10 s).

### `update_check`

Asks the version page now, the question of the daily update check; the daily schedule is left as it was. Answered with `update_result` and then a `status` (with the newer version, if there is one) to the page that asked.

### `subscribe`

Follow these topics (all are followed from the start): each is answered with `state`, then with `patch` as it changes. A topic that is followed already is sent whole again. A topic that is
not there is refused with an `error` that names it; the others in the command are not affected.

| field | type | | description |
|---|---|---|---|
| `topics` | string[] |  | (max 16 items) |

### `unsubscribe`

Stop following these topics. A topic that was not followed is ignored.

| field | type | | description |
|---|---|---|---|
| `topics` | string[] |  | (max 16 items) |

### `forget_station`

Removes a station from the station book (and its cache in the database) until it is heard again. Not our own station. Answered by the `del` of the row, or by an `error`.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |

### `tnc_reconnect`

Opens the radio's line again with the settings as they are now (the port, the speed, entering KISS): the TNC is stopped and started in the background. The new state is told in `tnc`.

### `list_ports`

Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a port of the machine: it is typed.

### `set_config`

Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is
left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) counts at once, `serial/*`, `tcp/*` and `tnc/profile` restart the
TNC, `station/*` move our own station on the map. `tnc/check_sec` and `map/hide_after_min` count at once, with no restart.

| field | type | | description |
|---|---|---|---|
| `values` | { [key: string]: string } |  | key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`) |

### `beacon_now`

Sends our position packet now, with the settings as they are (the same packet as the timer's), and the next one is an interval later. It goes out through the TNC, so it is not answered:
it arrives as the new `packets` row with direction `out`, and `status` follows with the time of the beacon. Answered with an `error` when it could not be sent: the TNC is not connected, or
the settings make no frame.

### `status_now`

Sends our status report now, with the settings as they are (from the text or from the radio, as `status/source` says), whether it changed and inside the interval; the next one of the timer
is an interval later. It goes out through the TNC, so it is not answered: it arrives as the new `packets` row with direction `out`, and `status` follows with the text. Answered with an `error` when
it could not be sent: the status is off or has no text, the radio is away, the call is not set, the TNC is not connected or the settings make no frame.

### `send_message`

Sends a message to a station: the addressee is a call with an optional SSID, the text at most 67 bytes of UTF-8 without `|`, `~`, `{` or a control character. The message is kept and transmitted at
once with the next message id; it arrives as a new row of the topic `messages` (state `sending`) and as the `out` packet, and its row changes when the acknowledgement comes or the attempts run out. It is transmitted at most 4 times, 2 for `EMAIL-2`.
When the TNC is not connected the message is kept and its first attempt waits for the radio. Answered with an `error` that names the reason when the addressee or the text is refused.

| field | type | | description |
|---|---|---|---|
| `to` | string |  | (max 64 chars, min 1 chars) |
| `text` | string |  | (max 512 chars) |

### `message_retry`

Sends a message of ours that failed, is unconfirmed, was rejected or was cancelled again, from the first attempt of the schedule. Answered by the new state of its row, or by an `error` (no such message, or it is
not in a state that can be sent again).

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | (>= 1) |

### `message_cancel`

Stops sending a message of ours that is still being sent; its row becomes `cancelled`. Answered by the new state of its row, or by an `error`.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | (>= 1) |

### `message_delete`

Removes a message of any kind (one of ours, one sent to us, one we only overheard) from the database, from the daemon and from every page: its row is a `del` of the topic `messages`. A message that is
still being sent is cancelled first, so that no attempt is made while it goes. Answered by the `del`, or by an `error` (no such message).

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | (>= 1) |

### `conversation_delete`

Removes the whole conversation with a station: every message we sent to it and every one it sent to us (not the messages it was only overheard sending to others), from the database in one write, from
the daemon and from every page: each message's row is a `del` of the topic `messages`. A message that is still being sent is cancelled first. The path and the timeout of the station stay. Answered by the
`del`s, or by an `error` (the call is none, or there is no message with that station).

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |

### `overheard_delete`

Removes every message we only overheard `from_call` sending to `to_call` (the state `overheard`, that sender, that addressee: one pair of the Messages list's overheard rows) from the database in one write,
from the daemon and from every page: each message's row is a `del` of the topic `messages`. The conversations are not touched: a message we sent or one sent to us is never removed by this. Answered by the
`del`s, or by an `error` (no overheard message of that pair).

| field | type | | description |
|---|---|---|---|
| `from_call` | string |  | (max 64 chars, min 1 chars) |
| `to_call` | string |  | (max 64 chars, min 1 chars) |

### `set_station_path`

Gives a station a path of its own: the digipeaters that a message to it, and the ack of a message from it, go by way of. `path` is up to 8 digipeater calls separated by commas, checked as the setting
`beacon/path` is; an empty `path` is a valid path of its own, direct with no digipeaters at all, which is not the same as none set. Answered by the `set` of the station's entry in the topic `station_prefs`
(its `hide_after_min` is whatever it was), or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `path` | string |  | (max 256 chars) |

### `clear_station_path`

Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path`
(or the `del` of the entry when it had no timeout either), or by an `error`.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |

### `set_station_timeout`

Gives a station a timeout of its own: how long after its last position it stays on the map, in minutes; 0 is never. The page hides a station whose last position is older than that (a station
without one of its own uses the setting `map/hide_after_min`), and the daily prune does not remove a station with a timeout of 0 from the station book. `call` is a station's call as it is in the
topic `stations` (the name of an object or an item too). Answered by the `set` of the station's entry in the topic `station_prefs` (its `path` is whatever it was), or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `minutes` | integer |  | (>= 0, <= 10080) |

### `clear_station_timeout`

Takes a station's own timeout away, so that it has the setting `map/hide_after_min` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null
`hide_after_min` (or the `del` of the entry when it had no path either), or by an `error`.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |

### `set_station_rf_only`

Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE`
already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set`
of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `on` | boolean |  |  |

### `weather_series`

Asks for the observations a weather station made in the last `hours` hours. Answered with a `weather_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a call with no
observations is answered with no points.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the `stations` topic has it (an object's name for a weather object) (max 64 chars, min 1 chars) |
| `hours` | integer |  | how far back to go: 24 for a day, 168 for a week (>= 1, <= 168) |

### `alert_test`

Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM`
is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page
that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`).

### `bulletin_delete`

Removes an entry from the message board, from the database and from every page: its row is a `del` of the topic `bulletins`. The same bulletin heard again afterwards is a new entry (heard once). Answered by
the `del`, or by an `error` (no such entry).

| field | type | | description |
|---|---|---|---|
| `sender` | string |  | the call that sent it, as the row has it (max 64 chars, min 1 chars) |
| `slot` | string |  | the addressee as the row has it: `BLN1`, `BLNA`, `BLN3HAMS`, `QST` (max 16 chars, min 1 chars) |

### `object_set`

Makes an object or an item of ours, or changes the one of that name (a changed object starts its schedule again, and is sent at once, never sooner than a minute after its last packet). `name` is 1 to 9
characters for an object and 3 to 9 for an item, printable ASCII without `!`, `_`, `|` and `~` and without a blank at either end, and not our own call or the call of a station; `lat` and `lon` the position in decimal
degrees; the symbol is a table character and a code character; `comment` at most 43 characters (36 with a course or speed); `course_deg` and `speed_kmh` the course and speed, each or both or none; `path` the digipeaters, calls
separated by commas (null: `beacon/path`). Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | (max 9 chars, min 1 chars) |
| `kind` | "object" \| "item" |  |  |
| `lat` | number |  | (>= -90, <= 90) |
| `lon` | number |  | (>= -180, <= 180) |
| `symbol_table` | string |  | (max 1 chars, min 1 chars) |
| `symbol_code` | string |  | (max 1 chars, min 1 chars) |
| `comment` | string |  | (max 43 chars) |
| `course_deg` | integer \| null |  | (>= 0, <= 359) |
| `speed_kmh` | number \| null |  | (>= 0, <= 1850) |
| `path` | string \| null |  | (max 256 chars) |

### `object_kill`

Kills an object or an item of ours: the killed form is sent three times (at once, after a minute and after three) and then it is forgotten, and it leaves the map now. One that was never sent is removed at
once. Answered by the `del` of its row in `stations` (and in `own_objects` once the kill is sent, or at once), or by an `error` (no such object of ours).

| field | type | | description |
|---|---|---|---|
| `name` | string |  | (max 9 chars, min 1 chars) |

### `bulletin_post`

Posts a bulletin, an announcement or a group bulletin of ours: `slot` is `BLN0`..`BLN9`, `BLNA`..`BLNZ` or `BLN`, a number and a group of up to five characters (`BLN3HAMS`), `text` at most 67 characters of
printable ASCII without `|`, `~` and `{`. It is sent at once and then on the schedule of the specification (a bulletin a few times early and every 20 minutes for 4 hours, an announcement every hour for 72 hours);
a text for a slot that holds one replaces it. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_bulletins`, or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `slot` | string |  | (max 9 chars, min 4 chars) |
| `text` | string |  | (max 512 chars, min 1 chars) |

### `bulletin_unpost`

Deletes a bulletin of ours: it is not sent again and leaves the board. Answered by the `del` of its row in `own_bulletins`, or by an `error` (no such bulletin of ours).

| field | type | | description |
|---|---|---|---|
| `slot` | string |  | (max 9 chars, min 4 chars) |

### `map_estimate`

Starts a dry run: how big the detailed map for `map/radius_km` and `map/maxzoom` round our position will be. Answered by the topic `map` (state `estimating`, then `estimate` filled in), or by an `error` when no job can start
(no position, or a job is running). The pmtiles program is fetched first when it is not there.

### `map_fetch`

Starts making the maps: the world map first when it is not there, then the detailed map for `map/radius_km` and `map/maxzoom` round our position, from `map/source` or the latest daily build. The progress is the topic
`map`. An `error` when no job can start (no position, or a job is running).

### `map_cancel`

Ends the running job; the files it was making are removed and the maps stay as they were. An `error` when no job is running.

## Server to client

10 messages, each a JSON object with `"type"`. The first is `hello`. Where a field is `X | null` it is always present, with null.

### `hello`

The first message of a connection; `status` and the `state` of every topic follow it at once, so a page need not ask for them.

| field | type | | description |
|---|---|---|---|
| `protocol` | integer |  | the version of these messages: a page built for another one says so and loads itself again |
| `version` | string |  | the version of the daemon: a page built for another one loads itself again, once for each version |
| `install` | InstallInfo |  | how this daemon was installed, for the steps of an update |
| `topics` | string[] |  | the topics the page is following from the start: all of them (a page may `unsubscribe` from one) |

### `status`

What the daemon is, for the status bar: sent after `hello`, every 10 s, when asked (`status`), and when a packet of ours has gone out (the count of packets and the beacon's times have changed). It also says what the daemon costs the machine: the CPU share, the resident memory and the uptime.

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the version of the daemon |
| `started_at` | time |  | when the daemon started |
| `packets` | integer |  | how many packets the database holds |
| `stations` | integer |  | how many stations the station book holds |
| `call` | string |  | our own call, from the settings; empty while none is set (nothing is transmitted then) |
| `lat` | number \| null |  | our own latitude, from the settings; null while none is set |
| `lon` | number \| null |  | our own longitude, from the settings; null while none is set |
| `beacon_interval_min` | integer |  | minutes between our position packets, from the settings; 0 is off |
| `beacon_last_sent` | time \| null |  | when the latest beacon was sent, by the timer or on request; null for none since the daemon started |
| `beacon_next_due` | time \| null |  | when the timer sends the next one; null while the interval is 0 |
| `station_status` | string |  | the text of the status report last sent in this run (services/rigstatus.py); empty until one has gone |
| `rig_state` | "off" \| "on" \| "unused" |  | whether the radio the status is made from answers: `on`, `off` (rigctld is away or the radio is off, nothing is sent), or `unused` while the status does not come from a radio (`status/source` is `text` or `off`) |
| `cpu_percent` | number |  | the daemon's CPU time (user and system) as a share of one core, in percent to a tenth, since the previous status that was at least a second before; the first counts from the start |
| `rss_mb` | number \| null |  | the daemon's resident memory in megabytes, to a tenth; null where the system does not say |
| `uptime_sec` | integer |  | seconds since the daemon started, by its clock |
| `update` | UpdateInfo \| null |  | the latest version while it is newer than this one, from the daily update check; null when there is none or the check has not been answered |

### `pong`

The answer to `ping`.

| field | type | | description |
|---|---|---|---|
| `now` | time |  | the daemon's clock |

### `error`

A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed.

| field | type | | description |
|---|---|---|---|
| `text` | string |  | what could not be done and why, in a sentence; for a setting it begins with the key |

### `ports`

The answer to `list_ports`.

| field | type | | description |
|---|---|---|---|
| `ports` | PortRow[] |  | the ports, in natural order (`COM2` before `COM10`), then the paired Bluetooth devices |
| `search` | boolean |  | whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list |

### `state`

A topic as it is now: its revision and its whole `value`, which replaces what the page had. Patches for the changes made meanwhile follow.

| field | type | | description |
|---|---|---|---|
| `topic` | string |  | (max 64 chars, min 1 chars) |
| `rev` | integer |  | how many changes the topic has had since the daemon started (>= 0, <= 2^53) |
| `value` | any |  |  |

### `patch`

What changed in a topic: apply the ops in order; the copy is then at `rev`. An op says what the item is, not what to add, so an op that is applied twice ends where it should. Changes are told
on a tick of 100 ms (the topic `tnc` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key.

| field | type | | description |
|---|---|---|---|
| `topic` | string |  | (max 64 chars, min 1 chars) |
| `rev` | integer |  | how many changes the topic has had since the daemon started (>= 0, <= 2^53) |
| `ops` | (SetOp \| DelOp \| ReplaceOp)[] |  |  |

### `weather_series`

The observations of one weather station, the answer to `weather_series`: one point for each weather packet heard, the oldest first (a packet that came by two digipeaters is two points).

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station asked about |
| `hours` | integer |  | the hours asked for: a page that asked twice (a day, then a week) tells the answers apart by it (>= 1, <= 168) |
| `points` | ([time, number \| null, number \| null, number \| null, number \| null, number \| null, number \| null])[] |  | [time, temp_c, pressure_hpa, wind_kmh, gust_kmh, rain_1h_mm, humidity] for each observation; a value the report did not have is null |

### `alert_result`

The answer to `alert_test`, when the command has ended or run out of its 20 s.

| field | type | | description |
|---|---|---|---|
| `ok` | boolean |  | the command ended with exit code 0 |
| `text` | string |  | `ran` when it worked; else why not: the exit code and the first line of stderr (`exit code 3: no display`), or that it could not start or was killed after 20 s |

### `update_result`

The answer to `update_check`: what the version page said, or why it said nothing.

| field | type | | description |
|---|---|---|---|
| `outcome` | "newer" \| "current" \| "no_answer" |  | `newer`: a newer version is out; `current`: this is the latest; `no_answer`: the page could not be reached or did not name a version |
| `version` | string |  | the latest version for `newer`, this version for `current`; empty for `no_answer` |
| `text` | string |  | for `no_answer` why, in a sentence; empty otherwise |

## Topics

The value of each topic (`state` carries it, a `replace` op brings a new one).

| topic | value | |
|---|---|---|
| `stations` | { [key: string]: StationRow } | the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del` |
| `packets` | { [key: string]: PacketRow } | the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest |
| `tnc` | TncState | the radio; told whole as it changes, at most four times a second |
| `config` | ConfigValues | the settings; told again after every save, though nothing differs: the settings form waits for it |
| `station_prefs` | { [key: string]: StationPref } | what the operator set for each station that has anything set, by call: its own path and its own timeout, each null where none is set, and whether it is RF only. `set_station_path`, `clear_station_path`, `set_station_timeout`, `clear_station_timeout` and `set_station_rf_only` each give a `set` of the entry, or a `del` when nothing is left in it |
| `messages` | { [key: string]: MessageRow } | every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own |
| `bulletins` | { [key: string]: BulletinRow } | the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del` |
| `own_objects` | { [key: string]: OwnObjectRow } | the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations` |
| `own_bulletins` | { [key: string]: OwnBulletinRow } | the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`) |
| `map` | MapState | the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps; told whole as it changes, at most four times a second |

## Objects

The objects the commands and the messages are made of.

### StationRow

One station of the station book: who it is, where it was heard and how often. An object or an item is a row of its own, named by the object. The rows are the values of the topic `stations`
(keyed by `call`): a station heard again is a `set` of its row, a station that is forgotten or pruned (or an object that was killed) a `del`. When our own position changes in the settings every
row has a new distance and bearing, and the topic is told whole again.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the call with its SSID, or the name of the object or item |
| `kind` | "station" \| "object" \| "item" |  |  |
| `reported_by` | string |  | who sent the report, for an object or an item; empty for a station |
| `symbol_table` | string |  | `/` (primary), `\` (alternate) or an overlay character 0-9, A-Z; empty until a position is heard |
| `symbol_code` | string |  | the character of the symbol in its table; empty until a position is heard |
| `symbol_name` | string |  | the name of the symbol ("Car", "Digipeater"), `unknown` for none |
| `lat` | number \| null |  | decimal degrees, south negative; null until a position is heard |
| `lon` | number \| null |  | decimal degrees, west negative; null until a position is heard |
| `altitude_m` | number \| null |  |  |
| `course_deg` | integer \| null |  |  |
| `speed_kmh` | number \| null |  |  |
| `first_heard` | time |  | UTC, ISO 8601 with a Z |
| `last_heard` | time |  | UTC, ISO 8601 with a Z |
| `last_position_at` | time \| null |  |  |
| `last_status` | string |  | the text of the latest status report |
| `last_comment` | string |  | the comment of the latest position |
| `packets` | integer |  | how many packets of this station were heard |
| `last_path` | string[] |  | the digipeaters of the latest packet, the one that repeated it marked with `*` |
| `last_route` | string |  | how the latest packet reached us: `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in) |
| `heard_direct` | integer |  | how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept) (>= 0) |
| `last_direct_at` | time \| null |  | when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`; null for a station never heard direct |
| `heard_gated` | integer |  | how many packets came as third-party packets: an iGate put what it heard on the internet on the air; counted, but never a route to send by (>= 0) |
| `heard_via` | [string, integer][] |  | [the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted |
| `best_route` | string |  | the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted |
| `suggested_path` | string \| null |  | the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned) |
| `weather` | WeatherValues \| null |  | the latest weather the station sent (a position with the weather symbol, or a positionless weather report); null for a station that sent none since the weather log began (or was made from the packets kept) |
| `weather_at` | time \| null |  | when `weather` was heard; null as it is |
| `telemetry` | TelemetryValues \| null |  | the latest telemetry report of the station, scaled and named by the definitions it sent (read again from the latest packets at the start); null for a station that sent none |
| `telemetry_at` | time \| null |  | when `telemetry` was heard; null as it is |
| `locator` | LocatorValues \| null |  | the Maidenhead locator of the station's latest status report (or Mic-E status text): where it says it is, to the square; null when it sent none |
| `extensions` | ExtensionValues \| null |  | the PHG, RNG, DF or area data of the station's latest position; null when it had none |
| `distance_km` | number \| null |  | from our position, null for us and for a station without a position |
| `bearing_deg` | number \| null |  | the direction from our position, degrees from north; null as the distance is |
| `is_me` | boolean |  | our own station: the row of the call in the settings, at the position in the settings |
| `own` | boolean |  | an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row |
| `track` | [time, number, number][] |  | the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed (max 50 items) |

### PacketRow

One packet heard or sent. The rows are the values of the topic `packets`, keyed by `id` as text: the daemon holds the latest 200, a packet that comes is a `set` and the one that falls out of the
200 a `del`. The page shows them newest first (the highest id).

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | counts up in the order the packets came in this run of the daemon; not kept in the database (>= 0) |
| `heard_at` | time |  | UTC, ISO 8601 with a Z |
| `direction` | "in" \| "out" |  | heard on the air, or sent by us |
| `source` | string |  | who sent the frame we heard; for a third-party packet the iGate (see `via`) |
| `destination` | string |  |  |
| `path` | string[] |  | the digipeaters, the one that repeated it marked with `*` |
| `kind` | "position" \| "message" \| "object" \| "item" \| "status" \| "other" \| "undecoded" |  | a telemetry report is `other`; its `decoded.type` is `telemetry` |
| `route` | string |  | how a packet that was heard reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours |
| `via` | string |  | the iGate, for a third-party packet: `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet |
| `summary` | string |  | one line, as the log has it |
| `tnc2` | string |  | the packet as a line of TNC2 monitor text |
| `decoded` | DecodedPosition \| DecodedMessage \| DecodedObject \| DecodedItem \| DecodedStatus \| DecodedTelemetry \| DecodedOther \| DecodedUndecoded |  |  |

### MessageRow

One message: one we sent or one that was sent to us. The rows are the values of the topic `messages`, keyed by `id` as text: the daemon holds every message (none leaves on its
own; a database with more than 10000 gives the latest 10000 at a start). A message that is new or changes (its state, its attempts) is a `set` of its row, one that is deleted (`message_delete`, `conversation_delete`) a `del`. The conversation a message belongs to is the other station: `from_call`
of a message that came in, `to_call` of one we sent.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | the number the database gave the message; it counts up and is kept across runs of the daemon (>= 1) |
| `at` | time |  | when the message was made (sent messages) or heard (received messages) |
| `direction` | "in" \| "out" |  | `in` was heard (sent to us, or overheard), `out` is one of ours |
| `from_call` | string |  | the sender: the packet's source for a message that came in, our call for one of ours |
| `to_call` | string |  | the addressee: our call for a message sent to us, the other station for one of ours, whoever it is for when overheard |
| `text` | string |  |  |
| `msg_id` | string \| null |  | the message id the acknowledgement quotes (1 to 5 letters or digits); null for a message that came in without one |
| `state` | "sending" \| "acked" \| "rejected" \| "failed" \| "unconfirmed" \| "cancelled" \| "received" \| "overheard" |  | `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; `received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for) |
| `attempts` | integer |  | how many times it has been transmitted (at most `attempts_max`: 0, 30, 60, 120, 240, 480, 960 ... seconds after the first, no wait longer than 960) (>= 0) |
| `attempts_max` | integer |  | how many attempts the message was given when it was sent: 4, 2 for the email gateway `EMAIL-2`, 1 for a bulletin (messages from before the count was fixed have their own, up to 10) (>= 1, <= 10) |
| `last_attempt_at` | time \| null |  | when it was transmitted last; null until the first attempt (the TNC may be away) |
| `acked_at` | time \| null |  | when the acknowledgement was heard |
| `attempts_detail` | AttemptRow[] |  | for a message of ours, each attempt made (`attempts` of them, the oldest first; fewer for a message sent before the delivery chain was kept, none until the first attempt) with the hops of its path that a copy of our own message was heard back with; a hop heard is a `set` of the message's row. Empty for a message that came in |
| `route` | string |  | how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept |

### DecodedPosition

A position report.

| field | type | | description |
|---|---|---|---|
| `lat` | number |  |  |
| `lon` | number |  |  |
| `symbol_table` | string |  |  |
| `symbol_code` | string |  |  |
| `comment` | string |  |  |
| `course_deg` | integer \| null |  |  |
| `speed_kmh` | number \| null |  |  |
| `altitude_m` | number \| null |  |  |
| `timestamp` | time \| null |  | the time the packet itself carries, when it has one |
| `messaging` | boolean |  | the station can receive messages |
| `compressed` | boolean |  |  |
| `ambiguity` | integer |  | how many digits of the position were blanked out, 0 to 4 |
| `weather` | DecodedWeather \| null |  | the weather a station with the weather symbol (`_`) sent after its position; the rest of the text is the `comment` |
| `extensions` | ExtensionValues \| null |  | the PHG, RNG, DFS, DF bearing or area data after the symbol of an uncompressed position; null when there was none |
| `timestamp_local` | boolean |  | the `timestamp` was sent in the sender's local time (`/`): it is the time as it was sent, not UTC |
| `locator` | LocatorValues \| null |  | the Maidenhead locator in the status text of a Mic-E packet; null for any other position |
| `type` | "position" |  |  |

### DecodedMessage

A text message; an ack has `ack_id` and no text, a reject `rej_id`.

| field | type | | description |
|---|---|---|---|
| `type` | "message" |  |  |
| `addressee` | string |  |  |
| `text` | string |  |  |
| `msg_id` | string \| null |  |  |
| `ack_id` | string \| null |  |  |
| `rej_id` | string \| null |  |  |

### DecodedObject

An object report: a thing (a storm, an event) that a station puts on the map.

| field | type | | description |
|---|---|---|---|
| `type` | "object" |  |  |
| `name` | string |  |  |
| `alive` | boolean |  | false when the report kills the object |
| `position` | PositionFields |  |  |
| `timestamp` | time \| null |  |  |

### DecodedItem

An item report: like an object, without a time.

| field | type | | description |
|---|---|---|---|
| `type` | "item" |  |  |
| `name` | string |  |  |
| `alive` | boolean |  |  |
| `position` | PositionFields |  |  |

### DecodedStatus

A status report.

| field | type | | description |
|---|---|---|---|
| `type` | "status" |  |  |
| `text` | string |  | the status text; after the locator when there is one |
| `timestamp` | time \| null |  |  |
| `locator` | LocatorValues \| null |  | a Maidenhead locator with a symbol at the start of the report (a report that has one has no timestamp) |

### DecodedTelemetry

A telemetry report (`T#005,199,000,255,073,123,01101001`). The definitions of the channels are messages of the station, applied by the daemon: see `telemetry` of the station.

| field | type | | description |
|---|---|---|---|
| `type` | "telemetry" |  |  |
| `sequence` | integer \| null |  | the sequence number; null for the `MIC` of a Mic-E unit |
| `analog` | number[] |  | the five analog values as sent (0 to 255) |
| `bits` | string |  | the eight digital values as a text of 0 and 1 |
| `comment` | string |  |  |

### DecodedOther

A data type that is recognised but not (fully) decoded: a positionless weather report is decoded (`weather`, `timestamp`), the station capabilities and an Agrelo DF report are read into `items`.

| field | type | | description |
|---|---|---|---|
| `type` | "other" |  |  |
| `kind` | string |  | a short word: weather, nmea, query, test, capabilities, agrelo-df, shelter, space-weather, third-party, user-defined, telemetry (one that is not a report), ... |
| `text` | string |  | the whole information field |
| `weather` | DecodedWeather \| null |  | the observation of a positionless weather report (`_`); null for anything else |
| `items` | { [key: string]: string } \| null |  | `capabilities`: the items of the list by token (`IGATE`, `MSG_CNT`...), the value empty for a token alone; `agrelo-df`: `bearing` and `quality`; null for anything else |
| `timestamp` | time \| null |  | the time of a positionless weather report (its MMDDhhmm, resolved to the latest such time that is not in the future) |

### DecodedUndecoded

A field that should have decoded and did not.

| field | type | | description |
|---|---|---|---|
| `type` | "undecoded" |  |  |
| `error` | string |  | why it did not |
| `text` | string |  | the information field as latin-1 |

### DecodedWeather

The weather fields of a weather station's position or of a positionless weather report, in metric units; null where the report did not have the field.

| field | type | | description |
|---|---|---|---|
| `wind_dir` | integer \| null |  | degrees the wind blows from |
| `wind_kmh` | number \| null |  |  |
| `gust_kmh` | number \| null |  |  |
| `temp_c` | number \| null |  |  |
| `humidity` | integer \| null |  | per cent, 1 to 100 |
| `pressure_hpa` | number \| null |  |  |
| `rain_1h_mm` | number \| null |  |  |
| `rain_24h_mm` | number \| null |  |  |
| `rain_today_mm` | number \| null |  | since midnight |
| `luminosity` | integer \| null |  | W/m2 |
| `snow_mm` | number \| null |  | in the last 24 hours |
| `rain_counter` | integer \| null |  | the raw rain counter, as the station counts it |
| `raw` | string |  | the weather fields as they were sent |

### PositionFields

A position as the parser made it: decimal degrees, south and west negative, speed in km/h, altitude in metres.

| field | type | | description |
|---|---|---|---|
| `lat` | number |  |  |
| `lon` | number |  |  |
| `symbol_table` | string |  |  |
| `symbol_code` | string |  |  |
| `comment` | string |  |  |
| `course_deg` | integer \| null |  |  |
| `speed_kmh` | number \| null |  |  |
| `altitude_m` | number \| null |  |  |
| `timestamp` | time \| null |  | the time the packet itself carries, when it has one |
| `messaging` | boolean |  | the station can receive messages |
| `compressed` | boolean |  |  |
| `ambiguity` | integer |  | how many digits of the position were blanked out, 0 to 4 |
| `weather` | DecodedWeather \| null |  | the weather a station with the weather symbol (`_`) sent after its position; the rest of the text is the `comment` |
| `extensions` | ExtensionValues \| null |  | the PHG, RNG, DFS, DF bearing or area data after the symbol of an uncompressed position; null when there was none |
| `timestamp_local` | boolean |  | the `timestamp` was sent in the sender's local time (`/`): it is the time as it was sent, not UTC |
| `locator` | LocatorValues \| null |  | the Maidenhead locator in the status text of a Mic-E packet; null for any other position |

### TncState

The TNC, the one feed of packets: its state and why it is not connected, the port, and the latest lines of what it saw and did. The value of the topic `tnc`.

| field | type | | description |
|---|---|---|---|
| `state` | "stopped" \| "connecting" \| "connected" \| "waiting" \| "silent" |  | `waiting` is between two attempts to open the line; `problem` says why. `silent`: the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer); nothing is sent until it does |
| `problem` | string |  | why it is not (yet) connected or not sending KISS; empty when all is well |
| `last_error` | string |  | the latest reason for waiting |
| `path` | string |  | the serial port in use; empty while none is open |
| `baud` | integer |  |  |
| `describe` | string |  | one line for the status bar: the port, the speed and what the TNC does; while `silent` it says since when, in UTC |
| `silent_since` | time \| null |  | while `state` is `silent`, when the latest byte came; null otherwise |
| `stats` | TncStats |  |  |
| `last_watchdog_action` | "" \| "check" \| "probe" \| "reopen" |  | what the watchdog did last: `check` (the radio asked whether it is there, after a quiet period), `probe` (the same, while the radio is silent) or `reopen` (the port closed and opened again); empty if it has done nothing since the daemon started |
| `last_watchdog_at` | time \| null |  | when the watchdog did that; null if it has done nothing since the daemon started |
| `lines` | string[] |  | the latest 100 lines of what the TNC saw (TNC2 text and what it understood of it) and did (`NeoAPRS: ...`), oldest first, each begins with the time HH:MM:SS (max 100 items) |

### TncStats

What the TNC has counted since the daemon started.

| field | type | | description |
|---|---|---|---|
| `opens` | integer |  | times the line was opened |
| `bytes_in` | integer |  |  |
| `bytes_out` | integer |  |  |
| `frames_in` | integer |  | frames received, including the ones that could not be read as a packet |
| `packets` | integer |  | packets handed on |
| `rejected` | integer |  | frames that could not be read as a packet |
| `last_packet` | time \| null |  | when the latest packet was heard; null for none yet |
| `keepalive_checks` | integer |  | times the keep-alive checked that the radio is there (after `tnc/check_sec` of nothing heard) (>= 0) |
| `watchdog_probes` | integer |  | times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds) (>= 0) |
| `port_reopens` | integer |  | times the port was closed and opened again (every 5th probe of a silent radio) (>= 0) |
| `digipeated` | integer |  | frames the digipeater (`digi/enabled`) sent again for other stations (>= 0) |

### ConfigValues

The settings: each key of the settings table (`station/call`, `serial/baud`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic
`config`, told again after every save, though nothing differs.

| field | type | | description |
|---|---|---|---|
| `values` | { [key: string]: string } |  | the settings in force, key to text; every key is there |
| `defaults` | { [key: string]: string } |  | the same keys with their defaults, for a form's reset |
| `urls` | string[] |  | where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off |

### SetOp

The item at `key` is `value` (the whole item, new or changed).

| field | type | | description |
|---|---|---|---|
| `op` | "set" |  |  |
| `key` | string |  | the key of an item of a keyed topic: a station's call, a packet's id as text (max 256 chars) |
| `value` | any |  |  |

### DelOp

The item at `key` is gone.

| field | type | | description |
|---|---|---|---|
| `op` | "del" |  |  |
| `key` | string |  | the key of an item of a keyed topic: a station's call, a packet's id as text (max 256 chars) |

### ReplaceOp

The whole value of the topic is `value`.

| field | type | | description |
|---|---|---|---|
| `op` | "replace" |  |  |
| `value` | any |  |  |

### AreaValues

An area object (the symbol `\l`): its shape and colour, and how far down and to the right of the object's position it reaches.

| field | type | | description |
|---|---|---|---|
| `shape` | string |  | open circle, line, open ellipse, open triangle, open box, filled circle, coloured line, filled ellipse, filled triangle or filled box |
| `colour` | string |  |  |
| `lat_offset_deg` | number |  |  |
| `lon_offset_deg` | number |  |  |

### AttemptRow

One transmission of a message of ours and what came back of it.

| field | type | | description |
|---|---|---|---|
| `sent_at` | time |  | UTC, ISO 8601 with a Z |
| `hops` | HopRow[] |  | the digipeaters of the path the attempt went by, in order; empty for a direct path |
| `internet` | string \| null |  | the call of the iGate that put a copy of the message back on the air as a third-party packet, when one was heard for this attempt; null otherwise |
| `acked` | boolean |  | the acknowledgement was heard after this attempt and before the next one: the attempt the ack answers |

### BulletinRow

One bulletin, announcement, group bulletin or group message on the board: what a station sent to `BLN0`..`BLN9`, `BLNA`..`BLNZ`, `BLN3HAMS` (a number or letter and a group of up to five characters) or `ALL`, `CQ`
or `QST`. None of them is a conversation and none is acked. The rows are the values of the topic `bulletins`, keyed by `sender/slot` (`OH2XYZ/BLN1`): the board holds one row for each sender and slot, a sender
sending the slot again replaces the text. A bulletin that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del`. Nothing ages out: an
entry stays on the board until it is deleted.

| field | type | | description |
|---|---|---|---|
| `sender` | string |  | the call that sent it (for a third-party packet the call inside it) |
| `slot` | string |  | the addressee in capitals: `BLN1`, `BLNA`, `BLN3HAMS`, `QST` |
| `group` | string |  | the group of a group bulletin (`HAMS` of `BLN3HAMS`); empty for any other |
| `kind` | "announcement" \| "bulletin" \| "group" \| "nws" |  | `announcement` is `BLNA`..`BLNZ`, `bulletin` is `BLN0`..`BLN9`, `group` is a group bulletin or a message to `ALL`, `CQ` or `QST`, `nws` is a weather service bulletin (`NWS-xxxxx`, `SKY...`, `CWA...`) |
| `text` | string |  |  |
| `first_heard` | time |  | when this text was first heard; a sender that changes the text starts again |
| `last_heard` | time |  | when it was last heard |
| `times_heard` | integer |  | how often this text was heard (the copies of one transmission that came by different digipeaters within 10 seconds are one) (>= 1) |

### DfBearingValues

The bearing and quality of a DF report (`/270/729` after the course and speed).

| field | type | | description |
|---|---|---|---|
| `bearing_deg` | integer |  |  |
| `hits` | integer |  | 0 nothing, 1 to 8 the share of the possible samples that hit, 9 a manual report |
| `range_km` | number |  | the length the line is drawn to |
| `quality` | integer |  | (>= 0, <= 9) |

### DfsValues

The strength of a signal heard by a direction finder (`DFS2360`) with the height, gain and directivity of its antenna.

| field | type | | description |
|---|---|---|---|
| `strength` | integer |  | 0 to 9; 0 is where the signal is not heard (>= 0, <= 9) |
| `height_m` | number |  |  |
| `gain_db` | integer |  |  |
| `direction_deg` | integer \| null |  |  |

### ExtensionValues

The data extensions after the symbol of an uncompressed position (taken off the comment); null for what the position did not have.

| field | type | | description |
|---|---|---|---|
| `phg` | PhgValues \| null |  |  |
| `range_km` | number \| null |  | a pre-calculated radio range (`RNG0050`) |
| `dfs` | DfsValues \| null |  |  |
| `df_bearing` | DfBearingValues \| null |  |  |
| `area` | AreaValues \| null |  |  |

### HopRow

One digipeater of the path an attempt went by, and whether a copy of our own message was heard back with that hop used.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the digipeater as the path named it (`OH2RCH-2`, or an alias such as `WIDE1-1`); once heard, the call that did it, which replaces an alias |
| `heard` | boolean |  | a copy was heard by radio with this hop's has-been-repeated bit set (or a later hop's: a hop works the first unused address) |
| `heard_at` | time \| null |  | when the first copy that showed the hop was heard (by radio if there was one, else over the internet); null when it was not heard |
| `by_internet` | boolean |  | a copy gated back by an iGate as a third-party packet showed the hop used; with `heard` false the hop is known only that way |

### InstallInfo

How this copy of the daemon was installed, which is what the steps of an update depend on (neoaprs/versions.py, neoaprs/cli/installkind.py).

| field | type | | description |
|---|---|---|---|
| `kind` | "windows-installer" \| "appimage" \| "deb" \| "uv-tool" \| "pip" \| "source" |  | `windows-installer` (the frozen program of the installer), `appimage`, `deb` (the Debian package, in /opt/neoaprs), `uv-tool` (the install script, or `uv tool install`), `pip` (a plain environment) or `source` (a clone of the repository) |
| `appimage` | string |  | the AppImage file this runs from; empty for the other kinds |
| `service` | boolean |  | whether a service starts it: the systemd unit, the launchd agent or the Windows Run key |
| `arch` | string |  | the architecture of the package it was installed from, `amd64` or `arm64`; empty for the other kinds, and for a machine that has no package |

### LocatorValues

A Maidenhead locator (grid square) with the symbol that came with it, in a status report or in the status text of a Mic-E packet; the position is the centre of the square.

| field | type | | description |
|---|---|---|---|
| `grid` | string |  | 4 or 6 characters, `IO91sx` |
| `lat` | number |  |  |
| `lon` | number |  |  |
| `symbol_table` | string |  |  |
| `symbol_code` | string |  |  |

### MapFileInfo

A map file in the data folder.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | `basemap.pmtiles` (the detailed map) or `basemap-world.pmtiles` (the world to zoom 5) |
| `bytes` | integer |  | (>= 0) |
| `modified` | time |  | when the file was made |
| `bbox` | number[] \| null |  | the area it covers, [west, south, east, north] in degrees, as its header says; null for a file whose header cannot be read (max 4 items) |
| `min_zoom` | integer \| null |  |  |
| `max_zoom` | integer \| null |  | the deepest zoom it has tiles for; the page draws a deeper one from these |
| `build` | string |  | the day (`20261022`) of the Protomaps build it was cut from; empty if not known (a file made by hand) |

### MapSizeEstimate

What a dry run said: how big the detailed map will be for the area and the zoom it was made for.

| field | type | | description |
|---|---|---|---|
| `bytes` | integer |  | the tiles it will hold (>= 0) |
| `tiles` | integer |  | (>= 0) |
| `radius_km` | integer |  | the radius it was estimated for; it is stale when `map/radius_km` is another number now |
| `maxzoom` | integer |  | the zoom it was estimated for |
| `box` | number[] |  | the area, [west, south, east, north] (max 4 items) |
| `build` | string |  | the day of the build it was estimated from; empty for a source that is not a daily build |

### MapState

The base map: the files, the area and detail the settings ask for, the size estimated, and the job that is running. The value of the topic `map`, told whole at most four times a second.

| field | type | | description |
|---|---|---|---|
| `state` | "none" \| "estimating" \| "downloading" \| "ready" \| "error" |  | `none`: there is no detailed map. `ready`: there is one. `estimating` and `downloading`: a job is running (`step` and `percent` say how far). `error`: the last job failed and `problem` says why; the map files are as they were |
| `step` | "" \| "tool" \| "build" \| "world" \| "area" |  | what the running job is doing: fetching the pmtiles program (`tool`), looking for the latest build (`build`), making the world map (`world`) or the detailed map (`area`); empty while no job runs |
| `percent` | integer \| null |  | how far the step is; null when it cannot say (the program and the build have no bar) (>= 0, <= 100) |
| `downloaded` | integer \| null |  | the size so far of the file the step is making, in bytes (it grows while the download moves); null when no file is being made yet (>= 0) |
| `note` | string |  | what the job says of a download that has not moved for a while: `no progress: trying again (2 of 3)`; empty when all is well |
| `blocked` | string |  | why no job can be started now (no position, or a job is running); empty when one can |
| `problem` | string |  | why the last job failed; empty if it did not, and while a job runs |
| `estimate` | MapSizeEstimate \| null |  | the latest dry run (`map_estimate`); null before one, and after a download |
| `radius_km` | integer |  | `map/radius_km` |
| `maxzoom` | integer |  | `map/maxzoom` |
| `box` | number[] \| null |  | the area those settings make round our position, [west, south, east, north]; null without a position (max 4 items) |
| `detail` | MapFileInfo \| null |  | `basemap.pmtiles`; null if it is not there |
| `world` | MapFileInfo \| null |  | `basemap-world.pmtiles`; null if it is not there |

### OwnBulletinRow

One bulletin, announcement or group bulletin of ours: its text and where its schedule stands. The rows are the values of the topic `own_bulletins`, keyed by `slot` (`BLN1`): a bulletin that is posted, and
each time it is sent, is a `set` of its row, one that is deleted (`bulletin_unpost`) a `del`. One whose schedule is over stays, with a null `next_at`, until it is deleted or posted again.

| field | type | | description |
|---|---|---|---|
| `slot` | string |  | the addressee: `BLN1`, `BLNA`, `BLN3HAMS` |
| `group` | string |  | the group of a group bulletin (`HAMS`); empty for any other |
| `kind` | "bulletin" \| "announcement" \| "group" |  |  |
| `text` | string |  |  |
| `posted_at` | time |  | when the text was posted |
| `sent` | integer |  | how often it was sent (>= 0) |
| `last_sent_at` | time \| null |  | when it was last sent; null while it has not been sent |
| `next_at` | time \| null |  | when it is sent next; null when its schedule is over (a bulletin: now, after 2 and 6 minutes, then every 20 minutes until 4 hours after the first; an announcement: the same early, then every hour until 72 hours after the first) |

### OwnObjectRow

One object or item of ours: what we send and where its schedule stands. The rows are the values of the topic `own_objects`, keyed by `name`: an object that is made or changed, and each time it is sent,
is a `set` of its row, one that is gone (the kill was sent three times, or another station took the name over) a `del`. A live object is also a row of the topic `stations` with `own` true, which is what the
map shows; a killed one leaves that topic at once and stays here, as `killing`, until its kill has been sent.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | the name of the object (1 to 9 characters) or of the item (3 to 9), as it is sent: case-sensitive |
| `kind` | "object" \| "item" |  |  |
| `lat` | number |  |  |
| `lon` | number |  |  |
| `symbol_table` | string |  | `/` (primary), `\` (alternate) or an overlay character 0-9, A-Z |
| `symbol_code` | string |  |  |
| `comment` | string |  | at most 43 characters, 36 when it follows a course and speed |
| `course_deg` | integer \| null |  | the course in degrees from north (0 to 359); null for none |
| `speed_kmh` | number \| null |  | the speed in km/h; null for none |
| `path` | string \| null |  | the digipeaters it goes by, calls separated by commas; null: the path of the setting `beacon/path` is used |
| `state` | "live" \| "killing" |  | `live`: it is being sent on the decay schedule; `killing`: it was killed and its killed form is being sent (three times), then it is forgotten |
| `created_at` | time |  | when it was first made |
| `updated_at` | time |  | when it was last changed or killed |
| `sent` | integer |  | how often it was sent since it was last changed or killed (>= 0) |
| `last_sent_at` | time \| null |  | when it was last sent; null while it has not been sent (the call is not set, or the radio is away) |
| `next_at` | time \| null |  | when it is sent next: 1, 2, 4 ... minutes after the last packet, never more than the net cycle time of its path apart; a time that has passed means it waits for the radio or for the call |

### PhgValues

A station's power, antenna height above average terrain, antenna gain and directivity (`PHG5132`), and the radio range that the formula of the APRS specification gives them.

| field | type | | description |
|---|---|---|---|
| `power_w` | integer |  |  |
| `height_m` | number |  |  |
| `gain_db` | integer |  |  |
| `direction_deg` | integer \| null |  | the direction of the best gain, degrees from north; null for an omni antenna |
| `range_km` | number |  |  |

### PortRow

A serial port the system lists, or a Bluetooth device paired with it (Linux). Nothing was opened or connected to find it.

| field | type | | description |
|---|---|---|---|
| `device` | string |  | the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`, `bt://AA:BB:CC:DD:EE:FF` for a paired Bluetooth device |
| `description` | string |  | what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say |
| `hwid` | string |  | the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say |
| `vid` | integer \| null |  | the USB vendor id of an adapter; null for a port that is not USB |
| `pid` | integer \| null |  | the USB product id of an adapter; null for a port that is not USB |

### StationPref

What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path and no timeout of its
own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`.

| field | type | | description |
|---|---|---|---|
| `path` | string \| null |  | the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); null if none is set, and the setting `beacon/path` counts |
| `hide_after_min` | integer \| null |  | the minutes after the station's last position that it leaves the map (the page does the hiding); 0 is never; null if none is set, and the setting `map/hide_after_min` counts (>= 0, <= 10080) |
| `rf_only` | boolean |  | true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet |

### TelemetryBit

One digital channel of a station's latest telemetry report.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | from the station's `PARM.` message, else `B1` to `B8` |
| `on` | boolean |  | the bit has the sense that its `BITS.` message gives (1 when there is none) |

### TelemetryChannel

One analog channel of a station's latest telemetry report.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | from the station's `PARM.` message, else `A1` to `A5` |
| `unit` | string |  | from its `UNIT.` message; empty when it sent none |
| `raw` | number |  | the value as it was sent (0 to 255) |
| `value` | number |  | `a*raw^2 + b*raw + c` with the coefficients of its `EQNS.` message; the raw value when it sent none |

### TelemetryValues

A station's latest telemetry report with the definitions the station sent as messages (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`) applied.

| field | type | | description |
|---|---|---|---|
| `sequence` | integer \| null |  | the sequence number; null for the `MIC` of a Mic-E unit |
| `channels` | TelemetryChannel[] |  | the five analog channels |
| `bits` | TelemetryBit[] |  | the eight digital channels |
| `project` | string |  | the project title of the `BITS.` message; empty when there is none |
| `comment` | string |  |  |

### UpdateInfo

A newer version than the daemon's, as the version page named it (services/updatecheck.py).

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the latest version |
| `url` | string |  | where to get it: an https address, or empty |
| `message` | string |  | a short note from the project, at most 200 characters; empty for none |

### WeatherValues

One weather observation in metric units; each field is null where the report did not have it.

| field | type | | description |
|---|---|---|---|
| `wind_dir` | integer \| null |  | the direction the wind blows from, degrees from north (0 to 360) |
| `wind_kmh` | number \| null |  | the sustained wind, km/h |
| `gust_kmh` | number \| null |  | the gust, km/h |
| `temp_c` | number \| null |  | degrees Celsius |
| `humidity` | integer \| null |  | per cent (1 to 100) |
| `pressure_hpa` | number \| null |  | barometric pressure, hPa |
| `rain_1h_mm` | number \| null |  | rain in the last hour, mm |
| `rain_24h_mm` | number \| null |  | rain in the last 24 hours, mm |
| `rain_today_mm` | number \| null |  | rain since midnight, mm |
| `luminosity` | integer \| null |  | W/m2 |
| `snow_mm` | number \| null |  | snow in the last 24 hours, mm |
