"""Our own copy heard back: a packet showing one of our calls, passed or repeated by us and heard
again through another digipeater, keeps its place in the packet log and last heard but adds nothing
to what the radio heard.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from neoaprs import app
from neoaprs.clock import utc
from neoaprs.config import Config
from neoaprs.messagerule import message_radio
from neoaprs.packet import Packet, Status
from neoaprs.pairsetting import PairSpec
from neoaprs.radiospec import FM_ID, HF_ID, RadioHeard, RadioSpec
from neoaprs.station import Station
from neoaprs.stationbook import StationBook, carries_path
from neoaprs.stationnotes import came_back

T0 = utc(2026, 11, 19, 12, 0, 0)
OURS = ("OH2GBA", "OH2GBA-12")
HF_STATION = "OH5XYZ-10"
TWO = (RadioSpec(FM_ID, "fm", "kiss", "", True, 1), RadioSpec(HF_ID, "hf", "mercury", "", True, 2))


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def packet(radio_id: int, minutes: float, path: tuple[str, ...], source: str = HF_STATION) -> Packet:
    return Packet(
        heard_at=at(minutes),
        direction="in",
        raw=b"",
        source=source,
        destination="APRS",
        path=path,
        info=b">x",
        decoded=Status("x"),
        radio_id=radio_id,
    )  # type: ignore[arg-type]


def gateway_book() -> StationBook:
    return StationBook(carries_path=lambda radio: carries_path(TWO, radio), own_calls=lambda: OURS)


def heard(book: StationBook, call: str = HF_STATION) -> Station:
    found = book.get(call)
    assert found is not None
    return found


@pytest.mark.parametrize(
    "path",
    [("OH2GBA-12*", "OH2RCH-2*"), ("OH2GBA-12", "OH2RCH-2*"), ("OH2GBA*", "OH2RCH-2*")],
    ids=["pair", "tnc2-star", "fill-in"],
)
def test_our_own_copy_heard_back_on_fm_is_no_hearing_of_the_station_there(path: tuple[str, ...]) -> None:
    book = gateway_book()
    book.take(packet(HF_ID, 0, ()))
    book.take(packet(FM_ID, 1, path))
    s = heard(book)
    assert s.heard_by == {HF_ID: RadioHeard(1, at(0), ())}, (
        "no FM entry: the copy proves our pass, not that FM hears the station"
    )
    assert FM_ID not in s.routes and s.deliveries.by_route == {} and s.heard_rf == 1
    assert (s.packets, s.last_heard) == (2, at(1)), "the packet is still the station's"
    assert message_radio(None, s.heard_by, TWO, at(2)) == HF_ID, "a message to it goes on HF, where it is heard"


def test_a_station_heard_on_fm_keeps_its_fm_path_when_the_fill_ins_copy_comes_back() -> None:
    book = gateway_book()
    book.take(packet(FM_ID, 0, ("OH2RDG*",)))
    book.take(packet(FM_ID, 1, ("OH2GBA*", "OH2RCH-2*")))
    s = heard(book)
    assert s.heard_by[FM_ID] == RadioHeard(1, at(0), ("OH2RDG*",)) and s.routes[FM_ID].by_route == {("OH2RDG",): 1}


def test_a_packet_digipeated_by_another_station_or_asking_for_our_pair_still_counts() -> None:
    book = gateway_book()
    book.take(packet(FM_ID, 0, ("OH2RCH-2*",)))
    book.take(packet(FM_ID, 1, ("OH2GBA-12", "WIDE2-1")))
    s = heard(book)
    assert s.heard_by[FM_ID] == RadioHeard(2, at(1), ("OH2GBA-12", "WIDE2-1")), (
        "a hop of ours not yet used is a request, heard direct"
    )
    assert s.routes[FM_ID].by_route == {("OH2RCH-2",): 1} and s.routes[FM_ID].direct == 1


def test_the_station_heard_direct_right_after_its_copy_came_back_counts_at_once() -> None:
    book = gateway_book()
    book.take(packet(FM_ID, 0, ("OH2GBA-12*", "OH2RCH-2*")))
    book.take(packet(FM_ID, 0.1, ()))
    s = heard(book)
    assert s.heard_by == {FM_ID: RadioHeard(1, at(0.1), ())} and s.routes[FM_ID].direct == 1


def test_a_call_of_another_ssid_or_a_pair_that_is_not_ours_is_no_copy_of_ours() -> None:
    assert not came_back(("OH2GBA-2*", "OH2GBA-12*"), ("OH2GBA",)), (
        "a hill digi of the same base call, and a pair call we do not hold"
    )
    assert came_back(("OH2GBA-0*",), ("OH2GBA",)) and not came_back(("OH2GBA-12",), OURS) and not came_back((), OURS)


def test_the_routes_the_log_kept_leave_out_our_own_copies() -> None:
    book = gateway_book()
    book.seed([Station(HF_STATION, first_heard=at(0), last_heard=at(1))])
    book.seed_deliveries(
        [
            (HF_STATION, ("OH2RCH-2*",), "", 3, at(0), None, FM_ID),
            (HF_STATION, ("OH2GBA-12*", "OH2RCH-2*"), "", 5, at(1), None, FM_ID),
        ]
    )
    s = heard(book)
    assert s.routes[FM_ID].by_route == {("OH2RCH-2",): 3}, (
        "the latest group is our copy: the route and the path stay those of the station's own packets"
    )


def test_the_app_gives_the_book_the_station_call_and_the_enabled_pairs_calls(tmp_path: Path) -> None:
    services = app.Services(tmp_path)
    services.config = Config(
        station_call="OH2GBA", pairs=(PairSpec(FM_ID, HF_ID, True, 12), PairSpec(FM_ID, 3, False, 11))
    )
    services.stationbook.take(packet(HF_ID, 0, ()))
    services.stationbook.take(packet(FM_ID, 1, ("OH2GBA-12*", "OH2RCH-2*")))
    services.stationbook.take(packet(FM_ID, 2, ("OH2GBA-11*", "OH2RCH-2*"), source="OH3ABC-9"))
    assert (
        FM_ID not in heard(services.stationbook).heard_by and FM_ID in heard(services.stationbook, "OH3ABC-9").heard_by
    ), "a pair that is off holds no call of ours"
