"""The AIS decoder (neoaprs/aisdecode.py): the positions and the words of ships from NMEA sentences,
the joining of a message's parts, and what is passed over."""

import time
from datetime import timedelta

from neoaprs.aisdecode import AisDecoder, AisPosition, AisStatic
from neoaprs.clock import utc
from tests.support import aissentences as ais

AT = utc(2026, 11, 18, 12, 0, 0)


def decode(lines: list[str], decoder: AisDecoder | None = None) -> list[AisPosition | AisStatic | None]:
    decoder = decoder or AisDecoder()
    return [decoder.feed(line, AT) for line in lines]


def test_a_class_a_position_of_a_well_known_sentence_has_its_place_speed_course_and_heading() -> None:
    found = AisDecoder().feed("!AIVDM,1,1,,A,13u?etPv2;0n:dDPwUM1U1Cb069D,0*24", AT)
    assert isinstance(found, AisPosition)
    assert found.mmsi == 265547250 and found.at == AT
    assert (round(found.lat, 4), round(found.lon, 4)) == (57.6604, 11.833)
    assert (found.sog_kn, found.cog_deg, found.heading_deg) == (13.9, 40.4, 41)


def test_every_position_type_decodes_to_its_place_course_and_speed() -> None:
    for kind in (1, 2, 3):
        found = decode(ais.sentences(ais.class_a(230123000, 60.1699, 24.9384, 12.3, 271.5, 270, kind)))[0]
        assert found == AisPosition(230123000, found.lat, found.lon, AT, 12.3, 271.5, 270)  # type: ignore[union-attr]
        assert abs(found.lat - 60.1699) < 1e-5 and abs(found.lon - 24.9384) < 1e-5  # type: ignore[union-attr]
    for kind in (18, 19):
        found = decode(ais.sentences(ais.class_b(230999000, -33.8568, -151.2153, 5.0, 0.0, 0, kind)))[0]
        assert isinstance(found, AisPosition) and found.mmsi == 230999000
        assert (
            abs(found.lat + 33.8568) < 1e-5
            and abs(found.lon + 151.2153) < 1e-5
            and (found.sog_kn, found.cog_deg, found.heading_deg) == (5.0, 0.0, 0)
        )


def test_what_is_not_available_is_none() -> None:
    found = decode(ais.sentences(ais.class_a(230123000, 60.0, 24.0, 102.3, 360.0, 511)))[0]
    assert isinstance(found, AisPosition) and (found.sog_kn, found.cog_deg, found.heading_deg) == (None, None, None)


def test_a_message_without_a_position_gives_none() -> None:
    assert decode(ais.sentences(ais.class_a(230123000, 91.0, 24.0)))[0] is None
    assert decode(ais.sentences(ais.class_a(230123000, 60.0, 181.0)))[0] is None
    assert decode(ais.sentences(ais.class_b(230123000, 91.0, 181.0)))[0] is None


def test_a_type_5_in_two_sentences_gives_the_name_kind_and_destination() -> None:
    lines = ais.sentences(ais.static_a(352002374, "Lady Jamila", 70, "Helsinki"))
    assert len(lines) == 2
    assert decode(lines) == [None, AisStatic(352002374, "LADY JAMILA", 70, "HELSINKI")]


def test_a_type_24_in_its_two_parts_gives_the_name_and_then_the_kind() -> None:
    a = decode(ais.sentences(ais.static_b(230555000, 0, name="Sea Lark")))
    b = decode(ais.sentences(ais.static_b(230555000, 1, ship_type=37)))
    assert a == [AisStatic(230555000, "SEA LARK", None, "")]
    assert b == [AisStatic(230555000, "", 37, "")]


def test_a_ship_type_of_0_or_of_a_reserved_range_is_none() -> None:
    assert decode(ais.sentences(ais.static_b(230555000, 1, ship_type=0))) == [AisStatic(230555000, "", None, "")]
    assert decode(ais.sentences(ais.static_a(230555000, "X", 200, ""), per=100)) == [
        AisStatic(230555000, "X", None, "")
    ]


def test_names_lose_their_trailing_padding_and_blanks() -> None:
    assert decode(ais.sentences(ais.static_a(230555000, "AURA  ", 60, "  "), per=100)) == [
        AisStatic(230555000, "AURA", 60, "")
    ]


