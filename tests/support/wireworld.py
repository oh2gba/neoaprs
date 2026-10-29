"""A small world of the daemon's objects, one of every kind the page is told about, and every `neoaprs/web/views.py` view of it as JSON: what the golden file tests/fixtures/wire/rows.json holds."""
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from neoaprs.aprsisline import parse_is_line
from neoaprs.aprsparse import parse
from neoaprs.bulletin import BulletinRecord
from neoaprs.chain import AT_GATE, Attempt, HopSeen
from neoaprs.gpsfix import Fix
from neoaprs.message import MessageRecord
from neoaprs.ownbulletin import OwnBulletin
from neoaprs.ownobject import OwnObject
from neoaprs.packet import Message, Packet, ThirdParty, Undecoded
from neoaprs.pref import Pref
from neoaprs.qrutext import Asked, Server
from neoaprs.smartbeacon import Reason, Sent
from neoaprs.stationbook import StationBook
from neoaprs.dummyline import DUMMY_PATH
from neoaprs.tnc import Tnc
from neoaprs.tncprofile import DUMMY
from tests.support.clock import FixedClock

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
ME = "OH2GBA-7"


def heard(info: str, source: str, path: tuple[str, ...] = (), at: datetime = T0, destination: str = "APRS") -> Packet:
    return Packet(at, "in", b"", source, destination, path, info.encode("latin-1"), parse(info.encode("latin-1"), source, destination, at))


def internet(line: str, at: datetime = T0) -> Packet:
    """A packet received from APRS-IS, from the line the server sent."""
    return parse_is_line(line, at)


def made_up(info: str, source: str, at: datetime = T0) -> Packet:
    """A packet of the Dummy radio, which makes up traffic to try the program with."""
    return replace(heard(info, source, ("WIDE1*",), at), via="dummy")


def packets() -> list[Packet]:
    """A packet of every kind the page tells: positions (plain, with course and speed, with PHG, Mic-E), objects, items, status with a locator, telemetry, weather, a message, a third-party
    packet, one received from the internet, one of ours."""
    return [
        heard("!4903.50N/07201.75W-Test", "N0AAA", ("OH2RCH-2*", "WIDE2-1")),
        heard("=4903.50N/07201.75W>088/036/A=000123 mobile", "N0BBB-9", ("WIDE1*", "OH2RDG-1*"), destination="APK004"),
        heard("!4903.50N/07201.75W#PHG5132", "N0CCC"),
        heard("@092345z4903.50N/07201.75W>RNG0050 range", "N0DDD", ("WIDE1-1",), destination="APDR15"),
        heard(">IO91sx/- on the air", "N0EEE", ("OH2RCH-3*",)),
        heard(";LEADER   *092345z6012.00N/02456.00E>090/020 convoy", "N0FFF", ("OH2RCH-2*",)),
        heard(")AID #!6015.00N/02458.00EA first aid", "N0FFF"),
        heard(";SEARCH   *092345z4903.50N\\07201.75Wl710/310", "N0GGG"),
        heard("_10090556c220s004g005t077r000p000P000h50b09720", "N0WX"),
        heard("!4903.50N/07201.75W_220/004g005t077r000p000P000h50b09720", "N0WX-1", ("WIDE1*",)),
        heard("T#005,199,000,255,073,123,01101001", "N0TEL"),
        heard("%123%4", "N0ODD"),
        heard("{junk", "N0BAD"),
        Packet(T0, "in", b"", "N0MIC", "S32UVT", ("WIDE1*",), b'(_fn"Oj/', parse(b'(_fn"Oj/', "N0MIC", "S32UVT", T0)),
        Packet(T0, "in", b"", "N0UND", "APRS", (), b"!4903", Undecoded("too short", "!4903")),
        Packet(T0, "in", b"", "OH7JHF-1", "APRS", ("OH2RCH-3*",), b"info", Message("OH2GBA", "", ack_id="10"), ThirdParty("OH2DPN", "APJYC1", ("TCPIP", "OH7JHF-1*")), "rf-gated"),
        Packet(T0 + timedelta(seconds=7), "out", b"", ME, "APNEO0", ("WIDE1-1", "WIDE2-1"), b"!6010.00N/02450.00E-", parse(b"!6010.00N/02450.00E-", ME, "APNEO0", T0)),
        Packet(T0, "in", b"", "N0MSG", "APRS", (), b":OH2GBA   :hello{7", Message("OH2GBA", "hello", "7")),
        heard("!4903.50N/07201.75W-145.775MHz T118 -060 R40k Voice", "N0FRQ"),
        heard(";145.775-A*111111z4903.50N/07201.75WrT079 R25m NET Tu9PM", "N0RPT"),
        heard(";BRENDA   *092345z4903.50N\\07202.75W@088/036/HC/150^200/0980>090&030%040", "N0STM"),
        heard(")I91 3N!4903.50N\\07201.75Wm{55}", "N0SGN"),
        internet("N0ISX-9>APRS,TCPIP*,qAC,T2FINLAND:=6012.34N/02456.78E-from the internet"),
        made_up("=6015.00N/02500.00E-made up", "QDUMMY-1"),
    ]


