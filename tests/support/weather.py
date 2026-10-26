"""Weather packets for the tests: a packet as the TNC makes it, with the real report of OH2MUI as the default, and the same packet with the weather kept as plain comment text.

    report("t050", "OH2NJR", at)        # a position with the weather symbol; `old=True` is the packet with the weather as plain comment text
    heard(b"_10090556t050", "OH2NJR")   # any information field, third-party wrappers included
"""
from datetime import datetime

from neoaprs import ax25
from neoaprs.aprsthirdparty import parse_packet
from neoaprs.aprsweather import Weather
from neoaprs.clock import utc
from neoaprs.packet import Other, Packet, Position, channel_of

T0 = utc(2026, 10, 21, 12, 0, 0)
REAL = "107/001g001t050r001p016P013h85b10284"
WX = Weather(107, 1.6, 1.6, 10.0, 85, 1028.4, 0.3, 4.1, 3.3, raw=REAL)


def heard(info: bytes, source: str = "OH2MUI", at: datetime = T0, direction: str = "in", old: bool = False) -> Packet:
    """A packet as the TNC makes it; `old` keeps the weather as plain comment text, undecoded."""
    frame = ax25.Frame(ax25.Address("APRX29"), ax25.Address.parse(source), (ax25.Address.parse("OH2RCH-2"),), info=info)
    decoded, third = parse_packet(info, source, "APRX29", at)
    if old and isinstance(decoded, Position) and decoded.weather is not None:
        decoded = Position(decoded.lat, decoded.lon, decoded.symbol_table, decoded.symbol_code, decoded.weather.raw + decoded.comment, timestamp=decoded.timestamp, messaging=decoded.messaging)
    if old and isinstance(decoded, Other):
        decoded = Other(decoded.kind, decoded.text)
    return Packet(at, direction, ax25.encode(frame), source, "APRX29", ("OH2RCH-2",), info, decoded, third, channel_of(third))  # type: ignore[arg-type]


def report(fields: str = REAL, source: str = "OH2MUI", at: datetime = T0, **more: object) -> Packet:
    return heard(b"@210945z6024.43N/02352.73E_" + fields.encode() + b" RX Igate & WX station", source, at, **more)  # type: ignore[arg-type]
