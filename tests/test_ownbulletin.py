"""A bulletin, an announcement or a group bulletin of ours (neoaprs/ownbulletin.py): the information field byte for byte as the specification's chapter 14 shows it, read back by our own parser, and what is refused."""
from datetime import UTC, datetime

import pytest

from neoaprs import ax25
from neoaprs.aprsparse import parse
from neoaprs.bulletin import board_slot
from neoaprs.ownbulletin import OwnBulletin, PostError, info_of, make_bulletin, slot_of
from neoaprs.packet import Message

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("slot, text, info", [
    ("BLN3", "Snow expected in Tampa RSN", b":BLN3     :Snow expected in Tampa RSN"),                                  # the specification's general bulletin
    ("BLNQ", "Mt St Helen digi will be QRT this weekend", b":BLNQ     :Mt St Helen digi will be QRT this weekend"),    # its announcement
    ("BLN4WX", "Stand by your snowplows", b":BLN4WX   :Stand by your snowplows"),                                       # its group bulletin, the group padded with blanks
    ("BLN0", "x", b":BLN0     :x"), ("BLN9", "y" * 67, b":BLN9     :" + b"y" * 67), ("BLNZ", "z", b":BLNZ     :z"), ("BLN7HAMS1", "full group", b":BLN7HAMS1:full group")])
def test_a_bulletin_is_a_message_to_the_slot_padded_to_nine_characters_without_an_id(slot: str, text: str, info: bytes) -> None:
    assert info_of(make_bulletin(NOW, slot, text)) == info


def test_our_own_parser_reads_it_back_as_a_message_to_a_slot_of_the_board_and_the_slot_is_what_we_made() -> None:
    for slot, kind, group in (("BLN3", "bulletin", ""), ("BLNQ", "announcement", ""), ("BLN4WX", "group", "WX")):
        bulletin = make_bulletin(NOW, slot, "Stand by")
        decoded = parse(info_of(bulletin), "OH2GBA", "APZNEO", NOW)
        assert decoded == Message(slot, "Stand by") and isinstance(decoded, Message) and decoded.msg_id is None
        found = board_slot(decoded.addressee)
        assert found is not None and (found.slot, found.kind, found.group) == (slot, kind, group) == (bulletin.slot, bulletin.kind, bulletin.group)


def test_the_packet_is_one_ax25_frame_that_goes_over_the_air_and_comes_back() -> None:
    frame = ax25.Frame(ax25.Address.parse("APZNEO"), ax25.Address.parse("OH2GBA"), (ax25.Address.parse("WIDE1-1"),), info=info_of(make_bulletin(NOW, "bln1", "y" * 67)))
    assert ax25.decode(ax25.encode(frame)) == frame and frame.tnc2() == "OH2GBA>APZNEO,WIDE1-1:" + frame.info.decode()


def test_the_slot_is_written_in_capitals_and_the_text_is_stripped() -> None:
    bulletin = make_bulletin(NOW, " bln3hams ", "  Net tonight  ")
    assert (bulletin.slot, bulletin.group, bulletin.kind, bulletin.text) == ("BLN3HAMS", "HAMS", "group", "Net tonight")
    assert slot_of("blna") == ("BLNA", "", "announcement")


@pytest.mark.parametrize("slot", ["", "BLN", "BLNa1", "BLNAB", "BLNABC", "BLN3HAMSXX", "BLN3H M", "BLN3:", "ALL", "CQ", "QST", "NWS-WARN", "SKY", "OH2RDG", "BLN-", "BLN3-"])
def test_a_slot_that_is_not_ours_to_post_is_refused(slot: str) -> None:
    with pytest.raises(PostError):
        slot_of(slot)


@pytest.mark.parametrize("text", ["", "   ", "x" * 68, "a|b", "a~b", "a{b", "åäö", "ta\tb", "ack12"])
def test_a_text_that_cannot_be_sent_is_refused(text: str) -> None:
    with pytest.raises(PostError):
        make_bulletin(NOW, "BLN1", text)


def test_a_slot_posted_again_is_a_new_text_with_the_schedule_from_the_start_and_the_time_of_the_last_packet_kept() -> None:
    first = make_bulletin(NOW, "BLN1", "one")
    sent = OwnBulletin(first.slot, first.group, first.kind, first.text, NOW, 3, NOW, NOW)
    later = datetime(2026, 10, 21, 12, 30, tzinfo=UTC)
    again = make_bulletin(later, "BLN1", "two", before=sent)
    assert (again.text, again.created_at, again.sent, again.first_sent_at, again.last_sent_at) == ("two", later, 0, None, NOW)
