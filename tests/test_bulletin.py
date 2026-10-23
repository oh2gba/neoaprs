"""Which addressees are the message board's (neoaprs/bulletin.py): bulletins, announcements, group bulletins, the group messages and the weather service's, and that none of them ages out."""
from datetime import timedelta

import pytest

from neoaprs.bulletin import BulletinRecord, board_slot, key_of
from neoaprs.clock import utc

T0 = utc(2026, 10, 21, 12, 0, 0)


@pytest.mark.parametrize("addressee, slot, kind, group", [
    ("BLN0", "BLN0", "bulletin", ""), ("BLN9", "BLN9", "bulletin", ""), ("BLNA", "BLNA", "announcement", ""), ("BLNZ", "BLNZ", "announcement", ""),
    ("BLN3HAMS", "BLN3HAMS", "group", "HAMS"), ("BLN1WX", "BLN1WX", "group", "WX"), ("BLNAHAMS", "BLNAHAMS", "group", "HAMS"), ("BLN5GRP-1", "BLN5GRP-1", "group", "GRP-1"),
    ("ALL", "ALL", "group", ""), ("CQ", "CQ", "group", ""), ("QST", "QST", "group", ""),
    ("NWS-WARNV", "NWS-WARNV", "nws", ""), ("nws-tstwr", "NWS-TSTWR", "nws", ""), ("NWS-X", "NWS-X", "nws", ""), ("SKY", "SKY", "nws", ""), ("SKYWRN", "SKYWRN", "nws", ""), ("CWA", "CWA", "nws", ""),
    ("CWAABC", "CWAABC", "nws", ""),
    ("bln1", "BLN1", "bulletin", ""), (" qst ", "QST", "group", ""), ("BLN3hams", "BLN3HAMS", "group", "HAMS"), ("BLNA ", "BLNA", "announcement", "")])
def test_the_addressees_of_the_board(addressee: str, slot: str, kind: str, group: str) -> None:
    found = board_slot(addressee)
    assert found is not None and (found.slot, found.kind, found.group) == (slot, kind, group)


@pytest.mark.parametrize("addressee", ["OH2GBA", "OH2GBA-9", "BLN", "BLN-1", "BLN12345678", "ALLX", "ALLCALL", "QSTX", "XBLN1", "", "BLN!", "NWS", "NWS-", "NWS-TOOLONG", "NWSX", "SKYWARN1", "CWAXXXX", "XSKY"])
def test_a_station_and_other_text_are_no_slot(addressee: str) -> None:
    assert board_slot(addressee) is None


def test_a_bulletin_is_known_by_its_sender_and_slot_and_has_no_lifetime() -> None:
    heard = BulletinRecord("OH2XYZ", "BLNA", "", "announcement", "x", T0, T0 + timedelta(hours=1))
    assert heard.key == key_of("OH2XYZ", "BLNA") == "OH2XYZ/BLNA"
    assert not hasattr(heard, "expires_at"), "nothing on the board ages out"
