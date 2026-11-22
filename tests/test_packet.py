"""The packet dataclasses: frozen, the kind and summary of each decoded form, text decoding, and the
packet's radio kept as an id with the frame reader that stamps it (neoaprs/tncmode.py).
"""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime

import pytest

from neoaprs.aprsextension import Extensions, Phg
from neoaprs.aprsfreq import Frequency
from neoaprs.aprslocator import Locator
from neoaprs.aprsstorm import Storm
from neoaprs.aprstelemetry import Telemetry
from neoaprs import ax25, kiss
from neoaprs.packet import (
    ItemReport,
    Message,
    ObjectReport,
    Other,
    Packet,
    Position,
    Status,
    ThirdParty,
    Undecoded,
    channel_of,
    decode_text,
    duplicate_key,
    via_of,
)
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.tncmode import packet_of, read_frame

T = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
POS = Position(60.17, 24.94, "/", "-", "comment")


def packet(decoded: object) -> Packet:
    return Packet(T, "in", b"raw", "OH2XYZ-9", "APRS", ("WIDE1-1",), b"info", decoded)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("decoded", "kind", "summary"),
    [
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
        (
            Telemetry(5, [199, 0, 255, 73, 123.5], "01101001", "Balloon"),
            "other",
            "telemetry #5: 199 0 255 73 123.5 01101001 Balloon",
        ),
        (Telemetry(None, [1, 2, 3, 4, 5], "00000000"), "other", "telemetry #MIC: 1 2 3 4 5 00000000"),
        (
            Status("my house", locator=Locator("IO91sx", 51.9, -0.4, "/", "-")),
            "status",
            "status locator IO91sx my house",
        ),
        (Status("", locator=Locator("IO91", 51.5, -1.0, "/", "G")), "status", "status locator IO91"),
        (
            Position(60.17, 24.94, "/", "-", "x", extensions=Extensions(phg=Phg(25, 6.1, 3, 90, 12.8), range_km=80.0)),
            "position",
            "position 60.1700 24.9400 /- [PHG 25 W, 6 m, 3 dB, 90°, range 13 km, range 80 km] x",
        ),
        (
            Position(60.17, 24.94, "/", "-", timestamp=T, timestamp_local=True),
            "position",
            "position 60.1700 24.9400 /- (time 21 12:00 local)",
        ),
        (
            Position(60.17, 24.94, "/", ">", locator=Locator("IO91sx", 51.9, -0.4, "/", "-")),
            "position",
            "position 60.1700 24.9400 /> locator IO91sx",
        ),
        (Other("capabilities", "<IGATE", items={"IGATE": ""}), "other", "capabilities: <IGATE"),
        (Undecoded("position too short", "!49"), "undecoded", "undecoded (position too short): !49"),
    ],
)
def test_kind_and_summary(decoded: object, kind: str, summary: str) -> None:
    p = packet(decoded)
    assert (p.kind, p.summary) == (kind, summary)


def test_a_summary_tells_the_frequency_the_storm_and_the_sign() -> None:
    frequency = Frequency(145.775, tone_hz=118, offset_khz=-600)
    assert (
        packet(Position(60.17, 24.94, "/", "-", "Voice", frequency=frequency)).summary
        == "position 60.1700 24.9400 /- [145.775 MHz, tone 118 Hz, -600 kHz] Voice"
    )
    storm = Position(60.17, 24.94, "\\", "@", storm=Storm("TD", 50.0), sign="55")
    assert packet(storm).summary == "position 60.1700 24.9400 \\@ [tropical depression, wind 50 km/h] [sign 55]"
    assert packet(Status("net", frequency=Frequency(145.5))).summary == "status [145.500 MHz] net"


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
    assert (
        p.comment,
        p.course_deg,
        p.speed_kmh,
        p.altitude_m,
        p.timestamp,
        p.messaging,
        p.compressed,
        p.ambiguity,
    ) == ("", None, None, None, None, False, False, 0)
    assert (p.extensions, p.timestamp_local, p.locator) == (None, False, None)
    assert (p.frequency, p.storm, p.sign) == (None, None, None)


def test_a_naive_time_is_refused() -> None:
    with pytest.raises(ValueError, match="aware"):
        Packet(datetime(2026, 1, 1), "in", b"", "A", "B", (), b"", POS)


def test_text_is_utf_8_when_it_is_and_latin_1_when_not() -> None:
    assert decode_text("Hyvää".encode()) == "Hyvää"
    assert decode_text(b"Hyv\xe4\xe4") == "Hyvää"
    assert decode_text(b"") == ""


