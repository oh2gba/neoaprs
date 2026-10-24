#!/usr/bin/env python3
"""Generates everything that describes the wire protocol from the models in neoaprs/web/protocol.py and the neoaprs/web/*wire.py modules:

  ui/src/protocol/schema.json   JSON Schema of the Command and the Message union, and of the value of each topic
  ui/src/protocol/protocol.ts   TypeScript types made from it (by this script: no node, no json-schema-to-typescript)
  ui/src/protocol/lists.ts      the lists the daemon owns and the page shows (the settings' keys, the TNC profiles, the symbol names, ...) and `LIMITS`, every number the page checks a value against (the
                                ranges of the settings, the length of a comment, a message, a status, the minimum interval ...), written from the daemon's own constants
  ui/src/protocol/errors.json   the refusals of the daemon that carry a code: for each code the values it passes and the English sentence it writes (found in the source by scripts/errorcodes.py); the page's catalogue
                                is held to it by ui/src/i18n/errors.test.ts
  ui/src/protocol/vectors.json  the rules that are code and not numbers (is this a call? what is the PHG text of this antenna? what beacon does this make?): inputs with the results that Python gives; tests/test_vectors.py
                                and ui/src/protocol/vectors.test.ts hold the daemon and the page to them
  ui/src/i18n/en/symbols.ts     the names of the APRS symbols as messages of the page's English catalogue (`symbol.primary.21`, `symbol.alternate.7e`: the table and the code in hex), so that they can be translated
  PROTOCOL.md                   the reference: the prose below, then the commands and the messages from the models' docstrings and field descriptions

Run it with the venv's python from the repository root:  .venv/bin/python scripts/gen-protocol.py
`--check` writes nothing and exits 1 when a file is out of date (tests/test_protocol.py does the same inside pytest).
"""
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pydantic import BaseModel  # noqa: E402

import neoaprs.web.protocol as protocol  # noqa: E402
from errorcodes import error_codes  # noqa: E402
from neoaprs import TOCALL  # noqa: E402
from neoaprs.aprsmessage import FORBIDDEN, MAX_TEXT  # noqa: E402
from neoaprs.ax25 import MAX_PATH  # noqa: E402
from neoaprs.route import DIRECT_ONLY, FIXED_PATH, WIDE_PATH  # noqa: E402
from neoaprs.callsign import AMATEUR_BASE_MIN, BASE_MAX, MAX_SSID, PLACEHOLDER_CALLS, call_problem, parse_call  # noqa: E402
from neoaprs.config import ANTENNA_DIRECTIONS, DEFAULTS, KEYS, LATITUDE, LONGITUDE, MAX_COMMENT, MAX_COMMENT_PHG, MIN_BEACON_INTERVAL_MIN, MIN_STATUS_INTERVAL_MIN, RANGES, SYMBOL_TABLES, Config  # noqa: E402
from neoaprs.configstatus import MAX_STATUS  # noqa: E402
from neoaprs.message import EMAIL_GATEWAY, check_text, normal_path  # noqa: E402
from neoaprs.ownbulletin import GROUP_MAX, PostError, make_bulletin, slot_of  # noqa: E402
from neoaprs.ownobject import COMMENT_MAX, COMMENT_MAX_MOTION, COURSE_MAX, ITEM_NAME, NAME_FORBIDDEN, OBJECT_NAME, SPEED_MAX_KMH, OwnError, make_object  # noqa: E402
from neoaprs.policy import HIDE_AFTER_MIN, MAX_HIDE_AFTER_MIN  # noqa: E402
from neoaprs.aprsposition import uncompressed_position  # noqa: E402
from neoaprs.services.beacon import Beacon, BeaconError, phg_text  # noqa: E402
from neoaprs.symbols import MOBILE_CODES, SYMBOL_NAMES  # noqa: E402
from neoaprs.tncprofile import PROFILES  # noqa: E402
from neoaprs.web.hubwire import PROTOCOL  # noqa: E402

SCHEMA = ROOT / "ui" / "src" / "protocol" / "schema.json"
TYPES = ROOT / "ui" / "src" / "protocol" / "protocol.ts"
LISTS = ROOT / "ui" / "src" / "protocol" / "lists.ts"
VECTORS = ROOT / "ui" / "src" / "protocol" / "vectors.json"
ERRORS = ROOT / "ui" / "src" / "protocol" / "errors.json"
SYMBOLS = ROOT / "ui" / "src" / "i18n" / "en" / "symbols.ts"
DOC = ROOT / "PROTOCOL.md"
# The order of the first objects of the Objects section of PROTOCOL.md; every other model of the schema follows them, sorted by name.
OBJECT_ORDER = "StationRow PacketRow MessageRow DecodedPosition DecodedMessage DecodedObject DecodedItem DecodedStatus DecodedTelemetry DecodedOther DecodedUndecoded DecodedWeather PositionFields TncState TncStats ConfigValues SetOp DelOp ReplaceOp".split()


