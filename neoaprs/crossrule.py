"""Rules for passing a packet between two radios of the station when its path asks for it.

The rule labels (P1, N1, M1 ...) refer to aprs-reference/cross-radio-digipeat-plan.md section 3."""
from collections.abc import Collection, Sequence
from dataclasses import replace

from neoaprs import ax25
from neoaprs.bulletin import board_slot
from neoaprs.callsign import CallsignError, parse_call
from neoaprs.message import is_query, is_telemetry_definition, same_call
from neoaprs.packet import Message, Packet
from neoaprs.radiotype import Limits
from neoaprs.route import INTERNET_MARKERS, is_marker, parse_alias, used_path

# The hop after a gateway's call when the station reached it through a digipeater (M1).
REPLY_WIDE = "WIDE2-1"


def spliced(raw: bytes, heard: ax25.Frame, frame: ax25.Frame) -> bytes:
    start = 2 * ax25.ADDRESS_LEN
    return raw[:start] + ax25.encode_path(frame.path) + raw[start + ax25.ADDRESS_LEN * len(heard.path):]


def first_unused(frame: ax25.Frame) -> int | None:
    return next((i for i, hop in enumerate(frame.path) if not hop.repeated), None)


def cross(frame: ax25.Frame, call: tuple[str, int], ours: Collection[tuple[str, int]]) -> ax25.Frame | None:
    """Return the frame as it goes out on the other radio of the pair with call `call`, or None.

    First unused hop = the pair call (P1); it is marked used, nothing else changes (P4)."""
    if not frame.is_ui or (frame.source.call, frame.source.ssid) in ours:
        return None
    path = frame.path
    if any(hop.call in INTERNET_MARKERS or (hop.repeated and (hop.call, hop.ssid) == call) for hop in path):
        return None
    at = first_unused(frame)
    if at is None or (path[at].call, path[at].ssid) != call:
        return None
    return replace(frame, path=path[:at] + (replace(path[at], repeated=True),) + path[at + 1:])


def not_to_pass(packet: Packet, ours: Collection[str], target_paths: bool) -> bool:
    """Return whether the packet is never passed: third-party, queries, messages to `ours`."""
    if packet.third_party is not None or packet.info.startswith(b"?"):
        return True
    decoded = packet.decoded
    if not isinstance(decoded, Message):
        return False
    if any(same_call(decoded.addressee, call) for call in ours):
        return True
    asks = decoded.ack_id is None and decoded.rej_id is None and is_query(decoded.text)
    return asks and not target_paths


def message_id(packet: Packet) -> str | None:
    """Return the id of a message an ack can answer, else None (M2)."""
    decoded = packet.decoded
    if not isinstance(decoded, Message) or not decoded.msg_id or not decoded.text:
        return None
    if decoded.ack_id is not None or decoded.rej_id is not None:
        return None
    if board_slot(decoded.addressee) is not None or is_telemetry_definition(decoded.text):
        return None
    return decoded.msg_id


def slow_channel(limits: Limits) -> bool:
    """Return whether a frame onto the radio holds its shared channel for seconds (HF, LoRa)."""
    return limits.retry_jitter_sec > 0


def _is_call(hop: str) -> bool:
    if parse_alias(hop) is not None or is_marker(hop):
        return False
    try:
        parse_call(hop)
    except CallsignError:
        return False
    return True


def reply_path(last_path: Sequence[str], ours: Collection[str]) -> tuple[str, ...]:
    """Return the path of our message or ack on a radio that carries no path (M1), or ()."""
    used = [hop[:-1] for hop in used_path(tuple(last_path)) if hop.endswith("*") and not is_marker(hop)]
    if not used or not _is_call(used[-1]) or any(same_call(used[-1], call) for call in ours):
        return ()
    gateway = used[-1]
    if used[:-1]:
        return (gateway, REPLY_WIDE)
    return (gateway,)


def back_path(path: Sequence[ax25.Address], call: tuple[str, int]) -> tuple[ax25.Address, ...]:
    return (*(hop for hop in path if hop.repeated), ax25.Address(call[0], call[1], repeated=True))