def test_a_third_party_packet_is_from_the_sender_inside_and_its_summary_says_who_put_it_on_the_air() -> None:
    plain = packet(Status("Net on"))
    assert (plain.sender, plain.gate, plain.summary) == ("OH2XYZ-9", "", "status Net on")
    third = Packet(
        T,
        "in",
        b"raw",
        "OH7JHF-1",
        "APRS",
        ("OH2RCH-3*",),
        b"info",
        Message("OH2GBA", "", ack_id="10"),
        ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*")),
        "rf-gated",
    )
    assert (third.source, third.sender, third.gate, third.summary) == (
        "OH7JHF-1",
        "OH2DPN",
        "OH7JHF-1",
        "ack 10 to OH2GBA via OH7JHF-1 (third-party)",
    )


# ---- how the packet reached us


def test_a_packet_comes_by_the_radio_unless_it_is_made_otherwise_and_the_channel_is_frozen_with_it() -> None:
    made = packet(Status("x"))
    assert (made.via, made.on_air, made.gate) == ("rf", True, "")
    with pytest.raises(FrozenInstanceError):
        made.via = "is"  # type: ignore[misc]


def test_the_channels_are_three_words_and_a_text_that_is_none_of_them_is_refused() -> None:
    assert [via_of(text) for text in ("rf", "rf-gated", "is")] == ["rf", "rf-gated", "is"]
    for bad in ("", "RF", "tcp", "rf_gated"):
        with pytest.raises(ValueError, match="no channel"):
            via_of(bad)
    with pytest.raises(ValueError, match="no channel"):
        Packet(T, "in", b"", "A", "B", (), b"", POS, None, "wifi")  # type: ignore[arg-type]


def test_a_packet_is_rf_gated_exactly_when_it_came_on_the_radio_as_a_third_party_packet() -> None:
    third = ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*"))
    assert (
        channel_of(None) == "rf"
        and channel_of(third) == "rf-gated"
        and channel_of(third, internet=True) == "is"
        and channel_of(None, internet=True) == "is"
    )
    with pytest.raises(ValueError, match="rf-gated exactly when"):
        Packet(T, "in", b"", "OH7JHF-1", "APRS", (), b"", POS, third, "rf")
    with pytest.raises(ValueError, match="rf-gated exactly when"):
        Packet(T, "in", b"", "OH7JHF-1", "APRS", (), b"", POS, None, "rf-gated")
    gated = Packet(T, "in", b"", "OH7JHF-1", "APRS", (), b"", POS, third, "rf-gated")
    assert (gated.via, gated.on_air, gated.gate) == ("rf-gated", True, "OH7JHF-1"), (
        "an iGate put it on the air: it is on the radio's channel"
    )


def test_a_packet_from_the_internet_was_never_on_the_air_has_no_gate_and_is_never_one_of_ours() -> None:
    internet = Packet(T, "in", b"", "OH2ABC", "APRS", ("TCPIP*", "qAC", "T2FINLAND"), b"", Status("x"), None, "is")
    assert (internet.via, internet.on_air, internet.gate, internet.summary) == ("is", False, "", "status x (APRS-IS)")
    wrapped = Packet(
        T,
        "in",
        b"",
        "OH7JHF-1",
        "APRS",
        ("TCPIP*", "qAC", "T2FINLAND"),
        b"",
        Status("x"),
        ThirdParty("OH2DPN", "APJYC1"),
        "is",
    )
    assert (wrapped.sender, wrapped.gate, wrapped.on_air) == ("OH2DPN", "", False), (
        "a wrapper in a line of APRS-IS is opened, and nobody put it on the air"
    )
    with pytest.raises(ValueError, match="never goes by the internet"):
        Packet(T, "out", b"", "OH2GBA", "APRS", (), b"", Status("x"), None, "is")


# ---- the Dummy radio


def test_a_packet_of_the_dummy_radio_is_on_the_air_for_every_service_but_is_never_gateable() -> None:
    from neoaprs.packet import GATEABLE, VIAS

    made_up = Packet(T, "in", b"", "QDUMMY-1", "APRS", ("WIDE1*",), b"", Status("x"), None, "dummy")
    assert (made_up.via, made_up.on_air, made_up.gate, made_up.summary) == ("dummy", True, "", "status x")
    assert GATEABLE == frozenset({"rf", "rf-gated"}) and isinstance(GATEABLE, frozenset)
    assert "dummy" not in GATEABLE and "is" not in GATEABLE, (
        "what the Dummy radio makes up never reaches APRS-IS, and what came from APRS-IS never goes back"
    )
    assert set(VIAS) - GATEABLE == {"is", "dummy"}, (
        "a new channel is not gateable until it is put in GATEABLE on purpose"
    )
    assert (
        channel_of(None, dummy=True) == "dummy"
        and channel_of(ThirdParty("A", "B"), dummy=True) == "dummy"
        and channel_of(None, internet=True, dummy=True) == "is"
    )
    wrapped = Packet(T, "in", b"", "QDUMMY-1", "APRS", (), b"", Status("x"), ThirdParty("QDUMMY-2", "APRS"), "dummy")
    assert (wrapped.sender, wrapped.gate) == ("QDUMMY-2", "")


