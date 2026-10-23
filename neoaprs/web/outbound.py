"""The one way out of the daemon: every message to a page goes through the Publisher, to one page (`send`) or to all (`broadcast`). Here a message becomes a frame (compact JSON), here the size of
a frame is held to a cap, and here the outgoing check against neoaprs/web/protocol.py sits (NEOAPRS_VALIDATE_OUT=1).
"""
import json
import logging
import os
from collections import Counter
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .protocol import MESSAGES, TOPIC_ITEMS, TOPIC_VALUES
from .session import Client, Connection

log = logging.getLogger("neoaprs.web")

MEGABYTE = 1024 * 1024
MAX_WRITE_BUFFER = 32 * MEGABYTE   # what a socket holds for a page that does not read, and is then cut off (neoaprs/web/server.py); the whole station book is a few megabytes, so a page that reads is far below it.
                                   # The state hub (neoaprs/web/hub.py) calls a page behind when its socket holds a share of it.
MAX_MESSAGE = 16 * MEGABYTE        # the largest message sent to one page, whole: the `state` of the stations after years of listening. The write buffer of a socket is bigger, and holds what a page has not yet read.

# Every message that did not match neoaprs/web/protocol.py, when outgoing validation is on. The tests look at it after each test: a signal handler that raises is only logged by the Signal, the list is
# what cannot be missed.
VIOLATIONS: list[str] = []
SEEN: Counter[str] = Counter()          # per message type: how many were checked and found right (the contract tests read it)


class ProtocolViolation(Exception):
    """A message the daemon was about to send does not match neoaprs/web/protocol.py."""


def encode(message: dict[str, Any]) -> str:
    """The frame: compact JSON, what JSON cannot hold written as text."""
    return json.dumps(message, separators=(",", ":"), default=str)


def _type_of(text: str) -> str:
    try:
        kind = json.loads(text).get("type")
    except (ValueError, AttributeError):
        return "?"
    return kind if isinstance(kind, str) else "?"


def _why(e: ValidationError, skip: int = 1) -> str:
    """The fields and what is wrong with them; `skip` is the places of the location that are the tag of the union and not a field."""
    errors = e.errors(include_url=False, include_input=False)
    return "; ".join(f"{'.'.join(str(x) for x in err['loc'][skip:])}: {err['msg']}" for err in errors[:4]) + (f" (and {len(errors) - 4} more)" if len(errors) > 4 else "")


def _validate(adapter: "TypeAdapter[Any]", value: Any, what: str) -> None:
    """The value against the type, as JSON (a tuple of the protocol is a list on the wire)."""
    try:
        adapter.validate_json(json.dumps(value))
    except ValidationError as e:
        raise ValueError(f"{what}: {_why(e, 0)}") from None


def _check_topic_values(message: Any) -> None:
    """A `state`, or the `replace` of a `patch`, holds a value of the type the topic has in TopicValues (a topic the protocol has no type for is a mistake of the daemon's). A `set` of a topic
    that is a table holds an item of the type in TOPIC_ITEMS."""
    if message.type not in ("state", "patch"):
        return
    topic = message.topic
    if topic not in TOPIC_VALUES:
        raise LookupError(f"{topic}: a topic that has no type in TopicValues")
    if message.type == "state":
        _validate(TOPIC_VALUES[topic], message.value, f"the value of {topic}")
        return
    for op in message.ops:
        if op.op == "replace":
            _validate(TOPIC_VALUES[topic], op.value, f"the value of {topic}")
        elif op.op == "set" and topic in TOPIC_ITEMS:
            _validate(TOPIC_ITEMS[topic], op.value, f"the item {op.key} of {topic}")


class Publisher:
    """The open pages and the ways to write to them."""

    def __init__(self, validate_out: bool | None = None) -> None:
        # outgoing messages are checked against the protocol models when asked (NEOAPRS_VALIDATE_OUT=1): off in production, where it would only cost time
        self.validate_out = os.environ.get("NEOAPRS_VALIDATE_OUT") == "1" if validate_out is None else validate_out
        self.raise_on_invalid = os.environ.get("NEOAPRS_VALIDATE_RAISE") == "1"
        self._reported: set[str] = set()
        self.connections: dict[Client, Connection] = {}

    def open(self, client: Client, ip: str) -> Connection:
        conn = self.connections[client] = Connection(client, self, ip)
        return conn

    def close(self, client: Client) -> None:
        conn = self.connections.pop(client, None)
        if conn is not None:
            conn.closed = True

    def send(self, conn: Connection, message: dict[str, Any]) -> None:
        self.send_frame(conn, encode(message))

    def send_frame(self, conn: Connection, text: str) -> None:
        """A frame that is made already: the size is held to the cap, and the outgoing check looks at it."""
        if len(text) > MAX_MESSAGE:                               # the page is told, instead of being cut off by a write that cannot be made
            kind = _type_of(text)
            log.warning("a %s message of %.0f MB was not sent to %s: more than %d MB", kind, len(text) / MEGABYTE, conn.ip, MAX_MESSAGE // MEGABYTE)
            text = encode({"type": "error", "text": f"The {kind} answer is {len(text) / MEGABYTE:.0f} MB, too big to send ({MAX_MESSAGE // MEGABYTE} MB at most)"})
        self._check(text)
        conn.client.send_json(text)

    def broadcast(self, message: dict[str, Any]) -> None:
        if not self.connections:
            return
        text = encode(message)
        self._check(text)
        for conn in list(self.connections.values()):
            self._deliver(conn, text)

    @staticmethod
    def _deliver(conn: Connection, frame: str) -> None:
        """One page's frame; what goes wrong with this page's socket is this page's: the others are sent theirs."""
        try:
            conn.client.send_json(frame)
        except Exception:
            log.exception("a frame could not be sent to %s", conn.ip)

    def _check(self, text: str) -> None:
        """Outgoing validation: the frame, as it goes over the wire, against the Message union."""
        if not self.validate_out:
            return
        try:
            message = MESSAGES.validate_json(text)
            _check_topic_values(message)
            SEEN[message.type] += 1
        except (ValidationError, LookupError, ValueError) as e:
            kind, why = _type_of(text), _why(e) if isinstance(e, ValidationError) else str(e)
            if len(VIOLATIONS) < 200:
                VIOLATIONS.append(f"{kind}: {why}")
            if self.raise_on_invalid:
                raise ProtocolViolation(f"message {kind} does not match the protocol: {why}") from None
            if kind not in self._reported:                       # once for each type: a flood in the log would hide the first one
                self._reported.add(kind)
                log.error("message %s does not match the protocol (reported once): %s", kind, why)
