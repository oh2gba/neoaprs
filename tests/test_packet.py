"""The packet dataclasses: frozen, the kind and the summary of each decoded form, text decoding."""
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from neoaprs.aprsextension import Extensions, Phg
from neoaprs.aprslocator import Locator
from neoaprs.aprstelemetry import Telemetry
from neoaprs.packet import ItemReport, Message, ObjectReport, Other, Packet, Position, Status, ThirdParty, Undecoded, decode_text

T = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
POS = Position(60.17, 24.94, "/", "-", "comment")


def packet(decoded: object) -> Packet:
    return Packet(T, "in", b"raw", "OH2XYZ-9", "APRS", ("WIDE1-1",), b"info", decoded)  # type: ignore[arg-type]


@pytest.mark.parametrize(("decoded", "kind", "summary"), [
    (POS, "position", "position 60.1700 24.9400 /- comment"),
    (Position(-33.75, 151.2, "\\", ">"), "position", "position -33.7500 151.2000 \\>"),
    (Message("OH2GBA-7", "text", "12"), "message", "message to OH2GBA-7: text {12}"),
    (Message("OH2GBA-7", "text"), "message", "message to OH2GBA-7: text"),
    (Message("OH2GBA-7", "", ack_id="12"), "message", "ack 12 to OH2GBA-7"),
    (Message("OH2GBA-7", "", rej_id="12"), "message", "reject 12 to OH2GBA-7"),
    (ObjectReport("LEADER", True, POS), "object", "object LEADER alive 60.1700 24.9400 /- comment"),
    (ObjectReport("LEADER", False, POS), "object", "object LEADER killed 60.1700 24.9400 /- comment"),
    (ItemReport("AID #2", True, POS), "item", "item AID #2 alive 60.1700 24.9400 /- comment"),
    (Status("Net on"), "status", "status Net on"),
    (Other("telemetry", "T#005"), "other", "telemetry: T#005"),
    (Telemetry(5, [199, 0, 255, 73, 123.5], "01101001", "Balloon"), "other", "telemetry #5: 199 0 255 73 123.5 01101001 Balloon"),
    (Telemetry(None, [1, 2, 3, 4, 5], "00000000"), "other", "telemetry #MIC: 1 2 3 4 5 00000000"),
    (Status("my house", locator=Locator("IO91sx", 51.9, -0.4, "/", "-")), "status", "status locator IO91sx my house"),
    (Status("", locator=Locator("IO91", 51.5, -1.0, "/", "G")), "status", "status locator IO91"),
    (Position(60.17, 24.94, "/", "-", "x", extensions=Extensions(phg=Phg(25, 6.1, 3, 90, 12.8), range_km=80.0)), "position", "position 60.1700 24.9400 /- [PHG 25 W, 6 m, 3 dB, 90°, range 13 km, range 80 km] x"),
    (Position(60.17, 24.94, "/", "-", timestamp=T, timestamp_local=True), "position", "position 60.1700 24.9400 /- (time 21 12:00 local)"),
    (Position(60.17, 24.94, "/", ">", locator=Locator("IO91sx", 51.9, -0.4, "/", "-")), "position", "position 60.1700 24.9400 /> locator IO91sx"),
    (Other("capabilities", "<IGATE", items={"IGATE": ""}), "other", "capabilities: <IGATE"),
    (Undecoded("position too short", "!49"), "undecoded", "undecoded (position too short): !49"),
])
def test_kind_and_summary(decoded: object, kind: str, summary: str) -> None:
    p = packet(decoded)
    assert (p.kind, p.summary) == (kind, summary)


def test_a_summary_is_one_line() -> None:
    assert "\n" not in packet(Status("a\nb\r\x00c")).summary
    assert packet(Status("a\nb")).summary == "status a?b"


def test_the_dataclasses_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        POS.lat = 1.0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        packet(POS).source = "X"  # type: ignore[misc]


def test_position_defaults() -> None:
    p = Position(1.0, 2.0, "/", "-")
    assert (p.comment, p.course_deg, p.speed_kmh, p.altitude_m, p.timestamp, p.messaging, p.compressed, p.ambiguity) == ("", None, None, None, None, False, False, 0)
    assert (p.extensions, p.timestamp_local, p.locator) == (None, False, None)


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        Packet(datetime(2026, 1, 1), "in", b"", "A", "B", (), b"", POS)


def test_text_is_utf_8_when_it_is_and_latin_1_when_not() -> None:
    assert decode_text("Hyvää".encode()) == "Hyvää"
    assert decode_text(b"Hyv\xe4\xe4") == "Hyvää"
    assert decode_text(b"") == ""


def test_a_third_party_packet_is_from_the_sender_inside_and_its_summary_says_who_put_it_on_the_air() -> None:
    plain = packet(Status("Net on"))
    assert (plain.sender, plain.via, plain.summary) == ("OH2XYZ-9", "", "status Net on")
    third = Packet(T, "in", b"raw", "OH7JHF-1", "APRS", ("OH2RCH-3*",), b"info", Message("OH2GBA", "", ack_id="10"), ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*")))
    assert (third.source, third.sender, third.via, third.summary) == ("OH7JHF-1", "OH2DPN", "OH7JHF-1", "ack 10 to OH2GBA via OH7JHF-1 (third-party)")
