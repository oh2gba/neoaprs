"""Messages: parsing the addressee, the text, the ids, acks and rejects; formatting and the round trip."""
import pytest

from neoaprs.aprsmessage import MessageError, format_ack, format_message, line_of, parse_message, reply_ack_of
from neoaprs.packet import Message


@pytest.mark.parametrize(("body", "want"), [
    (b"WU2Z     :Testing", Message("WU2Z", "Testing")),
    (b"WU2Z     :Testing{003", Message("WU2Z", "Testing", "003")),
    (b"WU2Z     :Testing{003}", Message("WU2Z", "Testing", "003")),
    (b"WU2Z     :Hello{AB}CD", Message("WU2Z", "Hello", "AB")),
    (b"WU2Z     :Hello{05}", Message("WU2Z", "Hello", "05")),
    (b"WU2Z     :ack05}CD", Message("WU2Z", "", ack_id="05")),               # the ack of a reply-ack message is a copy of its number
    (b"WU2Z     :rej05}CD", Message("WU2Z", "", rej_id="05")),
    (b"WU2Z     :ack05}", Message("WU2Z", "", ack_id="05")),
    (b"WU2Z     :Hello{05}ABCDEF", Message("WU2Z", "Hello{05}ABCDEF")),     # (more than five characters of it is no number)
    (b"WU2Z     :{1", Message("WU2Z", "", "1")),
    (b"OH2GBA-7 :ack12345", Message("OH2GBA-7", "", ack_id="12345")),
    (b"OH2GBA-7 :rej7", Message("OH2GBA-7", "", rej_id="7")),
    (b"OH2GBA-15:Hi", Message("OH2GBA-15", "Hi")),
    (b"BLN1     :Net at 19:00", Message("BLN1", "Net at 19:00")),
    (b"WU2Z     :", Message("WU2Z", "")),
    (b"WU2Z     :Testing\r\n", Message("WU2Z", "Testing")),
    (b"WU2Z     :two  spaces  ", Message("WU2Z", "two  spaces  ")),
    (b"WU2Z     :Hyv\xc3\xa4", Message("WU2Z", "Hyvä")),
    (b"WU2Z     :Hyv\xe4", Message("WU2Z", "Hyvä")),
    (b"WU2Z     :a {b c}", Message("WU2Z", "a {b c}")),            # not an id: it has spaces
    (b"WU2Z     :x{123456", Message("WU2Z", "x{123456")),          # too long to be an id
    (b"WU2Z     :x{}", Message("WU2Z", "x{}")),
    (b"WU2Z     :{a}{b", Message("WU2Z", "{a}", "b")),
    (b"WU2Z     :ack", Message("WU2Z", "ack")),
    (b"WU2Z     :acknowledged", Message("WU2Z", "acknowledged")),
    (b"WU2Z     :ack123456", Message("WU2Z", "ack123456")),
    (b"WU2Z     :ack12{5", Message("WU2Z", "ack12", "5")),         # an ack is "ack" and its id and nothing else
    (b"WB4APR-14:ack12  ", Message("WB4APR-14", "", ack_id="12")),   # blanks, CR and LF after an ack or a number do not count
    (b"WB4APR-14:ack12\r", Message("WB4APR-14", "", ack_id="12")),
    (b"WB4APR-14:rej12 \r\n", Message("WB4APR-14", "", rej_id="12")),
    (b"OH2GBA   :Hello{12}  ", Message("OH2GBA", "Hello", "12")),
    (b"OH2GBA   :Hi{12\r\n", Message("OH2GBA", "Hi", "12")),
    (b"KH2Z:hi", Message("KH2Z", "hi")),                              # an addressee field a little short: the first colon ends it
    (b"WU2Z    :x{3", Message("WU2Z", "x", "3")),
    (b"OH2GBA-7:ack05", Message("OH2GBA-7", "", ack_id="05")),
])
def test_parse(body: bytes, want: Message) -> None:
    assert parse_message(body) == want


@pytest.mark.parametrize("body", [b"", b"WU2Z", b"WU2Z     ", b"WU2Z     x", b"WU2ZABCDEF:x", b"OH2GBA-7 x:y", b"          :x", b":x"])
def test_bad_bodies(body: bytes) -> None:
    with pytest.raises(MessageError):
        parse_message(body)


