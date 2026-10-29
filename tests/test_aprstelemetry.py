"""Telemetry: the report, the four definition messages and the scaling."""
import math

import pytest

from neoaprs.aprstelemetry import Telemetry, TelemetryDefinition, apply_definition, describe, is_definition, parse_telemetry, split_comment_telemetry

REPORT = Telemetry(5, [199, 0, 255, 73, 123], "01101001")


def test_the_specs_report() -> None:
    assert parse_telemetry("T#005,199,000,255,073,123,01101001") == REPORT
    assert parse_telemetry("T#MIC,001,002,003,004,005,00000000") == Telemetry(None, [1, 2, 3, 4, 5], "00000000")
    assert parse_telemetry("T#012,1.5,2,3,4,5,10101010 Balloon ") == Telemetry(12, [1.5, 2, 3, 4, 5], "10101010", "Balloon")


@pytest.mark.parametrize(("text", "want"), [
    ("T#MIC199,000,255,073,123,01101001", Telemetry(None, [199, 0, 255, 73, 123], "01101001")),                  # APRS 1.2: MIC without a comma
    ("T#151,45.7,2.3,190.0,91.0,-7.3,00001100", Telemetry(151, [45.7, 2.3, 190.0, 91.0, -7.3], "00001100")),      # any width, signed, a decimal point
    ("T#005,1000,000,255,073,123,01101001", Telemetry(5, [1000, 0, 255, 73, 123], "01101001")),
    ("T#005,199", Telemetry(5, [199], "")),                                                                       # fewer than five values, no bits
    ("T#005,199,000,255,073,123", Telemetry(5, [199, 0, 255, 73, 123], "")),
    ("T#005,199,000,255,073,123,0110", Telemetry(5, [199, 0, 255, 73, 123], "0110")),                               # fewer than eight bits
    ("T#005,199,000,255,073,123,0110100x", Telemetry(5, [199, 0, 255, 73, 123], "0110100", "x")),
    ("T#7,1,.5,-2 note", Telemetry(7, [1, 0.5], "", "-2 note")),                                                    # a field that is no number ends the values
    ("T#005,199,000,255,073,123,01101001,Balloon 3", Telemetry(5, [199, 0, 255, 73, 123], "01101001", "Balloon 3")),  # a comma between the bits and the comment, as most senders write it
])
def test_the_forms_of_aprs_1_2(text: str, want: Telemetry) -> None:
    assert parse_telemetry(text) == want


@pytest.mark.parametrize(("comment", "rest", "want"), [
    ("Hi |ss11|", "Hi", Telemetry(7544, [1472], "")),                                                            # the specification's examples
    ("|ss112233|", "", Telemetry(7544, [1472, 1564, 1656], "")),
    ("Balloon|ss1122334455!\"|!W12!", "Balloon!W12!", Telemetry(7544, [1472, 1564, 1656, 1748, 1840], "10000000")),   # the bits after the fifth: B1 is the lowest
    ("|!!!!|", "", Telemetry(0, [0], "")),
])
def test_base91_telemetry_in_a_comment(comment: str, rest: str, want: Telemetry) -> None:
    assert split_comment_telemetry(comment) == (rest, want)


@pytest.mark.parametrize("comment", ["", "a|b", "|ss|", "|ss1|", "|ss1122334455667788|", "|s}11|"])
def test_a_comment_without_base91_telemetry_is_left_alone(comment: str) -> None:
    assert split_comment_telemetry(comment) == (comment, None)


@pytest.mark.parametrize("text", ["", "T", "T#005", "T#005,", "T#005,a,000,255,073,123,01101001", "T#MICx", "T#,199,000,255,073,123,01101001", "t#005,199,000,255,073,123,01101001",
                                  "X#005,199,000,255,073,123,01101001", "T#123456,1"])
def test_text_that_is_no_report(text: str) -> None:
    assert parse_telemetry(text) is None


def definition_of(*texts: str) -> TelemetryDefinition:
    d = TelemetryDefinition()
    for text in texts:
        updated = apply_definition(d, text)
        assert updated is not None, text
        d = updated
    return d


# The four beacons of the specification's example, addressed to N0QBF-11.
SPEC = ("PARM.Battery,Btemp,ATemp,Pres,Alt,Camra,Chut,Sun,10m,ATV", "UNIT.v/100,deg.F,deg.F,Mbar,Kft,Click,OPEN,on,on,hi", "EQNS.0,5.2,0,0,.53,-32,3,4.39,49,-32,3,18,1,2,3", "BITS.10110000,N0QBF's Big Balloon")


