"""A line of APRS-IS as a Packet (neoaprs/aprsisline.py): the header, the path with its q-construct, the information field read by the ordinary dispatcher, the channel `is`, and the lines that are no packet."""
from datetime import timedelta

import pytest

from neoaprs.aprsisline import IsLineError, QConstruct, heard_by_radio, is_comment, parse_is_line, q_construct
from neoaprs.clock import utc
from neoaprs.packet import IS, Message, Other, Position, Status, Undecoded

NOW = utc(2026, 10, 26, 12, 0, 0)


def test_a_position_from_a_client_is_a_packet_that_came_by_the_internet() -> None:
    packet = parse_is_line("OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi", NOW)
    assert (packet.via, packet.direction, packet.heard_at, packet.source, packet.destination, packet.sender) == (IS, "in", NOW, "OH2ABC", "APRS", "OH2ABC")
    assert packet.path == ("TCPIP*", "qAC", "T2FINLAND") and packet.info == b"=6012.34N/02456.78E-hi" and packet.third_party is None
    assert packet.raw == b"OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi"
    assert isinstance(packet.decoded, Position) and (packet.decoded.symbol_code, packet.decoded.comment, packet.decoded.messaging) == ("-", "hi", True)
    assert packet.decoded.lat == pytest.approx(60.2057, abs=1e-4) and packet.decoded.lon == pytest.approx(24.9463, abs=1e-4)
    assert (packet.gate, packet.on_air, packet.kind) == ("", False, "position")
    assert packet.summary.endswith("(APRS-IS)") and "third-party" not in packet.summary


@pytest.mark.parametrize(("line", "q", "server", "radio"), [
    ("OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-hi", "qAC", "T2FINLAND", False),
    ("N0CALL-1>APRS,TCPIP*,qAS,PE1RXF:>on the net", "qAS", "PE1RXF", False),
    ("OH2RDG-7>APRX29,WIDE1-1,OH2RCH-2*,qAR,OH2RDK-1:!6010.00N/02456.00E>mobile", "qAR", "OH2RDK-1", True),
    ("OH2XYZ>APRS,qAO,OH2RDK-1*::OH2GBA   :Hello{12", "qAO", "OH2RDK-1", True),
    ("OH2UDP>APRS,qAU,T2FINLAND:>udp", "qAU", "T2FINLAND", False),
    ("CW1234>APRS,TCPXX*,qAX,CWOP-5:>unverified", "qAX", "CWOP-5", False),
    ("OH2TRC>APRS,TCPIP*,qAI,T2FINLAND,OH2ABC:>traced", "qAI", "T2FINLAND", False),
    ("OH2LOW>APRS,qAo,OH2RDK-1:>lower case", "qAo", "OH2RDK-1", False),
])
def test_the_q_construct_and_the_call_after_it_are_read_from_the_path(line: str, q: str, server: str, radio: bool) -> None:
    packet = parse_is_line(line, NOW)
    assert q_construct(packet.path) == QConstruct(q, server) and heard_by_radio(packet.path) is radio


def test_a_path_without_a_q_construct_has_none() -> None:
    packet = parse_is_line("OH2ABC>APRS,TCPIP*:>no q", NOW)
    assert q_construct(packet.path) is None and heard_by_radio(packet.path) is False and q_construct(()) is None
    assert parse_is_line("OH2ABC>APRS:>no path", NOW).path == ()


def test_the_path_keeps_the_digipeaters_with_their_stars_before_the_q_construct() -> None:
    packet = parse_is_line("OH2RDG-7>APRX29,WIDE1*,OH2RCH-2*,WIDE2-1,qAR,OH2RDK-1:!6010.00N/02456.00E>mobile", NOW)
    assert packet.path == ("WIDE1*", "OH2RCH-2*", "WIDE2-1", "qAR", "OH2RDK-1") and packet.destination == "APRX29"


def test_a_message_a_status_a_weather_report_and_an_object_are_read_as_on_the_air() -> None:
    message = parse_is_line("OH2XYZ>APRS,qAO,OH2RDK-1::OH2GBA   :Hello{12", NOW)
    assert message.decoded == Message("OH2GBA", "Hello", "12") and message.kind == "message"
    assert parse_is_line("OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:>Net on 145.500", NOW).decoded == Status("Net on 145.500")
    weather = parse_is_line("CW1234>APRS,TCPXX*,qAX,CWOP-5:@092345z4903.50N/07201.75W_220/004g005t077r000p000P000h50b09720", NOW)
    assert isinstance(weather.decoded, Position) and weather.decoded.weather is not None and weather.decoded.weather.temp_c == pytest.approx(25.0) and weather.weather_report is not None
    obj = parse_is_line("OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:;LEADER   *092345z6012.00N/02456.00E>090/020 convoy", NOW)
    assert obj.kind == "object" and obj.weather_report is None


