"""How a packet reached us (neoaprs/route.py): the route read from the starred addresses of a path, its text, the path to send by that is made from it, and the count of the routes of a station."""
from datetime import timedelta

import pytest

from neoaprs.clock import utc
from neoaprs.route import ROUTES_KEPT, WIDE_PATH, Deliveries, Route, automatic_path, digipeaters, heard_path, is_marker, received_text, recommended_path, rf_only_path, route_of, route_text, suggested_path


@pytest.mark.parametrize("path, hops, heard_from, direct, anonymous, text", [
    ((), (), None, True, 0, "direct"),
    (("WIDE1-1", "WIDE2-1"), (), None, True, 0, "direct"),                               # (nothing used: heard from the sender itself)
    (("OH2RCH-2*",), ("OH2RCH-2",), "OH2RCH-2", False, 0, "via OH2RCH-2"),
    (("OH2RCH-3*", "TRACE2-1"), ("OH2RCH-3",), "OH2RCH-3", False, 0, "via OH2RCH-3"),       # (an alias that was not used is not part of the route)
    (("WIDE1*", "OH2RCH-2*", "WIDE2-2"), ("?", "OH2RCH-2"), "OH2RCH-2", False, 1, "via ? → OH2RCH-2"),
    (("OH2RCH-1*", "OH2RCH-3*"), ("OH2RCH-1", "OH2RCH-3"), "OH2RCH-3", False, 0, "via OH2RCH-1 → OH2RCH-3"),
    (("WIDE1", "OH2RCH-2*"), ("OH2RCH-2",), "OH2RCH-2", False, 0, "via OH2RCH-2"),          # (the TH-D7's monitor text: only what is starred counts)
    (("WIDE2-1*",), ("?",), None, False, 1, "via ?"),                                      # (the last hop has no call: nobody to name)
    (("TRACE2-1*", "OH2RCH-3*"), ("?", "OH2RCH-3"), "OH2RCH-3", False, 1, "via ? → OH2RCH-3"),
    (("WIDE1*", "WIDE2-1*"), ("?", "?"), None, False, 2, "via ? → ?"),
    (("OH2RCH-2*", "WIDE2-1*"), ("OH2RCH-2", "?"), None, False, 1, "via OH2RCH-2 → ?"),
])
def test_the_route_of_a_path(path: tuple[str, ...], hops: tuple[str, ...], heard_from: str | None, direct: bool, anonymous: int, text: str) -> None:
    route = route_of(path)
    assert (route.hops, route.heard_from, route.direct, route.anonymous) == (hops, heard_from, direct, anonymous)
    assert route_text(route) == text == received_text(path)


def test_the_aliases_are_kept_as_the_path_wrote_them() -> None:
    assert route_of(("WIDE1*", "OH2RCH-2*", "WIDE2-2")).written == ("WIDE1", "OH2RCH-2")
    assert route_of(("TRACE2-1*",)).written == ("TRACE2-1",)


@pytest.mark.parametrize("alias", ["WIDE1", "WIDE2-1", "TRACE2-2", "TRACE3", "RELAY", "ECHO", "GATE", "TEMP1-1", "SAR", "TRACK1"])
def test_an_alias_is_an_anonymous_hop(alias: str) -> None:
    assert route_of((alias + "*",)).anonymous == 1


@pytest.mark.parametrize("call", ["OH2RCH", "OH2RCH-2", "WIDEX1", "OH7JHF-1", "K1ABC-15"])
def test_a_call_is_not_an_alias(call: str) -> None:
    assert route_of((call + "*",)).anonymous == 0


@pytest.mark.parametrize("path, text, sent_by", [
    ((), "direct", ""),
    (("OH2RCH-2*",), "via OH2RCH-2", "OH2RCH-2"),
    (("OH2RCH-1*", "OH2RCH-3*"), "via OH2RCH-1 → OH2RCH-3", "OH2RCH-3,OH2RCH-1"),
    (("WIDE1*", "OH2RCH-2*"), "via ? → OH2RCH-2", WIDE_PATH),
    (("WIDE2-1*",), "via ?", WIDE_PATH),
])
def test_the_path_to_send_by_is_the_route_turned_round(path: tuple[str, ...], text: str, sent_by: str) -> None:
    route = route_of(path)
    assert route_text(route) == text and suggested_path(route) == sent_by


