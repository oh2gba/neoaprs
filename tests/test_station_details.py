"""What the page is told of a station beyond where it is: its latest telemetry scaled by its own definitions, its locator and its data extensions; and that the daemon's own decoded packets fit the wire models."""
import json
from datetime import UTC, datetime

import pytest

from pydantic import TypeAdapter

from neoaprs.aprsparse import parse
from neoaprs.packet import Message, Packet
from neoaprs.packetcodec import encode_decoded
from neoaprs.stationbook import StationBook
from neoaprs.web.packetwire import Decoded
from neoaprs.web.stationwire import StationRow
from neoaprs.web.views import station_row

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def heard(info: str, source: str = "N0QBF-11", destination: str = "APRS") -> Packet:
    return Packet(T0, "in", b"", source, destination, (), info.encode("latin-1"), parse(info.encode("latin-1"), source, destination, T0))


def row_of(book: StationBook, call: str) -> StationRow:
    station = book.get(call)
    assert station is not None
    return StationRow.model_validate_json(json.dumps(station_row(book, station)))


def test_a_station_row_has_the_telemetry_named_and_scaled_by_its_definitions() -> None:
    book = StationBook()
    book.take(heard("T#005,199,000,255,073,123,01101001"))
    plain = row_of(book, "N0QBF-11")
    assert plain.telemetry is not None and plain.telemetry.channels[0].name == "A1" and plain.telemetry.channels[0].value == 199 and plain.telemetry_at == "2026-10-21T12:00:00Z"
    for text in ("PARM.Battery,Btemp", "UNIT.v/100,deg.F", "EQNS.0,5.2,0,0,.53,-32", "BITS.10110000,Big Balloon"):
        book.take(Packet(T0, "in", b"", "N0QBF-11", "APRS", (), b"", Message("N0QBF-11", text)))
    row = row_of(book, "N0QBF-11")
    assert row.telemetry is not None
    battery = row.telemetry.channels[0]
    assert (battery.name, battery.unit, battery.raw, battery.value) == ("Battery", "v/100", 199.0, 1034.8)
    assert row.telemetry.project == "Big Balloon" and row.telemetry.bits[0].on is False and row.telemetry.bits[2].on is True


def test_a_station_row_has_the_locator_and_the_extensions() -> None:
    book = StationBook()
    book.take(heard(">IO91sx/- My house", "OH2AAA"))
    book.take(heard("!4903.50N/07201.75W#PHG5132", "OH2BBB"))
    a, b = row_of(book, "OH2AAA"), row_of(book, "OH2BBB")
    assert a.locator is not None and a.locator.grid == "IO91sx" and a.locator.lat == pytest.approx(51.97917) and a.extensions is None and a.last_status == "My house"
    assert b.extensions is not None and b.extensions.phg is not None and b.extensions.phg.power_w == 25 and b.locator is None and b.telemetry is None


@pytest.mark.parametrize("info", [
    "T#005,199,000,255,073,123,01101001", ">IO91sx/- hi", "@092345/4903.50N/07201.75W>RNG0050", "<IGATE,MSG_CNT=2", "%123%4", "_10090556c220s004g005t077", "$GPGLL,2554.459,N,08020.187,W,154027.281,A",
    ";SEARCH   *092345z4903.50N\\07201.75Wl710/310", "=4903.50N/07201.75W>088/036/270/729", "[IO91sx", ",test",
])
def test_what_the_parser_makes_fits_the_wire_model(info: str) -> None:
    TypeAdapter(Decoded).validate_python(json.loads(encode_decoded(heard(info).decoded)))