def test_a_wrong_checksum_a_half_sentence_and_other_text_are_passed_over() -> None:
    good = ais.sentences(ais.class_a(230123000, 60.0, 24.0))[0]
    wrong = good[:-2] + ("00" if not good.endswith("00") else "01")
    assert decode([wrong, good[:30], "", "!AIVDM", "$GPGGA,1,2,3*00", "garbage", good[:-3]]) == [None] * 7
    assert isinstance(decode([good])[0], AisPosition)


def test_a_payload_character_outside_the_armour_is_passed_over_even_with_a_right_checksum() -> None:
    good = ais.sentences(ais.class_a(230123000, 60.0, 24.0))[0]
    fields = good[1 : good.index("*")].split(",")
    for char in "X[_":
        fields[5] = char + fields[5][1:]
        body = ",".join(fields)
        checksum = 0
        for byte in body.encode():
            checksum ^= byte
        assert decode([f"!{body}*{checksum:02X}"]) == [None]


def test_a_sentence_with_a_tag_block_in_front_is_read_from_its_exclamation_mark() -> None:
    good = ais.sentences(ais.class_a(230123000, 60.0, 24.0))[0]
    assert isinstance(decode([f"\\s:42,c:1700000000*00\\{good}"])[0], AisPosition)


def test_our_own_boats_sentence_is_read_too() -> None:
    data, fill = ais.payload(ais.class_a(230123000, 60.0, 24.0))
    assert isinstance(decode([ais.sentence(data, fill, talker="AIVDO")])[0], AisPosition)
    assert decode([ais.sentence(data, fill, talker="GPGGA")])[0] is None


def test_other_message_types_are_passed_over() -> None:
    other = [(4, 6), (0, 2), (230123000, 30), (0, 100)]
    assert decode(ais.sentences(other))[0] is None


def test_a_part_alone_or_out_of_order_or_from_another_message_gives_nothing() -> None:
    first, second = ais.sentences(ais.static_a(352002374, "LADY", 70, "X"))
    assert decode([second]) == [None]
    other = ais.sentences(ais.static_a(352002375, "OTHER", 70, "Y"), seq="4")
    decoder = AisDecoder()
    assert decoder.feed(first, AT) is None
    assert decoder.feed(other[1], AT) is None
    assert decoder.feed(second, AT) == AisStatic(352002374, "LADY", 70, "X")


def test_two_messages_in_turn_on_different_ids_are_joined_each_to_its_own() -> None:
    a1, a2 = ais.sentences(ais.static_a(1001, "ALPHA", 70, ""), seq="1")
    b1, b2 = ais.sentences(ais.static_a(1002, "BRAVO", 60, ""), seq="2")
    decoder = AisDecoder()
    found = [decoder.feed(line, AT) for line in (a1, b1, a2, b2)]
    assert found == [None, None, AisStatic(1001, "ALPHA", 70, ""), AisStatic(1002, "BRAVO", 60, "")]


def test_a_part_left_alone_for_ten_seconds_is_dropped() -> None:
    first, second = ais.sentences(ais.static_a(352002374, "LADY", 70, "X"))
    decoder = AisDecoder()
    assert decoder.feed(first, AT) is None
    assert decoder.feed(second, AT + timedelta(seconds=11)) is None
    assert decoder.feed(first, AT) is None and decoder.feed(second, AT + timedelta(seconds=9)) == AisStatic(
        352002374, "LADY", 70, "X"
    )


def test_a_thousand_lines_are_decoded_in_well_under_a_second() -> None:
    lines = [ais.sentences(ais.class_a(230000000 + n, 60.0 + n / 10000, 24.0, 5.0, 90.0, 90))[0] for n in range(500)]
    lines += [
        line for n in range(250) for line in ais.sentences(ais.static_a(230000000 + n, f"SHIP {n}", 70, "HELSINKI"))
    ]
    assert len(lines) == 1000
    decoder = AisDecoder()
    started = time.perf_counter()
    found = [decoder.feed(line, AT) for line in lines]
    assert time.perf_counter() - started < 0.5
    assert (
        sum(isinstance(item, AisPosition) for item in found) == 500
        and sum(isinstance(item, AisStatic) for item in found) == 250
    )