def test_a_third_party_packet_starts_at_its_gate() -> None:
    route = route_of(("OH2RCH-3*",), "OH7JHF-1")
    assert (route.hops, route.gate, route.direct, route.heard_from) == (("OH2RCH-3",), "OH7JHF-1", False, "OH2RCH-3")
    assert route_text(route) == "via OH7JHF-1 (internet) → OH2RCH-3"
    heard_direct = route_of((), "OH7JHF-1")
    assert (heard_direct.direct, heard_direct.heard_from) == (False, "OH7JHF-1") and route_text(heard_direct) == "via OH7JHF-1 (internet)"
    assert received_text(("WIDE1*",), "OH7JHF-1") == "via OH7JHF-1 (internet) → ?"


def test_the_deliveries_count_direct_and_each_route_and_name_the_most_frequent() -> None:
    d = Deliveries()
    assert d.best() is None and d.heard_via() == []
    for path in [("OH2RCH-2*",)] * 3 + [("OH2RCH-3*", "TRACE2-1")] * 2 + [()] * 2:
        d.note(route_of(path))
    assert d.direct == 2 and d.heard_via() == [("OH2RCH-2", 3), ("OH2RCH-3", 2)]
    best = d.best()
    assert best is not None and best.hops == ("OH2RCH-2",) and not best.direct


def test_direct_wins_a_tie_and_a_shorter_route_beats_a_longer_one_of_the_same_count() -> None:
    d = Deliveries()
    d.note(route_of(("OH2RCH-1*", "OH2RCH-3*")))
    d.note(route_of(("OH2RCH-2*",)))
    best = d.best()
    assert best is not None and best.hops == ("OH2RCH-2",)
    d.note(route_of(()))
    best = d.best()
    assert best is not None and best.direct, "direct, with the same number of packets"


def test_of_equal_counts_and_hops_the_one_heard_last_wins() -> None:
    d = Deliveries()
    d.note(route_of(("OH2RCH-2*",)))
    d.note(route_of(("OH2RCH-3*",)))
    d.note(route_of(("OH2RCH-2*",)))
    d.note(route_of(("OH2RCH-3*",)))
    best = d.best()
    assert best is not None and best.hops == ("OH2RCH-3",)


def test_a_hop_with_no_call_counts_under_a_question_mark() -> None:
    d = Deliveries()
    d.note(route_of(("WIDE2-1*",)), 3)
    d.note(route_of(("WIDE1*", "OH2RCH-2*")), 2)
    assert d.heard_via() == [("?", 3), ("OH2RCH-2", 2)]
    best = d.best()
    assert best is not None and best.anonymous == 1 and suggested_path(best) == WIDE_PATH


def test_only_the_eight_most_frequent_routes_are_kept_and_the_one_heard_longest_ago_of_the_fewest_goes_first() -> None:
    d = Deliveries()
    for n in range(ROUTES_KEPT):
        d.note(Route((f"DIGI{n}",), f"DIGI{n}", False))
    d.note(Route(("DIGI0",), "DIGI0", False), 4)                      # (heard again: now the newest, and the most)
    d.note(Route(("NEW",), "NEW", False))
    assert len(d.by_route) == ROUTES_KEPT and ("DIGI1",) not in d.by_route and ("NEW",) in d.by_route and d.by_route[("DIGI0",)] == 5


def test_a_third_party_delivery_is_counted_apart_and_is_never_the_best_route() -> None:
    d = Deliveries()
    d.note(route_of(("OH2RCH-3*",), "OH7JHF-1"), 9)
    assert (d.gated, d.direct, d.by_route, d.best(), d.heard_via()) == (9, 0, {}, None, [])
    d.note(route_of(("OH2RCH-2*",)))
    best = d.best()
    assert d.gated == 9 and best is not None and best.hops == ("OH2RCH-2",)


