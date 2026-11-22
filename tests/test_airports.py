"""The table of airports (neoaprs/airportdata.py, made by scripts/gen-airports.py from OurAirports'
airports.csv) and the place it gives for an ICAO code (neoaprs/airports.py), and the generator on a
made-up list."""
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from neoaprs import airportdata
from neoaprs.airports import place

from tests.test_scripts import load_script

ROOT = Path(__file__).resolve().parent.parent
HEAD = "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,icao_code,iata_code,gps_code,local_code,home_link,wikipedia_link,keywords\n"
LIST = (HEAD
        + '1,EFHK,large_airport,Helsinki Vantaa Airport,60.3,24.9,179,EU,FI,FI-18,Helsinki (Vantaa),yes,EFHK,HEL,EFHK,,,,\n'
        + '2,ESSA,large_airport,Stockholm-Arlanda Airport,59.6,17.9,137,EU,SE,SE-AB,Stockholm,yes,ESSA,ARN,ESSA,,,,\n'
        + '3,XX01,medium_airport,Lonely Field,60.0,20.0,10,EU,FI,FI-01,,no,,,XX01,,,,\n'
        + '4,YY02,medium_airport,Gps Only,60.0,20.0,10,EU,FI,FI-01,Gpsville,no,,,YYGP,,,,\n'
        + '5,00AA,small_airport,Small One,38.7,-101.4,3435,NA,US,US-KS,Leoti,no,,,00AA,00AA,,,\n'
        + '6,EFXXX,large_airport,Five Letters,60.0,20.0,10,EU,FI,FI-01,Toolong,no,,,,,,,\n'
        + '7,EFHK,medium_airport,A second row of the code,60.0,20.0,10,EU,FI,FI-01,Elsewhere,no,EFHK,,,,,,\n'
        + '8,ZZ03,heliport,A Heliport,60.0,20.0,10,EU,FI,FI-01,Helipad,no,,,ZZ03,,,,\n')


def generator() -> ModuleType:
    return load_script("gen-airports.py")


def run_generator(monkeypatch: pytest.MonkeyPatch, target: Path, *arguments: str) -> int:
    module = generator()
    monkeypatch.setattr(module, "TARGET", target)
    monkeypatch.setattr(sys, "argv", ["gen-airports.py", *arguments])
    return int(module.main())


def test_the_place_of_an_airport_is_its_municipality_and_the_places_of_the_examples_are_in_the_table() -> None:
    assert [place(code) for code in ("EFHK", "ESSA", "LIRF", "ZBAD", "EGLL")] == ["Helsinki", "Stockholm", "Rome", "Beijing", "London"]


@pytest.mark.parametrize("code", ["", "ZZZZ", "efhk", "EFH", "EFHKX", "  "])
def test_a_code_the_table_does_not_know_has_no_place(code: str) -> None:
    assert place(code) == ""


def test_the_table_holds_the_large_and_medium_airports_in_the_order_of_their_codes_with_the_source_and_the_licence_in_its_head() -> None:
    table = airportdata.AIRPORTS
    assert 4500 < len(table) < 6000 and list(table) == sorted(table) and all(len(code) == 4 and name for code, name in table)
    assert airportdata.__doc__ is not None and "ourairports.com" in airportdata.__doc__ and "public domain" in airportdata.__doc__


def test_the_generator_keeps_large_and_medium_airports_with_a_four_character_code_and_names_each_by_its_municipality_else_its_name() -> None:
    made = generator().rows(LIST)
    assert made == [("EFHK", "Helsinki"), ("ESSA", "Stockholm"), ("XX01", "Lonely Field"), ("YYGP", "Gpsville")], "the ICAO code, else the GPS code; the first row of a code wins; no small airport, heliport or five-letter code"


def test_the_generator_writes_the_module_from_a_file_and_checks_it_against_that_file_and_not_against_another(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    source, target = tmp_path / "airports.csv", tmp_path / "airportdata.py"
    source.write_text(LIST, encoding="utf-8")
    assert run_generator(monkeypatch, target, "--from", str(source)) == 0
    text = target.read_text(encoding="utf-8")
    assert text.count("(\"") == 4 and "sha256 of the source file" in text and "AIRPORTS: tuple[tuple[str, str], ...] = (" in text
    assert run_generator(monkeypatch, target, "--check", str(source)) == 0
    other = tmp_path / "other.csv"
    other.write_text(LIST.replace("Stockholm,yes", "Stockholm Town,yes"), encoding="utf-8")
    assert run_generator(monkeypatch, target, "--check", str(other)) == 1 and "run scripts/gen-airports.py" in capsys.readouterr().err


def test_a_place_is_written_with_single_spaces_and_without_what_the_list_adds_in_brackets() -> None:
    row = "1,{code},medium_airport,{name},26.0,107.0,1,AS,CN,CN-GZ,{town},no,{code},,{code},,,,\n"
    made = generator().rows(HEAD + row.format(code="ZUKJ", name="Kaili Airport", town="Kaili  (Huangping)") + row.format(code="LFPG", name="Charles de Gaulle", town='"Paris (Roissy-en-France, Val-d\'Oise)"')
                            + row.format(code="XXAA", name="Santa  Cruz (closed) Field", town="") + row.format(code="XXBB", name="(Old) (Field)", town=""))
    assert made == [("LFPG", "Paris"), ("XXAA", "Santa Cruz Field"), ("XXBB", "(Old) (Field)"), ("ZUKJ", "Kaili")], "the card puts the code in brackets itself; a text that is brackets alone stays as it is"


def test_importing_the_places_does_not_read_the_table_until_a_place_is_asked() -> None:
    code = "import sys; import neoaprs.airports as a; before = 'neoaprs.airportdata' in sys.modules; a.place('ESSA'); print(before, 'neoaprs.airportdata' in sys.modules)"
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, cwd=ROOT)
    assert run.stdout.split() == ["False", "True"], run.stderr