def test_the_definitions_of_the_spec() -> None:
    d = definition_of(*SPEC)
    assert d.names[:3] == ("Battery", "Btemp", "ATemp") and len(d.names) == 10 and d.units[0] == "v/100"
    assert d.coefficients == ((0.0, 5.2, 0.0), (0.0, 0.53, -32.0), (3.0, 4.39, 49.0), (-32.0, 3.0, 18.0), (1.0, 2.0, 3.0))
    assert (d.sense, d.project) == ("10110000", "N0QBF's Big Balloon")


def test_the_spec_report_scaled_by_the_spec_definitions() -> None:
    """The specification computes the battery: 5.2 * 199 = 1034.8 hundredths of a volt."""
    view = describe(REPORT, definition_of(*SPEC))
    battery = view.channels[0]
    assert (battery.name, battery.unit, battery.raw, battery.value) == ("Battery", "v/100", 199, 1034.8)
    assert view.channels[1].value == pytest.approx(0.53 * 0 - 32, abs=1e-6)
    assert view.sequence == 5 and view.project == "N0QBF's Big Balloon"
    assert [b.on for b in view.bits[:3]] == [False, False, True]          # the bits 0 1 1 against the sense 1 0 1: only the third has the sense
    assert view.bits[0].name == "Camra"


def test_bit_sense() -> None:
    view = describe(REPORT, definition_of("BITS.10110000,x"))
    assert [b.on for b in view.bits] == [False, False, True, False, False, True, True, False]      # bits 01101001 against the sense 10110000


def test_a_report_with_no_definition_is_named_a1_to_b8_and_unscaled() -> None:
    view = describe(REPORT, None)
    assert [(c.name, c.unit, c.value) for c in view.channels] == [("A1", "", 199), ("A2", "", 0), ("A3", "", 255), ("A4", "", 73), ("A5", "", 123)]
    assert [(b.name, b.on) for b in view.bits[:3]] == [("B1", False), ("B2", True), ("B3", True)]
    assert describe(REPORT, TelemetryDefinition()) == view


def test_a_list_may_stop_at_any_field() -> None:
    view = describe(REPORT, definition_of("PARM.Volts,,Temp", "EQNS.0,2,0,1,0,0"))
    assert [c.name for c in view.channels] == ["Volts", "A2", "Temp", "A4", "A5"]
    assert view.channels[0].value == 398 and view.channels[1].value == 0 and view.channels[2].value == 255      # (a coefficient group that is cut short ends the list)


def test_later_messages_replace_earlier_ones_of_their_kind_only() -> None:
    d = definition_of("PARM.A,B", "UNIT.x,y", "PARM.C")
    assert d.names == ("C",) and d.units == ("x", "y")
    assert definition_of("BITS.2,x").sense == "" and definition_of("BITS.1010,x").sense == "1010"
    assert definition_of("EQNS.1,2,x,0,1,0").coefficients == ()


@pytest.mark.parametrize("text", ["", "Hello", "PARM", "parm.x", "ack12", "PARMS.x"])
def test_other_messages_are_not_definitions(text: str) -> None:
    assert apply_definition(TelemetryDefinition(), text) is None and not is_definition(text)
    assert is_definition("EQNS.0,1,0")


@pytest.mark.parametrize("text", ["T#001," + "9" * 320 + ",2,3,4,5,00000000", "T#001,1e999,2,3,4,5,00000000", "T#001,1,2,3,4," + "9" * 400, "T#001," + "9" * 320])
def test_a_value_that_is_not_a_finite_number_is_no_report(text: str) -> None:
    assert parse_telemetry(text) is None


def test_a_coefficient_that_is_not_a_finite_number_ends_the_list_and_a_channel_is_always_finite() -> None:
    definition = apply_definition(TelemetryDefinition(), "EQNS.0,1,0," + "9" * 320 + ",0,0,0,0,0")
    assert definition is not None and definition.coefficients == ((0.0, 1.0, 0.0),)
    huge = apply_definition(TelemetryDefinition(), "EQNS.1e9,1e9,0")
    report = parse_telemetry("T#001,1000000000,2,3,4,5,00000000")
    assert huge is not None and report is not None
    assert all(math.isfinite(channel.value) for channel in describe(report, huge).channels)