def book() -> StationBook:
    """The station book of the packets: ours, stations of every kind, a track, the definitions of a telemetry station, an object of ours, a station with no position."""
    book = StationBook(clock=FixedClock(T0))
    book.set_me(ME, 60.2, 24.9, "/", "-", "Home")
    for packet in packets():
        book.take(packet)
    book.take(heard("!4905.00N/07202.00W-moved", "N0AAA", ("OH2RCH-2*",), T0 + timedelta(minutes=10)))
    book.take(heard("!4905.50N/07202.00W-moved again", "N0AAA", (), T0 + timedelta(minutes=20)))
    for text in ("PARM.Battery,Btemp", "UNIT.v/100,deg.F", "EQNS.0,5.2,0,0,.53,-32", "BITS.10110000,Big Balloon"):
        book.take(Packet(T0, "in", b"", "N0TEL", "APRS", (), b"", Message("N0TEL", text)))
    book.take(internet("N0AAA>APRS,WIDE1-1,qAR,OH2RDK-1:!4905.60N/07202.10W-over the internet too", T0 + timedelta(minutes=25)))
    book.take(heard(">no position", "N0NONE"))
    book.own_object(OwnObject("MYOBJ", "object", 60.3, 24.8, "/", "O", T0, T0 + timedelta(minutes=1), "Mine", 90, 20.5, "WIDE1-1", True, 3, T0 + timedelta(minutes=2)))
    book.own_object(OwnObject("MYITEM", "item", 60.4, 24.7, "/", "-", T0, T0, sent=0))
    return book


def messages() -> list[tuple[MessageRecord, tuple[Attempt, ...]]]:
    """A message in each state and with attempts: acked (heard back by radio and by the internet), failed, sending, received, overheard."""
    seen = (HopSeen(1, "OH2RCH-2", T0 + timedelta(seconds=3), False), HopSeen(2, "OH2RDG-1", T0 + timedelta(seconds=5), True), HopSeen(AT_GATE, "OH7JHF-1", T0 + timedelta(seconds=6), True))
    a1 = Attempt(1, T0, ("OH2RCH-2", "WIDE2-1"), seen)
    a2 = Attempt(2, T0 + timedelta(seconds=30), ("WIDE1-1",), ())
    a3 = Attempt(3, T0 + timedelta(seconds=90), (), ())
    out = MessageRecord(1, T0, "out", ME, "OH2XYZ", "Hello", "12", "acked", 3, T0 + timedelta(seconds=90), T0 + timedelta(seconds=100), 4, "")
    return [
        (out, (a1, a2, a3)),
        (MessageRecord(2, T0, "out", ME, "OH2XYZ", "Never", "13", "failed", 4, T0 + timedelta(seconds=500), None, 4, ""), (a1,)),
        (MessageRecord(3, T0, "out", ME, "EMAIL-2", "me@example.org hi", "14", "sending", 1, T0, None, 2, ""), (a3,)),
        (MessageRecord(4, T0, "in", "OH2XYZ", ME, "Hi back", "7", "received", 0, None, None, 4, "via OH2RCH-2"), ()),
        (MessageRecord(5, T0, "in", "OH2AAA", "OH2BBB", "overheard text", None, "overheard", 0, None, None, 4, "direct"), ()),
    ]


