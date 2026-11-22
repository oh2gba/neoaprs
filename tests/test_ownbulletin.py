"""A bulletin, announcement or group bulletin of ours (neoaprs/ownbulletin.py): the information
field byte for byte as the specification's chapter 14 shows it, read back by our parser, the slot a
new post takes, how long it may be sent for, and what is refused.
"""

from datetime import UTC, datetime

import pytest

from neoaprs import ax25
from neoaprs.aprsparse import parse
from neoaprs.bulletin import board_slot
from neoaprs.ownbulletin import (
    Kind,
    DEFAULT_HOURS,
    SENT_FOR,
    PostError,
    check_group,
    free_slot,
    info_of,
    make_bulletin,
    slot_of,
)
from neoaprs.packet import Message

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "slot, text, info",
    [
        # The specification's general bulletin
        ("BLN3", "Snow expected in Tampa RSN", b":BLN3     :Snow expected in Tampa RSN"),
        (
            "BLNQ",
            "Mt St Helen digi will be QRT this weekend",
            b":BLNQ     :Mt St Helen digi will be QRT this weekend",
        ),  # its announcement
        # Its group bulletin, the group padded with blanks
        ("BLN4WX", "Stand by your snowplows", b":BLN4WX   :Stand by your snowplows"),
        ("BLN0", "x", b":BLN0     :x"),
        ("BLN9", "y" * 67, b":BLN9     :" + b"y" * 67),
        ("BLNZ", "z", b":BLNZ     :z"),
        ("BLN7HAMS1", "full group", b":BLN7HAMS1:full group"),
    ],
)
def test_a_bulletin_is_a_message_to_the_slot_padded_to_nine_characters_without_an_id(
    slot: str, text: str, info: bytes
) -> None:
    assert info_of(make_bulletin(NOW, slot, text, 4 if len(slot) != 4 or slot[3].isdigit() else 72)) == info


def test_our_own_parser_reads_it_back_as_a_message_to_a_slot_of_the_board_and_the_slot_is_what_we_made() -> None:
    for slot, kind, group in (("BLN3", "bulletin", ""), ("BLNQ", "announcement", ""), ("BLN4WX", "group", "WX")):
        bulletin = make_bulletin(NOW, slot, "Stand by", 24 if kind == "announcement" else 1)
        decoded = parse(info_of(bulletin), "OH2GBA", "APZNEO", NOW)
        assert decoded == Message(slot, "Stand by") and isinstance(decoded, Message) and decoded.msg_id is None
        found = board_slot(decoded.addressee)
        assert found is not None and (found.slot, found.kind, found.group) == (slot, kind, group) == (
            bulletin.slot,
            bulletin.kind,
            bulletin.group,
        )


def test_the_packet_is_one_ax25_frame_that_goes_over_the_air_and_comes_back() -> None:
    frame = ax25.Frame(
        ax25.Address.parse("APZNEO"),
        ax25.Address.parse("OH2GBA"),
        (ax25.Address.parse("WIDE1-1"),),
        info=info_of(make_bulletin(NOW, "bln1", "y" * 67, 4)),
    )
    assert ax25.decode(ax25.encode(frame)) == frame and frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1:" + frame.info.decode()


def test_the_slot_is_written_in_capitals_and_the_text_is_stripped() -> None:
    bulletin = make_bulletin(NOW, " bln3hams ", "  Net tonight  ", 12)
    assert (bulletin.slot, bulletin.group, bulletin.kind, bulletin.text) == ("BLN3HAMS", "HAMS", "group", "Net tonight")
    assert slot_of("blna") == ("BLNA", "", "announcement")


@pytest.mark.parametrize(
    "slot",
    [
        "",
        "BLN",
        "BLNa1",
        "BLNAB",
        "BLNABC",
        "BLN3HAMSXX",
        "BLN3H M",
        "BLN3:",
        "ALL",
        "CQ",
        "QST",
        "NWS-WARN",
        "SKY",
        "OH2RDG",
        "BLN-",
        "BLN3-",
    ],
)
def test_a_slot_that_is_not_ours_to_post_is_refused(slot: str) -> None:
    with pytest.raises(PostError):
        slot_of(slot)


@pytest.mark.parametrize("text", ["", "   ", "x" * 68, "a|b", "a~b", "a{b", "åäö", "ta\tb", "ack12"])
def test_a_text_that_cannot_be_sent_is_refused(text: str) -> None:
    with pytest.raises(PostError):
        make_bulletin(NOW, "BLN1", text, 4)


DIGITS = [f"BLN{c}" for c in "0123456789"]
LETTERS = [f"BLN{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]


@pytest.mark.parametrize(
    ("kind", "group", "taken", "slot"),
    [
        ("bulletin", "", [], "BLN0"),
        ("announcement", "", [], "BLNA"),
        ("group", "HAMS", [], "BLN0HAMS"),
        ("bulletin", "", ["BLN0", "BLN2"], "BLN1"),
        ("bulletin", "", DIGITS[:9], "BLN9"),
        ("bulletin", "", DIGITS, None),
        ("announcement", "", LETTERS, None),
        ("announcement", "", DIGITS, "BLNA"),
        ("bulletin", "", ["BLNA", "BLN0HAMS", "BLN0WX"], "BLN0"),
        ("group", "HAMS", ["BLN0", "BLN0WX"], "BLN0HAMS"),
        ("group", "HAMS", [f"{s}HAMS" for s in DIGITS], None),
        ("group", "WX", [f"{s}HAMS" for s in DIGITS], "BLN0WX"),
        ("group", " hams ", ["BLN0HAMS"], "BLN1HAMS"),
        ("group", "", [], None),
        ("group", "HAMS12", [], None),
        ("group", "HA-MS", [], None),
        ("bulletin", "HAMS", [], "BLN0"),
    ],
)
def test_a_new_post_takes_the_lowest_slot_of_its_kind_and_group_that_holds_none_of_ours(
    kind: Kind, group: str, taken: list[str], slot: str | None
) -> None:
    assert free_slot(kind, group, taken) == slot


def test_a_post_is_sent_for_one_of_the_choices_of_its_kind_and_nothing_else() -> None:
    assert SENT_FOR == {"bulletin": (1, 2, 4, 8, 12), "group": (1, 2, 4, 8, 12), "announcement": (24, 72, 168)}
    assert all(DEFAULT_HOURS[kind] in hours for kind, hours in SENT_FOR.items())
    for slot, kind in (("BLN1", "bulletin"), ("BLNA", "announcement"), ("BLN1HAMS", "group")):
        for hours in SENT_FOR[kind]:  # type: ignore[index]
            made = make_bulletin(NOW, slot, "x", hours)
            assert made.hours == hours and made.plan.lasts == hours * 3600
        for hours in {0, 3, 24, 72, 169, 1, 12} - set(SENT_FOR[kind]):  # type: ignore[index]
            with pytest.raises(PostError) as refused:
                make_bulletin(NOW, slot, "x", hours)
            assert (refused.value.code, refused.value.params) == ("bulletin.hours", {"hours": hours})


def test_a_group_is_written_in_capitals_and_one_that_is_no_group_is_refused() -> None:
    assert check_group(" hams1 ") == "HAMS1"
    for bad in ("", "  ", "HAMS12", "HA-MS", "HA MS", "ÄÖ"):
        with pytest.raises(PostError) as refused:
            check_group(bad)
        assert refused.value.code == "bulletin.group"