def test_two_copies_of_a_packet_are_one_by_source_destination_without_its_ssid_and_information() -> None:
    assert (
        duplicate_key("OH2XYZ-9", "APRS-3", b"!x")
        == duplicate_key("OH2XYZ-9", "APRS", b"!x")
        == ("OH2XYZ-9", "APRS", b"!x")
    )
    assert duplicate_key("OH2XYZ-9", "APRS", b"!x") != duplicate_key("OH2XYZ-8", "APRS", b"!x")
    assert duplicate_key("OH2XYZ-9", "APRS", b"!x") != duplicate_key("OH2XYZ-9", "APRS", b"!y")


# ---- the radio of a packet: its id


def test_a_packet_keeps_the_id_of_its_radio() -> None:
    assert [f.name for f in fields(Packet)].count("radio_id") == 1
    by_id = {radio_id: replace(packet(POS), radio_id=radio_id) for radio_id in (None, FM_ID, HF_ID, 3, 12)}
    assert [p.radio_id for p in by_id.values()] == [None, 1, 2, 3, 12], "any radio by its id"
    assert packet(POS).radio_id is None, "one made without a radio (a test's, or the internet's)"
    with pytest.raises(FrozenInstanceError):
        by_id[3].radio_id = 1  # type: ignore[misc]
    assert by_id[3].radio_id == 3, "and the packet is as it was"


def test_the_constructor_and_replace_take_the_id() -> None:
    hf = Packet(T, "in", b"raw", "OH2XYZ-9", "APRS", ("WIDE1-1",), b"info", POS, radio_id=HF_ID)
    assert hf == replace(packet(POS), radio_id=HF_ID) and hash(hf) == hash(replace(packet(POS), radio_id=HF_ID))
    assert replace(hf, radio_id=3).radio_id == 3 and replace(hf, snr=4.5).radio_id == HF_ID, (
        "replace by the id, and of anything else"
    )
    in_place = Packet(T, "in", b"raw", "OH2XYZ-9", "APRS", ("WIDE1-1",), b"info", POS, None, "rf", HF_ID, 4.5)
    assert (in_place.radio_id, in_place.snr) == (HF_ID, 4.5) and in_place == replace(hf, snr=4.5), (
        "the id in its place, the eleventh value"
    )


def test_what_names_no_radio_is_refused() -> None:
    for bad in (0, -1, 1.0, True, "fm", "hf", "both", "1", "lora"):
        with pytest.raises(ValueError, match="is no radio"):
            replace(packet(POS), radio_id=bad)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="is no radio"):
            Packet(T, "in", b"", "A", "B", (), b"", POS, None, "rf", bad)  # type: ignore[arg-type]


def test_the_frame_reader_stamps_the_id_of_the_radio_and_radio_1_when_none_is_said() -> None:
    frame = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH2XYZ-9"), (), info=b">hello")
    raw = ax25.encode(frame)
    [kiss_frame] = kiss.KissDecoder().feed(kiss.encode(raw))
    for radio_id in (FM_ID, HF_ID, 3, None):
        read = read_frame(kiss_frame, T, radio_id=radio_id)
        assert not isinstance(read, str) and read[0].radio_id == radio_id and read[1] == frame
        assert packet_of("out", raw, frame, T, radio_id=radio_id).radio_id == radio_id
    plain = read_frame(kiss_frame, T)
    assert not isinstance(plain, str) and plain[0].radio_id == FM_ID == packet_of("in", raw, frame, T).radio_id, (
        "a caller that says no radio means radio 1, as it meant the FM radio"
    )


def test_the_frame_reader_of_the_dummy_radio_stamps_its_radio_and_its_channel() -> None:
    frame = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OH2XYZ-9"), (), info=b">hello")
    raw = ax25.encode(frame)
    [kiss_frame] = kiss.KissDecoder().feed(kiss.encode(raw))
    for radio_id in (FM_ID, HF_ID):
        by_place, by_name = (
            read_frame(kiss_frame, T, True, radio_id=radio_id),
            packet_of("in", raw, frame, T, True, radio_id=radio_id),
        )
        assert (
            not isinstance(by_place, str)
            and by_place[0].radio_id == radio_id == by_name.radio_id
            and by_place[0].via == "dummy" == by_name.via
        )
