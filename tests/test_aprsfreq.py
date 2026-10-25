"""The frequency specification (neoaprs/aprsfreq.py): the frequency at the start of a comment or a status text, its fields, the frequency that is an object's name, and the text of one. The cases of
the dispatcher that decode whole packets are in tests/fixtures/aprs/cases.json."""
import pytest

from neoaprs.aprsfreq import Frequency, frequency_text, name_frequency, named_frequency, split_frequency


def test_the_frequency_alone_has_no_field() -> None:
    assert split_frequency("145.775MHz") == ("", Frequency(145.775))
    assert split_frequency("146.52 MHz Enroute Alabama") == ("Enroute Alabama", Frequency(146.52))


def test_every_field_of_the_specification() -> None:
    rest, f = split_frequency("145.775MHz C107 +060 R25m 430.100rx D-STAR")
    assert rest == "D-STAR" and f == Frequency(145.775, tone_hz=107, tone_both=True, offset_khz=600, range_km=40.2, rx_mhz=430.1)
    assert split_frequency("146.805MHz D023 R25k")[1] == Frequency(146.805, dcs="023", range_km=25.0)
    assert split_frequency("145.5 MHz")[1] is None                                       # (one decimal is no form of the specification)


def test_a_lower_case_first_letter_is_narrow_modulation() -> None:
    assert split_frequency("145.500MHz t088")[1] == Frequency(145.5, tone_hz=88, narrow=True)
    assert split_frequency("145.500MHz d023")[1] == Frequency(145.5, dcs="023", narrow=True)
    assert split_frequency("145.500MHz l750")[1] == Frequency(145.5, tone_burst=True, narrow=True)
    assert split_frequency("145.500MHz 1750")[1] == Frequency(145.5, tone_burst=True)


def test_no_tone_and_forced_simplex_are_told_from_fields_that_were_not_sent() -> None:
    assert split_frequency("145.500MHz Toff -000")[1] == Frequency(145.5, tone_off=True, offset_khz=0)
    assert split_frequency("145.500MHz T000")[1] == Frequency(145.5, tone_off=True)
    assert split_frequency("145.500MHz")[1] == Frequency(145.5, offset_khz=None)


def test_the_unit_is_read_in_any_case_and_the_microwave_forms_are_the_specifications() -> None:
    assert split_frequency("145.775mhz")[1] == Frequency(145.775)
    assert split_frequency("A96.000MHz")[1] == Frequency(1296.0)
    assert split_frequency("O01.000MHz")[1] == Frequency(24201.0)
    assert split_frequency("10.368GHz")[1] == Frequency(10368.0)


def test_one_delimiter_before_the_frequency_is_skipped() -> None:
    assert split_frequency("/145.775MHz T100") == ("", Frequency(145.775, tone_hz=100))
    assert split_frequency(" / 145.775MHz")[1] == Frequency(145.775)


@pytest.mark.parametrize("text", ["", "hello", "QRV 145.500MHz", "145.500 MHz", "145.775MHzT100", "145.775MH", "T100 -060", "45.775MHz", "145.775 GHz", "//145.775MHz"])
def test_text_that_does_not_begin_with_the_specified_form_is_left_alone(text: str) -> None:
    assert split_frequency(text) == (text, None)


def test_the_fields_end_at_the_first_word_that_is_none_and_a_field_is_read_once() -> None:
    assert split_frequency("145.775MHz T100 hello R25m") == ("hello R25m", Frequency(145.775, tone_hz=100))
    assert split_frequency("145.775MHz T100 C107") == ("C107", Frequency(145.775, tone_hz=100))
    assert split_frequency("145.775MHz -060 +060") == ("+060", Frequency(145.775, offset_khz=-600))


def test_an_object_name_is_a_frequency() -> None:
    assert [name_frequency(n) for n in ("145.775-", "145.7750", "146.94xyz", "146.94-yz", "145.775-A", "146.940ab")] == [145.775, 145.775, 146.94, 146.94, 145.775, 146.94]
    assert [name_frequency(n) for n in ("145.775", "145.775 ", "EL-123456", "IRLP-1234", "HAMFEST", "145,775-A", "14.775-AB")] == [None] * 7


def test_the_comment_of_a_frequency_object_begins_with_the_fields() -> None:
    assert named_frequency("145.775-A", None, "T079 R25m NET Tu9PM") == (Frequency(145.775, tone_hz=79, range_km=40.2), "NET Tu9PM")
    assert named_frequency("145.775-A", None, "Hello") == (Frequency(145.775), "Hello")
    assert named_frequency("MYOBJ", None, "T079 R25m") == (None, "T079 R25m")


def test_a_frequency_in_both_the_name_and_the_comment_makes_the_name_the_transmit_frequency() -> None:
    comment = Frequency(430.1, tone_hz=100)
    assert named_frequency("145.775-A", comment, "") == (Frequency(145.775, tone_hz=100, rx_mhz=430.1), "")
    assert named_frequency("145.775-A", Frequency(145.775, tone_hz=100), "") == (Frequency(145.775, tone_hz=100), "")
    assert named_frequency("145.775-A", Frequency(430.1, rx_mhz=430.2), "")[0] == Frequency(145.775, rx_mhz=430.2)
    assert named_frequency("MYOBJ", comment, "x") == (comment, "x")


def test_a_frequency_in_words() -> None:
    assert frequency_text(Frequency(145.775, tone_hz=118, offset_khz=-600, range_km=40.2)) == "145.775 MHz, tone 118 Hz, -600 kHz, range 40 km"
    assert frequency_text(Frequency(146.52)) == "146.520 MHz"
    full = Frequency(145.775, tone_hz=107, tone_both=True, dcs="023", tone_off=True, tone_burst=True, narrow=True, offset_khz=0, rx_mhz=430.1)
    assert frequency_text(full) == "145.775 MHz, tone 107 Hz both ways, DCS 023, no tone, tone burst 1750 Hz, narrow, simplex, receive 430.100 MHz"
