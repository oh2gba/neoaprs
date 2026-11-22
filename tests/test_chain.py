"""The delivery chain's rules (neoaprs/chain.py): which hops of the path we sent by a heard path shows used, with aliases, implied hops and the internet's own pieces left out, and which attempt a copy belongs to."""
from dataclasses import fields, replace

import pytest

from neoaprs.chain import Attempt, HopSeen, attempt_before, hops_used, internet_hops
from neoaprs.clock import utc
from neoaprs.radiotype import FM_ID, HF_ID

SENT = ("OH2RCH-2", "OH2RDG")
WIDE = ("WIDE1-1", "WIDE2-1")


@pytest.mark.parametrize("sent, heard, used", [
    (SENT, ("OH2RCH-2*", "OH2RDG"), [(1, "OH2RCH-2")]),
    (SENT, ("OH2RCH-2*", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),
    (SENT, ("OH2RCH-2", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),                      # (the TNC2 star: the last hop used, so the one before it was too)
    (SENT, ("OH2RCH-2", "OH2RDG"), []),
    (SENT, (), []),
    (SENT, ("OH2XYZ*", "OH2RDG"), []),                                                       # (a digipeater that is none of ours)
    (WIDE, ("OH2RCH-2*", "WIDE2-1"), [(1, "OH2RCH-2")]),                                     # (the alias replaced by the call that used it)
    (WIDE, ("OH2RCH-2*", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),
    (WIDE, ("WIDE1*", "WIDE2-1"), [(1, "WIDE1")]),                                           # (an alias used and left as it is: the call is not known)
    (("WIDE2-2",), ("OH2RCH-2*", "OH2RDG*", "WIDE2*"), [(1, "OH2RCH-2")]),
    (("WIDE1-1", "OH2RDG"), ("OH2RDG*",), [(1, "WIDE1-1"), (2, "OH2RDG")]),                  # (OH2RDG is the second hop's call, not the alias's: the first is implied)
    ((), ("OH2RCH-2*",), []),
    (("SS3-3",), ("OH2RCH-2*", "SS3-2"), [(1, "OH2RCH-2")]),                                 # (a regional New-N alias is an alias like WIDE: the call that used it takes its place)
    (("HOP7-7",), ("FI2*",), [(1, "FI2")]),
    (SENT + ("RFONLY",), ("OH2RCH-2*", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),           # (RFONLY, NOGATE, TCPIP and the q-constructs are no hops, in the path we sent or the one heard)
    (SENT + ("RFONLY",), ("OH2RCH-2*", "OH2RDG", "RFONLY"), [(1, "OH2RCH-2")]),
    (("OH2RCH-2", "NOGATE", "OH2RDG"), ("OH2RCH-2*", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),
    (WIDE + ("RFONLY",), ("OH2RCH-2*", "WIDE2-1", "RFONLY"), [(1, "OH2RCH-2")]),
    (SENT, ("OH2RCH-2*", "TCPIP*", "qAR", "OH2RDG*"), [(1, "OH2RCH-2"), (2, "OH2RDG")]),
    (("RFONLY",), ("RFONLY*",), []),
])
def test_the_starred_addresses_of_a_heard_path_show_which_hops_of_the_path_we_sent_were_used(sent: tuple[str, ...], heard: tuple[str, ...], used: list[tuple[int, str]]) -> None:
    assert hops_used(sent, heard) == used


def test_the_internets_own_pieces_of_a_third_party_path_and_the_gate_are_not_hops_of_ours() -> None:
    assert internet_hops(WIDE, ("TCPIP", "OH7JHF-1*"), "OH7JHF-1") == []
    assert internet_hops(WIDE, ("qAR", "OH7JHF-1"), "OH7JHF-1") == []
    assert internet_hops(WIDE, ("OH2RCH-2*", "WIDE2-1", "TCPIP*", "OH7JHF-1*"), "OH7JHF-1") == [(1, "OH2RCH-2")]
    assert internet_hops(SENT, ("OH2RCH-2*", "OH2RDG*", "qAO", "OH7JHF-1"), "OH7JHF-1") == [(1, "OH2RCH-2"), (2, "OH2RDG")]


def test_a_copy_belongs_to_the_latest_attempt_sent_at_or_before_it_was_heard() -> None:
    t = utc(2026, 10, 22, 12, 0, 0)
    first, second = Attempt(1, t, SENT), Attempt(2, utc(2026, 10, 22, 12, 0, 30), SENT)
    assert attempt_before([first, second], utc(2026, 10, 22, 12, 0, 10)) == first
    assert attempt_before([first, second], utc(2026, 10, 22, 12, 0, 30)) == second
    assert attempt_before([first, second], utc(2026, 10, 22, 12, 5, 0)) == second
    assert attempt_before([first, second], utc(2026, 10, 22, 11, 59, 59)) is None
    assert attempt_before([], t) is None
    assert attempt_before([Attempt(1, t, SENT), Attempt(2, t, SENT)], t).number == 2        # type: ignore[union-attr]


def test_the_hops_the_page_is_told_leave_out_what_is_no_hop_even_in_an_attempt_that_was_stored_with_it() -> None:
    from neoaprs.message import MessageRecord
    from neoaprs.web.views import attempt_rows
    at = utc(2026, 10, 22, 12, 0, 0)
    record = MessageRecord(1, at, "out", "OH2GBA", "OH2RDG", "Hello", "01", "sending")
    stored = (Attempt(1, at, ("OH2RCH-2", "OH2RDG", "RFONLY")), Attempt(2, at, ("WIDE1-1", "NOGATE", "WIDE2-1", "TCPIP")), Attempt(3, at, ("RFONLY",)))
    assert [[h["call"] for h in row["hops"]] for row in attempt_rows(record, stored)] == [["OH2RCH-2", "OH2RDG"], ["WIDE1-1", "WIDE2-1"], []]


# ---- the radio of an attempt: its id

def test_an_attempt_keeps_the_id_of_its_radio() -> None:
    t = utc(2026, 11, 14, 12, 0, 0)
    assert [f.name for f in fields(Attempt)] == ["number", "sent_at", "path", "seen", "radio_id"]
    made = [Attempt(1, t, SENT, radio_id=radio_id) for radio_id in (None, FM_ID, HF_ID, 3)]
    assert [a.radio_id for a in made] == [None, 1, 2, 3], "any radio by its id"
    assert Attempt(1, t, SENT).radio_id is None, "an attempt kept before there were two radios"
    seen = made[3].with_seen(HopSeen(1, "OH2RCH-2", t, False))
    assert seen.radio_id == 3 and seen.has(1, False), "what was heard of it changes nothing of its radio"


def test_the_constructor_and_replace_of_an_attempt_take_the_id() -> None:
    t = utc(2026, 11, 14, 12, 0, 0)
    assert Attempt(1, t, SENT, (), HF_ID) == Attempt(1, t, SENT, radio_id=HF_ID)
    assert replace(Attempt(1, t, SENT, radio_id=FM_ID), radio_id=HF_ID).radio_id == HF_ID and replace(Attempt(1, t, SENT, radio_id=FM_ID), radio_id=3).radio_id == 3


def test_a_third_party_path_that_stars_only_the_last_digipeater_shows_every_hop_up_to_it_as_the_radio_does() -> None:
    gated = internet_hops(WIDE, ("OH2RCH-2", "OH2RDG*"), "OH7JHF-1")
    assert gated == hops_used(WIDE, ("OH2RCH-2*", "OH2RDG*")) == [(1, "OH2RCH-2"), (2, "OH2RDG")]