def test_format() -> None:
    assert format_message("WU2Z", "Testing") == b"WU2Z     :Testing"
    assert format_message("WU2Z", "Testing", "003") == b"WU2Z     :Testing{003"
    assert format_message("OH2GBA-15", "Hi") == b"OH2GBA-15:Hi"
    assert format_message("WU2Z", "Testing", "05", "") == b"WU2Z     :Testing{05}"
    assert format_message("WU2Z", "Testing", "05", "AB") == b"WU2Z     :Testing{05}AB"
    assert format_ack("N3LTQ-7", "05", "AB") == b"N3LTQ-7  :ack05}AB"
    assert format_ack("N3LTQ-7", "05", "") == b"N3LTQ-7  :ack05}", "the ack of {05} is the exact copy of the number"
    assert format_ack("N3LTQ-7", "05", None) == b"N3LTQ-7  :ack05"
    assert format_ack("N3LTQ-7", "003") == b"N3LTQ-7  :ack003"


@pytest.mark.parametrize(("addressee", "text", "msg_id"), [
    ("", "x", None), ("TOOLONG-123", "x", None), (" A", "x", None), ("A ", "x", None), ("A:B", "x", None), ("Ä", "x", None),
    ("A", "a|b", None), ("A", "a~b", None), ("A", "a{b", None), ("A", "a\nb", None), ("A", "x" * 68, None), ("A", "Hyvä", None), ("A", "ack12", None), ("A", "ack12}34", None), ("A", "rej1", None),
    ("A", "x", ""), ("A", "x", "123456"), ("A", "x", "a b"), ("A", "x", "a}"),
])
def test_format_refuses(addressee: str, text: str, msg_id: str | None) -> None:
    with pytest.raises(MessageError):
        format_message(addressee, text, msg_id)


def test_format_refuses_a_reply_ack_without_an_id_or_with_a_bad_one() -> None:
    for msg_id, reply in ((None, ""), (None, "AB"), ("05", "ABCDEF"), ("05", "a b")):
        with pytest.raises(MessageError):
            format_message("A", "x", msg_id, reply)


@pytest.mark.parametrize(("line", "want"), [("Hello{05}AB", "AB"), ("Hello{05}", ""), ("Hello{05", None), ("Hello", None), ("{05}AB", "AB"), ("Hello{05}ABCDEF", None), ("a}b", None), ("Hello{05}  ", ""), ("Hello{05}AB\r", "AB")])
def test_the_reply_ack_of_a_text_is_what_follows_the_brace_of_its_number(line: str, want: str | None) -> None:
    assert reply_ack_of(line) == want


def test_the_line_of_a_message_is_its_text_with_the_number_and_a_field_that_is_none_has_none() -> None:
    assert line_of(b":OH2GBA   :Hello{05}AB\r") == "Hello{05}AB" and line_of(b":OH2GBA   :") == "" and line_of(b":KH2Z:hi{3}") == "hi{3}"
    for info in (b"", b">status", b":OH2GBA", b":OH2GBA    x"):
        assert line_of(info) is None


def test_format_ack_refuses_a_bad_id() -> None:
    for bad in ("", "123456", "a{"):
        with pytest.raises(MessageError):
            format_ack("A", bad)


def test_the_longest_message_is_allowed() -> None:
    assert parse_message(format_message("A", "x" * 67, "12345")) == Message("A", "x" * 67, "12345")


def test_round_trips() -> None:
    for addressee, text, msg_id in [("WU2Z", "Testing", None), ("OH2GBA-7", "Hyvaa paivaa", "1"), ("OH2GBA-7", "Hi", "05"), ("BLN1", "", "ab"), ("A", "ack is fine inside", "AB123"), ("A", "x}", None)]:
        assert parse_message(format_message(addressee, text, msg_id)) == Message(addressee, text, msg_id)


def test_an_ack_round_trips() -> None:
    assert parse_message(format_ack("OH2GBA-7", "12")) == Message("OH2GBA-7", "", ack_id="12")
