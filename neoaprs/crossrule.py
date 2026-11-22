"""The pure rules of passing a packet from one radio of the station to another, only when its path asks for it by the pair's call (aprs-reference/cross-radio-digipeat-plan.md section 3): the request and its step, what is never passed, which radios are slow, and the paths of the replies; and `spliced`, the bytes of a frame sent again with another path, which the fill-in digipeater uses too."""
from collections.abc import Collection, Sequence
from dataclasses import replace

from neoaprs import ax25
from neoaprs.bulletin import board_slot
from neoaprs.callsign import CallsignError, parse_call
from neoaprs.message import is_query, is_telemetry_definition, same_call
from neoaprs.packet import Message, Packet
from neoaprs.radiotype import Limits
from neoaprs.route import INTERNET_MARKERS, is_marker, parse_alias, used_path

REPLY_WIDE = "WIDE2-1"          # the one hop after a gateway's call when the station reached the gateway through a digipeater (M1)


def spliced(raw: bytes, heard: ax25.Frame, frame: ax25.Frame) -> bytes:
    """The bytes that were heard (`heard` is what they decode to) with the path of `frame` in place of theirs; everything else is as it arrived."""
    start = 2 * ax25.ADDRESS_LEN
    return raw[:start] + ax25.encode_path(frame.path) + raw[start + ax25.ADDRESS_LEN * len(heard.path):]


def first_unused(frame: ax25.Frame) -> int | None:
    """The index of the first hop of the path without its H bit, wherever it stands; None for a path with none."""
    return next((i for i, hop in enumerate(frame.path) if not hop.repeated), None)


def cross(frame: ax25.Frame, call: tuple[str, int], ours: Collection[tuple[str, int]]) -> ax25.Frame | None:
    """The frame as it goes out on the other radio of the pair whose call is `call`, or None when it is no request for it: a UI frame whose first unused hop is the pair call exactly, SSID included (P1), with that hop marked used where it stands and nothing else changed (P4). None for a source that is one of `ours` (N1), a path that shows `call` used already (N2) or carries TCPIP or TCPXX anywhere (N5), and any other first unused hop or none (N4)."""
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
    """Whether the packet is never passed whatever its path: a third-party packet (N5, `packet.third_party`), a general query (an information field that starts with `?`), a message, ack, rej or directed query addressed to one of `ours`, the station call or a pair call, and a directed query onto a radio that carries no path, whose answer could not come back (N6)."""
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
    """The id of a message to a station that an ack can answer (a `Message` with text and `msg_id`, no ack or rej id, addressed to a station, not a bulletin, a group or a telemetry definition); None for any other packet (M2)."""
    decoded = packet.decoded
    if not isinstance(decoded, Message) or not decoded.msg_id or not decoded.text:
        return None
    if decoded.ack_id is not None or decoded.rej_id is not None:
        return None
    if board_slot(decoded.addressee) is not None or is_telemetry_definition(decoded.text):
        return None
    return decoded.msg_id


def slow_channel(limits: Limits) -> bool:
    """Whether a frame onto the radio holds its one shared channel for seconds, so that what a pair passes onto it is limited by L2 to L4: the types that pause before a retry for that reason (`retry_jitter_sec`; HF and LoRa today)."""
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
    """The path of a message or an ack of ours on a radio that carries no path (M1), from the path of the station's latest packet heard there (starred hops): its last used hop when that is a call, not an alias or a marker, and none of `ours` (a gateway), alone, or followed by REPLY_WIDE when any used hop stands before it (a digipeater on the way to the gateway; the gateway's own station call cannot be told from an own hill digi of its base, so a reply to a station heard through the gateway's own fill-in gets one wide hop too); () for anything else."""
    used = [hop[:-1] for hop in used_path(tuple(last_path)) if hop.endswith("*") and not is_marker(hop)]
    if not used or not _is_call(used[-1]) or any(same_call(used[-1], call) for call in ours):
        return ()
    gateway = used[-1]
    if used[:-1]:
        return (gateway, REPLY_WIDE)
    return (gateway,)


def back_path(path: Sequence[ax25.Address], call: tuple[str, int]) -> tuple[ax25.Address, ...]:
    """The path of an ack passed back (M2): the hops already used, in order, then the pair call marked used; the unused hops are dropped."""
    return (*(hop for hop in path if hop.repeated), ax25.Address(call[0], call[1], repeated=True))