class Protocol(BaseModel):
    """Both unions and the value of each topic in one document, so that one schema carries every definition."""
    command: protocol.Command
    message: protocol.Message
    topics: protocol.TopicValues


def build_schema() -> dict[str, Any]:
    schema = Protocol.model_json_schema(ref_template="#/$defs/{model}")
    defs = schema["$defs"]
    # a model keeps its title (the TypeScript name); a field loses its (pydantic made it up from the field's name)
    for d in defs.values():
        for prop in d.get("properties", {}).values():
            _strip_titles(prop)
    for prop in schema["properties"].values():
        prop.pop("title", None)
    schema["properties"]["command"]["title"] = "Command"
    schema["properties"]["message"]["title"] = "Message"
    schema["properties"]["topics"].pop("description", None)
    schema["title"] = "Protocol"
    schema["description"] = ("The WebSocket protocol of NeoAPRS: `command` is what the page sends (tagged by cmd), `message` what the daemon sends (tagged by type), "
                             "`topics` the value of each topic the page follows.")
    schema["$defs"] = {k: defs[k] for k in sorted(defs)}
    return schema


def _strip_titles(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("title", None)
        for v in node.values():
            _strip_titles(v)
    elif isinstance(node, list):
        for v in node:
            _strip_titles(v)


def schema_text() -> str:
    return json.dumps(build_schema(), indent=2, sort_keys=False) + "\n"


# ---- protocol.ts: the types, from the schema

TS_HEAD = """// The types of the wire protocol between the daemon and the page, written from the models of neoaprs/web/protocol.py by scripts/gen-protocol.py: never edited by hand.
// `Command` is what the page sends (tagged by `cmd`), `Message` what the daemon sends (tagged by `type`), `TopicValues` the value of each topic the page follows.
"""


def _comment(text: str, indent: str = "") -> str:
    text = " ".join(text.split()).replace("*/", "*\\/")
    return f"{indent}/** {text} */\n" if text else ""


def _ts(node: dict[str, Any], names: dict[str, str]) -> str:
    """The TypeScript type of a (sub)schema."""
    if "$ref" in node:
        return names[node["$ref"].rsplit("/", 1)[-1]]
    if "const" in node:
        return json.dumps(node["const"])
    if "enum" in node:
        return " | ".join(json.dumps(x) for x in node["enum"])
    for key in ("anyOf", "oneOf"):
        if key in node:
            return " | ".join(dict.fromkeys(_ts(x, names) for x in node[key]))
    kind = node.get("type")
    if kind == "array":
        if "prefixItems" in node:
            return "[" + ", ".join(_ts(x, names) for x in node["prefixItems"]) + "]"
        inner = _ts(node.get("items", {}), names)
        return f"({inner})[]" if " | " in inner else f"{inner}[]"
    if kind == "object":
        extra = node.get("additionalProperties")
        return "{ [key: string]: " + _ts(extra, names) + " }" if isinstance(extra, dict) else "{ [key: string]: unknown }"
    return {"integer": "number", "number": "number", "string": "string", "boolean": "boolean", "null": "null"}.get(str(kind), "unknown")


def _interface(name: str, model: dict[str, Any], names: dict[str, str]) -> str:
    required = set(model.get("required", []))
    lines = [_comment(model.get("description", "")) + f"export interface {name} {{"]
    tags = [p for p in ("cmd", "type", "op") if p in model.get("properties", {})]          # the tag of a union comes first
    for prop, node in sorted(model.get("properties", {}).items(), key=lambda item: item[0] not in tags):
        lines.append(_comment(node.get("description", ""), "  ").rstrip("\n") if node.get("description") else "")
        key = prop if re.fullmatch(r"[A-Za-z_]\w*", prop) else json.dumps(prop)
        lines.append(f"  {key}{'' if prop in required else '?'}: {_ts(node, names)};")
    lines.append("}")
    return "\n".join(line for line in lines if line != "") + "\n"


def types_text(schema: dict[str, Any]) -> str:
    defs: dict[str, Any] = schema["$defs"]
    names = {key: d.get("title", key) for key, d in defs.items()}
    out = [TS_HEAD]
    for prop, title in (("command", "Command"), ("message", "Message")):
        node = schema["properties"][prop]
        out.append(_comment(node.get("description", "")) + f"export type {title} = {_ts({'anyOf': node['oneOf']}, names)};\n")
    for key in sorted(defs, key=lambda k: names[k]):
        out.append(_interface(names[key], defs[key], names))
    return "\n".join(out)


# ---- lists.ts

LISTS_HEAD = """// The lists the daemon owns and the page shows, written from the daemon's own constants by scripts/gen-protocol.py: never edited by hand.
"""


LISTS_WIDTH = 160                      # the printWidth of ui/.prettierrc.json: a list that fits stays on one line, a longer one has one item to a line


def _literal(value: Any, indent: int = 0, used: int = 40) -> str:
    """A value as TypeScript, laid out the way prettier does: a list of strings or numbers on one line when it fits, else one item to a line; a list of objects one object to a line; an object with a list in it
    one key to a line. So that two edits of two items do not meet in one long line, and git merges them."""
    pad = "  " * (indent + 1)
    if isinstance(value, list):
        flat = json.dumps(value)
        if not any(isinstance(x, (dict, list)) for x in value) and indent * 2 + len(flat) + used <= LISTS_WIDTH:        # (used: what else is on the line)
            return flat
        return "[\n" + "".join(f"{pad}{_literal(x, indent + 1)},\n" for x in value) + "  " * indent + "]"
    if isinstance(value, dict) and any(isinstance(x, list) for x in value.values()):
        return "{\n" + "".join(f"{pad}{json.dumps(k)}: {_literal(x, indent + 1)},\n" for k, x in value.items()) + "  " * indent + "}"
    return json.dumps(value)


def _array(name: str, words: tuple[str, ...] | list[str], daemon: str) -> str:
    return f"/** {daemon} */\nexport const {name} = {_literal(list(words), used=len(f'export const {name} = ') + len(' as const;'))} as const;\n"


def _number(name: str, value: float, daemon: str) -> str:
    return f"/** {daemon} */\nexport const {name} = {json.dumps(value)};\n"


def _profiles() -> str:
    """The TNC profiles the settings form offers, with what the form needs of each: how it is reached, its speed, and whether it can be asked if it is there."""
    rows = [{"key": p.key, "name": p.name, "transport": p.transport, "baud": p.baud, "probe": p.can_probe} for p in PROFILES]
    return ("/** The TNC profiles, in the order the settings form offers them (PROFILES of neoaprs/tncprofile.py): how each is reached (`serial` or `tcp`), its speed and whether the daemon can ask it if it is there. */\n"
            f"export const TNC_PROFILES = {_literal(rows)} as const;\n")


def _symbol_names() -> str:
    return ("/** The names of the APRS symbols, the codes `!` to `~` in order, of the primary and of the alternate table (SYMBOL_NAMES of neoaprs/symbols.py): the symbol picker lists them. */\n"
            f"export const SYMBOL_NAMES = {_literal({k: list(v) for k, v in SYMBOL_NAMES.items()})} as const;\n")


def _mobile_symbols() -> str:
    return ("/** The codes `!` to `~` of the symbols of a station that moves or is carried, in the primary and in the alternate table (MOBILE_CODES of neoaprs/symbols.py): a station with one of them is recommended WIDE1-1,WIDE2-1, any other WIDE2-1. */\n"
            f"export const MOBILE_SYMBOLS = {_literal(dict(MOBILE_CODES))} as const;\n")


def symbols_text() -> str:
    """The names of the symbols as the English catalogue's messages: `symbol.<table>.<code in hex>` for each code "!" to "~" of the primary and of the alternate table, and `symbol.unknown` for none."""
    rows = [f'  "symbol.{table}.{ord("!") + index:02x}": {json.dumps(name)},\n' for table in ("primary", "alternate") for index, name in enumerate(SYMBOL_NAMES[table])]
    return ("// The names of the APRS symbols, written from the daemon's own list (SYMBOL_NAMES of neoaprs/symbols.py) by scripts/gen-protocol.py: never edited by hand. The id is the table and the code of the symbol in hex\n"
            "// (`symbol.primary.3e` is the car of `/>`); an overlay table is the alternate one. Another language translates them in its own catalogue; the page falls back to these.\n"
            "export const symbols = {\n" + "".join(rows) + '  "symbol.unknown": "unknown",\n} as const;\n')


def limits() -> dict[str, Any]:
    """Every number the page checks a value against, by area: the daemon's own constants, so that the page types none of them again."""
    ranges = {**{key: {"min": low, "max": high} for key, (low, high) in RANGES.items()}, "station/lat": {"min": LATITUDE[0], "max": LATITUDE[1]}, "station/lon": {"min": LONGITUDE[0], "max": LONGITUDE[1]}}
    return {
        "range": ranges,
        "comment": {"max": MAX_COMMENT, "maxWithPhg": MAX_COMMENT_PHG},
        "status": {"max": MAX_STATUS},
        "interval": {"beaconMinMin": MIN_BEACON_INTERVAL_MIN, "statusMinMin": MIN_STATUS_INTERVAL_MIN},
        "message": {"textMax": MAX_TEXT, "forbidden": FORBIDDEN, "gateway": EMAIL_GATEWAY},
        "call": {"baseMax": BASE_MAX, "amateurBaseMin": AMATEUR_BASE_MIN, "maxSsid": MAX_SSID, "placeholders": sorted(PLACEHOLDER_CALLS)},
        "path": {"maxCalls": MAX_PATH, "direct": DIRECT_ONLY, "recommendedMobile": WIDE_PATH, "recommendedFixed": FIXED_PATH},
        "object": {"nameMax": OBJECT_NAME[1], "itemNameMin": ITEM_NAME[0], "nameForbidden": NAME_FORBIDDEN, "commentMax": COMMENT_MAX, "commentMaxMotion": COMMENT_MAX_MOTION,
                   "courseMax": COURSE_MAX, "speedMaxKmh": round(SPEED_MAX_KMH)},
        "bulletin": {"groupMax": GROUP_MAX},
        "station": {"hideAfterMin": HIDE_AFTER_MIN, "maxHideAfterMin": MAX_HIDE_AFTER_MIN},
    }


_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")


def _object(value: Any, indent: int = 0) -> str:
    """A nested object as TypeScript, one key to a line (a list of words on one line)."""
    if not isinstance(value, dict):
        return json.dumps(value)
    pad = "  " * (indent + 1)
    rows = (f"{pad}{key if _IDENTIFIER.fullmatch(key) else json.dumps(key)}: {_object(item, indent + 1)},\n" for key, item in value.items())
    return "{\n" + "".join(rows) + "  " * indent + "}"


def _limits_block() -> str:
    return ("/** Every number the page checks a value against, by area, from the daemon's own constants (the ranges of the settings by key: RANGES of neoaprs/config.py; the comment, status and message "
            "lengths, the least interval, the calls, the objects and bulletins, the time a station stays on the map). */\n"
            f"export const LIMITS = {_object(limits())} as const;\n")


def lists_text() -> str:
    """The daemon's lists as TypeScript constants: the page reads them instead of keeping a second copy."""
    blocks = [
        _number("PROTOCOL", PROTOCOL, "The version of the messages (PROTOCOL of neoaprs/web/hubwire.py): a `hello` of another number means the page is out of date."),
        _array("TOPIC_NAMES", protocol.TOPIC_NAMES, "The topics of the hub, in the order the daemon tells them (TopicValues of neoaprs/web/protocol.py)."),
        _array("MESSAGE_TYPES", sorted(protocol.MESSAGE_NAMES), "Every message the daemon sends (the `type` of the Message union)."),
        _array("CONFIG_KEYS", KEYS, "The keys of the settings, in the order of the settings form (SETTINGS of neoaprs/config.py)."),
        _profiles(),
        _symbol_names(),
        _mobile_symbols(),
        f"/** The destination call of every frame we send; the beacon's preview shows it (TOCALL of neoaprs/__init__.py). */\nexport const TOCALL = {json.dumps(TOCALL)};\n",
        _limits_block(),
        f"/** The characters a symbol table can be: the primary, the alternate and the overlays (SYMBOL_TABLES of neoaprs/config.py). */\nexport const SYMBOL_TABLES = {json.dumps(SYMBOL_TABLES)};\n",
    ]
    return LISTS_HEAD + "\n" + "\n".join(blocks)


# ---- PROTOCOL.md

PROSE = """# The protocol between the daemon and the page

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
field the model does not know is an error, text has a maximum length, `NaN` and `Infinity` are not JSON. A frame that does not fit is answered with an `error` whose `cmd` is the command, whose `code` is `invalid` and whose `text` is
"<command>: <field>: <what is wrong>", for example `forget_station: call: is missing`, and nothing at all is executed. A frame that is not JSON, or not an object, or names no known command is answered the same
way (`cmd` is empty; `code` is `not_json`, `not_object`, `no_command` or `unknown_command`). The values of `set_config` are checked by the settings (`neoaprs/config.py`), all before any is stored: the first that
is wrong is the answer, with `cmd` `set_config`, `key` the setting (`station/lat`), `code` what is wrong (`setting.range`), `params` its figures (`value`, `min`, `max`) and `text` `set_config: station/lat: 95 is
not between -90 and 90`.

A page goes by `cmd`, `key` and `code` and never reads `text`; `text` is the English sentence for a log and for a code the page has no sentence for. The codes are stable words: `setting.*` for the values
of the settings (and `call.*`, `path.*` inside them), `message.*`, `object.*` and `bulletin.*` for what is posted or sent, `station.*`, `beacon.*`, `status.*`, `map.*` and `topic.*` for the rest of the commands,
and `other` for a refusal that has no code yet (only `text` says what it is).

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
"""


def _type(s: dict[str, Any], names: dict[str, str]) -> str:
    """A short description of a (sub)schema for the tables of PROTOCOL.md."""
    if "$ref" in s:
        return names.get(s["$ref"].rsplit("/", 1)[-1], s["$ref"].rsplit("/", 1)[-1])
    if "const" in s:
        return json.dumps(s["const"])
    if "enum" in s:
        return " | ".join(json.dumps(x) for x in s["enum"])
    for key in ("anyOf", "oneOf"):
        if key in s:
            return " | ".join(_type(x, names) for x in s[key])
    t = s.get("type")
    if t == "array":
        if "prefixItems" in s:
            return "[" + ", ".join(_type(x, names) for x in s["prefixItems"]) + "]"
        inner = _type(s.get("items", {}), names)
        return f"({inner})[]" if " | " in inner else f"{inner}[]"
    if t == "object":
        extra = s.get("additionalProperties")
        return "{ [key: string]: " + _type(extra, names) + " }" if isinstance(extra, dict) else "object"
    if t == "string":
        pattern = s.get("pattern", "")
        return "time" if pattern.startswith("^\\d{4}-\\d{2}-\\d{2}T") else "string"
    return {"integer": "integer", "number": "number", "boolean": "boolean", "null": "null"}.get(str(t), "any")


def _limits(s: dict[str, Any]) -> str:
    out = []
    for b in s.get("anyOf", [s]):
        for key, label in (("minimum", ">="), ("maximum", "<="), ("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")):
            if key in b:
                out.append(f"{label} {'2^53' if b[key] == 2**53 else b[key]}")
        if "maxLength" in b:
            out.append(f"max {b['maxLength']} chars")
        if "minLength" in b:
            out.append(f"min {b['minLength']} chars")
        if "maxItems" in b and "prefixItems" not in b:
            out.append(f"max {b['maxItems']} items")
    return ", ".join(out)


def _fields(model: dict[str, Any], names: dict[str, str], tag: str) -> list[str]:
    required = set(model.get("required", []))
    rows = ["| field | type | | description |", "|---|---|---|---|"]
    for name, s in model.get("properties", {}).items():
        if name == tag:
            continue
        note = []
        if "default" in s:
            note.append(f"default `{json.dumps(s['default'])}`")
        lim = _limits(s)
        if lim:
            note.append(lim)
        desc = (s.get("description") or "").replace("|", "\\|").replace("\n", " ")
        if note:
            desc = (desc + " " if desc else "") + "(" + "; ".join(note) + ")"
        rows.append(f"| `{name}` | {_type(s, names).replace('|', '\\|')} | {'' if name in required else 'optional'} | {desc} |")
    return rows


def doc_text() -> str:
    schema = build_schema()
    defs: dict[str, Any] = schema["$defs"]
    names = {k: k for k in defs}
    cmd_defs = [t.__name__ for t in protocol.COMMAND_TYPES]
    msg_defs = [t.__name__ for t in protocol.MESSAGE_TYPES]
    # every model the schema reaches that is not a command, a message or the topic values: the curated order first, a model it does not name after it, by name
    reached = [name for name in defs if name not in cmd_defs and name not in msg_defs and name != "TopicValues"]
    objects = [name for name in OBJECT_ORDER if name in reached] + sorted(name for name in reached if name not in OBJECT_ORDER)
    out = [PROSE.rstrip("\n"), ""]

    out += ["## Client to server", "",
            f"{len(cmd_defs)} commands, each a JSON object with `\"cmd\"` as the first field. Types: `integer` and `number` are JSON numbers, `time` is UTC ISO 8601 with a `Z`.", ""]
    for name in cmd_defs:
        d = defs[name]
        tag = d["properties"]["cmd"]["const"]
        out += [f"### `{tag}`", "", d.get("description", "").strip(), ""]
        if len(d["properties"]) > 1:
            out += _fields(d, names, "cmd") + [""]
    out += ["## Server to client", "",
            f"{len(msg_defs)} messages, each a JSON object with `\"type\"`. The first is `hello`. Where a field is `X | null` it is always present, with null.", ""]
    for name in msg_defs:
        d = defs[name]
        tag = d["properties"]["type"]["const"]
        out += [f"### `{tag}`", "", d.get("description", "").strip(), ""]
        if len(d["properties"]) > 1:
            out += _fields(d, names, "type") + [""]
    out += ["## Topics", "", "The value of each topic (`state` carries it, a `replace` op brings a new one).", "", "| topic | value | |", "|---|---|---|"]
    for name, field in defs["TopicValues"]["properties"].items():
        out.append(f"| `{name}` | {_type(field, names).replace('|', '\\|')} | {(field.get('description') or '').replace('|', '\\|')} |")
    out += ["", "## Objects", "", "The objects the commands and the messages are made of.", ""]
    for name in objects:
        d = defs[name]
        out += [f"### {name}", "", d.get("description", "").strip(), ""]
        out += _fields(d, names, "") + [""]
    return "\n".join(out).rstrip("\n") + "\n"


# ---- vectors.json: the rules that are code, with the results Python gives

CALLS = ["OH2GBA", "oh2gba", " oh2gba ", "OH2GBA-7", "OH2GBA-15", "OH2GBA-16", "OH2GBA-0", "OH2GBA-00", "OH2GBA-07", "OH2GBA-007", "OH2GBA-", "-7", "", "  ", "N0CALL", "n0call-5", "NOCALL", "MYCALL",
         "AB", "A1", "A1B", "ABC", "123", "1234", "OH2GBAA", "OH2G BA", "OH2GBA/P", "OH2GB\u00c4", "\u00df1A", "W1AW", "K1", "KB1ABC-9", "EMAIL-2", "WIDE1-1", "APZNEO", "TCPIP", "a-b", "OH 2GBA"]
PATHS = ["", " ", "WIDE1-1,WIDE2-1", "wide1-1, wide2-1", "WIDE2-2", ",", "WIDE1-1,", ",WIDE1-1", "WIDE1-1,,WIDE2-1", "OH2RCH-0", "A,B,C,D,E,F,G,H", "A,B,C,D,E,F,G,H,I", "TOOLONGCALL", "OH2RCH-16", "WIDE1-1,N0CALL"]
MESSAGE_TEXTS = ["Hello", " Hello ", "", "   ", "x" * 67, "x" * 68, " " + "x" * 66 + " "]
BULLETIN_TEXTS = ["Snow expected", "", "   ", " padded ", "x" * 67, "x" * 68, "with | bar", "with ~ tilde", "with { brace", "tab\there", "\u00e5\u00e4\u00f6", "emoji \U0001f600", "a:b"]
BULLETIN_SLOTS = [("bulletin", i, "") for i in "0189AZ"] + [("announcement", i, "") for i in "09AZ"] + [("group", i, g) for i in "09A" for g in ("", "HAMS", "HAMS1", "HAMS12", "HA-MS", "ha ms", "ham", "H")]
OBJECT_NAMES = [("object", n) for n in ("A", "OH2GBA", "NINECHARS", "TENCHARS12", "", " X", "X ", "A B", "has!bang", "has_under", "has|bar", "has~tilde", "caf\u00e9", "lower", "UPPER 1")] + \
    [("item", n) for n in ("AB", "ABC", "NINECHARS", "TENCHARS12", "", "A_B", "A!")]
OBJECT_COMMENTS = [("", False), ("x" * 43, False), ("x" * 44, False), ("x" * 36, True), ("x" * 37, True), ("x" * 43, True), ("with | bar", False), ("with ~ tilde", False), ("caf\u00e9", False), ("tab\there", False), (" padded ", False)]
SETTING_VALUES = [(key, text) for key in ("station/lat", "station/lon") for text in ("0", "60.17", "-90", "90", "-180", "180", "90.0001", "-90.1", "180.5", "", " 45 ", "abc")] + \
    [(key, text) for key in ("serial/baud", "tcp/port", "beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "map/radius_km")
     for text in ("", "0", "1", "9", "10", "299", "300", "1000", "1001", "9999", "10000", "65535", "65536", "921600", "921601", "-1", "1.5", "abc", " 5 ")]
PHG_CASES = [(p, h, 3, "NE") for p in (0, 1, 2, 5, 25, 81, 100, 9999) for h in (0, 1, 3, 3.048, 4, 10, 20, 100, 9999)] + [(5, 10, g, d) for g in (0, 3, 9, 10, -1) for d in ANTENNA_DIRECTIONS]
POSITIONS = [(60.17, 24.94), (0.0, 0.0), (-33.8688, 151.2093), (90.0, 180.0), (-90.0, -180.0), (59.999999, 24.999999), (0.03125, 0.09375), (60.169999, -24.940001), (-0.00001, -0.00001), (0.0083333, 100.0)]
BEACON_BASE = {"station/call": "OH2GBA", "station/lat": "60.17", "station/lon": "24.94", "station/symbol_table": "/", "station/symbol_code": "-", "station/comment": "NeoAPRS",
               "beacon/power_w": "", "beacon/antenna_height_m": "0", "beacon/antenna_gain_db": "0", "beacon/antenna_direction": "omni", "beacon/path": "WIDE1-1,WIDE2-1"}
BEACONS = [{}, {"beacon/power_w": "5", "beacon/antenna_height_m": "10", "beacon/antenna_gain_db": "3", "beacon/antenna_direction": "NE", "station/comment": "Home"}, {"station/comment": ""}, {"station/call": "oh2gba-7"},
           {"station/call": ""}, {"station/lat": ""}, {"station/lat": "91"}, {"station/lon": "181"},
           {"station/symbol_table": "Z", "station/symbol_code": "~"}, {"station/symbol_table": "a"}, {"station/symbol_code": " "}, {"beacon/path": ""}, {"beacon/path": "", "station/symbol_code": ">"}, {"beacon/path": "", "station/symbol_table": "\\", "station/symbol_code": "s"},
           {"beacon/path": "", "station/symbol_table": "E", "station/symbol_code": ">"}, {"beacon/path": "", "station/symbol_table": "\\", "station/symbol_code": "#"}, {"beacon/path": "", "station/symbol_code": "b"},
           {"beacon/path": "", "station/symbol_code": "_"}, {"beacon/path": "", "station/symbol_table": "2", "station/symbol_code": "k"}, {"beacon/path": "DIRECT"}, {"beacon/path": "WIDE2-2"}, {"beacon/path": "BAD CALL"},
           {"station/lat": "0.03125", "station/lon": "0.09375"}, {"station/lat": "-0.00001", "station/lon": "-0.00001"}, {"beacon/power_w": "100", "beacon/antenna_height_m": "9999", "beacon/antenna_gain_db": "9",
            "beacon/antenna_direction": "N", "station/comment": "x" * 36}]


def _call_vector(text: str) -> dict[str, Any]:
    """Whether the text typed in station/call may be transmitted under (the settings' call, then the interlock's), and the call as it is kept."""
    try:
        call = Config.check("station/call", text)
    except ValueError:
        return {"input": text, "ok": False, "call": ""}
    ok = call != "" and call_problem(call) == ""
    return {"input": text, "ok": ok, "call": call if ok else ""}


def _parse_vector(text: str) -> dict[str, Any]:
    try:
        parse_call(text.strip())
    except ValueError:
        return {"input": text, "ok": False}
    return {"input": text, "ok": True}


def _path_vector(text: str) -> dict[str, Any]:
    try:
        normal_path(text)
    except ValueError:
        return {"input": text, "ok": False}
    return {"input": text, "ok": True}


def _message_vector(text: str) -> dict[str, Any]:
    """Whether the text, as far as its length and its being there go, fits in a message."""
    try:
        check_text(text)
    except ValueError:
        return {"input": text, "ok": False}
    return {"input": text, "ok": True}


def _bulletin_text_vector(text: str) -> dict[str, Any]:
    try:
        make_bulletin(datetime(2026, 10, 21, tzinfo=UTC), "BLN1", text)
    except PostError:
        return {"input": text, "ok": False}
    return {"input": text, "ok": True}


def _bulletin_slot_vector(kind: str, ident: str, group: str) -> dict[str, Any]:
    """The slot a bulletin of this kind, identifier and group is posted to, null when the kind does not take it."""
    try:
        slot, _, found = slot_of(f"BLN{ident}{group}")
    except PostError:
        return {"kind": kind, "id": ident, "group": group, "slot": None}
    return {"kind": kind, "id": ident, "group": group, "slot": slot if found == kind else None}


def _object_vector(kind: str, name: str) -> dict[str, Any]:
    try:
        make_object(datetime(2026, 10, 21, tzinfo=UTC), name, kind, 60.0, 24.0, "/", ">")
    except OwnError as e:
        return {"name": name, "kind": kind, "ok": False, "code": e.code}
    return {"name": name, "kind": kind, "ok": True, "code": ""}


def _comment_vector(comment: str, moving: bool) -> dict[str, Any]:
    try:
        make_object(datetime(2026, 10, 21, tzinfo=UTC), "OBJ", "object", 60.0, 24.0, "/", ">", comment, 90 if moving else None, None)
    except OwnError as e:
        return {"comment": comment, "moving": moving, "ok": False, "code": e.code}
    return {"comment": comment, "moving": moving, "ok": True, "code": ""}


def _setting_vector(key: str, text: str) -> dict[str, Any]:
    try:
        Config.check(key, text)
    except ValueError:
        return {"key": key, "input": text, "ok": False}
    return {"key": key, "input": text, "ok": True}


def _beacon_vector(changes: dict[str, str]) -> dict[str, Any]:
    """The TNC2 text of the beacon these settings make, null when they make none (a setting refused, a call that may not transmit, a position missing)."""
    values = {**BEACON_BASE, **changes}
    try:
        config = Config.checked(DEFAULTS, values)
        text: str | None = Beacon(object(), lambda: config).frame().tnc2()                 # type: ignore[arg-type]  (the frame needs no radio)
    except (ValueError, BeaconError):
        text = None
    return {"values": values, "text": text}


def vectors() -> dict[str, list[dict[str, Any]]]:
    return {
        "calls": [_call_vector(t) for t in CALLS],
        "parse_calls": [_parse_vector(t) for t in CALLS],
        "paths": [_path_vector(t) for t in PATHS],
        "message_texts": [_message_vector(t) for t in MESSAGE_TEXTS],
        "bulletin_texts": [_bulletin_text_vector(t) for t in BULLETIN_TEXTS],
        "bulletin_slots": [_bulletin_slot_vector(*row) for row in BULLETIN_SLOTS],
        "object_names": [_object_vector(*row) for row in OBJECT_NAMES],
        "object_comments": [_comment_vector(*row) for row in OBJECT_COMMENTS],
        "settings": [_setting_vector(*row) for row in SETTING_VALUES],
        "phg": [{"power": p, "height": h, "gain": g, "direction": d, "text": phg_text(p, h, g, d)} for p, h, g, d in PHG_CASES],
        "positions": [{"lat": lat, "lon": lon, "table": "/", "code": "-", "text": uncompressed_position(lat, lon, "/", "-").decode("ascii")} for lat, lon in POSITIONS],
        "beacons": [_beacon_vector(changes) for changes in BEACONS],
    }


def vectors_text() -> str:
    """One case to a line, so that two additions meet in two lines and not in one."""
    blocks = [f' "{name}": [\n' + ",\n".join(f"  {json.dumps(case, ensure_ascii=True)}" for case in cases) + "\n ]" for name, cases in vectors().items()]
    return "{\n" + ",\n".join(blocks) + "\n}\n"


def errors_text() -> str:
    """One code to a line, so that two additions meet in two lines and not in one."""
    codes = error_codes(ROOT / "neoaprs")
    return "{\n" + ",\n".join(f" {json.dumps(code)}: {json.dumps(entry, ensure_ascii=False)}" for code, entry in codes.items()) + "\n}\n"


def render() -> dict[Path, str]:
    schema = build_schema()
    return {SCHEMA: json.dumps(schema, indent=2) + "\n", TYPES: types_text(schema), LISTS: lists_text(), VECTORS: vectors_text(), ERRORS: errors_text(), SYMBOLS: symbols_text(), DOC: doc_text()}


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    files = render()
    if "--check" in argv:
        stale = [str(p.relative_to(ROOT)) for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("out of date:", ", ".join(stale), "(run scripts/gen-protocol.py)")
            return 1
        return 0
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