def bulletins() -> list[BulletinRecord]:
    return [BulletinRecord("OH2XYZ", "BLN1", "", "bulletin", "Net tonight", T0, T0 + timedelta(minutes=5), 3), BulletinRecord("OH2XYZ", "BLN3HAMS", "HAMS", "group", "Åland ä ö", T0, T0)]


def own_objects() -> list[tuple[OwnObject, datetime | None]]:
    return [
        (OwnObject("LEADER", "object", 60.2, 24.9, "/", ">", T0, T0 + timedelta(minutes=1), "Moved", 90, 20.5, "WIDE1-1", True, 2, T0 + timedelta(minutes=2)), T0 + timedelta(minutes=4)),
        (OwnObject("AID", "item", 60.3, 24.8, "/", "+", T0, T0, qru_group="FOOD", on_request=True), None),
        (OwnObject("GONE", "object", 60.1, 24.7, "\\", "k", T0, T0, "", None, None, None, False, 1, T0), T0 + timedelta(minutes=1)),
    ]


def own_bulletins() -> list[tuple[OwnBulletin, datetime | None]]:
    return [(OwnBulletin("BLN3HAMS", "HAMS", "group", "Net tonight", T0, 2, T0, T0 + timedelta(minutes=2)), T0 + timedelta(minutes=8)), (OwnBulletin("BLNA", "", "announcement", "Hello", T0), None)]


def prefs() -> list[Pref]:
    return [Pref(), Pref(("WIDE1-1", "WIDE2-1"), True), Pref((), False), Pref(None, True)]


def tnc() -> Tnc:
    clock = FixedClock(T0)
    tnc = Tnc(clock=clock)
    tnc._note("opened /dev/brainbox_1")
    clock.advance(3)
    tnc._saw("OH2XYZ>APRS:>hello  ->  status hello")
    tnc.stats.opens, tnc.stats.bytes_in, tnc.stats.frames_in, tnc.stats.packets, tnc.stats.last_packet = 2, 1234, 7, 6, T0 + timedelta(seconds=3)
    tnc.stats.keepalive_checks, tnc.stats.watchdog_probes, tnc.stats.port_reopens, tnc.stats.digipeated = 1, 2, 3, 4
    tnc.stats.digipeated_at, tnc.stats.digipeat_held = T0 + timedelta(seconds=2), 1
    tnc.last_watchdog_action, tnc.last_watchdog_at = "probe", T0 + timedelta(seconds=2)
    return tnc


def tnc_dummy() -> Tnc:
    found = Tnc(profile=DUMMY, clock=FixedClock(T0))
    found.path = DUMMY_PATH
    return found


def tnc_searching() -> Tnc:
    found = tnc()
    found._search.listening = ["/dev/ttyUSB0", "/dev/ttyUSB1"]
    found.last_error = "no answer"
    return found


@dataclass
class FakeGps:
    """The GPS service as the `gps` topic reads it: a fix, a state, a problem, and whether the fix is fresh."""
    fix: Fix | None = None
    state: str = "off"
    problem: str = ""
    fresh: bool = False

    def current(self) -> Fix | None:
        return self.fix if self.fresh else None


@dataclass
class FakePlan:
    last: Sent | None = None
    last_reason: Reason | None = None


