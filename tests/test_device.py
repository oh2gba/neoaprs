"""What a station runs (neoaprs/device.py), from the destination call and the Mic-E type code of its packets, by the snapshot of the APRS device identification list the program carries."""
from datetime import UTC, datetime

import pytest

from neoaprs.aprsparse import parse
from neoaprs.device import DeviceTable, packet_device, table
from neoaprs.packet import Message, Packet, ThirdParty

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
WORKED = b'(_fn"Oj/'                                      # a Mic-E body (the longitude, the speed and course, the symbol), 33 25.64 N 112 07.74 W for the destination S32UVT


def heard(info: bytes, destination: str, source: str = "N0CALL", third_party: ThirdParty | None = None) -> Packet:
    decoded = parse(info, source, destination, NOW) if third_party is None else Message("OH2GBA", "x")
    return Packet(NOW, "in", b"", source, destination, (), info, decoded, third_party)


@pytest.mark.parametrize(("destination", "device"), [
    ("APK004", "Kenwood TH-D74"),               # exact
    ("APK005-3", "Kenwood TH-D75"),             # (an SSID on the destination is no part of the tocall)
    ("APDR15", "APRSdroid"),                    # `APDR??`
    ("APOT21", "OpenTracker"),                  # `APOT??`
    ("APK0XX", "Kenwood TH-D7"),                # `APK0??`, shorter than the exact entries above it
    ("APAGW5", "AGWtracker"),                   # `APAGW?` is written out further than `APAG??`
    ("APAGX5", "AGate"),
    ("APRS", ""), ("BEACON", ""), ("TCPIP", ""), ("", ""), ("APZZZZ", ""),     # (the list's "Unknown" entries are no name)
])
def test_a_tocall_names_its_device(destination: str, device: str) -> None:
    assert table().by_tocall(destination) == device


def test_n_is_a_digit_and_a_star_is_the_rest_of_the_call() -> None:
    devices = DeviceTable([("APDnnn", "aprsd"), ("APTT*", "Tiny"), ("APXYZ?", "Wide"), ("APXY??", "Narrow"), ("APEXAC", "Exact")], [], [])
    assert devices.by_tocall("APD123") == "aprsd" and devices.by_tocall("APDABC") == ""
    assert devices.by_tocall("APTT4") == "Tiny" and devices.by_tocall("APTTXY") == "Tiny"
    assert devices.by_tocall("APXYZ1") == "Wide" and devices.by_tocall("APXYA1") == "Narrow"
    assert devices.by_tocall("apexac") == "Exact"


@pytest.mark.parametrize(("comment", "device"), [
    ("`Hello_#", "Yaesu VX-8G"), ("`Hello_)", "Yaesu FTM-100D"), ("'Hello|3", "TinyTrak3"), ("`Hello[1", "APRSdroid"),       # a two-character suffix after the type code
    (">Hello", "Kenwood TH-D7A"), (">Hello^", "Kenwood TH-D74"), (">Hello=", "Kenwood TH-D72"), (">Hello&", "Kenwood TH-D75"),     # Kenwood, told apart by the last character
    ("]Hello", "Kenwood TM-D700"), ("]Hello=", "Kenwood TM-D710"), (">", "Kenwood TH-D7A"),
    ("`Hello_9", ""), ("`", ""), ("`ab", ""), ("Hello=", ""), ("", ""),                 # a suffix the list does not have, no type code
])
def test_a_mice_comment_names_its_device(comment: str, device: str) -> None:
    assert table().by_mice(comment) == device


def test_a_mice_packet_is_named_by_its_comment_and_not_by_the_destination() -> None:
    assert packet_device(heard(b"`" + WORKED + b"`Hello_#", "S32UVT")) == "Yaesu VX-8G"
    assert packet_device(heard(b"`" + WORKED + b">Hello^", "S32UVT")) == "Kenwood TH-D74"
    assert packet_device(heard(b"'" + WORKED + b"'Hi|4", "S32UVT")) == "TinyTrak4"
    assert packet_device(heard(b"`" + WORKED + b"`Hello", "S32UVT")) == ""           # (a Mic-E destination holds the latitude, it is no tocall: a comment with no known suffix names nothing)


def test_a_plain_packet_is_named_by_its_destination() -> None:
    assert packet_device(heard(b"!4903.50N/07201.75W-Test", "APDR15")) == "APRSdroid"
    assert packet_device(heard(b":OH2GBA   :hello{7", "APK004")) == "Kenwood TH-D74"
    assert packet_device(heard(b"!4903.50N/07201.75W-Test", "APRS")) == ""


def test_a_third_party_packet_is_named_by_the_packet_inside() -> None:
    inside = b"}OH2DPN>APDR15,TCPIP*:!4903.50N/07201.75W-Test"
    assert packet_device(heard(inside, "APRS", "OH7JHF-1", ThirdParty("OH2DPN", "APDR15", ("TCPIP*",)))) == "APRSdroid"
    unnamed = b"}OH2DPN>APRS,TCPIP*:!4903.50N/07201.75W-Test"
    assert packet_device(heard(unnamed, "APDR15", "OH7JHF-1", ThirdParty("OH2DPN", "APRS", ("TCPIP*",)))) == ""         # (the iGate's own destination says nothing of the station)


def test_the_snapshot_is_credited_to_its_source() -> None:
    from neoaprs import devicedata
    assert devicedata.__doc__ is not None and "aprsorg/aprs-deviceid" in devicedata.__doc__ and "CC BY-SA 2.0" in devicedata.__doc__
    assert len(devicedata.TOCALLS) > 300 and len(devicedata.MICE) > 20 and len(devicedata.MICE_LEGACY) >= 6