def test_the_time_of_the_latest_direct_packet_is_kept_with_the_count_and_nothing_else_has_one() -> None:
    d = Deliveries()
    t = utc(2026, 10, 21, 12, 0, 0)
    d.note(route_of(("OH2RCH-2*",)), 5, t)
    d.note(route_of(("OH2RCH-2*",), "OH7JHF-1"), 2, t)
    assert d.direct == 0 and d.last_direct_at is None, "only a direct packet has a time"
    d.note(route_of(()), 2, t)
    d.note(route_of(()), 1, t + timedelta(minutes=5))
    d.note(route_of(()), 1, t + timedelta(minutes=1))
    assert d.direct == 4 and d.last_direct_at == t + timedelta(minutes=5), "the latest wins, whatever the order they are noted in"
    d.note(route_of(()), 1)
    assert d.direct == 5 and d.last_direct_at == t + timedelta(minutes=5), "a count without a time leaves it"


@pytest.mark.parametrize("address, marker", [("RFONLY", True), ("NOGATE", True), ("TCPIP", True), ("TCPIP*", True), ("TCPXX*", True), ("NOTCP", True), ("qAR", True), ("qAC", True),
                                             ("OH2RCH-2", False), ("WIDE1-1", False), ("WIDE2*", False), ("RELAY", False)])
def test_the_markers_for_the_igates_are_no_digipeaters(address: str, marker: bool) -> None:
    assert is_marker(address) is marker


def test_the_digipeaters_of_a_path_leave_out_its_markers_and_keep_the_order() -> None:
    assert digipeaters(("OH2RCH-2", "WIDE2-1", "RFONLY")) == ("OH2RCH-2", "WIDE2-1")
    assert digipeaters(("WIDE1*", "NOGATE", "OH2RDG", "TCPIP*", "qAR", "OH7JHF-1")) == ("WIDE1*", "OH2RDG", "OH7JHF-1")
    assert digipeaters(()) == ()


@pytest.mark.parametrize("path, made", [
    ((), ("RFONLY",)), (("OH2RCH-2", "WIDE2-1"), ("OH2RCH-2", "WIDE2-1", "RFONLY")), (("OH2RCH-2", "RFONLY"), ("OH2RCH-2", "RFONLY")), (("NOGATE",), ("NOGATE",)),
    (("OH2RCH-2", "NOGATE", "WIDE2-1"), ("OH2RCH-2", "NOGATE", "WIDE2-1")), (("RFONLY", "OH2RCH-2"), ("RFONLY", "OH2RCH-2"))])
def test_rf_only_adds_rfonly_at_the_end_unless_the_path_says_it_already(path: tuple[str, ...], made: tuple[str, ...]) -> None:
    assert rf_only_path(path) == made


# ---- the path a message goes by when the operator has set none --------------------------------------------------------------------------------------

NOW = utc(2026, 10, 24, 12, 0)


def heard_at(deliveries: Deliveries, minutes_ago: float, *path: str, gate: str = "") -> None:
    deliveries.note(route_of(path, gate), 1, NOW - timedelta(minutes=minutes_ago))


def test_a_station_heard_direct_twice_within_an_hour_is_reached_direct() -> None:
    d = Deliveries()
    heard_at(d, 50)
    assert heard_path(d, NOW) is None, "one packet is luck"
    heard_at(d, 10)
    assert heard_path(d, NOW) == ()
    assert automatic_path(d, NOW, 1) == () and automatic_path(d, NOW, 2) == ()


def test_direct_wins_over_a_named_route_that_is_more_recent() -> None:
    d = Deliveries()
    heard_at(d, 30)
    heard_at(d, 20)
    heard_at(d, 5, "OH2RCH-2*")
    heard_at(d, 1, "OH2RCH-2*")
    assert heard_path(d, NOW) == ()


def test_a_named_route_that_two_packets_came_by_within_an_hour_is_turned_round() -> None:
    d = Deliveries()
    heard_at(d, 40, "OH2RCH-1*", "OH2RCH-3*", "WIDE2-1")
    assert heard_path(d, NOW) is None
    heard_at(d, 5, "OH2RCH-1*", "OH2RCH-3*")
    assert heard_path(d, NOW) == ("OH2RCH-3", "OH2RCH-1")


