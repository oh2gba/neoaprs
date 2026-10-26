"""What a receive-only iGate gates (neoaprs/igaterules.py), as a table: every rule of the specification (https://www.aprs-is.net/IGateDetails.aspx, https://www.aprs-is.net/q.aspx) with the packet that breaks it and the line
that comes out of one that does not: the path as heard with the star where a monitor writes it, `qAO` and our call, the information field as the bytes it is, a third-party packet opened and judged again."""
import pytest

from neoaprs import ax25
from neoaprs.igaterules import FRAME, LONG, MAX_LINE, NEWLINE, NOGATE, OWN, QUERY, SOURCE, TCPIP, Dropped, Gate, gate_of, source_is_station

OURS = "OH2GBA-10"
POSITION = b"!6010.00N/02456.00E>Test"


def frame(source: str = "OH2XYZ-9", destination: str = "APZ123", path: str = "WIDE1-1*,WIDE2-1", info: bytes = POSITION, **options: int) -> ax25.Frame:
    return ax25.Frame(ax25.Address.parse(destination), ax25.Address.parse(source), tuple(ax25.Address.parse(hop) for hop in path.split(",") if hop), info=info, **options)


def lined(f: ax25.Frame, ours: str = OURS) -> str:
    result = gate_of(f, ours)
    assert isinstance(result, Gate), result
    return result.line(ours).decode("latin-1")


def reason(f: ax25.Frame, ours: str = OURS) -> str:
    result = gate_of(f, ours)
    assert isinstance(result, Dropped), result
    return result.reason


# ---- the line

def test_a_packet_heard_goes_as_it_was_heard_with_qao_and_our_call_after_the_path() -> None:
    assert lined(frame()) == "OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"


def test_the_path_is_the_one_heard_the_hops_not_used_yet_as_well() -> None:
    assert lined(frame(path="WIDE1-1,WIDE2-1")) == "OH2XYZ-9>APZ123,WIDE1-1,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"
    assert lined(frame(path="")) == "OH2XYZ-9>APZ123,qAO,OH2GBA-10:!6010.00N/02456.00E>Test", "(heard direct: no path at all)"


def test_the_star_is_written_after_the_last_digipeater_the_frame_has_been_through() -> None:
    assert lined(frame(path="OH2RDG*,OH2RCH*,WIDE2-1")) == "OH2XYZ-9>APZ123,OH2RDG,OH2RCH*,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"


def test_the_destination_keeps_its_ssid_and_the_igate_call_has_no_star() -> None:
    assert lined(frame(destination="APRS-3", path="")).startswith("OH2XYZ-9>APRS-3,qAO,OH2GBA-10:")


def test_the_information_field_is_the_bytes_it_is() -> None:
    info = b"`c&<\x7fl <\x1c-/>\xe4\xf6\x00\x80\xff|!wLK!|3"
    result = gate_of(frame(info=info), OURS)
    assert isinstance(result, Gate) and result.info == info
    assert result.line(OURS) == b"OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:" + info, "(not decoded, not encoded again)"


def test_the_line_end_a_tnc_may_add_is_cut_off_and_nothing_else_is() -> None:
    result = gate_of(frame(info=POSITION + b" \r\n"), OURS)
    assert isinstance(result, Gate) and result.info == POSITION + b" "
    assert reason(frame(info=b"=6010.00N/02456.00E>Te\rst")) == NEWLINE and reason(frame(info=b"=6010.00N/02456.00E>Te\nst")) == NEWLINE


# ---- what is not gated

@pytest.mark.parametrize("path", ["TCPIP*", "WIDE1-1*,TCPIP", "TCPIP*,WIDE2-1", "tcpip", "TCPXX*", "WIDE1*,TCPXX*", "TCPIP-1*"])
def test_a_path_that_has_been_on_the_internet_is_not_gated(path: str) -> None:
    assert reason(frame(path=path)) == TCPIP


@pytest.mark.parametrize("path", ["NOGATE", "WIDE1-1*,NOGATE", "RFONLY", "RFONLY,WIDE2-1", "NOGATE*"])
def test_a_packet_that_asks_not_to_be_gated_is_not(path: str) -> None:
    assert reason(frame(path=path)) == NOGATE


@pytest.mark.parametrize("info", [b"?APRS?", b"?IGATE?", b"?WX?", b"?"])
def test_a_generic_query_is_not_gated(info: bytes) -> None:
    assert reason(frame(info=info)) == QUERY


def test_a_message_that_has_a_question_mark_inside_is_gated() -> None:
    assert lined(frame(info=b":OH2GBA   :what is this?{3}")).endswith(":OH2GBA   :what is this?{3}")


@pytest.mark.parametrize("control", [0x01, 0x11, 0x3F])
def test_a_frame_that_is_no_ui_frame_is_not_gated(control: int) -> None:
    assert reason(frame(control=control)) == FRAME


def test_a_frame_with_another_pid_is_not_gated() -> None:
    assert reason(frame(pid=0xCF)) == FRAME


@pytest.mark.parametrize("path", ["qAR", "WIDE1*,qAO,OH2RDG", "qAC", "WIDE1*,I", "qAZ"])
def test_a_q_construct_or_the_i_construct_on_the_air_is_not_believed(path: str) -> None:
    assert reason(frame(path=path)) == FRAME


@pytest.mark.parametrize("source", ["N0CALL", "NOCALL", "MYCALL", "WIDE1-1", "WIDE2", "TRACE3-3", "TCPIP", "RELAY", "SERVER", "NOGATE", "RFONLY", "BEACON"])
def test_a_source_that_is_no_station_is_not_gated(source: str) -> None:
    assert reason(frame(source=source)) == SOURCE