def gps_rows(views: Any) -> list[dict[str, Any]]:
    """The `gps` topic: off, a mobile station with a fresh fix that turned a corner, and a mobile station whose receiver is not up."""
    from neoaprs.config import DEFAULTS
    mobile = replace(DEFAULTS, gps_source="gpsd")
    fix = Fix(60.17, 24.94, T0, 54.6, 270, 31.0, 9)
    return [
        views.gps_state(DEFAULTS, FakeGps(), FakePlan(), None),
        views.gps_state(mobile, FakeGps(fix, "fix", "", True), FakePlan(Sent(T0 - timedelta(seconds=20), 180), "turn"), T0 + timedelta(seconds=40)),
        views.gps_state(replace(mobile, gps_source="serial", gps_device="/dev/ttyUSB1"), FakeGps(None, "connecting", "/dev/ttyUSB1: No such file or directory"), FakePlan(), None),
    ]


@dataclass
class FakeIgate:
    """The iGate service as the `igate` topic reads it."""
    state: str = "off"
    problem: str = ""
    server_name: str = ""
    gated: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    last_gated_at: datetime | None = None


def igate_rows(views: Any) -> list[dict[str, Any]]:
    """The `igate` topic: off, connected with packets gated and not gated, not connected, listening only, and a passcode the server did not accept."""
    from neoaprs.config import DEFAULTS
    on = replace(DEFAULTS, igate_enabled=True, station_call="OH2GBA")
    return [
        views.igate_state(DEFAULTS, FakeIgate()),
        views.igate_state(on, FakeIgate("connected", "", "T2FINLAND", 1234, {"tcpip": 31, "duplicate": 6, "query": 3}, T0 - timedelta(seconds=12))),
        views.igate_state(on, FakeIgate("connecting", "127.0.0.1:14580: Connection refused")),
        views.igate_state(on, FakeIgate("listening", "", "T2FINLAND")),
        views.igate_state(on, FakeIgate("unverified", "the server did not accept the password", "T2FINLAND")),
    ]


@dataclass
class FakeQru:
    """The QRU client as the `qru` topic reads it."""
    asked: Asked | None = None
    held: list[Server] = field(default_factory=list)

    def servers(self) -> list[Server]:
        return self.held


def qru_rows(views: Any) -> list[dict[str, Any]]:
    """The `qru` topic: nothing yet, a request nobody answered, and two servers (one with its closing line, one in miles that has only sent the closing line of a group)."""
    first = Server("DF8LS-10", (("RP70", 10), ("RP2M", 3)), 5, 50, "km", T0, False, "Sent 5 RP70 Objects Max 5@50km de DF8LS-10", T0 + timedelta(seconds=40))
    second = Server("W1AW", (), None, None, "", T0 + timedelta(minutes=2), False, "Sent 2 of 7 FOOD Objects, NEXT for more. de W1AW", T0 + timedelta(minutes=2))
    return [views.qru_state(FakeQru()), views.qru_state(FakeQru(Asked("INFO", T0))), views.qru_state(FakeQru(Asked("RP70 150", T0 + timedelta(seconds=30)), [first, second]))]


def rows(views: Any) -> dict[str, Any]:
    """Every row of the world as `views` (neoaprs/web/views.py, or an older copy of it) makes it."""
    from neoaprs.config import DEFAULTS
    world = book()
    return {
        "stations": {s.call: views.station_row(world, s) for s in world.stations()},
        "packets": {str(n): views.packet_row(n, p) for n, p in enumerate(packets(), 1)},
        "messages": {str(r.id): views.message_row(r, attempts) for r, attempts in messages()},
        "bulletins": {b.key: views.bulletin_row(b) for b in bulletins()},
        "own_objects": {o.name: views.own_object_row(o, at) for o, at in own_objects()},
        "own_bulletins": {b.slot: views.own_bulletin_row(b, at) for b, at in own_bulletins()},
        "station_prefs": [views.pref_row(p) for p in prefs()],
        "tnc": [views.tnc_state(Tnc(clock=FixedClock(T0))), views.tnc_state(tnc()), views.tnc_state(tnc_searching()), views.tnc_state(tnc_dummy())],
        "gps": gps_rows(views),
        "igate": igate_rows(views),
        "qru": qru_rows(views),
        "config": [views.config_values(DEFAULTS, []), views.config_values(DEFAULTS, ["http://192.168.1.2:8730"], {"on": True, "port": 8731, "fingerprint": "AB:CD", "problem": ""})],
    }