def test_a_mic_e_packet_keeps_its_bytes_and_is_read_by_the_destination() -> None:
    line = b'OH2MIC>S32UVT,WIDE1-1,qAR,OH2RDK-1:`(_fn"Oj/>mobile'
    packet = parse_is_line(line, NOW)
    assert packet.via == IS and packet.info == b'`(_fn"Oj/>mobile' and isinstance(packet.decoded, Position)
    assert packet.raw == line


def test_bytes_that_are_not_text_are_kept_as_they_came() -> None:
    line = "OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:>Hyv\xe4 p\xe4iv\xe4".encode("latin-1")
    packet = parse_is_line(line, NOW)
    assert packet.info == b">Hyv\xe4 p\xe4iv\xe4" and packet.decoded == Status("Hyvä päivä")
    assert parse_is_line(">Hyvä päivä".join(["OH2ABC>APRS,qAC,T2FINLAND:", ""]), NOW).info == ">Hyvä päivä".encode()


def test_the_end_of_the_line_and_the_case_of_the_names_do_not_matter() -> None:
    packet = parse_is_line(b"oh2abc-0>aprs,tcpip*,qAC,T2FINLAND:>x\r\n", NOW)
    assert (packet.source, packet.destination, packet.info, packet.raw) == ("OH2ABC", "APRS", b">x", b"oh2abc-0>aprs,tcpip*,qAC,T2FINLAND:>x")


def test_a_third_party_packet_inside_a_line_from_the_internet_is_opened_and_is_still_from_the_internet() -> None:
    packet = parse_is_line("OH7JHF-1>APRS,TCPIP*,qAC,T2FINLAND:}OH2DPN>APJYC1,TCPIP,OH7JHF-1*::OH2GBA   :ack10", NOW)
    assert packet.via == IS and packet.third_party is not None and packet.sender == "OH2DPN" and packet.decoded == Message("OH2GBA", "", ack_id="10")
    assert packet.gate == "" and not packet.on_air


def test_an_information_field_that_does_not_decode_is_still_a_packet() -> None:
    packet = parse_is_line("OH2ABC>APRS,TCPIP*,qAC,T2FINLAND:!49", NOW)
    assert packet.via == IS and isinstance(packet.decoded, Undecoded | Other)


@pytest.mark.parametrize("line", ["# aprsc 2.1.15-gc67551b", "# logresp OH2GBA verified, server T2FINLAND", "#", b"# javAPRSSrvr 4.2.0b05"])
def test_a_comment_of_the_server_is_no_packet_and_says_so(line: str | bytes) -> None:
    assert is_comment(line)
    with pytest.raises(IsLineError) as caught:
        parse_is_line(line, NOW)
    assert caught.value.comment


@pytest.mark.parametrize("line", ["", "OH2ABC", "OH2ABC>APRS,TCPIP*,qAC", "OH2ABC>APRS:", "OH2ABC,APRS:>x", ">APRS:>x", "OH2ABC>:>x", "OH2 ABC>APRS:>x", "TOOLONGSOURCE1>APRS:>x", "OH2ABC>APRS,TCPIP*,,qAC:>x",
                                  "OH2ABC>APRS,T C:>x", "OH2ABC>APRS," + ",".join(["WIDE1-1"] * 40) + ":>x", "OH2ÄBC>APRS:>x", "OH2ABC>APRS,WIDE1-1;qAC:>x"])
def test_a_line_that_is_no_packet_is_refused_with_a_reason_and_is_not_a_comment(line: str) -> None:
    with pytest.raises(IsLineError) as caught:
        parse_is_line(line, NOW)
    assert not caught.value.comment and str(caught.value)


def test_the_time_is_the_time_given_and_must_be_aware() -> None:
    assert parse_is_line("OH2ABC>APRS:>x", NOW + timedelta(seconds=5)).heard_at == NOW + timedelta(seconds=5)
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_is_line("OH2ABC>APRS:>x", NOW.replace(tzinfo=None))