def test_the_most_recent_good_route_wins() -> None:
    d = Deliveries()
    heard_at(d, 55, "OH2RCH-2*")
    heard_at(d, 20, "OH2RCH-2*")
    heard_at(d, 40, "OH2RCH-3*")
    heard_at(d, 10, "OH2RCH-3*")
    heard_at(d, 2, "OH2RCH-4*")
    assert heard_path(d, NOW) == ("OH2RCH-3",), "OH2RCH-4 came once only; of the other two the one heard last"


def test_a_route_with_a_hop_with_no_call_is_none() -> None:
    d = Deliveries()
    for minutes in (30, 5):
        heard_at(d, minutes, "WIDE1*", "OH2RCH-2*")
    assert heard_path(d, NOW) is None


def test_a_packet_that_came_through_a_gate_is_none() -> None:
    d = Deliveries()
    for minutes in (30, 5):
        heard_at(d, minutes, "OH2RCH-3*", gate="OH7JHF-1")
    assert d.gated == 2 and heard_path(d, NOW) is None


def test_a_route_of_four_digipeaters_is_none_and_one_of_three_is_not() -> None:
    d = Deliveries()
    for minutes in (30, 5):
        heard_at(d, minutes, "OH2RCH-1*", "OH2RCH-2*", "OH2RCH-3*", "OH2RCH-4*")
    assert heard_path(d, NOW) is None
    for minutes in (30, 5):
        heard_at(d, minutes, "OH2RCH-1*", "OH2RCH-2*", "OH2RCH-3*")
    assert heard_path(d, NOW) == ("OH2RCH-3", "OH2RCH-2", "OH2RCH-1")


def test_a_path_heard_longer_ago_than_an_hour_is_none() -> None:
    d = Deliveries()
    heard_at(d, 61, "OH2RCH-2*")
    heard_at(d, 5, "OH2RCH-2*")
    assert heard_path(d, NOW) is None, "one of the two is older than 60 minutes"
    heard_at(d, 90)
    heard_at(d, 61)
    assert heard_path(d, NOW) is None
    assert heard_path(d, NOW - timedelta(minutes=20)) == ("OH2RCH-2",), "twenty minutes earlier both of them were within the hour"


def test_only_the_first_two_attempts_go_by_the_heard_path() -> None:
    d = Deliveries()
    heard_at(d, 10, "OH2RCH-2*")
    heard_at(d, 5, "OH2RCH-2*")
    assert [automatic_path(d, NOW, n) for n in (1, 2, 3, 4)] == [("OH2RCH-2",), ("OH2RCH-2",), None, None]
    assert automatic_path(None, NOW, 1) is None, "a station never heard"


def test_the_times_kept_of_a_route_are_the_two_latest_and_follow_a_route_that_is_dropped() -> None:
    d = Deliveries()
    for minutes in (50, 40, 30, 2):
        heard_at(d, minutes, "OH2RCH-2*")
    assert d.times[("OH2RCH-2",)] == [NOW - timedelta(minutes=30), NOW - timedelta(minutes=2)]
    d.note(route_of(("OH2RCH-9*",)), 1, NOW)
    for n in range(ROUTES_KEPT):
        d.note(route_of((f"OH2RCH-{n + 10}*",)), 5, NOW)
    assert set(d.times) == set(d.by_route), "a route that was dropped has no times left"


def test_a_group_seeded_from_the_database_brings_its_two_latest_times() -> None:
    d = Deliveries()
    d.note(route_of(("OH2RCH-2*",)), 7, NOW - timedelta(minutes=3), NOW - timedelta(minutes=9))
    assert heard_path(d, NOW) == ("OH2RCH-2",)


@pytest.mark.parametrize(("table", "code", "path"), [("/", "-", "WIDE2-1"), ("/", "#", "WIDE2-1"), ("/", ">", WIDE_PATH), ("\\", "s", WIDE_PATH), ("J", "^", WIDE_PATH), ("/", "?", "WIDE2-1"), ("", "", "WIDE2-1")])
def test_the_recommended_path_is_the_fill_in_hop_and_a_wide_hop_for_a_mobile_symbol_and_a_wide_hop_for_any_other(table: str, code: str, path: str) -> None:
    assert recommended_path(table, code) == path
