"""The one way out to the pages: the Publisher sends to one page or broadcasts to all.

It encodes messages as compact JSON frames, caps frame size and runs the outgoing check against
protocol.py (NEOAPRS_VALIDATE_OUT=1).
"""
import json
import logging
import math
import os
from collections import Counter
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .protocol import MESSAGES, TOPIC_ITEMS, TOPIC_VALUES
from .session import Client, Connection, error_message

log = logging.getLogger("neoaprs.web")

MEGABYTE = 1024 * 1024
# What a socket may hold for a page that does not read before it is cut off. The station book is a
# few megabytes, so a reading page is far below it. The hub calls a page behind at a share of this
# size.
MAX_WRITE_BUFFER = 32 * MEGABYTE
# Largest single message to one page (the whole `state` of the stations); smaller than the write
# buffer.
MAX_MESSAGE = 16 * MEGABYTE

# Messages that did not match protocol.py while outgoing validation is on. The tests read it after
# each test, because a signal handler that raises is only logged.
VIOLATIONS: list[str] = []
NOT_FINITE_SEEN: set[str] = set()  # message kinds with a non-finite number, each logged once
SEEN: Counter[str] = Counter()  # per message type: how many were checked and found valid


class ProtocolViolation(Exception):
    """A message about to be sent does not match protocol.py."""


def _finite(value: Any) -> Any:
    """Return the value with every NaN and infinity replaced by None."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    return value


def encode(message: dict[str, Any]) -> str:
    """Return the compact JSON frame; a non-finite number (rejected by JSON.parse) is sent as null."""
    try:
        return json.dumps(message, separators=(",", ":"), default=str, allow_nan=False)
    except ValueError:
        pass
    kind = f"{message.get('type', '?')} {message.get('topic', '')}".strip()
    if kind not in NOT_FINITE_SEEN:
        NOT_FINITE_SEEN.add(kind)
        log.warning("a %s message holds a number that is not finite (NaN or infinity): it is sent as null (reported once for each kind)", kind)
    return json.dumps(_finite(message), separators=(",", ":"), default=str, allow_nan=False)


def _type_of(text: str) -> str:
    try:
        kind = json.loads(text).get("type")
    except (ValueError, AttributeError):
        return "?"
    return kind if isinstance(kind, str) else "?"


def _why(e: ValidationError, skip: int = 1) -> str:
    """Return the fields and their problems; the first `skip` location items are the union tag."""
    errors = e.errors(include_url=False, include_input=False)
    return "; ".join(f"{'.'.join(str(x) for x in err['loc'][skip:])}: {err['msg']}" for err in errors[:4]) + (f" (and {len(errors) - 4} more)" if len(errors) > 4 else "")


def _validate(adapter: "TypeAdapter[Any]", value: Any, what: str) -> None:
    """Validate the value against the type as JSON (a protocol tuple is a list on the wire)."""
    try:
        adapter.validate_json(json.dumps(value))
    except ValidationError as e:
        raise ValueError(f"{what}: {_why(e, 0)}") from None


def _check_topic_values(message: Any) -> None:
    """Check a `state` or `replace` value and a table `set` item against the protocol types."""
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
    def __init__(self, validate_out: bool | None = None) -> None:
        # Off in production, where checking would only cost time.
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
        """Send an already encoded frame, applying the size cap and the outgoing check."""
# Tell the page rather than cut it off with an unwritable frame.
        if len(text) > MAX_MESSAGE:
            kind = _type_of(text)
            log.warning("a %s message of %.0f MB was not sent to %s: more than %d MB", kind, len(text) / MEGABYTE, conn.ip, MAX_MESSAGE // MEGABYTE)
            text = encode(error_message(f"The answer is {len(text) / MEGABYTE:.0f} MB, too big to send ({MAX_MESSAGE // MEGABYTE} MB at most)", code="too_big", params={"kind": kind, "megabytes": len(text) // MEGABYTE, "max": MAX_MESSAGE // MEGABYTE}))
        self._check(text)
        conn.client.send_json(text)

    def send_binary(self, conn: Connection, data: bytes) -> None:
        """Send a binary frame; it is not JSON so it is not validated.

        A failing socket affects this page only.
        """
        try:
            conn.client.send_binary(data)
        except Exception:
            log.exception("a binary frame could not be sent to %s", conn.ip)

    def broadcast(self, message: dict[str, Any]) -> None:
        if not self.connections:
            return
        text = encode(message)
        self._check(text)
        for conn in list(self.connections.values()):
            self._deliver(conn, text)

    @staticmethod
    def _deliver(conn: Connection, frame: str) -> None:
        """Send a frame to one page; a failure on its socket does not stop the others."""
        try:
            conn.client.send_json(frame)
        except Exception:
            log.exception("a frame could not be sent to %s", conn.ip)

    def _check(self, text: str) -> None:
        """Validate the outgoing frame against the Message union."""
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
            if kind not in self._reported:  # once per type; a flood would hide the first
                self._reported.add(kind)
                log.error("message %s does not match the protocol (reported once): %s", kind, why)