@pytest.mark.parametrize(("name", "ok"), [("OH2GBA", True), ("OH2GBA-7", True), ("OH2XYZ-L", True), ("WINLINK", True), ("OH2XYZ-20", True), ("N0CALL-9", False), ("WIDE3-3", False), ("", False), ("A,B", False)])
def test_what_is_a_station_on_aprs_is(name: str, ok: bool) -> None:
    assert source_is_station(name) is ok


def test_our_own_call_as_the_source_is_not_gated_but_the_same_call_with_another_ssid_is() -> None:
    assert reason(frame(source="OH2GBA-10")) == OWN
    assert lined(frame(source="OH2GBA-9")).startswith("OH2GBA-9>")
    assert lined(frame(source="OH2GBA")).startswith("OH2GBA>")


def test_a_packet_that_would_make_a_line_over_512_bytes_is_not_gated() -> None:
    header = len(b"OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:")
    longest = MAX_LINE - 2 - header
    assert isinstance(gate_of(frame(info=b"=" + b"x" * (longest - 1)), OURS), Gate)
    assert reason(frame(info=b"=" + b"x" * longest)) == LONG


def test_a_packet_with_nothing_in_its_information_field_is_not_gated() -> None:
    assert reason(frame(info=b"")) == FRAME and reason(frame(info=b"\r\n")) == FRAME


# ---- third-party packets

THIRD = b"}OH2XYZ-9>APZ123,%s:!6010.00N/02456.00E>Test"


def test_a_third_party_packet_that_came_from_the_internet_is_not_gated_at_all() -> None:
    assert reason(frame(source="OH7JHF-1", path="WIDE1-1*", info=THIRD % b"TCPIP,OH7JHF-1*")) == TCPIP
    assert reason(frame(source="OH7JHF-1", path="WIDE1-1*", info=THIRD % b"TCPXX,OH7JHF-1*")) == TCPIP
    assert reason(frame(source="OH7JHF-1", path="WIDE1-1*", info=THIRD % b"WIDE1-1*,TCPIP,OH7JHF-1*")) == TCPIP


def test_a_third_party_packet_that_did_not_is_gated_as_the_packet_inside_with_the_rf_header_and_the_mark_taken_off() -> None:
    assert lined(frame(source="OH7JHF-1", destination="APRS", path="WIDE2-1", info=THIRD % b"WIDE1-1*,WIDE2-1")) == \
        "OH2XYZ-9>APZ123,WIDE1-1*,WIDE2-1,qAO,OH2GBA-10:!6010.00N/02456.00E>Test"
    assert lined(frame(source="OH7JHF-1", info=b"}OH2XYZ-9>APZ123:>direct")) == "OH2XYZ-9>APZ123,qAO,OH2GBA-10:>direct"


def test_the_packet_inside_is_judged_by_every_rule_again() -> None:
    assert reason(frame(info=b"}OH2XYZ-9>APZ123,NOGATE:>x")) == NOGATE
    assert reason(frame(info=b"}OH2XYZ-9>APZ123:?APRS?")) == QUERY
    assert reason(frame(info=b"}N0CALL>APZ123:>x")) == SOURCE
    assert reason(frame(source="OH7JHF-1", info=b"}OH2GBA-10>APZ123:>x")) == OWN, "(our own packet, by way of somebody else)"
    assert reason(frame(info=b"}OH2XYZ-9>APZ123,qAR,OH7JHF-1:>x")) == FRAME


def test_the_inner_source_may_be_a_name_that_is_no_ax25_call() -> None:
    assert lined(frame(source="OH7JHF-1", info=b"}WINLINK>APRS:>x")).startswith("WINLINK>APRS,qAO,")


def test_a_third_party_packet_in_a_third_party_packet_is_opened_again_to_a_depth() -> None:
    assert lined(frame(info=b"}OH7JHF-1>APRS,WIDE1*:}OH2XYZ-9>APZ123:>deep")) == "OH2XYZ-9>APZ123,qAO,OH2GBA-10:>deep"
    assert reason(frame(info=b"}OH7JHF-1>APRS:}OH2XYZ-9>APZ123,TCPIP:>deep")) == TCPIP
    assert lined(frame(info=b"}A1>APRS:}B2>APRS:}C3>APRS:>x")) == "C3>APRS,qAO,OH2GBA-10:>x"
    assert reason(frame(info=b"}A1>APRS:}B2>APRS:}C3>APRS:}D4>APRS:>x")) == FRAME


@pytest.mark.parametrize("info", [b"}", b"}garbage", b"}OH2XYZ-9>:>x", b"}>APRS:>x", b"}OH2XYZ-9>APRS", b"}OH2XYZ-9>APRS:", b"}OH2XYZ-9>APRS,qAR,X:>x"])
def test_a_third_party_header_that_is_none_is_not_gated(info: bytes) -> None:
    assert reason(frame(info=info)) == FRAME


# ---- the same packet

def test_two_copies_of_a_packet_are_the_same_packet_whatever_path_and_destination_ssid() -> None:
    a = gate_of(frame(path="WIDE1-1*,WIDE2-1"), OURS)
    b = gate_of(frame(path="OH2RDG*,WIDE2-1", destination="APZ123-4"), OURS)
    c = gate_of(frame(info=POSITION + b"!"), OURS)
    assert isinstance(a, Gate) and isinstance(b, Gate) and isinstance(c, Gate)
    assert a.key == b.key and a.key != c.key
