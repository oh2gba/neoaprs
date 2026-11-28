# The protocol between the daemon and the page

*This file is generated from the models in `neoaprs/web/protocol.py` and the `neoaprs/web/*wire.py` modules by `scripts/gen-protocol.py`: change the models (their docstrings and field descriptions are the
text below) or the prose in the script, not this file. `tests/test_protocol.py` fails when it is out of date.*

One WebSocket per browser tab at `ws://host:7303/ws`. JSON text frames both ways, and binary frames to the page for the waterfall (*Binary frames*). Every time is UTC ISO 8601 with a `Z`. A station is referred to by its call and a packet by its id, never by
a position in a list.

The conversation: the page opens the socket and is sent `hello` (the version of this protocol, the version of the daemon, how it was installed, the topics), then the **state** of every topic (`state`: its revision
and its whole value), and `status`. From then on it is sent what changes (`patch`). Everything else is a **command** from the page (`ping`, `set_config`, `forget_station`, ...), answered by
the change it makes in a topic, or by `pong`, `status` or `error`. All the state of the daemon that the page shows is small, so a page follows every topic from the start; it may stop following one
(`unsubscribe`) and ask for it again (`subscribe`, which is answered with `state`).

```
page                                     daemon
  |  <-------------------------------------  hello {protocol, version, install, topics}
  |  <-------------------------------------  state {topic, rev, value}          (one for each topic, all of them listed under Topics below)
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

The files: `/` and what is under it come from `page/` (`scripts/build-page` makes it; while there is none, a line says so), as it was when the daemon started (the daemon reads it into memory once, so a page rebuilt on disk is served after the next start, and the `page` of `hello` is the build it serves), `/basemap.pmtiles` and `/basemap-world.pmtiles` are the files of those names in the data folder
(the detailed map and the world under it), served with byte ranges (a `404` with a line of text while one is not there: the `map_fetch` command makes them), `/ws` is the socket. Nothing whose name begins with a dot is served, and no source map. Every answer
carries the security headers: a Content-Security-Policy that allows the page's own scripts, workers, styles and its own socket and nothing else, `X-Frame-Options: DENY`, `Referrer-Policy:
no-referrer`, `X-Content-Type-Options: nosniff` and `Cross-Origin-Resource-Policy: same-origin`. An error is a line of text. The shell `index.html` is sent `Cache-Control: no-cache`, the hashed
files of `assets/` `public, max-age=31536000, immutable`.

`POST /support/bundle` with `{"page": {...}}` (at most 256 KB; what the page tells of itself) answers with the support bundle, one zip (`application/zip`, as a download named `neoaprs-support-CALL-YYYYmmdd-HHMMSSZ.zip`): the logs, the
settings with the access key left out, the state of the running parts, the doctor's checks, the database's, the latest packets and what the page reported (`page_error`). It is behind the same login as the socket (`401` without the
session, `403` for a Host name that is not ours or an `Origin` that is not the `Host`), one at a time (`429` while another is being made, with `Retry-After`) and `400` for a body that is not a JSON object with a `page` object.

`POST /support/send` with `{"page": {...}, "note": "...", "file": ..., "email": "..."}` (at most 256 KB; the note is text of at most 2000 characters, optional with a file) is Send feedback / logs: the daemon makes the same bundle and posts it with the note, the address for a reply, the call, the version and the platform to the project's server. `email` is optional: an address of at most 254 characters with one `@` and something on each side of it, and no blank or control character (`reply_addresses` of the vectors); one that is not, or none, goes as empty, and the report is sent all the same. It is not written into the bundle or the log. `file` says which file goes: left out or `true`, a bundle made now; the name of the bundle the page just downloaded from `/support/bundle`, that very file (the daemon keeps the latest one for an hour; a new one is made when it is gone); `false`, none, and the note, which must then have words, goes alone. It answers `200` with `{"ok": true, "ref": "NEO-YYYYmmdd-HHMM-XXXX"}`, the reference the person can quote, or `{"ok": false, "reason": CODE}` with `offline` (the server could not be reached), `rate` (too many from this connection in the last hour), `too_large` or `refused`. It is behind the same login and gates as `/support/bundle`, shares its one-at-a-time (`429`) and answers `400` for a body that is not as described (a `file` that is neither, and no file with no words, too).

At most 256 connections are open at once (32 from one address that is not the loopback). A message from the page is at most 64 KiB (a bigger one closes the socket with 1009). A page whose socket
holds more than 4 MiB it has not read is sent no patches and is sent the topic whole when it has read down; one that holds 32 MiB is cut off. The socket is compressed when the browser offers
`permessage-deflate`.

## Following the state of the daemon

The state of the daemon that a page shows and that changes is held in named *topics* (`neoaprs/web/hub.py`; what changes each is in the table of `neoaprs/web/topics.py`). The value of each topic is in *Topics*
below; its type is the one in `TopicValues` of `neoaprs/web/protocol.py`. There are two kinds: a topic of **one whole value** (`config`, `map`, `update`, `gps`, `igate`, `qru`, `skeds`, `general`), which changes by `replace`, and a **table of items** by
key (`stations`, `station_prefs` and `station_keys` by call, `packets` and `messages` by id as text, `radios` by id as text, `bulletins` by `sender/slot`, `own_objects` by name, `own_bulletins` by slot), which changes by `set` and `del` of one item.

### `subscribe` and `unsubscribe`

All topics are followed from the start. `unsubscribe` stops following some (a topic that was not followed is ignored), `subscribe` follows them again and is answered with `state` for each (a
topic that is followed already is sent whole again: a page may ask at any time). A name that is no topic is refused with an `error` that names it; the others in the command are not affected.

### `state`

`state` is a topic as it is: its `rev` (the revision) and its whole `value`, which replaces what the page had. It is the first message of every topic, the answer to `subscribe`, and what a page is
sent when it was too slow to be sent patches and has read down its socket.

### `patch`

`patch` is what changed: `rev`, the revision the copy is at when the ops are applied in order, and the ops: `replace` (the whole value), `set` (the item at `key` is `value`) and `del` (the item
is gone). An op says what the item *is*, not what to add, so an op that is applied twice ends where it should. A change of the daemon is told on the hub's **tick** of 100 ms: what changed between
two ticks is one patch for a topic, with at most one op for each key, so a burst of 200 packets is one message. A radio's row in `radios` changes with every line its TNC sees and is told at most four times
a second. A page that sees a revision other than the one before plus one has missed something and asks again with `subscribe`.

Revisions count up in each topic and start again at 0 when the daemon starts. The packets of a topic `packets` are numbered by the daemon in the order they come in this run (`id`); the 200 the
daemon starts with are the latest the database holds. The messages of a topic `messages` are numbered by the database (`id`) and kept across runs; the daemon holds all of them
(a database with more than 10000 gives the latest 10000 at a start); none leaves on its own.

## Binary frames

A page that has asked for a radio's scope (`radio_scope`) is sent **binary frames**: one row of that radio's waterfall, at the modem's own resolution, for every 2 spectra
the modem makes (up to ten a second; about 310 bytes each). The socket's binary type on the page is `arraybuffer`. No other page is sent them, and a page whose socket holds a share of what it has not read is skipped.
Every frame names its radio (*Frames that name their radio*, below) and carries one of the two kinds that follow. A row is exactly 310 bytes:

| offset | size | field | meaning |
|---:|---:|---|---|
| 0 | 1 | kind | `1`: a row of the waterfall (a frame of another kind is to be ignored: more may come) |
| 1 | 1 | flags | bit 0 (`1`): the radio transmits and the row is of our own signal; the other bits are 0 |
| 2 | 1 | level | the RMS level of the audio in the passband, whole dBFS as a signed byte, -90 for silence (a full-scale sine reads -3) |
| 3 | 307 | bins | one unsigned byte for each bin of the passband 300 to 2700 Hz, the lowest first |

The bins are those of the modem's own spectrum (512 of 7.8125 Hz from 0 Hz at 8000 Hz): bin `i` of a row is the modem's bin `39 + i`, centred on `(39 + i) * 7.8125` Hz. A byte `b` is
`-110 + b * 0.5` dB on the modem's own scale (a tone of amplitude 1650 of 32768 reads 0 dB), the mean in power of the row's spectra; a value outside -110 to 17.5 dB is the nearest byte.
A row is wholly of reception or wholly of our own transmission. A row carries no time: it is of the moment it arrives. What a bin is over the noise (the floor) is found by the page from the rows, in one place
(`ui/src/lib/waterfallfloor.ts`); the daemon sends the modem's dB and keeps no floor for these frames.

The daemon makes the rows all the time and keeps those of the last 120 s (at most 1200). A page that asks for the scope is sent them first, in **one frame of the rows kept**, and then every row made after the newest of them, none twice and none
left out. A page that is behind when it asks is sent no rows kept, only the rows that follow once it has read. When the rows kept would lie (the modem stopped, ended or started anew, its control line or the link to its interface made
anew, the radio's type, sound card or keying changed), they are forgotten and every page that has the scope open is sent the frame with no row, which says to forget them too (a page that is behind, as soon as it has read).
A page that asks again on the same socket is sent the rows from the one before the newest it was sent on, while they are kept, and finds by those two where they go on from what it holds. The frame is the kind and the daemon's
clock, then each row, oldest first, 313 bytes each (a full one is about 375 KB):

| offset | size | field | meaning |
|---:|---:|---|---|
| 0 | 1 | kind | `2`: the rows kept |
| 1 | 8 | clock | the daemon's clock when the frame was made, milliseconds since 1970, a little-endian float64: the page places the times the daemon writes (a packet's `heard_at`) on its own clock by it |
| 9 + n * 313 | 1 | flags | of row `n`, as in a row |
| 10 + n * 313 | 1 | level | of row `n`, as in a row |
| 11 + n * 313 | 4 | age | how long ago row `n` was made when the frame was, whole milliseconds, little-endian, counted on a clock that counts the time the machine was asleep: the page places it by its own clock, whatever the daemon's says |
| 15 + n * 313 | 307 | bins | of row `n`, as in a row |

A page that does not know this kind lets it go, as it does any other, and has the rows from then on.

**Frames that name their radio.** Each frame of a radio's scope says whose rows it carries: a page may look at several radios at once, each with its own rows kept and its own hand-over as above. Such a frame is
the kind and the radio's id, then a frame of one of the two kinds above, whole (a row, or the rows kept, with its own kind byte):

| offset | size | field | meaning |
|---:|---:|---|---|
| 0 | 1 | kind | `3`: a frame of a radio's scope |
| 1 | 4 | radio | the radio's id, the `id` of its row in the topic `radios`, a little-endian unsigned 32-bit number |
| 5 | the rest | frame | a row (kind `1`) or the rows kept (kind `2`), byte for byte as above |

## Validation

Every frame the page sends is checked against the `Command` union before anything is done. The models are strict: a number is a number (not `"5"`), a flag is `true` or `false` (not `1`), a
field the model does not know is an error, text has a maximum length, `NaN` and `Infinity` are not JSON. A frame that does not fit is answered with an `error` whose `cmd` is the command, whose `code` is `invalid` and whose `text` is
"<command>: <field>: <what is wrong>", for example `forget_station: call: is missing`, and nothing at all is executed. A frame that is not JSON, or not an object, or names no known command is answered the same
way (`cmd` is empty; `code` is `not_json`, `not_object`, `no_command` or `unknown_command`). The values of `set_config` are checked by the settings (`neoaprs/config.py`), all before any is stored: the first that
is wrong is the answer, with `cmd` `set_config`, `key` the setting (`station/lat`), `code` what is wrong (`setting.range`), `params` its figures (`value`, `min`, `max`) and `text` `set_config: station/lat: 95 is
not between -90 and 90`.

A page goes by `cmd`, `key` and `code` and never reads `text`; `text` is the English sentence for the log, and a code the page has no sentence for is said with its plain words of a failure. The codes are stable words: `setting.*` for the values
of the settings (and `call.*`, `path.*` inside them), `message.*`, `object.*` and `bulletin.*` for what is posted or sent, `radio.*` for a radio and why it takes no frame now, `station.*`, `beacon.*`, `status.*`, `map.*` and `topic.*` for the rest of the commands,
and `failed` for a refusal the operator can do nothing about (a race, the database, a frame no page of this daemon sends). A refusal that passes another's on (`status.not_sent`, `beacon.not_sent`, `transmit.call`: nothing was
sent, and why) carries the code of that reason as `params.why`, with its values. No other message carries a sentence of the daemon's for the page to show: a reason or a state's why is a code of its model.

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

65 commands, each a JSON object with `"cmd"` as the first field. Types: `integer` and `number` are JSON numbers, `time` is UTC ISO 8601 with a `Z`.

### `ping`

Answered with `pong`.

### `status`

Answered with `status` at once (the daemon also sends one every 10 s).

### `update_check`

Asks the version page now, the question of the daily update check; the daily schedule is left as it was. Answered with `update_result` and then a `status` (with the newer version, if there is one) to the page that asked.

### `release_notes`

Asks what is new up to `version`: the newer one the update check found (what an update brings, from this version on), or this version itself (what the update the page's browser has seen brought: the notes of this
version, or with `since` of every version after that one). The changelog of the project at the tag of `version` (neoaprs/releasenotes.py), fetched once. Answered with `release_notes`.

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the newer version, as `status.update.version` names it, or this one, as `hello.version` names it; another is answered with no sections |
| `since` | string | optional | the sections of the versions newer than this one; empty: this version for the newer one, and for this one its own section alone (default `""`) |

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

### `forget_all_stations`

A fresh start for what was heard: removes every station and every packet heard (and the weather of the stations), in the daemon and in its database. The station we are, the objects and bulletins we send, the messages, the
settings and the maps stay, and so do the packets we sent. Answered by the stations' topic told whole, or by an `error`.

### `list_ports`

Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a
port of the machine: it is typed. With `radio`, also the sound cards its modem lists while that radio's type has a modem on a sound card (Mercury, Sound card), and the proposals leave out what the other radios and
the GPS receiver hold; each row says who holds it (`held_by`). An `error` for a `radio` that is none (`radio.unknown`).

| field | type | | description |
|---|---|---|---|
| `radio` | integer \| null | optional | the radio the list is for (its id): the sound cards and the proposals are its own; left out: the ports alone, with no sound card and no proposal (default `null`; >= 1) |

### `find_radio`

Find my radio: tries the serial ports and the paired Bluetooth devices that the search for the radio looks at (not a KISS TCP address), one after the other and each at the usual speeds, until a TNC answers in KISS or can be
put into KISS the way a TNC profile does. The radio's own line is closed while it runs and opened again after it. It writes nothing but a carriage return and, to a TNC that answers with text, the steps of the TNC profiles that
put it into KISS; nothing is sent to the air. Told to the page that asked with `radio_search` messages (`trying` before each try, then `found` or `cancelled`); the page puts the answer in the settings. An `error` when a search is running
(`radio.busy`), when there is no port to try (`radio.no_ports`), when none answered (`radio.not_found`), for a `radio` that is none (`radio.unknown`) and for one of a type that has no serial line (`radio.no_line`). Only that radio's line is
let go (radio 1's when `radio` is left out), the ports another radio or the GPS receiver holds are passed over, and the messages name it.

| field | type | | description |
|---|---|---|---|
| `radio` | integer \| null | optional | the radio the search is for (its id); left out: radio 1, the packet radio of before (default `null`; >= 1) |

### `find_radio_cancel`

Ends the search of `find_radio`; the page that asked is told `cancelled`. An `error` (`radio.not_running`) when none is running. One search runs at a time, so `radio` changes nothing: it is taken so that the page names the radio
in every command of its box.

| field | type | | description |
|---|---|---|---|
| `radio` | integer \| null | optional | the radio whose search is ended; left out: the one running (default `null`; >= 1) |

### `set_config`

Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is
left out keeps its value. The answer to a request that carries an `id` is `saved` with that `id`, once the settings are in force (the `config` topic is told again too, to every page), or an `error` that carries it; a request without an `id` is answered by the topic alone. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `station/*` move our own station on the
map. A radio's own setting is `radio/<id>/<key>` (a key of `radio_values`): it is checked by the field of its kind, stored with the rest in one write and restarts that radio
alone where its driver says so; a radio that is none or removed is refused with `radio.unknown` (a removed one with its `name` and `removed` 1), a key its kind has not with `radio.no_setting` (its `name` and id,
`radio`), `email/radio` changed to name no radio with `radio.unknown`, a device another radio holds or is set to, or the GPS receiver holds, with `radio.resource_held` (`resource`, `holder`, and the holder's
id `held_by`, 0 for the GPS receiver), and the last radio that is on switched off with `radio.last_enabled` (the radio's id, `radio`), each with the key. A key of a radio's setting that does not name the
radio (`serial/port`, `hf/enabled`) is refused with `setting.unknown`: the radio's own key is `radio/<id>/<key>`, its type and Enable are `radio_change`'s. A page of another device is refused with `setting.local_only` for `messages/alert_command`, `update/url`, `map/source` and `web/allowed_hosts`.

| field | type | | description |
|---|---|---|---|
| `values` | { [key: string]: string } |  | key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`) |
| `id` | integer \| null | optional | the page's own number for this request, which the answer (`saved`, or an `error`) carries back; left out, the page is answered by the topic `config` alone (default `null`; >= 0, <= 2147483648) |

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
| `locked` | boolean | optional | true encrypts the message with the key shared with the station (its `seal` is `open`): the text may be UTF-8, at most 34 bytes. Refused while the daemon was started without `--encryption` (`lock.off`), while the station has not announced its key (`lock.no_key`), and when the text is over 34 bytes (`lock.too_long`) (default `false`) |

### `send_key`

Sends our public key to a station as an ordinary message (`seal` `key`), so that it can encrypt to us; our key pair is made the first time it is needed. Nothing is ever announced by itself: a station that is to read our
locked messages gets our key this way, by hand, and we read its when it has sent its key the same way. Refused while the daemon was started without `--encryption` (`lock.off`). Answered as `send_message` is.

| field | type | | description |
|---|---|---|---|
| `to` | string |  | (max 64 chars, min 1 chars) |

### `forget_station_key`

Takes a station's key away (the topic `station_keys`): the first key a station announces is kept, and a later announcement of a different key is not taken until the old one is forgotten. Answered by the `del` of the
station's entry, or by an `error` (`lock.no_key` when there is none).

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |

### `message_key_new`

Makes a new key pair of ours in place of the old: the stations that have the old key must be sent the new one (`send_key`) before they can read us again. The fingerprint of the new key comes with the next
`status`. Answered by that `status`, or by an `error` when the key could not be kept.

### `query`

Asks a station a directed query (APRS 1.0.1 chapter 15): a message to it with the text of the query, `?APRSP` (`kind` `position`: its position packet), `?APRSS` (`status`: its status report), `?APRSD` (`heard`: the stations it
hears direct, as a message), `?APRST` (`trace`: the path our query reached it by, as a message), `?WX?` (`weather`: its weather report; a general query in the specification, which many stations do not answer
when it is addressed to them) or the operator's own (`custom`, with `text`: `?APRSH OH2GBA-15`, `?PING?`). The query is sent once, without a message id: no attempts follow and no ack is expected. It is kept as a row of the topic
`messages` to the station, in state `sending` until it has been transmitted and then `unconfirmed`, whose `text` is the query; the page shows such a row (an `out` message with no `msg_id` whose text begins with `?`) as a note of what was asked. The answer is whatever the
station sends: a packet (the station's card changes) or a message (a row `in`). Not more than one query of the same text to a station in 60 seconds. Answered with an `error` when the station is not in the station book
(`station.unknown`), is no station that takes messages (`query.not_capable`: an object, an item, ourselves, a station whose position says it takes none and that never sent a message), the same query was sent less than 60 seconds ago
(`query.too_soon`) or the message is refused as `send_message` refuses it (the call is not set, the radio is silent); a `custom` text that is no query is refused as invalid.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `kind` | "position" \| "status" \| "heard" \| "trace" \| "weather" \| "custom" |  |  |
| `text` | string \| null | optional | the query of `custom`, as the operator wrote it: after the spaces at its ends are taken off it begins with `?` and has something after it, is printable ASCII without `\|`, `~` or `{` and at most 67 characters, the text of a message; it is sent upper-cased. Absent or null for the other kinds (default `null`; max 512 chars) |

### `qru_ask`

Asks the stations near us for local info (repeaters, events, places): one message to the addressee `QRU` (the services/qruask.py of the daemon), whose `text` is `INFO` (which groups are served near
us?), `NEXT` (the next objects of the group asked for last) or a group of 1 to 8 upper-case letters and digits (`RP70`), with a distance in kilometres, 1 to 20000, after it (`INFO 250`). A request to QRU is a
broadcast: it is sent once, with no message id, is not kept as a message and is not sent again; it goes by `path` when one is given (digipeater calls or aliases separated by commas, checked as a radio's
path is, or `DIRECT` for none), else by the path of messages to the station QRU (its own path, else the radio's), with RFONLY after it unless `rf_only` is false: by radio only. With no `radio` it goes
once on each radio of Local info's Send on (the radios whose `radio/<id>/local_info` is ticked; with one radio that can send, that one) that takes
frames now; with `radio`, on that radio alone. The answers come as messages to us (they are rows of the topic `messages` like any message) and as the topic `qru`; the objects arrive as objects. All or
nothing: answered with an `error`, and nothing is sent on any radio, when the text is none, the station is RX only or no call is set (`transmit.off`, or the interlock's reason), there is no radio
(`radio.none`) or none takes frames now, a request to QRU went on one of its radios less than 60 seconds ago with the same text or any less than 10 seconds ago (`qru.too_soon`, with the `seconds` that
are left, the longest), or the path is no path or too long with RFONLY (`path.*`, `call.*`).

| field | type | | description |
|---|---|---|---|
| `text` | string |  | (max 32 chars, min 1 chars) |
| `path` | string \| null | optional | the path the request goes by; left out (or null, or empty) the path of messages to QRU (default `null`; max 256 chars) |
| `rf_only` | boolean | optional | RFONLY after the path; left out it is true. The page no longer sends it (the request always goes with RFONLY); a page of an older build may (default `true`) |
| `radio` | integer \| null | optional | the one radio the request goes on, its id: the radio a server answered on (`QruServer.radio`), for a request of a group it listed or one asked again; left out: the radios of Local info's Send on. Refused with `radio.unknown` for a radio that is none, `radio.off` for one that is off, `radio.receive_only` for one that only receives and `radio.not_connected` for one that is not connected (default `null`; >= 1) |

### `general_query`

Asks the stations in radio range a general query of APRS 1.0.1 (the services/generalask.py of the daemon): one frame from our call to our tocall whose information field is exactly `?APRS?` (`kind`
`aprs`: who is around? the stations answer with their positions), `?IGATE?` (`igate`: the iGates answer with their capabilities) or `?WX?` (`wx`: the weather stations answer with their weather). It goes
once on each radio of asking around's Send on (the radios whose `radio/<id>/ask` is ticked; with one radio that can send, that one) that takes
frames now, by `path` (digipeater calls or aliases separated by commas, `OH2RDK-7,OH2RCH-2` or `WIDE1-1,WIDE2-1`, checked as a radio's path is, or `DIRECT` for none; null or empty is each radio's own
path, and a radio that carries no path goes without one) with `RFONLY` after it when `rf_only`. The answers are ordinary packets (rows of `stations` and `packets`); the topic `general` tells the query and the
stations heard after it. All or nothing: answered with an `error`, and nothing is sent on any radio, when the station is RX only or no call is set (`transmit.off`, or the interlock's reason), there is no
radio (`radio.none`) or none of them takes frames now, the path is no path (`path.*`, `call.*`) or is too long with RFONLY (`path.too_long_rf_only`), or the query of that kind went on one of those
radios less than 60 seconds ago (`general.too_soon`, with the `seconds` that are left, the longest).

| field | type | | description |
|---|---|---|---|
| `kind` | "aprs" \| "igate" \| "wx" |  |  |
| `path` | string \| null |  | (max 256 chars) |
| `rf_only` | boolean | optional | RFONLY after the path; left out it is true. The page no longer sends it (the request always goes with RFONLY); a page of an older build may (default `true`) |

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
`beacon/path` is, or `DIRECT` for a path of its own with no digipeaters at all; an empty `path` is no path of its own, as `clear_station_path` makes it. Answered by the `set` of the station's entry in the topic `station_prefs`
(its `rf_only` is whatever it was), or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `path` | string |  | (max 256 chars) |
| `radio` | integer \| null | optional | the radio the path is for (plan rule 3.3: a path belongs to the radio it was set on), its id; left out: radio 1, whose path is the entry's `path`; another radio's is the station's row's `paths` (default `null`; >= 1) |

### `clear_station_path`

Takes a station's own path away, so that it has the path of the setting `beacon/path` again (a station without one is no error). Answered by the `set` of its entry in `station_prefs` with a null `path`
(or the `del` of the entry when it was not RF only either), or by an `error`.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `radio` | integer \| null | optional | the radio whose path for the station is taken away, its id; left out: radio 1 (default `null`; >= 1) |

### `set_station_rf_only`

Makes everything we send to a station RF only, or not: `RFONLY` is added as the last element of the path of each message and attempt, each ack and each answer to a query (a path that holds `RFONLY` or `NOGATE`
already gets no second one). A path that would be more than 8 elements with it is refused when a message is sent ("path too long for RF only"). The email gateway `EMAIL-2` is on the internet and is refused. Answered by the `set`
of the station's entry in the topic `station_prefs` (its other parts are whatever they were), or by the `del` of the entry when `on` is false and nothing else is set, or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `on` | boolean |  |  |

### `set_station_alert`

Sets when the operator is told about a station (see `AlertWhen`): `on_air`, `within_km` (1 to 1000, null for none) and `direct`, any of them at once; all off takes the alert away. Our own station and our own objects and items
are refused. Answered by the `set` of the station's entry in the topic `station_prefs` (its path and RF only are whatever they were), or by its `del` when nothing else is set and the alert is taken away, or by an `error`.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `on_air` | boolean |  |  |
| `within_km` | integer \| null |  | (>= 1, <= 1000) |
| `direct` | boolean |  |  |

### `weather_series`

Asks for the observations a weather station made in the last `hours` hours. Answered with a `weather_series` message to the page that asked, or an `error` for a call that is empty or hours out of range; a call with no
observations is answered with no points.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the `stations` topic has it (an object's name for a weather object) (max 64 chars, min 1 chars) |
| `hours` | integer |  | how far back to go: 24 for a day, 168 for a week (>= 1, <= 168) |

### `packet_history`

Asks how many packets were heard (not sent by us) in each of the last `hours` hours: all of them, or those of one station (`call`). Answered with a `packet_history` message to the page that asked, or an
`error` for hours out of range or a call that is empty; a station with no packets is answered with every count 0.

| field | type | | description |
|---|---|---|---|
| `hours` | integer |  | how far back to go: 24 for a day, 168 for a week (>= 1, <= 168) |
| `call` | string \| null | optional | only the packets whose sender (the source of the frame heard) is this station, as the `stations` topic has it; absent or null for every packet heard (default `null`; max 64 chars, min 1 chars) |

### `packet_stats`

Asks for what the statistics card counts from the packet log: the packets heard by the hour by radio, what went out on each radio, the packets that came by several ways and the copies sent and gated
in the last hour. Answered with a `packet_stats` message to the page that asked.

### `position_history`

Asks where the stations were in the last `hours` hours, for the replay of the map. Answered with a `position_history` message to the page that asked, or an `error` for hours out of range.

| field | type | | description |
|---|---|---|---|
| `hours` | integer |  | how far back to go: the replay offers 1, 3, 6, 12, 24 (the choices of the Stations tab's On map for) and 48, 72, 168 (2, 3, 7 days; the packet log keeps 7) (>= 1, <= 168) |

### `speed_series`

Asks for the speeds a station reported in its positions in the last `hours` hours. Answered with a `speed_series` message to the page that asked, or an `error` for a call that is empty or hours out of
range; a station that reported no speed is answered with no points.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the `stations` topic has it: its position packets are those whose sender (the source of the frame heard) it is (max 64 chars, min 1 chars) |
| `hours` | integer |  | how far back to go: 24 for a day (>= 1, <= 168) |

### `signal_series`

Asks for the readings of a station's signal in the last `hours` hours: the SNR and the RSSI its radio measured of each packet heard direct from it (`snr` and `rssi` of a packet). Answered with a `signal_series`
message to the page that asked, or an `error` for a call that is empty or hours out of range; a station heard on no radio that measures is answered with no points.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the `stations` topic has it: its packets are those whose source it is (max 64 chars, min 1 chars) |
| `hours` | integer |  | how far back to go: 24 for a day (>= 1, <= 168) |

### `station_traffic`

Asks for the latest packets of one station, for the station panel of the Stations tab: those it sent (its own source, or inside a third-party packet an iGate put on the air) and the messages we sent
to it (a message, an ack, a directed query). Read from the packet log, so that they reach back past the 200 of the topic `packets`; the page adds the packets that come after. While `igate/enabled` is off no packet
that came from APRS-IS is read, as the topic shows none. Answered with a `station_traffic` message to the page that asked.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the `stations` topic has it (max 64 chars, min 1 chars) |

### `alert_test`

Runs the alert command as it is saved in the settings (`messages/alert_command`), exactly as for a message to us (the same shell, the same environment, the 20 s limit) with a made-up message: `NEOAPRS_FROM`
is `NEOAPRS`, `NEOAPRS_TEXT` is `This is a test of the NeoAPRS alert`, `NEOAPRS_AT` is now and `NEOAPRS_MSG_ID` is empty. `messages/alert` is not asked: a test is explicit. Waits for the command and answers the page
that asked with `alert_result`, or with an `error` when the command is empty (`no alert command`). A page of another device is refused with `setting.local_only`.

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
separated by commas, or `DIRECT` for none at all (null or empty: `beacon/path`); `qru_group` the group of QRU it belongs to (up to 8 letters and digits, not `INFO` or `NEXT`; empty for none) and `on_request` true to send it
only to a station that asks for it, never on the schedule; `radios` the radios it goes out on (their ids). Nothing is sent while the call is not set. Answered by the `set` of its row in `own_objects` and `stations`, or by an `error` that names the reason.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | (max 9 chars, min 1 chars) |
| `kind` | "object" \| "item" |  |  |
| `lat` | number |  | (>= -90.0, <= 90.0) |
| `lon` | number |  | (>= -180.0, <= 180.0) |
| `symbol_table` | string |  | (max 1 chars, min 1 chars) |
| `symbol_code` | string |  | (max 1 chars, min 1 chars) |
| `comment` | string |  | (max 43 chars) |
| `course_deg` | integer \| null |  | (>= 0, <= 359) |
| `speed_kmh` | number \| null |  | (>= 0, <= 1850.148) |
| `path` | string \| null |  | (max 256 chars) |
| `qru_group` | string |  | (max 8 chars) |
| `on_request` | boolean |  |  |
| `radios` | integer[] |  | the radios it goes out on, their ids (max 64 items) |

### `object_kill`

Kills an object or an item of ours: the killed form is sent three times (at once, after a minute and after three) and then it is forgotten, and it leaves the map now. One that was never sent is removed at
once. Answered by the `del` of its row in `stations` (and in `own_objects` once the kill is sent, or at once), or by an `error` (no such object of ours).

| field | type | | description |
|---|---|---|---|
| `name` | string |  | (max 9 chars, min 1 chars) |

### `bulletin_post`

Posts a bulletin, an announcement or a group bulletin of ours in the lowest free slot of its kind: `BLN0`..`BLN9` for a bulletin, `BLNA`..`BLNZ` for an announcement, `BLN0`..`BLN9` and the group for a
group bulletin (`BLN0HAMS`); a slot is free while no post of ours is in it, an ended one included. Nothing of ours is replaced: with every slot of the kind (of the group) taken it is refused (`bulletin.taken`),
and so it is with 36 posts of ours (`bulletin.full`). `text` is at most 67 characters of printable ASCII without `|`, `~` and `{`. It is sent at once and then on the schedule of the specification (a bulletin
a few times early and every 20 minutes, an announcement every hour) for `hours`. Nothing is sent while the call is not set. Answered by the `set` of its row in `own_bulletins`, or by an `error` that names the
reason.

| field | type | | description |
|---|---|---|---|
| `kind` | "bulletin" \| "announcement" \| "group" |  |  |
| `group` | string | optional | the group of a group bulletin, 1 to 5 letters and digits (written in capitals); ignored for the other kinds (default `""`; max 5 chars) |
| `text` | string |  | (max 512 chars, min 1 chars) |
| `hours` | integer \| null | optional | how long it is sent after its first packet, in hours: 1, 2, 4, 8 or 12 for a bulletin and a group bulletin, 24, 72 or 168 for an announcement; left out: `status.new_bulletin_hours` of its kind (default `null`; >= 1, <= 168) |
| `radios` | integer[] \| null | optional | the radios it goes out on, their ids; left out: `status.new_bulletin_radios` (default `null`; max 64 items) |

### `bulletin_unpost`

Deletes a bulletin of ours: it is not sent again and leaves the board. Answered by the `del` of its row in `own_bulletins`, or by an `error` (no such bulletin of ours).

| field | type | | description |
|---|---|---|---|
| `slot` | string |  | (max 9 chars, min 4 chars) |

### `map_estimate`

Starts a dry run: how big the detailed map for `map/radius_km` and `map/maxzoom` round our position will be. Answered by the topic `map` (state `estimating`, then `estimate` filled in), or by an `error` when no job can start
(no position, or a job is running).

### `map_fetch`

Starts making the maps: the world map first when it is not there, then the detailed map for `map/radius_km` and `map/maxzoom` round our position, from `map/source` or the latest daily build. The progress is the topic
`map`. An `error` when no job can start (no position, or a job is running).

### `map_wanted`

The setup guide went on from its Position step with the place the daemon has: the map of the area is wanted. The daemon begins making the detailed map for `map/radius_km` round our position, as `map_fetch` does (the
progress is the topic `map`), unless the detailed map that is there covers the place already or a job is running; it is never an error, and without a position nothing happens. A new place saved with `set_config` asks
the same by itself. The job is not the operator's: when it fails it is tried again at the next start of the daemon (`later` of the topic `map`), and `map_cancel` ends it.

### `map_cancel`

Ends the running job; the files it was making are removed and the maps stay as they were. An `error` when no job is running.

### `update_now`

Starts Update now to `version`, which must be the version the update check announced (the `update` of `status`): the daemon fetches SHA256SUMS, its signature and the file for this copy from the GitHub release of exactly that
version, checks the signature and the file's SHA-256 and installs it, and NeoAPRS restarts. The progress is the topic `update`. An `error` when this copy cannot update itself (`update.unsupported`, `update.blocked`), the version
is not the one announced (`update.not_announced`) or an update is running (`update.busy`).

| field | type | | description |
|---|---|---|---|
| `version` | string |  | (max 40 chars, min 1 chars) |

### `update_cancel`

Ends the download of Update now; nothing of it is left. An `error` (`update.not_running`) when no download is running: an install that has begun is not stopped.

### `skeds_wanted`

The page shows the HF tests tab (and while it stays visible): the daemon reads the board now, unless it read it less than 15 minutes ago or the update check is off (`NEOAPRS_UPDATE_CHECK=0`). Nothing is answered; the topic `skeds` tells what came.

### `sked_post`

Posts a sked of ours on the board of the project's server: our call (the setting `station/call`), `from` and `to` in UTC (`to` after `from` by 24 hours at most, not past, `from` not more than 30 days ahead), a `dial` in the form of the HF
box and a `note` of at most 80 characters (control and invisible characters are made spaces). It goes only on this command, and carries the call, the two times, the dial, the note and this installation's secret token. Answered by the topic `skeds`, whose
rows then have it with `ours` true. An `error` when no call is set (the interlock's reason; RX only does not matter, nothing is sent by radio), the sked has ended (`sked.past`) or begins more than 30 days ahead by the daemon's or the server's clock (`sked.far`), too many were posted from here lately (`sked.rate`), the board has no
room (`sked.full`), or the project's server could not be reached or would not take it (`sked.unreachable`). A board that is closed to the call is no error: the state of the topic says `closed`.

| field | type | | description |
|---|---|---|---|
| `from` | time |  | UTC, ISO 8601 with a Z; the field is called `from` on the wire |
| `to` | time |  | UTC, ISO 8601 with a Z |
| `dial` | string |  |  |
| `note` | string |  | at most 80 characters once cleaned; empty for none (max 320 chars) |

### `sked_delete`

Deletes a sked that this installation posted, by its id: the server takes it off the board for everybody. A sked that is not ours (another installation posted it, or the data folder is another one) is only dropped from `ours`: nothing is said, and the
board is read again. An `error` (`sked.unreachable`) when the project's server could not be reached. The topic `skeds` tells the new board.

| field | type | | description |
|---|---|---|---|
| `id` | string |  |  |

### `page_error`

An error that happened in the page itself (the browser's script, not a refusal of the daemon): the daemon writes it to its log as a warning, `page error (vue) on page BUILD: MESSAGE | FIRST LINE OF THE STACK`, and keeps the latest 100 for
the support bundle. At most 20 of a connection are logged in a minute; the rest are counted in one line. No answer: a page that cannot report must not fail twice.

| field | type | | description |
|---|---|---|---|
| `message` | string |  | what the error says (max 2000 chars) |
| `stack` | string |  | where it happened, as the browser gives it; empty for none (max 8000 chars) |
| `source` | "vue" \| "window" \| "promise" |  | who caught it: `vue` (the component framework's error handler), `window` (an uncaught error of the window), `promise` (a promise nobody caught) |
| `at` | time |  | when it happened, by the page's clock |
| `build` | string |  | the build of the page that reported it (the `page` of `hello`) (max 64 chars) |

### `radio_add`

Adds a radio of the type (`type`, a `key` of `RADIO_TYPES`): after the others, enabled, with the defaults of its kind, the name typed (empty or left out: none), and started at once. Answered with `radio_added` (its
id) to the page that asked, at once, and then the `set` of its row in `radios` (the topic is told at most four times a second: the row may come a few messages later, so a page that opens the new radio waits
for it), or with an `error`: `radio.unknown_type`, `radio.name_form`, `radio.name_taken`, `radio.name_label`, `setting.not_stored`.

| field | type | | description |
|---|---|---|---|
| `type` | string |  | (max 32 chars, min 1 chars) |
| `name` | string | optional | the name typed; left out or empty: none (default `""`; max 64 chars) |

### `radio_remove`

Removes the radio: it is stopped for good, and in the same write its id leaves the objects' sets, the stations' choices of it and their paths on it. Its row stays in `radios`, `removed`, so that what came by it keeps
its name. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on stays), `setting.not_stored`.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |

### `radio_change`

Changes what is given of the radio and nothing else: its `name` (empty: none), its `type` (one of its own kind), its Enable (`enabled`) or its place in the list (`position`, from 1; the others keep theirs, a tie goes by
id). Stored, then in force; the radio is restarted when its type or its Enable changed what runs. Answered by the row, or an `error`: `radio.unknown`, `radio.last_enabled` (the last radio that is on is not switched off),
`radio.name_form`, `radio.name_taken`, `radio.name_label`, `radio.type_kind`, `radio.unknown_type`, `setting.not_stored`.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |
| `name` | string \| null | optional | the new name; left out: unchanged (default `null`; max 64 chars) |
| `type` | string \| null | optional | the new type; left out: unchanged (default `null`; max 32 chars, min 1 chars) |
| `enabled` | boolean \| null | optional | the new Enable; left out: unchanged (default `null`) |
| `position` | integer \| null | optional | the new place; left out: unchanged (default `null`; >= 1, <= 2147483647) |

### `radio_tune`

Tune on the radio's modem: with `on`, keys the radio through its keying and sends its modem's tuning tone through its sound card for ten seconds (Mercury a steady 1000 Hz, its own TUNE; Direwolf its two tones by turns), then stops by itself; with `on` false, stops it early. The radio's row says `modem.test: "tune"`
meanwhile. Answered with an `error` for a radio that is none (`radio.unknown`), whose type has no modem or whose modem is not running (`radio.no_modem`, with its `name`), while the station is RX only (`transmit.off`) and
while a frame is on the air or the channel is busy (`hf.held`).

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |
| `on` | boolean |  | true starts the tone, false stops it |

### `radio_key_test`

The keying test on the radio's modem: keys it for one second, so that the operator sees it go to transmit and come back: with next to no audio (Mercury's TUNE at its quietest level) where the keying is a
line (RTS, DTR, CM108), with the tune tone where the radio keys on audio (VOX); the radio's row says `modem.test: "key"` meanwhile. The same refusals as `radio_tune`.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |

### `radio_scope`

The scope of the radio's modem: with `on`, this page is sent the rows of its waterfall as binary frames that name the radio (*Binary frames*), first the rows kept and then the rows as they come, with `on`
false, or when the page closes, no more. Several radios can be looked at at once. Nothing comes while the radio's modem is not running or has no interface (its row's `modem.scope`). Refused, with `on`, for a radio that is none
(`radio.unknown`) and for one whose type has no scope (`radio.no_scope`, with its `name`: `can.scope` of its row is false); `on` false is never refused.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |
| `on` | boolean |  | true starts the rows for this page, false stops them |

### `radio_level`

The receive level of a Sound card radio as its Direwolf says it ten times a second: with `on`, this page is sent `radio_level` for that radio, the level now at once and then each change, while it shows the
level (the radio's box is in view); with `on` false, or when the page closes, no more. A page that is behind is skipped. Every page has the slower `modem.rx_level` of the radio's row. Refused, with `on`, for a
radio that is none (`radio.unknown`) and for one whose type has no receive level (`radio.no_modem`, with its `name`: `can.rx_level` of its row is false); `on` false is never refused.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id, the `id` of its row in the topic `radios` (>= 1) |
| `on` | boolean |  | true starts the levels for this page, false stops them |

### `station_radio`

Chooses the radio messages to a station go out on (`radio`, or null to leave it to the daemon again: plan rule 3.2, the radio that heard it lately, a local one before HF). It holds from the next attempt on, also of a
message on its way, and across a restart; the station's row says it (`radio_choice`, and `radio_now` the radio a message takes now). A radio that is off is no choice: the station's row says null while it is. For a
station of the book it is answered by the station's row (and the `radio_now` of each message to it on its way); a call the book does not hold is chosen for too (plan rule 3.2: the choice is kept by call), with no
answer, and its station's row says it once the station is heard. The call is kept in its normal form, as a message names it (upper case, no SSID 0). Refused with an `error`: `radio.unknown` (no radio of that
id that is not removed), `radio.receive_only` (a radio of a type that only receives, with its `name`), or a `call.*` code for a text that is no call.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | (max 64 chars, min 1 chars) |
| `radio` | integer \| null |  | (>= 1) |

### `frequencies`

The page shows the station's suggested frequencies (the box of a radio whose type can show them, the HF tests tab): the daemon asks the project's server for them again, unless it asked less than 15 minutes ago or the
update check is off (`NEOAPRS_UPDATE_CHECK=0`). The suggested dials are the project's, not a radio's: one list for the station. Nothing is answered; the topic `skeds` and each Mercury radio's `modem` have the list
when it changes.

### `station_track`

Asks for a station's track: the positions its row's `track` has, for a page that draws the trail or works out the speed of one station without reading the whole row. Answered with a `station_track` message to the
page that asked, or an `error` `station.unknown` for a call the topic `stations` has no row of (with the internet hidden, a station known only from there). The track is as the row has it when the command is answered:
a page that shows it asks again when the row changes.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station, as the topic `stations` keys it (max 64 chars, min 1 chars) |

### `layer_look`

With `on`, this page looks at the layer (its tick is on, the page is in front and the replay is closed: the page decides); with `on` false, or when the page closes, no more. While a page looks, the daemon
asks the layer's source and sends the page `layer_things`. Never refused: a look at a layer whose source is `none` stands and is served once a source is chosen.

| field | type | | description |
|---|---|---|---|
| `layer` | "aircraft" \| "ships" |  |  |
| `on` | boolean |  |  |

### `satellite_look`

With `on`, this page shows the satellites layer (its tick is on, the page is in front and the replay is closed: the page decides) and has the cards of `cards` open; sent again whenever the cards change.
With `on` false, or when the page closes, no more. While a page looks, the daemon tells it `satellites` every 30 s and at once on this command.

| field | type | | description |
|---|---|---|---|
| `on` | boolean |  |  |
| `cards` | integer[] |  | (max 64 items) |

## Server to client

25 messages, each a JSON object with `"type"`. The first is `hello`. Where a field is `X | null` it is always present, with null.

### `hello`

The first message of a connection; `status` and the `state` of every topic follow it at once, so a page need not ask for them.

| field | type | | description |
|---|---|---|---|
| `protocol` | integer |  | the version of these messages: a page built for another one loads itself again, and when that does not help it does not run (it shows a notice and keeps the socket closed) |
| `version` | string |  | the version of the daemon, which the page shows (Settings → Update check); the page has no version of its own and does not compare this one |
| `page` | string |  | the build of the page this daemon serves, the name of its main script (`index-<hash>.js` of assets/); the daemon serves the page it took when it started, so this is the build a browser gets from it. A page of another build loads itself again, once for each build, and shows a notice when that does not help; empty when the daemon has no built page |
| `install` | InstallInfo |  | how this daemon was installed, for the steps of an update |
| `local` | boolean |  | whether this page is on the computer the daemon runs on (the loopback, with a request addressed to it): only such a page changes the settings that name a program or an address the daemon runs or fetches from (messages/alert_command, update/url, map/source, web/allowed_hosts) and runs the alert's Test; a page of another device does not show them |
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
| `beacon_interval_min` | integer |  | minutes between our position packets on some radio: `beacon/interval_min` as it is in force, the shortest of the radios the beacon goes out on (each raised to its own floor; each radio's own is `beacon.interval_min` of its row in `radios`); 0 is off |
| `beacon_last_sent` | time \| null |  | when the latest beacon was sent on any radio, by the timer or on request; null for none since the daemon started |
| `beacon_next_due` | time \| null |  | when the next timed beacon is due on any radio the beacon goes out on (each radio's own is its row's `beacon`); null while none is planned |
| `unheard_radio` | integer \| null |  | the radio a message to a call no radio heard goes out on (its id), and a text to an addressee that is no station (CQ, ALL, QST): the first radio that can send, in the order of the boxes. Route shows it as what Automatic gives. Null while no radio that can send is on |
| `email_radio` | integer \| null |  | the radio an email to the gateway goes out on (its id), of any kind: the one radio that can send; else the one chosen (`email/radio`, the select of the E-mail tab) while it is on and can send; else the first radio that can send, in the order of the boxes. Null while no radio that can send is on, and Send of an email is off |
| `unavailable_types` | string[] |  | the types of radio (keys of `RADIO_TYPES`) whose program this kind of installation does not carry (a Mac carries no Direwolf): the page does not offer them, and `radio_add` refuses them (`radio.unknown_type`) |
| `new_object_radios` | integer[] |  | the radios a new object is ticked for (their ids, ascending), when `object_set` names none: with one radio that can send, that one; else those of the object saved last with radios named while one of them is on, else the first radio that can send |
| `new_bulletin_radios` | integer[] |  | the radios a new bulletin goes on (their ids, ascending), when `bulletin_post` names none: as `new_object_radios`, by the bulletin posted last with radios named |
| `new_bulletin_hours` | PostHours |  | how long a new post of each kind is sent for, in hours, when `bulletin_post` names no `hours`: the one posted last of that kind |
| `station_status` | string |  | the text of the status report last sent in this run (services/rigstatus.py); empty until one has gone |
| `station_status_last_sent` | time \| null |  | when the latest status report was sent (kept over a restart); null for none yet |
| `rig_state` | "off" \| "on" \| "unused" |  | whether the radio the status is made from answers: `on`, `off` (rigctld is away or the radio is off, nothing is sent), or `unused` while the status does not come from a radio (`status/source` is `text` or `off`) |
| `cpu_percent` | number |  | the daemon's CPU time (user and system) as a share of one core, in percent to a tenth, since the previous status that was at least a second before; the first counts from the start |
| `rss_mb` | number \| null |  | the daemon's resident memory in megabytes, to a tenth; null where the system does not say |
| `uptime_sec` | integer |  | seconds since the daemon started, by its clock |
| `update` | UpdateInfo \| null |  | the latest version while it is newer than this one, from the daily update check; null when there is none or the check has not been answered |
| `message_key` | string |  | the fingerprint of our own key for encrypted messages (16 hex characters in four groups), made at the start of a daemon run with `--encryption`; empty while there is none (the daemon runs without the flag, or the key could not be made), which is also how the page knows the feature is not there |

### `pong`

The answer to `ping`.

| field | type | | description |
|---|---|---|---|
| `now` | time |  | the daemon's clock |

### `error`

A command that could not be done. A frame the daemon could not understand is answered the same way, naming the command, the field and the problem; nothing was changed. A page goes by `cmd`, `key`
and `code` (with the sentence of `why` for a refusal that passes another's on); `text` is the English sentence for the log, which the page never shows: a code it has no sentence for is said with its plain
words of a failure.

| field | type | | description |
|---|---|---|---|
| `cmd` | string |  | the command it answers; empty for a frame that was no command (not JSON, not an object, no `cmd`, an unknown one) |
| `key` | string \| null |  | the setting it is about (`set_config`), a key of `CONFIG_KEYS`; null for any other error |
| `code` | string |  | a stable word for what is wrong, such as `setting.range`, `call.ssid` or `message.too_long`; `failed` for one the operator can do nothing about; `other` for an error that has no code |
| `params` | { [key: string]: string \| integer \| number } |  | the values the sentence is made of, by name, such as `value`, `min` and `max` of `setting.range`, and `why`, the code of the reason, for a refusal that passes another's on (`status.not_sent`, `beacon.not_sent`, `transmit.call`); empty when there are none |
| `text` | string |  | what could not be done and why, in a sentence in English: the command, then the setting if there is one, then the reason (`set_config: station/lat: 95 is not between -90 and 90`) |
| `id` | integer \| null | optional | the `id` of the request this answers, when the command carried one (only `set_config` does: the `id` of another command is a radio's, a message's or a packet's number and is never echoed); the field is left out otherwise (default `null`) |

### `saved`

The answer to a `set_config` that carried an `id`, sent to the page that asked once the settings are in force.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | the `id` of the `set_config` this answers |

### `ports`

The answer to `list_ports`.

| field | type | | description |
|---|---|---|---|
| `ports` | PortRow[] |  | the ports, in natural order (`COM2` before `COM10`), then the paired Bluetooth devices |
| `search` | boolean |  | whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list |
| `find` | boolean |  | whether Find my radio (`find_radio`) can be asked for: on Linux, Windows and macOS |
| `sound_cards` | SoundCardRow[] |  | the sound cards the radio's modem lists, for a `radio` named whose type has a modem on a sound card (Mercury, Sound card) while the program is installed; empty otherwise |
| `keying` | string |  | the keying the daemon proposes with the card it proposes (`vox`, `cm108`, `rts:PORT` or `dtr:PORT`): the page preselects it and stores it as the radio's `keying` while that is empty; empty when no sound card is listed |
| `radio` | integer \| null |  | the radio the list was asked for (`radio` of `list_ports`: the sound cards and the proposals are its own); null for a list that named none. The ports are the machine's, the same whoever asked |

### `state`

A topic as it is now: its revision and its whole `value`, which replaces what the page had. Patches for the changes made meanwhile follow.

| field | type | | description |
|---|---|---|---|
| `topic` | string |  | (max 64 chars, min 1 chars) |
| `rev` | integer |  | how many changes the topic has had since the daemon started (>= 0, <= 2^53) |
| `value` | any |  |  |

### `patch`

What changed in a topic: apply the ops in order; the copy is then at `rev`. An op says what the item is, not what to add, so an op that is applied twice ends where it should. Changes are told
on a tick of 100 ms (a radio's row in `radios` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key.

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

### `packet_history`

The packets heard by the hour, the answer to `packet_history`: a count for each whole hour of the clock from `start`, the oldest first, as many as were asked for; the last is the hour that is running, so
it counts what has come since the top of the hour.

| field | type | | description |
|---|---|---|---|
| `hours` | integer |  | the hours asked for (>= 1, <= 168) |
| `call` | string \| null |  | the station asked about, null for every packet heard: a page that asked for several stations and for all of them tells the answers apart by it |
| `start` | time |  | the top of the first hour counted, UTC |
| `counts` | integer[] |  | the packets heard in each hour from `start`, the oldest first (an hour with none is 0) |

### `packet_stats`

The answer to `packet_stats`. The packets heard (not sent by us; none from APRS-IS while `igate/enabled` is off) by the hour of the clock over the week the log keeps, or since its oldest packet when that is
younger, for each radio and the internet that heard any, the running hour last; what went out and the packets heard more than once over the last 24 hours; the copies of the last 60 minutes. Hours that
are over are counted once; the answer is at most a minute behind.

| field | type | | description |
|---|---|---|---|
| `start` | time |  | the top of the first hour counted, UTC |
| `hours` | integer |  | how many hours each list of `heard` has: from `start` to the running one (>= 1, <= 168) |
| `heard` | ChannelHours[] |  | by radio, in the order of their ids, the internet last; one that heard nothing in the span is left out |
| `sent` | RadioSent[] |  | by radio, in the order of their ids; one that sent nothing in the last 24 hours is left out |
| `packets` | integer |  | the packets the radios heard in the last 24 hours, a packet heard by several ways counted once (the same source, destination and information field within a minute of the clock) (>= 0) |
| `frames` | integer |  | the frames those packets came in: `frames` less `packets` is how many came again by another way (>= 0) |
| `repeated_hour` | integer |  | the copies the digipeater sent in the last 60 minutes (>= 0) |
| `gated_hour` | integer \| null |  | the packets the iGate put on APRS-IS in the last 60 minutes; null while `igate/gate` (Send what I hear) is off |

### `position_history`

The positions of the stations over the span asked for, the answer to `position_history`, from the packet log: every position heard in it (a station's own, or the one inside a third-party packet), the
live objects and items heard by their names, and what we sent under our call (our beacons, and our objects by their names). While `igate/enabled` (Internet stations) is off, no packet that came from
APRS-IS is in it, whenever it was received: what was heard on the radio only, an iGate's third-party packets too, as the stations topic shows then. A station's points are thinned, the more the longer the span (REPLAY_THINNING
of neoaprs/web/views.py): up to a day, a point less than 10 m from the point kept before it or less than 30 s after it is left out; up to three days, 200 m and 2 minutes; a week, 300 m and 5 minutes.
The last point is always there, and so is the one where a station still was just before it moved off. The latest 1 000 000 position packets at most are read: on a feed busier than that, the span
begins at the first of them.

| field | type | | description |
|---|---|---|---|
| `hours` | integer |  | the hours asked for (>= 1, <= 168) |
| `start` | time |  | where the replay begins, UTC: `hours` hours before `end`, or the oldest packet the log keeps when that is later (a daemon that has run for less than the span, or a log busier than the packets read) |
| `end` | time |  | where the replay ends, UTC: when the daemon answered |
| `stations` | { [key: string]: [time, number, number][] } |  | [time, lat, lon] for each position kept, the oldest first, by the station's call (an object's or item's name); a station with no position in the span is not in it |

### `speed_series`

The speeds of one station, the answer to `speed_series`: one point for each position packet of it heard in the span that carried a speed (a course and speed after the position, a compressed position's,
a Mic-E's), the oldest first (a packet that came by two digipeaters is two points).

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station asked about: a page with several cards open tells the answers apart by it |
| `hours` | integer |  | the hours asked for (>= 1, <= 168) |
| `points` | [time, number][] |  | [time, speed_kmh] for each position that had a speed, the oldest first; a station standing still that says so has 0 |

### `signal_series`

The readings of one station's signal, the answer to `signal_series`: one point for each packet heard direct from it in the span that carried a reading, the oldest first, the latest 1000 at most. A digipeater's copy
and a third-party packet are left out: their frame is another station's signal.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station asked about: a page with several cards open tells the answers apart by it |
| `hours` | integer |  | the hours asked for (>= 1, <= 168) |
| `points` | ([time, number \| null, number \| null])[] |  | [time, snr_db, rssi_dbm] for each packet with a reading, the oldest first; a reading the radio does not give is null (Mercury gives the SNR alone) |

### `station_traffic`

The latest packets of one station (at most 50), the answer to `station_traffic`, the newest first. A third-party packet is looked for among the latest 20000 packets of the log, where an iGate's are.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station asked about |
| `packets` | PacketRow[] |  | the packets, as the rows of the topic `packets` but for `id`, which is the packet's number in the log here (the same packet in the topic has its own); the newest first |

### `alert_result`

The answer to `alert_test`, when the command has ended or run out of its 20 s.

| field | type | | description |
|---|---|---|---|
| `ok` | boolean |  | the command ended with exit code 0 |
| `outcome` | "ran" \| "exit" \| "timeout" \| "no_start" |  | how it ended, which the page says in its words: `ran` it worked; `exit` it ended with the exit code `status`; `timeout` it did not end within `seconds` and was killed; `no_start` it could not start (the log says why) |
| `status` | integer |  | the exit code for `exit`; 0 otherwise |
| `seconds` | number |  | how long a run may take, in seconds (>= 0) |
| `line` | string |  | for `exit`, the first line the command wrote to stderr, its own words (`no display`); empty otherwise |

### `update_result`

The answer to `update_check`: what the version page said, or why it said nothing.

| field | type | | description |
|---|---|---|---|
| `outcome` | "newer" \| "current" \| "no_answer" |  | `newer`: a newer version is out; `current`: this is the latest; `no_answer`: the page could not be reached or did not name a version |
| `version` | string |  | the latest version for `newer`, this version for `current`; empty for `no_answer` |
| `reason` | "" \| "offline" \| "bad_answer" |  | for `no_answer` why, as a code the page says in its words: `offline` the update server did not answer (is there a connection?), `bad_answer` it gave no usable answer; empty otherwise |

### `release_notes`

The answer to `release_notes`: the sections of the versions asked for, the newest first; none with `problem` saying why (the notes could not be fetched, or the version is neither the newer one known nor this one).

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the version asked for |
| `since` | string |  | the `since` asked for, empty when there was none |
| `sections` | NoteSection[] |  | the newest first; empty with `problem` |
| `problem` | "" \| "unreachable" \| "unknown_version" |  | why there are no sections, as a code: `unreachable` the notes could not be fetched, `unknown_version` the version is neither the newer one known nor this one; empty when there are |

### `radio_search`

How `find_radio` goes, to the page that asked.

| field | type | | description |
|---|---|---|---|
| `state` | "trying" \| "found" \| "cancelled" |  | `trying`: about to try `port` at `baud`; `found`: a TNC answered at `port` at `baud` and `profile` fits it, and the search is over; `cancelled`: `find_radio_cancel` ended it |
| `port` | string |  | the port being tried or found; empty for `cancelled` |
| `baud` | integer \| null |  | the speed; null for a port that has none (a Bluetooth device) and for `cancelled` |
| `profile` | string |  | for `found`, the key of the TNC profile (`tnc/profile`); empty otherwise |
| `number` | integer |  | the try that is under way, from 1; 0 for `found` and `cancelled` (>= 0) |
| `total` | integer |  | how many tries there are if nothing answers; 0 for `found` and `cancelled` (>= 0) |
| `radio` | integer \| null |  | the radio the search is for (its id); null for a search that named none (radio 1) |
| `radio_type` | string |  | for `found`, the radio type that fits the TNC (a `key` of `RADIO_TYPES`, the same as `profile` for every Packet type: 1.11's `type`, which the message's own tag takes); empty otherwise |

### `station_alert`

An alert set on a station fired (`set_station_alert`): told to every page that is open, once. The page alerts as for a message to us (the sound, the notification, the browser tab, as its own choice says) and shows it in its toast.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station |
| `kind` | "on_air" \| "within" \| "direct" |  | what happened: it came on the air, it came within the distance, it was heard direct |
| `at` | time |  | when the packet that fired it was heard (for `within`, when the station's position was, or when ours moved) |
| `km` | number \| null |  | for `within`, how far the station is, km with one decimal; else null |

### `radio_added`

The answer to `radio_add`, to the page that asked: the id the new radio was given.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | (>= 1) |

### `station_track`

The track of one station, the answer to `station_track`: what its row's `track` has now.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the station asked about: a page with several cards open tells the answers apart by it |
| `points` | [time, number, number][] |  | the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed; empty for a station that has sent no position (max 50 items) |

### `radio_level`

A Sound card radio's receive level as it is now, to a page that asked for it (`radio_level`): on Direwolf's own scale, as the row's `modem.rx_level`; null while its Direwolf does not run.

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | (>= 1) |
| `level` | integer \| null |  | (>= 0) |

### `layer_things`

A layer's whole table, to each page that looks at it and is not behind: at once on `layer_look`, after every answer of the source, at most every 5 s for an AIS receiver, when things grow too old, and
when the source in force changes (then with the new `source` and no things).

| field | type | | description |
|---|---|---|---|
| `at` | time |  | the daemon's time when the table was sent; the age of each thing's `at` is told by it, not by the page's clock |
| `layer` | "aircraft" \| "ships" |  |  |
| `source` | "none" \| "adsbfi" \| "adsblol" \| "fintraffic" \| "aisstream" \| "radarcape" \| "receiver" |  | the source in force that the things are from |
| `away` | boolean |  | true when the last question failed or was not in the expected form, the connection is down, or there is no position to ask for; `things` keeps the last things then |
| `things` | LayerThing[] |  |  |
| `trails` | LayerTrail[] |  | only in the first table a page gets on `layer_look`, else empty: the way each thing of `things` went in the last 30 minutes while the source was asked (it is asked on for 2 minutes after the last page stopped looking), oldest first: the last minute whole, older points at most one a minute and only where the way bends by more than 50 m |

### `satellites`

The satellites layer of now, to each page that looks: every satellite shown (elements no older than 14 days) and the cards that page has open. Empty before the project's file has come.

| field | type | | description |
|---|---|---|---|
| `at` | time |  | UTC, ISO 8601 with a Z |
| `elements_at` | time \| null |  | when the project's server took the orbital elements; null before a file |
| `satellites` | SatelliteMark[] |  |  |
| `cards` | SatelliteCard[] |  |  |

## Topics

The value of each topic (`state` carries it, a `replace` op brings a new one).

| topic | value | |
|---|---|---|
| `stations` | { [key: string]: StationRow } | the station book by call: a station heard again is a `set` of its row, one that is forgotten or pruned a `del` |
| `packets` | { [key: string]: PacketRow } | the latest 200 packets by id (as text): a packet is a `set`, and the one that falls out of the 200 a `del`; the highest id is the newest |
| `radios` | { [key: string]: RadioRow } | every radio of the station by id (as text), removed ones too (marked): what it is, how it is set, its line, its beacon and its modem. A radio added is a `set`; a change of its state, counters, lines, beacon or modem a `set` of its row, at most four times a second; a change of the settings or of the devices held tells it whole. No radio leaves it |
| `config` | ConfigValues | the settings; told again after every save, though nothing differs: the settings form waits for it |
| `station_prefs` | { [key: string]: StationPref } | what the operator set for each station that has anything set, by call: its own path (null where none is set), whether it is RF only and its alert. `set_station_path`, `clear_station_path`, `set_station_rf_only` and `set_station_alert` each give a `set` of the entry, or a `del` when nothing is left in it |
| `messages` | { [key: string]: MessageRow } | every message by id (as text), all of them sent with the first `state`: a message that is new or changes is a `set` of its row, one that is deleted a `del`; none leaves on its own |
| `station_keys` | { [key: string]: StationKey } | the public key each station announced for encrypted messages, by call: the fingerprint and when it was heard. A key heard is a `set`, `forget_station_key` a `del` |
| `bulletins` | { [key: string]: BulletinRow } | the message board by `sender/slot` (`OH2XYZ/BLN1`): the bulletins, announcements, group bulletins and group messages heard and not deleted; one that is new or heard again is a `set` of its row, one that is deleted (`bulletin_delete`) a `del` |
| `own_objects` | { [key: string]: OwnObjectRow } | the objects and items of ours by name: `object_set` makes or changes one (a `set` of its row, each time it is sent too), `object_kill` ends one (its row changes to `killing`, and is a `del` once the kill has been sent); a live one is also a row of `stations` |
| `own_bulletins` | { [key: string]: OwnBulletinRow } | the bulletins, announcements and group bulletins of ours by slot (`BLN1`): `bulletin_post` posts one in a free slot (a `set` of its row, each time it is sent too), `bulletin_unpost` deletes one (a `del`) |
| `map` | MapState | the base map: the files, the area and detail the settings ask for, the size estimated, and the job that makes the maps, the ALOHA circle, and the layers of traffic; told whole as it changes, at most four times a second |
| `update` | UpdateState | Update now: whether this copy can update itself, and the steps of the update it is doing; told whole as it changes, at most four times a second |
| `gps` | GpsState | the GPS receiver and the moving station's beacon: the latest fix, its state, and when the next beacon by time is due; told whole as it changes, at most once a second |
| `igate` | IgateState | the receive-only iGate: whether it is connected to APRS-IS, the server's name, the packets gated and not gated; told whole as it changes, at most once a second |
| `qru` | QruState | local info (QRU): the last request sent from here and the servers that answered it, forgotten an hour after; told whole as it changes |
| `skeds` | SkedsState | the sked board (the page calls it HF tests): when people will be on the air, as the project's server keeps it, the dials the project suggests, and whether it can be reached or is closed; told whole as it changes |
| `general` | GeneralState | asking around: the last general query of each kind sent from here (?APRS?, ?IGATE?, ?WX?) and the stations heard after it that had been quiet before it; told whole as it changes |

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
| `packets` | integer |  | how many packets of this station were received, whatever the channel (`heard_rf` + `heard_rf_gated` + `heard_is` + `heard_dummy`) |
| `heard_rf` | integer |  | how many of them were heard on the radio, direct or by digipeaters (`rf`) (>= 0) |
| `heard_rf_gated` | integer |  | how many came on the radio as third-party packets: an iGate put what it heard on the internet on the air (`rf-gated`); counted, but never a route to send by (>= 0) |
| `heard_is` | integer |  | how many were received from APRS-IS over the internet (`is`); they were never on the air (>= 0) |
| `heard_dummy` | integer |  | how many were made up by the Dummy radio (`dummy`), the radio for trying the program with no radio; they work as the radio's do, and never go to the internet (>= 0) |
| `last_rf_at` | time \| null |  | when a packet of the station was last heard on the radio (`rf`); null when none was |
| `last_rf_gated_at` | time \| null |  | when a third-party packet of the station was last heard on the radio (`rf-gated`); null when none was |
| `last_is_at` | time \| null |  | when a packet of the station was last received from the internet (`is`); null when none was |
| `last_dummy_at` | time \| null |  | when a packet of the station was last made up by the Dummy radio (`dummy`); null when none was |
| `heard` | { [key: string]: HeardOn } |  | what each radio heard of the station, by the radio's id as text: how many packets of the air came on it and when the latest did; a radio that heard nothing of it has no entry |
| `snr` | number \| null |  | the signal-to-noise ratio of the latest packet heard direct from the station whose radio measured one, dB (the Mercury modem and the Dummy Mercury radio do; a digipeater's copy and a third-party packet are another station's signal); null when none was |
| `rssi` | number \| null |  | the received strength of that packet, dBm; null when its radio gave none (Mercury gives none) |
| `signal_at` | time \| null |  | when that packet was heard; null until one with a reading was |
| `position_via` | "rf" \| "rf-gated" \| "is" \| "dummy" \| null |  | the channel of the packet that gave its position (the latest one wins); null for a station without a position and for our own |
| `packets_hour` | integer |  | how many of them were heard in the last hour (counted from the packets of the hour at the start and as they come; the row is told again each minute that it becomes fewer) (>= 0) |
| `device` | string |  | what the station runs, as the APRS device identification list names it ("Kenwood TH-D74", "APRSdroid"): by the destination call of its packets, or by the type code of a Mic-E packet; empty when unknown |
| `last_path` | string[] |  | the digipeaters of the latest packet heard on the radio, the one that repeated it marked with `*`: the packet the radio that heard the station last (`last_path_radio`) heard last |
| `last_path_radio` | integer \| null |  | the radio whose latest packet `last_path` is (the radio that heard the station last, radio 1 on a tie), its id; null for a station no radio heard. After a restart a station a Mercury radio heard last shows that radio's path, direct |
| `last_route` | string |  | how the latest packet heard on the radio reached us (empty for a station known from the internet only): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3` (the digipeaters that repeated it, in order, `?` for one that did not put its call in) |
| `heard_direct` | integer |  | how many packets came straight from the station (counted from the packets heard in this run and the latest 2000 the database kept) (>= 0) |
| `last_direct_at` | time \| null |  | when a packet of the station was last heard direct (no digipeater repeated it, it was not a third-party packet), from the packets counted in `heard_direct`, on the radios that may carry a path; null for a station never heard direct |
| `last_direct_any_at` | time \| null |  | when a packet of the station was last heard direct on any radio, a Mercury radio too (plan 6b: the green check, the map's ring and the "direct only" filter count any radio); null for a station never heard direct |
| `heard_via` | [string, integer][] |  | [the station we heard, packets] for each digipeater that repeated its packets, the most first; `?` stands for a hop that was an alias (WIDE1) and gave no call; the 8 most frequent routes are counted |
| `gated` | integer |  | how many third-party packets this station put on the air that we heard (an iGate wrapping what it took from the internet in a frame of its own; counted from the packets heard in this run and the latest 2000 the database kept, and for a station that is in the book); not `heard_rf_gated`, which counts the packets of this station that some iGate put on the air (>= 0) |
| `igate` | boolean |  | a capabilities packet of the station said `IGATE`: it says it is an iGate |
| `best_route` | string |  | the route most of its packets came by, as `last_route` writes it, direct included; empty until a packet was counted |
| `suggested_path` | string \| null |  | the path to send by to reach it, the best route turned round: empty for direct, `OH2RCH-2` for one hop, `OH2RCH-3,OH2RCH-1` for `via OH2RCH-1 → OH2RCH-3`, `WIDE1-1,WIDE2-1` when the best route has a hop with no call; null when no route is known (an object or item, or a station not heard since the packets were pruned) |
| `heard_path` | string \| null |  | the path that has lately been heard to reach the station, which the first two attempts of a message to it go by when the operator has set no path of its own (the later ones go by `beacon/path`): empty for direct (at least 2 packets heard direct within 60 minutes), else the latest named route that at least 2 packets came by within 60 minutes, turned round, as `suggested_path` writes it (no hop without a call, no iGate, at most 3 digipeaters); null when there is none. Worked out when the row is sent, so a path that goes stale is told with the station's next row |
| `internet_reach` | ReachValues \| null |  | how the latest packet of the station that came from the internet got there; null for a station none came from, and for one whose path does not say |
| `route_marks` | RouteMarkValues[] |  | the route of the station's latest packet and the one before it that came another way (any channel, the newest first): what the map draws of its routes, and no others; empty for a station nothing is known of (our own, our objects) (max 2 items) |
| `weather` | WeatherValues \| null |  | the latest weather the station sent (a position with the weather symbol, or a positionless weather report); null for a station that sent none since the weather log began (or was made from the packets kept) |
| `weather_at` | time \| null |  | when `weather` was heard; null as it is |
| `telemetry` | TelemetryValues \| null |  | the latest telemetry report of the station, scaled and named by the definitions it sent (read again from the latest packets at the start); null for a station that sent none |
| `telemetry_at` | time \| null |  | when `telemetry` was heard; null as it is |
| `locator` | LocatorValues \| null |  | the Maidenhead locator of the station's latest status report (or Mic-E status text): where it says it is, to the square; null when it sent none |
| `extensions` | ExtensionValues \| null |  | the PHG, RNG, DF or area data of the latest position of the station that had any (a position without them keeps the last); null while none had |
| `frequency` | FrequencyValues \| null |  | the voice frequency the station gave last, in the comment of a position (or the name of an object) or in a status text; null when it gave none (not kept over a restart of the daemon for a station that does not send it again) |
| `storm` | StormValues \| null |  | the storm data of the latest position of a storm object; null for anything else |
| `sign` | string \| null |  | what a signpost object says (`55`); null for anything else |
| `distance_km` | number \| null |  | from our position, null for us and for a station without a position |
| `bearing_deg` | number \| null |  | the direction from our position, degrees from north; null as the distance is |
| `is_me` | boolean |  | our own station: the row of the call in the settings, at the position in the settings |
| `own` | boolean |  | an object or an item of ours, which we send (the topic `own_objects` has its values and its schedule): the map marks it as ours and the card has Edit and Kill in place of Forget; false for any other row |
| `can_message` | boolean |  | a message can go to the station, and the card has a Message button: false for an object or an item, for our own station and for a station known only from the internet (`heard_is` > 0 and nothing on the radio: a message goes out by radio only); true for every other station, also one whose position says it takes none (`may_not_message`) |
| `may_not_message` | boolean |  | the station's latest position says it takes no messages (it began with `!` or `/`, or was a Mic-E one whose comment begins with the type code `'`) and it never sent a message or an ack: the conversation says a message may not be read there |
| `radio_choice` | integer \| null |  | the radio the operator chose for messages to the station (`station_radio`), its id, while that radio is enabled; null for the daemon's choice (plan rule 3.2), and while the radio chosen is off |
| `radio_now` | integer \| null |  | the radio a message to the station goes out on now, its id: the choice while it is in force, else the radio that heard the station most recently within six hours, a local one (Packet, LoRa) before Mercury, else the radio that heard it last, else the first radio that can send, in the order of the boxes; the email radio for the email gateway. Null for a station that takes no message and while there is no radio. A message on its way keeps its own (`radio_now` of its row). The page shows Route, the path and the radio's state of this radio |
| `replies` | { [key: string]: string } |  | the path a message or an ack of ours to the station goes by on each radio that carries no path (Mercury), by the radio's id as text: the gateway its latest packet there came by, then WIDE2-1 when a digipeater stood before the gateway, calls separated by commas, without RFONLY; a radio that carries a path, and one on which they go direct, has no entry |
| `paths` | { [key: string]: string } |  | the path the operator set for the station on each radio (`set_station_path` with `radio`), by the radio's id as text: calls separated by commas, empty for direct; a radio with none set has no entry (radio 1's is `path` of the topic `station_prefs` too) |
| `track` | [time, number, number][] |  | the latest 50 positions, oldest first, as [time, lat, lon]; a new one only when the station moved more than 10 m or 5 minutes passed (max 50 items) |

### PacketRow

One packet heard or sent. The rows are the values of the topic `packets`, keyed by `id` as text: the daemon holds the latest 200, a packet that comes is a `set` and the one that falls out of the
200 a `del`. The page shows them newest first (the highest id).

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | counts up in the order the packets came in this run of the daemon; not kept in the database (>= 0) |
| `heard_at` | time |  | UTC, ISO 8601 with a Z |
| `direction` | "in" \| "out" |  | heard on the air, or sent by us |
| `source` | string |  | who sent the frame we heard; for a third-party packet the iGate (see `gate`); for a packet from the internet the station that sent it |
| `sender` | string |  | the station the packet is from: `source`, or for a third-party packet the source of the packet inside it |
| `destination` | string |  |  |
| `path` | string[] |  | the digipeaters, the one that repeated it marked with `*`; for a packet from the internet everything between the destination and the colon of the line (`TCPIP*`, the q-construct `qAC`, the server `T2FINLAND`) |
| `kind` | "position" \| "message" \| "object" \| "item" \| "status" \| "other" \| "undecoded" |  | a telemetry report is `other`; its `decoded.type` is `telemetry` |
| `route` | string |  | how a packet that was heard on the radio reached us: `direct`, `via OH2RCH-2`, `via ? → OH2RCH-2`, `via OH7JHF-1 (internet)` for a third-party packet; empty for a packet of ours and for one from the internet |
| `radio_id` | integer \| null |  | the radio the packet came on or went out on, its id (a row of the topic `radios`, a removed one too); null for a packet from the internet |
| `snr` | number \| null |  | the signal-to-noise ratio the radio measured of the frame, dB, tied to the frame where it was read (the Mercury modem and the Dummy Mercury radio give it); null for a packet of ours, one from the internet and one of a radio that gives none (a KISS TNC) |
| `rssi` | number \| null |  | the received strength the radio measured of the frame, dBm; null as `snr` is, and for the Mercury modem, which gives none |
| `via` | "rf" \| "rf-gated" \| "is" \| "dummy" |  | the channel the packet came by, set once where it was made: `rf` heard on the radio (direct or by digipeaters; every packet of ours too), `rf-gated` heard on the radio as a third-party packet that an iGate put on the air, `is` received from APRS-IS over the internet (never on the air), `dummy` made up by the Dummy radio (it works as `rf` does and never goes to the internet) |
| `gate` | string |  | the iGate, for a third-party packet (`via` is `rf-gated`): `source` and `path` are those of the frame we heard (the iGate's), `decoded` is the packet inside it; empty for any other packet |
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
| `radio_id` | integer \| null |  | the radio a message that came in came on, its id; null for a message of ours (its attempts say) and for one from the internet or kept before the radio was |
| `radio_now` | integer \| null |  | for a message of ours on its way (`sending`, `queued`), the radio its next attempt goes on: the one its first attempt went on, which it keeps until it ends unless Route changes or that radio is switched off, else the station's radio now (plan rule 3.2); null for every other message and while there is no radio it may go on. The page shows Route, the path and the radio's state of this radio |
| `state` | "queued" \| "sending" \| "acked" \| "rejected" \| "failed" \| "unconfirmed" \| "cancelled" \| "received" \| "overheard" |  | `queued`: it waits, with no attempt made, for another message of ours to the same station to be acked, rejected, failed or cancelled (one message to a station is on the air at a time; one not expected to be acked, given 1 or 2 attempts, never waits); it can be cancelled, and becomes `sending` when its turn comes; `sending`: attempts are being made; `acked`: the addressee acknowledged it; `rejected`: the addressee refused it; `failed`: no answer after the last attempt, or the reason in `failure`; `unconfirmed`: no answer after the last attempt of a message that was given 1 or 2 attempts (the station is not expected to ack; a late ack still settles it); `cancelled`: stopped by the page; `received`: it was sent to us; `overheard`: it was sent to another station and we heard it (`from_call` sent it, `to_call` is who it is for) |
| `failure` | "too_long_for_radio" \| null |  | why a `failed` message failed when it is not that no answer came: `too_long_for_radio`, its frame does not fit the radio it goes out on (it may have been sent before the radio changed; sent again, it is refused with `message.too_long_for_radio` while it does not fit); null for every other message, and for a failed one that had no answer |
| `attempts` | integer |  | how many times it has been transmitted (at most `attempts_max`: 0, 32, 64, 128, 256, 512, 1024 ... seconds after the first, no wait longer than 960) (>= 0) |
| `attempts_max` | integer |  | how many attempts the message was given when it was sent: 4, 2 for the email gateway `EMAIL-2`, 1 for a bulletin (messages from before the count was fixed have their own, up to 10) (>= 1, <= 10) |
| `last_attempt_at` | time \| null |  | when it was transmitted last; null until the first attempt (the TNC may be away) |
| `acked_at` | time \| null |  | when the acknowledgement was heard |
| `attempts_detail` | AttemptRow[] |  | for a message of ours, each attempt made (`attempts` of them, the oldest first; fewer for a message sent before the delivery chain was kept, none until the first attempt) with the hops of its path that a copy of our own message was heard back with; a hop heard is a `set` of the message's row. Empty for a message that came in |
| `snr` | number \| null |  | the signal-to-noise ratio of the packet that carried it, dB: for a message that came in, its own packet's; for one of ours, the ack's (or the reject's) that settled it, null until one came; null too when that packet's radio gave none and for a message kept before readings were |
| `rssi` | number \| null |  | the received strength of that packet, dBm; null as `snr` is, and for the Mercury modem, which gives none |
| `route` | string |  | how a message that was heard reached us (from the path of the first copy heard): `direct`, `via OH2RCH-2`, `via OH2RCH-1 → OH2RCH-3`, `via OH7JHF-1 (internet)` for a third-party packet an iGate put on the air; empty for one of ours and for one heard before this was kept |
| `seal` | "" \| "key" \| "key_other" \| "open" \| "shut" |  | what the message is besides text (encrypted messages, a daemon started with `--encryption`): empty for a plain message; `key` an announcement of the sender's public key (`send_key`; for one that came in, the key was taken, or is the one kept already); `key_other` an announcement that differs from the key kept for the station, not taken (`forget_station_key` first); `open` an encrypted message that was read, `text` is what it says (for one of ours, what was written); `shut` an encrypted message that cannot be read here (no key from the sender, no key of ours, or not for us), `text` is the ciphertext as it came |

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
| `telemetry` | TelemetryFields \| null | optional | the base-91 telemetry `\|ss11\|` the comment carried (APRS 1.2), taken out of the `comment`; null when there was none (default `null`) |
| `frequency` | FrequencyValues \| null |  | the local information the comment began with (`145.775MHz T100 -060 R40k`), or the name of a frequency object with the fields of its comment, taken out of the `comment`; null when there was none |
| `storm` | StormValues \| null |  | the storm data the comment of a position with the symbol `@` began with (`/HC/150^200/0980>090&030%040`), taken out of the `comment`; null when there was none |
| `sign` | string \| null |  | the characters of a signpost (symbol `\m`): `55` for a comment that began `{55}`, taken out of the `comment`; null for any other position |
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
| `frequency` | FrequencyValues \| null |  | the frequency the text began with (`>145.775MHz T100`), taken out of the `text`; null when there was none |

### DecodedTelemetry

A telemetry report (`T#005,199,000,255,073,123,01101001`). The definitions of the channels are messages of the station, applied by the daemon: see `telemetry` of the station.

| field | type | | description |
|---|---|---|---|
| `sequence` | integer \| null |  | the sequence number; null for the `MIC` of a Mic-E unit |
| `analog` | number[] |  | the analog values as sent, 1 to 5 (APRS 1.2: any width, signed, with a decimal point) |
| `bits` | string |  | the digital values as a text of 0 and 1, B1 first: up to eight, empty when there were none |
| `comment` | string |  |  |
| `type` | "telemetry" |  |  |

### DecodedOther

A data type that is recognised but not (fully) decoded: a positionless weather report is decoded (`weather`, `timestamp`), the station capabilities and an Agrelo DF report are read into `items`.

| field | type | | description |
|---|---|---|---|
| `type` | "other" |  |  |
| `kind` | "weather" \| "nmea" \| "query" \| "test" \| "capabilities" \| "agrelo-df" \| "shelter" \| "space-weather" \| "third-party" \| "user-defined" \| "telemetry" \| "unknown" |  | what kind of packet it is: one of these words, which the page says in its words; `telemetry` is one that is not a report, `unknown` a data type the parser does not know |
| `text` | string |  | the whole information field |
| `weather` | DecodedWeather \| null |  | the observation of a positionless weather report (`_`); null for anything else |
| `items` | { [key: string]: string } \| null |  | `capabilities`: the items of the list by token (`IGATE`, `MSG_CNT`...), the value empty for a token alone; `agrelo-df`: `bearing` and `quality`; null for anything else |
| `timestamp` | time \| null |  | the time of a positionless weather report (its MMDDhhmm, resolved to the latest such time that is not in the future) |

### DecodedUndecoded

A field that should have decoded and did not.

| field | type | | description |
|---|---|---|---|
| `type` | "undecoded" |  |  |
| `code` | "empty" \| "position" \| "mice" \| "message" \| "nmea" \| "damaged" |  | what could not be read, which the page says in its words (the log has the parser's own): `empty` the information field is empty; `position` a position (of an object or an item too); `mice` a Mic-E position; `message` a message; `nmea` a GPS sentence; `damaged` anything else, and a packet kept before there was a code |
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
| `telemetry` | TelemetryFields \| null | optional | the base-91 telemetry `\|ss11\|` the comment carried (APRS 1.2), taken out of the `comment`; null when there was none (default `null`) |
| `frequency` | FrequencyValues \| null |  | the local information the comment began with (`145.775MHz T100 -060 R40k`), or the name of a frequency object with the fields of its comment, taken out of the `comment`; null when there was none |
| `storm` | StormValues \| null |  | the storm data the comment of a position with the symbol `@` began with (`/HC/150^200/0980>090&030%040`), taken out of the `comment`; null when there was none |
| `sign` | string \| null |  | the characters of a signpost (symbol `\m`): `55` for a comment that began `{55}`, taken out of the `comment`; null for any other position |

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
| `keepalive_checks` | integer |  | times the keep-alive checked that the radio is there (after 60 seconds of nothing heard) (>= 0) |
| `watchdog_probes` | integer |  | times the watchdog probed a silent radio (the same sequence as a check, every 30 seconds) (>= 0) |
| `port_reopens` | integer |  | times the port was closed and opened again (every 5th probe of a silent radio) (>= 0) |
| `digipeated` | integer |  | frames the digipeater sent again for other stations on this radio, the pairs' passed frames among them (>= 0) |
| `digipeated_at` | time \| null |  | when the latest of them went out; null for none yet |
| `digipeat_held` | integer |  | frames the digipeater left unsent because it had already sent the most it sends in a burst (`BURST_MAX` in 10 seconds) (>= 0) |
| `passed` | PassStats[] |  | what the pairs passed onto this radio, one entry for each radio packets came from, in the order of its id; empty while none |

### ConfigValues

The settings: each key of the station's settings (`station/call`, `beacon/interval_min`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic
`config`, told again after every save, though nothing differs.

| field | type | | description |
|---|---|---|---|
| `values` | { [key: string]: string } |  | the settings in force, key to text; every key is there (the keys of `CONFIG_KEYS`: the station's settings, and `serial/last_port`, the port radio 1's search found last, which the page shows and does not set) |
| `defaults` | { [key: string]: string } |  | the same keys with their defaults, for a form's reset |
| `radio_values` | { [key: string]: string } |  | the radios' own settings in force, `radio/<id>/<key>` to text, every field of its kind for each radio that is not removed (the fields of `RADIO_TYPES`), and the station's settings of the radios (`email/radio`, the id of the radio chosen for email, empty for none chosen: the radio in force is `status.email_radio`): what `set_config` takes beside `values`; kept apart from `values`, whose form shows none of them; and both keys of every two radios that are not removed and may form a pair (both transmit, both Dummy or both real), enabled or not: `pair/<low>/<high>/enabled` (`true` or `false`) and `pair/<low>/<high>/ssid` (1 to 15, the SSID of the pair's call on the station's base call; empty while none is chosen, and a pair switched on is given the highest free one), by the radios' ids, low first |
| `radio_defaults` | { [key: string]: string } |  | the same keys with their defaults (the field's of the radio's kind; a pair's `false` and empty) |
| `urls` | string[] |  | where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off (with `https` on, the https addresses) |
| `https` | HttpsState |  | the secure connection: whether it is served, its port, the fingerprint of the authority's certificate (which `GET /neoaprs-ca.crt` downloads), and why not when it could not start |

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

### AlertWhen

When the operator is told about a station: any of the three, each once for each time it happens (it is not told again for every packet), by the message `station_alert` to every page and by the alert command of
the settings (`messages/alert`, `messages/alert_command`), as a message to us is.

| field | type | | description |
|---|---|---|---|
| `on_air` | boolean |  | a packet of the station is heard after it was silent for 30 minutes or more, or for the first time; a packet over the internet counts while `igate/enabled` is on |
| `within_km` | integer \| null |  | its position comes from farther to this many km from us or nearer (it is outside again only some way beyond: a tenth more, at least 0.5 km); null if the distance is not watched. A station that is that near already when the alert is set is not told until it has been outside (>= 1, <= 1000) |
| `direct` | boolean |  | a packet of it is heard direct (no digipeater) after none was for 30 minutes or more |

### AlohaCircle

The ALOHA circle of one radio: the distance within which the stations that radio heard would fill its 1200 baud channel (WB4APR's method, worked out again every minute).

| field | type | | description |
|---|---|---|---|
| `radio` | integer |  | the radio's id |
| `km` | number |  | the radius round our position, in km to a tenth (>= 0) |

### AreaValues

An area object (the symbol `\l`): its shape and colour, and how far down and to the right of the object's position it reaches.

| field | type | | description |
|---|---|---|---|
| `shape` | "open circle" \| "line" \| "open ellipse" \| "open triangle" \| "open box" \| "filled circle" \| "line down-left" \| "filled ellipse" \| "filled triangle" \| "filled box" |  | the shape, which the page says in its words |
| `colour` | "black" \| "blue" \| "green" \| "cyan" \| "red" \| "violet" \| "yellow" \| "gray" \| "dim black" \| "dim blue" \| "dim green" \| "dim cyan" \| "dim red" \| "dim violet" \| "dim yellow" \| "dim gray" \| "unknown" |  | the colour, which the page says in its words; `unknown` for a number the specification has no colour for |
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
| `radio_id` | integer \| null |  | the radio the attempt went out on, its id (a row of the topic `radios`); null for an attempt kept before the radio was |

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

### CardLevelsRow

The radio's sound card's own levels (the radio's `tx_card` and `rx_card` set them): a slider is drawn only where the card has the control, at the card's level.

| field | type | | description |
|---|---|---|---|
| `tx` | integer \| null |  | the card's playback level in percent, what the radio is given to transmit (ALSA's Speaker, PCM or Master control; the playing device's master volume on Windows); null where the card has no such control, the radio has no sound card or its card was never read (>= 0, <= 100) |
| `rx` | integer \| null |  | the card's capture level in percent, what it takes from the radio (ALSA's Capture or Mic control; the recording device's master volume on Windows); null as `tx` (>= 0, <= 100) |
| `read` | boolean |  | the levels are the card's: its card was read in this run of the daemon, or there is nothing to wait for (this system has no mixer, the radio has no sound card of its own); false while an enabled radio's card was not read yet, and for a radio that is off and was never read in this run. While false the page draws neither the slider nor the modem's - and +, so that the row has one shape from its first paint |

### ChannelHours

The packets one radio, or the internet, heard in each hour.

| field | type | | description |
|---|---|---|---|
| `radio` | integer \| null |  | the radio that heard them, its id (a row of the topic `radios`, a removed one too); null for the internet |
| `counts` | integer[] |  | the packets heard in each hour from the message's `start`, the oldest first, `hours` of them (an hour with none is 0) |

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

### FrequencyRow

A frequency the project suggests for the HF radio.

| field | type | | description |
|---|---|---|---|
| `band` | string |  | the band, `40 m` |
| `dial` | string |  | the dial with its mode, `7.0541 MHz USB` |

### FrequencyValues

A frequency to call on, from the local information at the start of a comment, a status text or the name of a frequency object (`145.775MHz T100 -060 R40k`); null where the text did not say.

| field | type | | description |
|---|---|---|---|
| `mhz` | number |  | the transmit frequency, MHz |
| `tone_hz` | integer \| null |  | the CTCSS tone of `Tnnn` or `Cnnn`, whole hertz (the tenths are dropped: 107 is 107.2) |
| `tone_both` | boolean |  | `Cnnn`: the tone is needed to receive as well |
| `tone_off` | boolean |  | `Toff`: no tone and no DCS code |
| `dcs` | string \| null |  | the DCS code of `Dnnn`, three digits as sent |
| `tone_burst` | boolean |  | `1750`: a 1750 Hz tone burst opens the repeater |
| `narrow` | boolean |  | the first letter of the tone field was lower case: narrow modulation |
| `offset_khz` | integer \| null |  | the offset from the transmit frequency in kHz (`-060` is -600); 0 is simplex; null when the standard offset is meant |
| `range_km` | number \| null |  | the nominal range (`R25m` is 40.2 km) |
| `rx_mhz` | number \| null |  | a separate receive frequency (`FFF.FFFrx`), MHz |

### GeneralAsked

A general query sent from here: one press, on one or more radios.

| field | type | | description |
|---|---|---|---|
| `kind` | "aprs" \| "igate" \| "wx" |  | which query: `aprs` (?APRS?), `igate` (?IGATE?) or `wx` (?WX?) |
| `query` | string |  | the information field it went with, `?APRS?`, `?IGATE?` or `?WX?` |
| `radios` | integer[] |  | the radios it went on, their ids, in the order of their boxes; what any of them heard is counted in `new` |
| `at` | time |  | when it was sent |
| `path` | string[] \| null |  | the path it went by on the radios that carry one, `RFONLY` last when it was RF only; empty for no digipeaters; null when none was given and those radios' own paths differ |
| `until` | time |  | when the counting of `new` ends, two minutes after it was sent |
| `new` | string[] |  | the calls of the stations heard on one of its radios (not as a third-party packet, not from the internet) between the query and `until` that this radio had not heard in the ten minutes before it, in the order they were heard, each once whatever number of radios heard it: most are answers, but a station cannot be told to answer, so this is no more than who spoke after a quiet spell |

### GeneralSent

The last query of a kind on one radio.

| field | type | | description |
|---|---|---|---|
| `kind` | "aprs" \| "igate" \| "wx" |  |  |
| `radio` | integer |  | the radio, its id |
| `at` | time |  | when it went on that radio |

### GeneralState

The general queries sent from here: the last one of each kind. Forgotten when the daemon stops. Told whole as it changes.

| field | type | | description |
|---|---|---|---|
| `asked` | GeneralAsked[] |  | the last query of each kind, the oldest first; empty before one |
| `by_radio` | GeneralSent[] |  | when the last query of each kind went on each radio, the oldest first: the wait before the next of a kind is each radio's, and a query waits for every radio it would go on (`general.too_soon`) |

### GpsState

The GPS receiver and what the beacon does with it: the latest fix, whether it can be used, and the beacon of a moving station. Told whole as it changes, at most once a second.

| field | type | | description |
|---|---|---|---|
| `source` | "off" \| "gpsd" \| "serial" |  | `gps/source` as in force: where the fixes come from |
| `state` | "off" \| "connecting" \| "no_fix" \| "fix" \| "stale" |  | `off`: no source is set; `connecting`: the line to gpsd or the receiver is not up and no fix has come; `no_fix`: it is up and the receiver has no fix; `fix`: the latest fix is fresh; `stale`: the latest fix is older than 120 seconds and is not used (a mobile beacon sends nothing on it) |
| `reason` | "" \| "no_port" \| "no_address" \| "held" \| "no_answer" |  | why there is no fix to use, as a code the page says in its words, where `state` does not say it already (the log has the feed's own words): `no_port` no port of the receiver is set; `no_address` no address of gpsd is set; `held` the receiver's port is held by a radio; `no_answer` the receiver or gpsd does not answer, or its line was lost; empty for `off`, `fix`, `stale` and a plain wait or no fix |
| `lat` | number \| null |  | the latest fix, degrees north; null before the first fix of the source (a stale fix is still told, with its `fix_at`) |
| `lon` | number \| null |  | the latest fix, degrees east |
| `altitude_m` | number \| null |  | metres above mean sea level; null when the fix has none |
| `speed_kmh` | number \| null |  | kilometres per hour; null when the fix has none |
| `course_deg` | integer \| null |  | degrees from north, 0 to 359; null when the fix has none |
| `satellites` | integer \| null |  | the satellites used for the fix; null when the source does not say |
| `fix_at` | time \| null |  | when the latest fix was received, by the daemon's clock |
| `mobile` | boolean |  | `gps/source` is not `off`: the beacon follows the GPS. With no fresh fix nothing is sent at all (never the home position), which `state` and `reason` say |
| `next_beacon_at` | time \| null |  | when the next beacon by time is due, for the speed of the latest fix (a turn sends one sooner); null unless the beacon is mobile and has a fresh fix and has sent its first |
| `last_beacon_reason` | "" \| "start" \| "time" \| "turn" \| "request" |  | why the latest mobile beacon of this run went out: `start` (the first fix), `time`, `turn` (a corner), `request` (Beacon now); empty before the first |
| `last_beacon_at` | time \| null |  | when it went out; null before the first |

### HeardOn

What one radio heard of a station.

| field | type | | description |
|---|---|---|---|
| `count` | integer |  | how many of the packets of the air (`rf`, `rf-gated` and `dummy` alike) came on the radio (>= 1) |
| `last_at` | time \| null |  | when the latest of them did; null when that is not known |

### HopRow

One digipeater of the path an attempt went by, and whether a copy of our own message was heard back with that hop used.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the digipeater as the path named it (`OH2RCH-2`, or an alias such as `WIDE1-1`); once heard, the call that did it, which replaces an alias |
| `heard` | boolean |  | a copy was heard by radio with this hop's has-been-repeated bit set (or a later hop's: a hop works the first unused address) |
| `heard_at` | time \| null |  | when the first copy that showed the hop was heard (by radio if there was one, else over the internet); null when it was not heard |
| `by_internet` | boolean |  | a copy gated back by an iGate as a third-party packet showed the hop used; with `heard` false the hop is known only that way |

### HttpsState

The secure connection (`web/https`) as the daemon has it.

| field | type | | description |
|---|---|---|---|
| `on` | boolean |  | the page is served over https right now (`web/https` and `web/network` are on, and it started) |
| `port` | integer |  | the https port; 0 while it is not served |
| `fingerprint` | string |  | SHA-256 fingerprint of NeoAPRS's certificate authority, `AB:CD:...`, for a person to compare with what the device shows when the certificate is installed; empty while it is not served |
| `reason` | "" \| "no_library" \| "clock" \| "certificates" \| "no_port" |  | why the secure connection could not start or go on, when it was asked for, as a code the page says in its words (the log has the details): `no_library` this installation cannot make it; `clock` the clock of this computer is not set; `certificates` the certificates could not be made, read or loaded; `no_port` no port after the page's own was free for it; empty otherwise |

### IgateState

The login to APRS-IS (neoaprs/services/igate.py): it shows the internet's stations (`igate/enabled`), puts what the radios hear on APRS-IS (`igate/gate`, the iGate), or both, and nothing from APRS-IS is
ever sent on the air. Whether it is connected, to which server, and what it has done since the daemon started. Told whole as it changes, at most once a second.

| field | type | | description |
|---|---|---|---|
| `enabled` | boolean |  | `igate/enabled` (Show Internet stations) as in force |
| `gate` | boolean |  | `igate/gate` (Send what I hear) as in force: what the radios hear is put on APRS-IS while `state` is `connected` |
| `state` | "off" \| "connecting" \| "connected" \| "listening" \| "unverified" |  | `off`: both ticks are off; `connecting`: not logged in (yet, or again after a loss, or waiting for what `reason` says is missing); `connected`: logged in and verified, packets are gated; `listening`: logged in without a passcode (`gate` is off), so that nothing is gated and the stations of the internet are read only; `unverified`: the server did not accept the passcode, nothing is gated (the connection reads, as `listening` does) and the login is not tried again with another until the settings change |
| `server` | string |  | the name the server gave at the login (`T2FINLAND`); empty until it has answered |
| `reason` | "" \| "no_server" \| "no_call" \| "unreachable" \| "offline" \| "not_server" \| "lost" \| "unverified" |  | why it is not connected, as a code the page says in its words (the log has the connection's own): `no_server` no server is set; `no_call` our call is not set or is none; `unreachable` the server cannot be reached; `offline` the server's name cannot be looked up (no connection); `not_server` it answered as no APRS-IS server, or not in time; `lost` the connection ended; `unverified` the server did not accept the password; empty while `connected`, `listening` and `off` |
| `gated` | integer |  | packets put on APRS-IS since the daemon started (>= 0) |
| `dropped` | { [key: string]: integer } |  | packets heard and not put on APRS-IS since the daemon started, by the reason: `tcpip` (TCPIP or TCPXX in the path), `nogate` (NOGATE or RFONLY), `query` (a generic query), `source` (the source is not a station), `own` (our own call), `duplicate` (gated in the last 30 seconds), `newline` (a CR or LF inside), `long` (more than 512 bytes), `frame` (not a UI frame, or a third-party header that is none), `offline` (heard while not connected), `not_air` (not heard on the radio: a packet from the internet or one the Dummy radio made up). A reason that has not happened is not a key |
| `last_gated_at` | time \| null |  | when the latest packet was gated; null before the first |

### InstallInfo

How this copy of the daemon was installed, which is what the steps of an update depend on (neoaprs/versions.py, neoaprs/cli/installkind.py).

| field | type | | description |
|---|---|---|---|
| `kind` | "windows-installer" \| "appimage" \| "macos-app" \| "deb" \| "uv-tool" \| "pip" \| "source" |  | `windows-installer` (the frozen program of the installer), `appimage`, `macos-app` (the Python inside NeoAPRS.app), `deb` (the Debian package, in /opt/neoaprs), `uv-tool` (`uv tool install` of the wheel, which releases before 0.16 offered), `pip` (a plain environment with the wheel) or `source` (a clone of the repository) |
| `appimage` | string |  | the AppImage file this runs from; empty for the other kinds |
| `service` | boolean |  | whether a service starts it: the systemd unit, the launchd agent or the Windows Run key |
| `arch` | string |  | the architecture of the file it was installed from: `amd64` or `arm64` for a .deb, `arm64` for the macOS app; empty for the other kinds, and for a machine the release has no file for |

### LayerReceiver

The own receiver's state, for its line in Settings. It says nothing of addresses or ports.

| field | type | | description |
|---|---|---|---|
| `state` | "looking" \| "connected" \| "receiving" \| "no_answer" \| "no_ais" |  | `looking` until its first answer or connection; `receiving` after an answer in the expected form (AIS: from the first AIS sentence of a connection); `no_answer` after a failure, a wrong answer or a lost connection; `connected` (AIS only) the connection is made and nothing has come yet (a receiver with no ship in range is silent); `no_ais` (AIS only) the source sent something that is not AIS first, or ended the connection without an AIS sentence |
| `things` | integer |  | what it gave with a position at its last answer (aircraft), or the ships held now (AIS) (>= 0) |
| `heard_at` | time \| null |  | its last answer in the expected form (AIS: the last sentence decoded); null before one |

### LayerThing

An aircraft or a ship, as its source tells it. Every field is always there; one that is not the layer's is empty or null.

| field | type | | description |
|---|---|---|---|
| `id` | string |  | an aircraft's ICAO address as the source gives it, lower case (it may begin with `~`); a ship's MMSI |
| `lat` | number |  |  |
| `lon` | number |  |  |
| `at` | time |  | the time of its position |
| `heading_deg` | integer \| null |  | where the mark points; null: no direction (drawn as a diamond) (>= 0, <= 359) |
| `speed_kmh` | number \| null |  | (>= 0) |
| `name` | string |  | an aircraft's flight, a ship's name; empty when none |
| `emergency` | boolean |  | an aircraft that says it is in an emergency (or squawks 7500, 7600 or 7700) |
| `altitude_m` | integer \| null |  | an aircraft's height |
| `vertical_ms` | number \| null |  | an aircraft's vertical speed in metres a second, above zero climbing; null when not told (a ship's is null) |
| `registration` | string |  | an aircraft's registration (`OH-LZA`); empty when not known |
| `type` | string |  | an aircraft's type as the source names it; empty when not known |
| `category` | string |  | an aircraft's emitter category as the source gives it, upper case (`A3`, `A7`, `B1`); empty when not known |
| `designator` | string |  | an aircraft's ICAO type designator, upper case (`A321`, `EC35`); empty when not known |
| `ship_type` | integer \| null |  | a ship's AIS type of ship and cargo; null when not known (>= 1, <= 99) |
| `course_deg` | integer \| null |  | a ship's course over ground, an aircraft's ground track; null when not told (a heading is not a course) (>= 0, <= 359) |
| `destination` | string |  | a ship's destination as it gave it; an aircraft's: the ICAO code of the airport it is going to, upper case; empty when not known |
| `origin` | string |  | an aircraft's departure: the ICAO code of the airport it left, upper case; empty when not known |
| `origin_place` | string |  | the place of the airport `origin` names, from the table the program carries; empty when `origin` is empty or not in the table |
| `destination_place` | string |  | the place of the airport `destination` names, from the table the program carries; empty for a ship, and when `destination` is empty or not in the table |

### LayerTrail

The way one thing went: its id, and its places as [lon, lat, time], oldest first.

| field | type | | description |
|---|---|---|---|
| `id` | string |  |  |
| `points` | [number, number, time][] |  |  |

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
| `name` | string |  | `basemap.pmtiles` (the detailed map) or `basemap-world.pmtiles` (the world: zoom 4 when it is the one that ships with the program, zoom 5 when the daemon made it) |
| `bytes` | integer |  | (>= 0) |
| `modified` | time |  | when the file was made |
| `bbox` | number[] \| null |  | the area it covers, [west, south, east, north] in degrees, as its header says; null for a file whose header cannot be read (max 4 items) |
| `min_zoom` | integer \| null |  |  |
| `max_zoom` | integer \| null |  | the deepest zoom it has tiles for; the page draws a deeper one from these |
| `build` | string |  | the day (`20261022`) of the Protomaps build it was cut from; empty if not known (a file made by hand) |

### MapLayer

One layer of traffic in the topic `map`: where its things come from now and what the station is offered.

| field | type | | description |
|---|---|---|---|
| `layer` | "aircraft" \| "ships" |  |  |
| `source` | "none" \| "adsbfi" \| "adsblol" \| "fintraffic" \| "aisstream" \| "radarcape" \| "receiver" |  | the source in force: the one chosen in Settings while it is offered, else `none` (nothing is asked, and the Layers box has no row) |
| `offered` | ("none" \| "adsbfi" \| "adsblol" \| "fintraffic" \| "aisstream" \| "radarcape" \| "receiver")[] |  | the sources the Settings list holds, `none` first: `fintraffic` only where the map's circle reaches its waters; `aisstream` (with the operator's own key, `map/ships_key`) everywhere |
| `receiver` | LayerReceiver \| null |  | the own receiver's state while `source` is an own receiver (`radarcape` or `receiver`); else null |
| `problem` | "" \| "key_refused" |  | why the service in force gives nothing, where the operator can mend it: `key_refused` AISStream did not take the key of `map/ships_key` (asked again after a longer wait, and at once when the key is saved; cleared by a connection that is taken); empty otherwise |

### MapProblem

Why a map job failed, as a code the page says in its words, with the values of its sentence (the log has the details).

| field | type | | description |
|---|---|---|---|
| `code` | "no_position" \| "busy" \| "slow" \| "unreachable" \| "no_build" \| "too_big" \| "no_space" \| "failed" |  | `no_position` the station has no position; `slow` the map server was too slow; `unreachable` it could not be reached; `no_build` no daily build was found (`days`: how far back it was looked for); `too_big` the map would be bigger than it may be (`size` and `max`, in MB); `no_space` the disk is full; `failed` anything else (the log says why) |
| `params` | { [key: string]: integer } |  | the values of the sentence, by name; empty for a code that has none |

### MapRetry

A download that did not move for a while is begun again: the page says "no progress: trying again (2 of 3)".

| field | type | | description |
|---|---|---|---|
| `attempt` | integer |  | the try that is begun (>= 1) |
| `tries` | integer |  | the tries in all (>= 1) |

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

The base map: the files, the area and detail the settings ask for, the size estimated, the job that is running, the ALOHA circles and the layers of traffic. The value of the topic `map`, told whole at most four times a second.

| field | type | | description |
|---|---|---|---|
| `state` | "none" \| "estimating" \| "downloading" \| "ready" \| "error" |  | `none`: there is no detailed map. `ready`: there is one. `estimating` and `downloading`: a job is running (`step` and `percent` say how far). `error`: the last job failed and `problem` says why; the map files are as they were |
| `step` | "" \| "build" \| "world" \| "area" |  | what the running job is doing: looking for the latest build (`build`), making the world map (`world`) or the detailed map (`area`); empty while no job runs |
| `percent` | integer \| null |  | how far the step is; null when it cannot say (the build has no bar) (>= 0, <= 100) |
| `downloaded` | integer \| null |  | the size so far of the file the step is making, in bytes (it grows while the download moves); null when no file is being made yet (>= 0) |
| `retry` | MapRetry \| null |  | a download that has not moved for a while is begun again: which try this is; null when all is well |
| `blocked` | "" \| "no_position" \| "busy" |  | why no job can be started now: `no_position` the station has no position, `busy` a job is running; empty when one can |
| `problem` | MapProblem \| null |  | why the last job failed; null if it did not, and while a job runs |
| `estimate` | MapSizeEstimate \| null |  | the latest dry run (`map_estimate`); null before one, and after a download |
| `radius_km` | integer |  | `map/radius_km` |
| `maxzoom` | integer |  | `map/maxzoom` |
| `box` | number[] \| null |  | the area those settings make round our position, [west, south, east, north]; null without a position (max 4 items) |
| `detail` | MapFileInfo \| null |  | `basemap.pmtiles`; null if it is not there |
| `world` | MapFileInfo \| null |  | `basemap-world.pmtiles`: the data folder's own when it has one, else the one that ships with the program; null if there is neither (a base map the page cannot draw) |
| `later` | boolean |  | the detailed map was begun without being asked for (a place was set, or the setup guide said the map is wanted) and could not be fetched yet, most likely for want of a connection; it is tried again at the next start. False once a job runs or a detailed map is there |
| `aloha` | AlohaCircle[] |  | the ALOHA circles round our position, one for each radio that is on whose type shares a 1200 baud channel (Packet) and whose stations heard fill it, in the order of the boxes; none without a position |
| `layers` | MapLayer[] |  | the layers of traffic, the aircraft and then the ships: where each one's things come from now, what Settings offers, and an own receiver's state |

### ModemState

The modem program behind a radio's line, while its type is one the daemon starts a modem for (the Mercury modem, Direwolf on a sound card): the program's state, whether it keys the radio now and whether
it hears a signal.

| field | type | | description |
|---|---|---|---|
| `state` | "stopped" \| "starting" \| "running" \| "waiting" |  | `starting`: the program was started (or a Mercury something else runs is not yet answering on its control port); `running`: its control port answers; `waiting`: it is not running, `reason` says why |
| `reason` | "" \| "not_installed" \| "stopped" \| "network" \| "no_port" \| "not_started" \| "sound_card" \| "keying" \| "keying_in_use" \| "keying_missing" \| "ports_taken" \| "receive_stalled" |  | why the modem is `waiting`, as a code the page puts in its own words in the language of the viewer (the log has the English): `not_installed` this installation carries no such program; `stopped` the program ended and is started again; `network` the program listens on the network and is not run; `no_port` no port was free for it; `not_started` the program could not be started or its configuration written; `sound_card` the program could not open its sound card (or, on Windows, find it among the devices) and was ended, another is to be chosen; `keying` the program could not open its keying device (or, on Windows, found several CM108 chips) and was ended, another way of keying is to be chosen; `keying_in_use` its keying port is in use by another program (Mercury: Windows error 5, or the device is busy) and the program was ended; it is started again after a back-off for as long as the radio is on; `keying_missing` its keying port is not there and the program was ended, started again in the same way; `ports_taken` another program listens on the KISS or control port of the modem's pair (most likely a Mercury the operator started himself): no modem is started beside it, no line connects to it, and the start is tried again after a back-off; the radio's type `mercury-own` is the one for such a Mercury; `receive_stalled` the program heard nothing (its receive side stalled) again after three restarts in an hour and is not started again until the radio is; empty unless the state is `waiting` |
| `mode` | string |  | the modem's mode, the same for every station of the type: `DATAC3` (Mercury), `AFSK1200` (Direwolf) |
| `keyed` | boolean |  | the modem keys the radio now: a frame is on the air (about four seconds), or the tune tone or the keying test is on |
| `busy` | boolean |  | another station's signal is on the channel and our frames wait: for 20 s at most (`BUSY_HOLD_MAX_SEC`), after which it is false while the channel stays busy, since nothing waits any more. The daemon judges it from the modem's spectrum (a signal as wide as a frame; a step in the noise or a carrier is none) while it reads that, else it is the modem's own fixed-threshold detector |
| `test` | "" \| "tune" \| "key" |  | `tune` while the tune tone is on (`radio_tune`), `key` during the keying test (`radio_key_test`); empty otherwise. Our frames wait while either is on |
| `snr` | number \| null |  | the signal-to-noise ratio of the latest frame decoded, in dB; null before one |
| `frames_keyed` | integer |  | how many times the radio was keyed since the modem started (>= 0) |
| `max_frame` | integer \| null |  | the longest packet the modem carries whole, in bytes (Mercury 123): a longer message is refused, a longer beacon has its comment cut; null for AX.25's own (Direwolf) (>= 1) |
| `sound_card` | string |  | the sound card the modem runs with (`mercury/sound_card`, or the daemon's choice while that is empty); empty for the system's default device |
| `frequencies` | FrequencyRow[] |  | the frequencies the project suggests, one to five, by band, the longest first: the list of the project's file (site/frequencies.json, asked a minute after the start and when a page sends `frequencies`), else the dial the version page names, else the built-in five; the page shows them in the Mercury radio's box as they are, with the words "suggested": they are not read from the radio (max 5 items) |
| `keying` | string |  | how it keys the radio (`mercury/keying`, or the daemon's choice while that is empty): `vox`, `cm108`, `rts:PORT` or `dtr:PORT` |
| `scope` | boolean |  | the daemon reads the modem's UI interface: the spectrum scope can be shown (`radio_scope`) and the transmit gain is set live; false for a modem without the interface (the page shows no scope, and a change of the gain restarts the modem) |
| `tx_gain_db` | integer |  | the transmit gain the modem runs with, in dB (`mercury/tx_gain_db`); the tune tone follows it (>= -20, <= 20) |
| `tx_peak_dbfs` | integer \| null |  | the peak of the latest transmission (a frame, or the tune tone) in whole dBFS, as the modem says it; 0 or more clips in the sound card; null before one, and while the interface is not read |
| `rx_level` | integer \| null |  | the receive level as it is now, on Direwolf's own scale (0 to about 200: about 50 for most stations, under 5 too low, over 110 too high; `LIMITS.sound_card` has the zones): said every two seconds and at each packet heard; null while its Direwolf does not run, and for a modem that has none (>= 0) |

### NoteSection

One version's section of the changelog.

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the version the section is of |
| `text` | string |  | the section as it is written, markdown: paragraphs, `- ` bullets, `**bold**` and `code` |

### OwnBulletinRow

One bulletin, announcement or group bulletin of ours: its text and where its schedule stands. The rows are the values of the topic `own_bulletins`, keyed by `slot` (`BLN1`): a bulletin that is posted, and
each time it is sent, is a `set` of its row, one that is deleted (`bulletin_unpost`) a `del`. One whose schedule is over stays, with a null `next_at`, until it is deleted.

| field | type | | description |
|---|---|---|---|
| `slot` | string |  | the addressee: `BLN1`, `BLNA`, `BLN3HAMS` |
| `group` | string |  | the group of a group bulletin (`HAMS`); empty for any other |
| `kind` | "bulletin" \| "announcement" \| "group" |  |  |
| `text` | string |  |  |
| `hours` | integer |  | how long it is sent after its first packet, in hours: 1, 2, 4, 8 or 12 for a bulletin and a group bulletin, 24, 72 or 168 for an announcement (>= 1, <= 168) |
| `posted_at` | time |  | when the text was posted |
| `sent` | integer |  | how often it was sent (>= 0) |
| `last_sent_at` | time \| null |  | when it was last sent; null while it has not been sent |
| `next_at` | time \| null |  | when it is sent next; null when its schedule is over (a bulletin: now, after 2 and 6 minutes, then every 20 minutes, 30 while a radio it goes out on is Mercury or LoRa; an announcement: the same early, then every hour; either until `hours` after the first); a repeat after the radio's random pause, which is never longer than the wait nor past the end |
| `radios` | integer[] |  | the radios it is set to go out on (Send on), their ids, ascending, one at least, kept also while off; the radios it goes on now are those of them that are on and can send (with one radio that can send, that one; with none of them on, none) |

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
| `path` | string \| null |  | the digipeaters it goes by, calls separated by commas, or `DIRECT` for none at all; null: the path of the setting `beacon/path` is used |
| `qru_group` | string |  | the group of QRU (1 to 8 upper-case letters and digits) a station that asks the addressee `QRU` for it is answered with this object in; empty for none |
| `on_request` | boolean |  | true: it is never sent on the decay schedule, only to a station that asks for it (`?APRSO`, or its QRU group); false: it is sent on the schedule |
| `radios` | integer[] |  | the radios it is set to go out on (Send on), their ids, ascending, one at least, kept also while off; the radios it goes on now are those of them that are on and can send (with one radio that can send, that one; with none of them on, none) |
| `state` | "live" \| "killing" |  | `live`: it is being sent on the decay schedule; `killing`: it was killed and its killed form is being sent (three times), then it is forgotten |
| `created_at` | time |  | when it was first made |
| `updated_at` | time |  | when it was last changed or killed |
| `sent` | integer |  | how often it was sent since it was last changed or killed (>= 0) |
| `last_sent_at` | time \| null |  | when it was last sent; null while it has not been sent (the call is not set, or the radio is away) |
| `next_at` | time \| null |  | when it is sent next: 1, 2, 4 ... minutes after the slot of the last packet, never more than the net cycle time of its path apart (30 minutes on Mercury and LoRa: the radio's floor), plus the radio's random pause, which is never longer than the wait; a time that has passed means it waits for the radio or for the call; null for one that is `on_request` |

### PassStats

What the pairs of radios passed onto this radio from one other radio since the daemon started.

| field | type | | description |
|---|---|---|---|
| `heard_on` | integer |  | the radio the packets were heard on, by its id (>= 1) |
| `sent` | integer |  | frames sent on this radio (>= 0) |
| `sent_at` | time \| null |  | when the latest of them went out; null for none yet |
| `held` | integer |  | frames left unsent by this radio's limits: the burst on a fast radio; the budget, its share for packets other than messages and acks, a station's share of messages, the 30-minute floor, a frame already waiting, or a keyed or busy channel past 30 s on a slow one (>= 0) |
| `too_long` | integer |  | frames left unsent because they are longer than this radio carries (>= 0) |

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

A serial port the system lists, or a Bluetooth device paired with it (Linux; on Windows a paired Bluetooth serial port is a COM port of the system's list). Nothing was opened or connected to find it.

| field | type | | description |
|---|---|---|---|
| `device` | string |  | the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`, `bt://AA:BB:CC:DD:EE:FF` for a paired Bluetooth device |
| `description` | string |  | what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say |
| `hwid` | string |  | the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say |
| `vid` | integer \| null |  | the USB vendor id of an adapter; null for a port that is not USB |
| `pid` | integer \| null |  | the USB product id of an adapter; null for a port that is not USB |
| `held_by` | integer \| null |  | the radio of the station that holds the port now (its id), 0 for the GPS receiver; null while none of ours does. A port another radio holds is not proposed, and the page greys it with the holder's name |
| `usb_group` | string \| null | optional | which USB device the port sits on together with the others of one radio (an opaque token: equal for a sound card and the serial ports on one radio's own USB hub, or on one USB device; neoaprs/usbtie.py); null where it is not known (Windows, macOS, a port that is not USB, a Bluetooth device). The page orders the keying lines by it and never shows it (default `null`) |

### PostHours

The Sent for a new post of each kind starts with, in hours: the one posted last of that kind, else 4, 72 and 4.

| field | type | | description |
|---|---|---|---|
| `bulletin` | integer |  |  |
| `announcement` | integer |  |  |
| `group` | integer |  |  |

### QruAsked

The request we sent last.

| field | type | | description |
|---|---|---|---|
| `text` | string |  | what was asked (`INFO`, `RP70 150`) |
| `at` | time |  | when it was sent |
| `radios` | integer[] |  | the radios it went on, their ids, in the order of their boxes |

### QruGroup

A group of objects a server serves near us.

| field | type | | description |
|---|---|---|---|
| `name` | string |  | the group, 1 to 8 upper-case letters and digits (`RP70`, `FOOD`) |
| `count` | integer |  | how many objects the group has in the server's range (>= 0) |

### QruServer

A QRU server that answered, as it last said.

| field | type | | description |
|---|---|---|---|
| `call` | string |  | the server's call |
| `groups` | QruGroup[] |  | the groups it serves near us, in the order it listed them; empty when it has only sent the closing line of a group |
| `max_objects` | integer \| null |  | the most objects it sends for one request; null when its list did not say |
| `range` | integer \| null |  | the range round us it serves, in `unit`; null when its list did not say |
| `unit` | "km" \| "mi" \| "" |  | the unit of `range` (kilometres or miles, as the server counts); empty when the list did not say |
| `at` | time |  | when it answered last |
| `sent` | string |  | its last closing line as it was heard (`Sent 5 RP70 Objects Max 5@50km de DF8LS-10`); empty before one |
| `sent_at` | time \| null |  | when the closing line was heard; null before one |
| `sent_objects` | integer \| null |  | how many objects its last closing line says it sent; null before one |
| `request` | string |  | the request its closing line answers, which Ask again sends once more (`TEST 150`); empty before a closing line, and when the request is not known |
| `received` | string[] |  | the names of the objects heard from the server, on a radio that request went on, since it, until `settles_at` (or the last answer, before a closing line); each is an ordinary object of the stations and the map |
| `settles_at` | time \| null |  | when the counting of `received` ends, 30 seconds after the closing line (a late object may still come); null before a closing line. Fewer `received` than `sent_objects` after it means objects were lost |
| `radio` | integer \| null |  | the radio its latest answer came on, its id: a request of one of its groups, and one asked again, goes on it; null when the packet named none |

### QruState

The servers that answered a request for local info, and the last request. What is older than an hour is forgotten, with the daemon's restart. Told whole as it changes.

| field | type | | description |
|---|---|---|---|
| `asked` | QruAsked \| null |  | the last request sent from here; null before one, and an hour after it |
| `servers` | QruServer[] |  | the servers that answered in the last hour, by call |

### RadioAllowed

What we decided the radio's type may do (neoaprs/radiotype.py `Allowed`): a control exists only where it is true.

| field | type | | description |
|---|---|---|---|
| `paths` | boolean |  | our frames on it may carry digipeaters: the path controls are shown for it; false: every frame goes direct |
| `digipeat` | boolean |  | it may repeat what it hears (its own Digipeater tick, `radio/<id>/digipeat`) |
| `smart_beacon` | boolean |  | a moving station's SmartBeaconing applies on it; elsewhere the timed beacon goes with the latest fix |
| `gateway_heard` | boolean |  | internet gateways hear its kind |
| `shared_channel` | boolean |  | it is a 1200-baud shared channel: the ALOHA circle is worked out from what it hears |

### RadioBeaconState

The radio's own beacon timer.

| field | type | | description |
|---|---|---|---|
| `last_sent` | time \| null |  | when our position last went out on it; null before one |
| `next_due` | time \| null |  | when the next timed beacon is due on it: its slot and the radio's random pause; null while none is planned (off, a moving station, the radio off) |
| `interval_min` | integer |  | the interval in force on it, in minutes: `beacon/interval_min` raised to the radio's own floor; 0 while the beacon does not go out on it (off, Send on not ticked, the radio off) (>= 0) |
| `problem` | RadioProblem \| null |  | why the latest beacon due on it did not go out (`transmit.off`, `beacon.not_sent`); null after one that did |

### RadioCan

What the radio's type can do (neoaprs/radiotype.py `Can`): the controls of its box.

| field | type | | description |
|---|---|---|---|
| `find` | boolean |  | Find my radio (a serial line: `find_radio` with this radio) |
| `terminal` | boolean |  | its line's log can be shown (`lines`) |
| `tune` | boolean |  | Tune (`radio_tune`) |
| `key_test` | boolean |  | the keying test (`radio_key_test`) |
| `scope` | boolean |  | the spectrum scope (`radio_scope`); whether it is shown now is the modem's `scope` |
| `tx_gain` | boolean |  | the transmit gain (`radio/<id>/tx_gain_db`) |
| `frequencies` | boolean |  | the station's suggested frequencies are shown in its box |
| `transmit` | boolean |  | it can send: false for a receive-only type, which is never a message's, the beacon's, an object's, a bulletin's or the email radio, and whose line is never written to |
| `rx_level` | boolean |  | its receive level is shown in its box (its modem's `rx_level`) |

### RadioChoices

The operator's own values of the radio where its kind has them (`radio/<id>/beacon`, `radio/<id>/status`, `radio/<id>/ask`, `radio/<id>/local_info`, `radio/<id>/path`, `radio/<id>/digipeat`), as they are in force.

| field | type | | description |
|---|---|---|---|
| `beacon` | boolean |  | Send on: the beacon goes out on this radio (with one radio on, it goes on that one whatever this says) |
| `status` | boolean |  | the status's Send on: the status report goes out on this radio; false by default (with one radio that can send on, on that one whatever this says; with several, while none that is on is ticked, on none); false for a radio that only receives |
| `ask` | boolean |  | Ask around's Send on: a general query (`general_query`) goes out on this radio; read as `status` is |
| `local_info` | boolean |  | Local info's Send on: the request to QRU that names no radio (`qru_ask`) goes out on this radio; read as `status` is |
| `path` | string \| null |  | the digipeaters of its frames as the setting holds them (empty: the recommended path of the station's symbol, `DIRECT`: none); null for a kind that has no path |
| `digipeat` | boolean \| null |  | its digipeater is on; null for a kind that may not repeat |

### RadioHold

A device the radio holds now in the station's table of resources: no other radio, and not the GPS receiver, is given it.

| field | type | | description |
|---|---|---|---|
| `resource` | "serial" \| "sound_card" \| "keying" \| "modem_ports" \| "gps" |  | what kind of device: a serial port, a sound card, the keying line's port, the port pair of a Mercury modem |
| `value` | string |  | the device as the table holds it: a serial port's resolved path (`/dev/ttyUSB0`, `COM3`), a sound card's id, the broadcast port of a Mercury pair (`8100`) |

### RadioLimits

What the radio's type cannot do (neoaprs/radiotype.py `Limits`): constants of the type.

| field | type | | description |
|---|---|---|---|
| `max_frame` | integer \| null |  | the longest AX.25 frame the radio carries whole, in bytes (Mercury: 123); null for AX.25's own |
| `beacon_min_min` | integer |  | the shortest beacon interval the radio takes, in minutes (Packet 20, Mercury 30): the station's interval is raised to it on this radio (>= 1) |
| `slow` | boolean |  | a frame holds the shared channel for seconds (HF, LoRa): what the pairs pass onto the radio is limited (`LIMITS.pass` of the page) |

### RadioProblem

Why a radio, or its beacon, does not do what it is set to, as a code the page puts in its own words, with the values its sentence is made of (the English of the log is not told).

| field | type | | description |
|---|---|---|---|
| `code` | "radio.not_connected" \| "radio.searching" \| "radio.silent" \| "radio.text_lines" \| "radio.incoming_port" \| "radio.write_timeout" \| "radio.resource_held" \| "modem.not_installed" \| "modem.stopped" \| "modem.network" \| "modem.no_port" \| "modem.not_started" \| "modem.sound_card" \| "modem.keying" \| "modem.keying_in_use" \| "modem.keying_missing" \| "modem.ports_taken" \| "modem.receive_stalled" \| "modem.receive_deaf" \| "transmit.off" \| "beacon.not_sent" |  | `radio.not_connected` its line is not open (`name`: the radio's name in the log); `radio.searching` the daemon looks for its port; `radio.silent` its line is open and the radio does not answer (`since`: when the latest byte came, UTC); `radio.text_lines` its line is open and the LoRa board on it sends text lines, not KISS: nothing is sent until it is set to KISS; `radio.incoming_port` its port is the computer's incoming Bluetooth port (Windows), which reaches no device (`port`); `radio.write_timeout` the last write to its port timed out (`seconds`): shown until a write goes through or a byte comes; `radio.resource_held` a device it is set to use is another's (`resource`: `serial`, `sound_card`, `keying`, `modem_ports` or `gps`; `holder`: the name of the radio that holds it, `GPS` for the GPS receiver; `held_by`: its id, 0 for the GPS receiver); `modem.<reason>` its Mercury modem is not running, `reason` as `ModemState.reason` says it; `modem.receive_deaf` its Mercury modem runs and hears nothing (its receive side stalled) and is started again soon; for its beacon `transmit.off` (RX only) and `beacon.not_sent` (`why`: the code of the reason, whose sentence the page has as the refusal `error.<why>`, and that reason's values) |
| `params` | { [key: string]: string \| integer \| number } |  | the values of the sentence, by name; empty for a code that has none |

### RadioRow

One radio of the station: what it is, how it is set, and how its line, its beacon and its modem are now. The rows are the values of the topic `radios`, keyed by `id` as text; a removed radio stays, marked,
so that the packets and messages that name it still have its name. A radio that is added is a `set` of its row; a change of its state, counters, lines, beacon or modem is a `set` of the row, told at most four
times a second; a change of the settings tells the topic whole.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | the radio's id (an integer the database gave it, never given again): what every other row and command names it by (>= 1) |
| `kind` | "fm" \| "hf" \| "lora" |  | the kind of radio, fixed when it was added: its tag's colour and the defaults follow it |
| `type` | string |  | its type, a `key` of `RADIO_TYPES` (ui/src/protocol/lists.ts), of its kind; it may change within the kind (`radio_change`) |
| `name` | string |  | the name the operator typed (at most 8 characters); empty for none: the page calls it by its kind and `number` (`Packet`, `Mercury 2`) in its own words |
| `number` | integer |  | its number within its kind: 1 for the first of the kind by id among the radios not removed (`Mercury 2` is 2); a removed radio keeps its own (>= 1) |
| `enabled` | boolean |  | its Enable is ticked (`radio_change` with `enabled`); false for a removed radio |
| `position` | integer |  | its place in the list of boxes (and of the radio a call no radio heard takes: the first that can send): the lowest first, then by id (>= 1) |
| `removed` | boolean |  | it was removed: its row stays so that what came by it keeps its name; it is no longer started, chosen or offered |
| `dummy` | boolean |  | its type is a Dummy radio: the traffic is made up and nothing goes on the air; its tag is dashed |
| `state` | "stopped" \| "connecting" \| "connected" \| "waiting" \| "silent" |  | its line: `waiting` is between two attempts to open it, or its line is open again after a write timed out and nothing has gone through or come since, `silent` the line is open and the radio does not answer (a check of the keep-alive got no byte at all in answer), nothing is sent until it does; `stopped` for a radio that is off or removed |
| `problem` | RadioProblem \| null |  | why it is not connected, while it is enabled and not connected; null otherwise |
| `stats` | TncStats |  |  |
| `lines` | TncLine[] |  | the latest 100 lines of what its line saw and did, oldest first; empty for a removed radio (max 100 items) |
| `limits` | RadioLimits |  |  |
| `allowed` | RadioAllowed |  |  |
| `can` | RadioCan |  |  |
| `choices` | RadioChoices |  |  |
| `beacon` | RadioBeaconState |  |  |
| `status` | RadioStatusState |  |  |
| `modem` | ModemState \| null |  | its modem, while its type is one the daemon starts a modem for (Mercury, Sound card); null for every other type and for a removed radio |
| `card` | CardLevelsRow |  | its sound card's own levels, read every two seconds while it runs and kept as read last while it is stopped or its card cannot be read; both null for a radio without a sound card of its own and before its card was read (`read` says which) |
| `holds` | RadioHold[] |  | the devices it holds now: a serial port, a sound card, a keying line, a Mercury port pair; empty while it holds none |

### RadioSent

What went out on one radio in the last 24 hours, by what it was.

| field | type | | description |
|---|---|---|---|
| `radio` | integer \| null |  | the radio it went out on, its id; null for what went to the internet |
| `beacons` | integer |  | our positions and statuses (>= 0) |
| `messages` | integer |  | our messages, bulletins among them (>= 0) |
| `acks` | integer |  | our acks and rejects of messages (>= 0) |
| `objects` | integer |  | our objects and items (>= 0) |
| `other` | integer |  | anything else of ours: answers to queries, telemetry (>= 0) |
| `repeated` | integer |  | the digipeater's copies of other stations' packets (>= 0) |

### RadioStatusState

The status report on the radio (services/rigstatus.py `on_radio`).

| field | type | | description |
|---|---|---|---|
| `last_sent` | time \| null |  | when our status report last went out on it; null before one |
| `next_due` | time \| null |  | when the next timed report is due on it: an interval after the slot of its last, and the radio's random pause; null while none is (the status does not go on it, the beacon or the status is off, none sent on it yet) |
| `interval_min` | integer |  | the interval in force on it, in minutes: `status/interval_min` raised to the radio's own floor (`limits.beacon_min_min` on HF and LoRa); 0 while the status does not go out on it (>= 0) |

### ReachValues

How a station's latest packet from the internet got there, read from the q-construct of its APRS-IS path.

| field | type | | description |
|---|---|---|---|
| `kind` | "igate" \| "app" |  | `igate`: an iGate heard it on the radio and put it on the internet (`qAR`, `qAO`); `app`: it was sent from the internet by an app or a program and never was on the air (`TCPIP*`, `qAC`, `qAS`, `qAX`) |
| `igate` | string |  | the call of the iGate that heard it; empty for `app` |
| `hops` | string[] |  | the digipeaters that repeated it on the radio before the iGate heard it, in order (`?` for one that put no call in); empty for a packet the iGate heard direct, and for `app` |

### RouteMarkValues

One route a packet of a station came by, which the map draws (a line, or none for `app` and for a packet heard direct).

| field | type | | description |
|---|---|---|---|
| `kind` | "rf" \| "gated" \| "igate" \| "app" |  | `rf`: heard on the radio, direct when `hops` is empty; `gated`: heard on the radio as a third-party packet that the iGate `gate` put on the air, `hops` the digipeaters that repeated the iGate's frame; `igate`: heard on the radio by the iGate `gate`, which put it on the internet, `hops` the digipeaters before it; `app`: sent from the internet, never on the air |
| `hops` | string[] |  | the digipeaters in order, `?` for one that put no call in |
| `gate` | string |  | the iGate of `gated` and `igate`; empty for the others |
| `at` | time |  | when the packet was heard |
| `lat` | number \| null |  | where the station was when the packet was heard (the position it reported, else the one it had before); null when that is not known: the map takes its position now |
| `lon` | number \| null |  |  |

### SatelliteCard

A satellite whose card the page has open. A frequency, mode or path is there only where the project's list marks it sure.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | (>= 1) |
| `name` | string |  |  |
| `downlinks` | SatelliteTune[] |  |  |
| `uplinks` | SatelliteTune[] |  |  |
| `mode` | "afsk1200" \| "gmsk9600" \| null |  |  |
| `path` | string |  | the digipeater path to put in a packet (`ARISS`); empty when the list has none it is sure of |
| `alt_km` | number |  | (>= 0) |
| `footprint_km` | number |  | the radius on the ground of the circle from which it is above the horizon (>= 0) |
| `track` | SatellitePoint[] |  | the points under it for one orbit ahead, every minute |
| `next_pass` | SatellitePass \| null |  | null without the station's position or with no pass within a day |
| `looks` | SatelliteLookNow[] |  | empty unless it is up now |

### SatelliteLookNow

While the satellite is up: its elevation and the Doppler at a time, every 5 s for 90 s; the page tells now between them.

| field | type | | description |
|---|---|---|---|
| `at` | time |  | UTC, ISO 8601 with a Z |
| `el_deg` | number |  | (>= -90, <= 90) |
| `down_hz` | integer[] |  | the shift heard on each downlink, in their order |
| `up_hz` | integer[] |  | the offset to send by on each uplink, in their order |

### SatelliteMark

A satellite on the map: the points under it from 30 s ago to 5 minutes ahead, every 30 s; the page moves the mark between them.

| field | type | | description |
|---|---|---|---|
| `id` | integer |  | its catalogue (NORAD) number (>= 1) |
| `name` | string |  | its name as the project's list has it (`ISS`, `SONATE-2`) |
| `points` | SatellitePoint[] |  |  |

### SatellitePass

The pass under way or the next one whose highest point is 10 degrees or more, within a day.

| field | type | | description |
|---|---|---|---|
| `rise` | time |  | UTC, ISO 8601 with a Z |
| `set` | time |  | UTC, ISO 8601 with a Z |
| `max_at` | time |  | UTC, ISO 8601 with a Z |
| `max_el_deg` | number |  | (>= 0, <= 90) |
| `rise_az_deg` | number |  | (>= 0, < 360) |
| `set_az_deg` | number |  | (>= 0, < 360) |

### SatellitePoint

Where the point under the satellite is at a time.

| field | type | | description |
|---|---|---|---|
| `at` | time |  | UTC, ISO 8601 with a Z |
| `lat` | number |  | (>= -90, <= 90) |
| `lon` | number |  | (>= -180, <= 180) |

### SatelliteTune

A frequency of the list, and where to tune at the next pass: a downlink to hear, an uplink to send on.

| field | type | | description |
|---|---|---|---|
| `hz` | integer |  | (> 0) |
| `rise_hz` | integer \| null |  | at the rise; null without a pass |
| `max_hz` | integer \| null |  | at the highest point; null without a pass |
| `set_hz` | integer \| null |  | at the set; null without a pass |

### SkedFrequency

A dial the project suggests for the HF radio.

| field | type | | description |
|---|---|---|---|
| `band` | string |  | the band, `40 m` |
| `dial` | string |  | the dial with its mode, `7.0541 MHz USB` |

### SkedPast

A test that has ended, as the board had it: one row for each call that was on it. Checked again by the daemon as a row of the board is; it can no longer be joined or deleted.

| field | type | | description |
|---|---|---|---|
| `id` | string |  | the sked's id, 12 lowercase hex characters |
| `call` | string |  | the call that was on the air, upper case without an SSID of 0 |
| `from` | time |  | when it began (the field is called `from` on the wire) |
| `to` | time |  | when it ended, after `from` by 24 hours at most: the planned end, or when its poster deleted it while it ran |
| `dial` | string |  | the dial with its mode, `7.0541 MHz USB` |
| `note` | string |  | the short note, may be empty; the page shows it as text (max 80 chars) |

### SkedRow

A sked on the board: a call on the air at a dial from one instant to another. Every row was checked again by the daemon; the note is one line of at most 80 characters of letters, digits, punctuation and plain spaces.

| field | type | | description |
|---|---|---|---|
| `id` | string |  | the sked's id, 12 lowercase hex characters, which `sked_delete` names |
| `call` | string |  | the call that will be on the air, upper case without an SSID of 0 (`OH2GBA`, `OH2GBA-7`) |
| `from` | time |  | when it begins (the field is called `from` on the wire) |
| `to` | time |  | when it ends, after `from` by 24 hours at most; a sked that has ended by the daemon's clock is not told |
| `dial` | string |  | the dial with its mode, `7.0541 MHz USB` |
| `note` | string |  | a short note, may be empty (`Mercury, 10 W`); the page shows it as text (max 80 chars) |
| `ours` | boolean |  | this installation posted it, so `sked_delete` takes it off the board; no other row can be deleted from here |

### SkedsState

The sked board: where it stands, the dials the project suggests, and the skeds to come, the nearest first. The value of the topic `skeds`, told whole as it changes (a read of the board, a post, a delete, a sked that ends).

| field | type | | description |
|---|---|---|---|
| `state` | "ok" \| "offline" \| "off" \| "closed" |  | `ok`: the board was read (or has not been tried yet), and a sked may be posted. `offline`: the project's server could not be reached or its answer was not a board; `rows` are the last board known, and posting is off. `off`: the check is off (`NEOAPRS_UPDATE_CHECK=0`): nothing is read or posted, `rows` is empty. `closed`: the board is closed to new skeds (by the project, or for this call); `rows` are shown without the form |
| `fetched_at` | time \| null |  | when the board was last read from the server (or when the one kept from the last run was); null before the first |
| `frequencies` | SkedFrequency[] |  | the dials the project suggests for a Mercury radio, one to five, the same as `modem.frequencies` of a Mercury radio's row (the tab does not depend on a radio's state) (max 5 items) |
| `rows` | SkedRow[] |  | the skeds to come by the daemon's clock, the nearest start first; empty when there are none (max 100 items) |
| `past` | SkedPast[] | optional | the tests that have ended in the last 30 days: those the server lists (`skeds-past.json` beside the board) and the board's own that have ended by the daemon's clock since. Rows with the same `from`, `to` and `dial` are one test; the 20 newest tests by their end come first, then by their start and dial, each test's rows by id. Kept in memory only, so empty after a start until the board is read; empty when the check is off (max 100 items) |

### SoundCardRow

A sound card as the Mercury HF modem lists it (`mercury -z`), for the Sound card choice of the Mercury radio type.

| field | type | | description |
|---|---|---|---|
| `id` | string |  | the name to give as `mercury/sound_card`: `plughw:CARD=CODEC,DEV=0` on Linux (by the card's name, which a reboot does not change); on Windows the card's recording device and its playing device, joined by `\|` (one of them alone for a device with no partner) |
| `name` | string |  | what the system calls it, such as `USB Audio CODEC` |
| `numbered` | string | optional | the same card by its number (`plughw:3,0`), as a setting made before named it; empty where the id is not by name (default `""`) |
| `default` | boolean |  | whether it is the system's default device, which the empty setting means |
| `pick` | boolean |  | whether it is the card the daemon proposes for the radio (the one it would choose itself, else the system's default, else the first that records and plays): the page preselects it and stores it as `mercury/sound_card` while that is empty; at most one row has it |
| `held_by` | integer \| null |  | the radio of the station whose modem holds the card now (its id); null while none does. A card another radio holds is never the `pick` |
| `usb_group` | string \| null | optional | which USB device the card sits on together with the serial ports of one radio: the `usb_group` of those ports (an opaque token); null where it is not known (Windows, macOS, a card that is not USB) (default `null`) |

### StationKey

The public key a station announced, kept on first hearing. The entries are the values of the topic `station_keys`, keyed by call; a station that has not announced a key has no entry. A key heard from a station is a
`set`, `forget_station_key` a `del`.

| field | type | | description |
|---|---|---|---|
| `fingerprint` | string |  | 16 hex characters in four groups (`A1B2 C3D4 E5F6 0718`), the start of SHA-256 of the key, for the two operators to compare on voice |
| `heard_at` | time |  | when the key was heard |

### StationPref

What the operator has set for one station, apart from what its packets say. The entries are the values of the topic `station_prefs`, keyed by call: a station with no path of its
own, and not RF only, has no entry. A command that sets or changes one part is a `set` of the whole entry, one that clears the last part a `del`.

| field | type | | description |
|---|---|---|---|
| `path` | string \| null |  | the digipeaters that a message to the station, and the ack of a message from it, go by way of: calls separated by commas, empty for direct (no digipeaters at all); null if none is set, and the setting `beacon/path` counts |
| `rf_only` | boolean |  | true if everything sent to the station (a message and each attempt of it, an ack, the answer to a query) has `RFONLY` as the last element of its path, which iGates that honour it do not put on the internet |
| `alert` | AlertWhen \| null |  | when the operator is told about the station; null if no alert is set |

### StormValues

The storm data of a tropical storm, hurricane or tropical depression (APRS101, chapter 12), in metric units; null where the report did not have the field. The movement is the course and speed of the position.

| field | type | | description |
|---|---|---|---|
| `storm_type` | "TS" \| "HC" \| "TD" |  | TS tropical storm, HC hurricane, TD tropical depression |
| `wind_kmh` | number \| null |  | the sustained wind |
| `gust_kmh` | number \| null |  |  |
| `pressure_hpa` | integer \| null |  | the central pressure |
| `hurricane_radius_km` | number \| null |  | the radius of hurricane winds |
| `storm_radius_km` | number \| null |  | the radius of tropical storm winds |
| `gale_radius_km` | number \| null |  | the radius of whole gale (50 knot) winds |

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

### TelemetryFields

A telemetry report as the parser made it.

| field | type | | description |
|---|---|---|---|
| `sequence` | integer \| null |  | the sequence number; null for the `MIC` of a Mic-E unit |
| `analog` | number[] |  | the analog values as sent, 1 to 5 (APRS 1.2: any width, signed, with a decimal point) |
| `bits` | string |  | the digital values as a text of 0 and 1, B1 first: up to eight, empty when there were none |
| `comment` | string |  |  |

### TelemetryValues

A station's latest telemetry report with the definitions the station sent as messages (`PARM.`, `UNIT.`, `EQNS.`, `BITS.`) applied.

| field | type | | description |
|---|---|---|---|
| `sequence` | integer \| null |  | the sequence number; null for the `MIC` of a Mic-E unit |
| `channels` | TelemetryChannel[] |  | the analog channels, as many as the report had (1 to 5) |
| `bits` | TelemetryBit[] |  | the digital channels, as many as the report had (up to 8) |
| `project` | string |  | the project title of the `BITS.` message; empty when there is none |
| `comment` | string |  |  |

### TncLine

One line of the TNC's log.

| field | type | | description |
|---|---|---|---|
| `at` | time |  | when the line was written |
| `text` | string |  | what the TNC saw (TNC2 text and what it understood of it) or did (`NeoAPRS: ...`), without the time |

### UpdateInfo

A newer version than the daemon's, as the version page named it (services/updatecheck.py).

| field | type | | description |
|---|---|---|---|
| `version` | string |  | the latest version |
| `url` | string |  | where to get it: an https address, or empty |
| `message` | string |  | a short note from the project, at most 200 characters; empty for none |

### UpdateState

Update now (neoaprs/services/selfupdate.py): whether this copy can update itself, and the steps of the update it is doing. The value of the topic `update`, told whole as it changes, at most four times a second.

| field | type | | description |
|---|---|---|---|
| `supported` | boolean |  | this copy can update itself (the Windows installer, an AppImage in a folder its user can write): the page offers Update now; else it shows the steps |
| `state` | "idle" \| "downloading" \| "verifying" \| "installing" \| "restarting" \| "error" |  | `idle`: no update is running. `downloading`: SHA256SUMS, its signature and then the file of the release are fetched (`percent`). `verifying`: the file's SHA-256 is held to the signed SHA256SUMS. `installing`: the file is put in place. `restarting`: NeoAPRS ends and starts again as the new version (the page loses its socket and finds the new daemon). `error`: the update failed, `problem` says how |
| `version` | string |  | the version being installed; empty while idle |
| `percent` | integer \| null |  | how much of the file has come; null when the server did not say its size (>= 0, <= 100) |
| `downloaded` | integer |  | the bytes of the file so far (>= 0) |
| `total` | integer \| null |  | the size of the file in bytes, when the server said it (>= 0) |
| `problem` | "" \| "download" \| "unverified" \| "checksum" \| "install" \| "no_restart" |  | for `error`: `download` (the file or SHA256SUMS could not be fetched), `unverified` (SHA256SUMS could not be checked: its signature could not be fetched or does not hold with the project's key for this version, or the list does not name the file once; nothing was downloaded), `checksum` (the file's SHA-256 is not the one the signed SHA256SUMS gives it: it was deleted), `install` (it could not be put in place, or the installer could not be started), `no_restart` (it was installed but NeoAPRS did not restart); empty otherwise |

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
