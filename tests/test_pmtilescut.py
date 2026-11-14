"""The cut of the base map out of a big archive (neoaprs/pmtilescut.py, pmtilesplan.py, pmtilesrange.py, pmtilesformat.py) on made-up archives (tests/support/madepmtiles.py, written apart from the program's code, so that the two
check each other): the tiles a box holds and nothing else, a header the page can read, every shape of directory, the dry run that says the size and fetches no tile, the limits, archives and servers that lie (small inputs
that claim to be big), a request that is made again, a stop that ends the threads."""
import array
import asyncio
import gzip
import threading
from pathlib import Path

import pytest

from neoaprs.pmtilescut import Cut, Cutting, extract, part_of
from neoaprs.pmtilesformat import GZIP, Entries, FormatError, decode, parse_header, touched, unpack
from neoaprs.pmtilesplan import _requests
from neoaprs.pmtilesrange import STOPPED, CutError, Halt, HttpSource
from tests.support.env import until_started
from tests.support.madepmtiles import _number, archive, archive_of, directory, every_tile, fields_of, planet, tile_id, tiles_of
from tests.support.maprig import data_offset
from tests.support.rangeserver import range_server

BOX = (24.5, 59.9, 25.3, 60.4)
NOW = (0.0, 0.0, 0.0)                                            # (no pause between the tries of a request)


def cut_file(tmp_path: Path, data: bytes, box: tuple[float, float, float, float] | None, maxzoom: int, **options: object) -> tuple[bytes, Cut]:
    (tmp_path / "source.pmtiles").write_bytes(data)
    cutting = Cutting(str(tmp_path / "source.pmtiles"), tmp_path / "out.pmtiles", box, maxzoom, pauses=NOW, **options)       # type: ignore[arg-type]
    cut = cutting.run()
    return (tmp_path / "out.pmtiles").read_bytes(), cut


def expected(source: bytes, box: tuple[float, float, float, float] | None, deepest: int) -> dict[int, bytes]:
    stored = every_tile(source)
    keys = tiles_of(box or (-180.0, -85.0511, 180.0, 85.0511), int(fields_of(source)["min_zoom"]), deepest)
    return {tile_id(*key): stored[tile_id(*key)] for key in keys if tile_id(*key) in stored}


def world(max_zoom: int, shared: bool = False) -> dict[tuple[int, int, int], bytes]:
    return {(z, x, y): (b"sea" if shared and (x + y) % 3 else f"{z}/{x}/{y}".encode()) for z in range(max_zoom + 1) for x in range(1 << z) for y in range(1 << z)}


# ---- what is cut

@pytest.mark.parametrize("shape", [dict(leaf=None), dict(leaf=8), dict(leaf=8, deep=True), dict(leaf=8, packed=False), dict(leaf=5, runs=False, shared=False)])
@pytest.mark.parametrize("box", [BOX, (-10.0, -10.0, 30.0, 50.0), None])
def test_the_cut_holds_the_tiles_of_the_box_to_the_zoom_and_no_other(tmp_path: Path, shape: dict[str, object], box: tuple[float, float, float, float] | None) -> None:
    source = archive(world(6, shared=True), **shape)                # type: ignore[arg-type]
    out, cut = cut_file(tmp_path, source, box, 5)
    assert every_tile(out) == expected(source, box, 5)
    fields = fields_of(out)
    assert (fields["clustered"], fields["min_zoom"], fields["max_zoom"], fields["internal"], fields["compression"], fields["kind"]) == (1, 0, 5, fields_of(source)["internal"], 2, 1)
    assert fields["addressed"] == len(every_tile(out)) and cut.tiles == fields["entries"] and cut.contents == fields["contents"] and cut.bytes == len(out) == fields["data_offset"] + fields["data_length"]


def test_a_content_that_tiles_share_is_in_the_archive_once_and_a_run_of_tiles_is_one_entry(tmp_path: Path) -> None:
    source = archive({(2, x, y): b"the same sea" for x in range(4) for y in range(4)} | {(0, 0, 0): b"world"})
    out, cut = cut_file(tmp_path, source, None, 2)
    assert (cut.contents, cut.addressed) == (2, 17) and cut.tiles < 17
    assert fields_of(out)["data_length"] == len(b"the same sea") + len(b"world") and every_tile(out) == every_tile(source)


def test_a_run_of_tiles_that_reaches_out_of_the_box_is_cut_down_to_the_part_inside(tmp_path: Path) -> None:
    source = archive({(3, x, y): b"one sea" for x in range(8) for y in range(8)})
    out, cut = cut_file(tmp_path, source, (-100.0, 10.0, -50.0, 60.0), 3)
    assert every_tile(out) == expected(source, (-100.0, 10.0, -50.0, 60.0), 3) and 0 < len(every_tile(out)) < 64
    assert cut.addressed == len(every_tile(out))


def test_the_header_has_the_box_and_its_centre_and_the_zooms_the_source_has_when_it_has_fewer(tmp_path: Path) -> None:
    out, _ = cut_file(tmp_path, planet(), BOX, 12)
    fields = fields_of(out)
    assert fields["bounds"] == (int(24.5e7), int(59.9e7), int(25.3e7), int(60.4e7)) and fields["center"] == (int(24.9e7), int(60.15e7)) and fields["max_zoom"] == 6
    whole, _ = cut_file(tmp_path, planet(), None, 4)
    assert fields_of(whole)["bounds"] == fields_of(planet())["bounds"] and fields_of(whole)["max_zoom"] == 4


def test_the_archive_is_written_to_a_part_file_and_moved_into_place_whole(tmp_path: Path) -> None:
    (tmp_path / "out.pmtiles").write_bytes(b"the map before")
    out, _ = cut_file(tmp_path, planet(), BOX, 4)
    assert out.startswith(b"PMTiles") and not part_of(tmp_path / "out.pmtiles").exists()


def test_the_percent_only_rises_and_ends_at_100(tmp_path: Path) -> None:
    (tmp_path / "source.pmtiles").write_bytes(planet())
    told: list[int] = []
    Cutting(str(tmp_path / "source.pmtiles"), tmp_path / "out.pmtiles", None, 6, on_percent=told.append).run()
    assert told == sorted(told) and len(set(told)) == len(told) and told[-1] == 100 and all(0 <= p <= 100 for p in told)


# ---- the dry run, the limits

def test_the_dry_run_says_what_the_cut_makes_and_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "source.pmtiles").write_bytes(planet())
    cutting = Cutting(str(tmp_path / "source.pmtiles"), tmp_path / "out.pmtiles", BOX, 6)
    said = cutting.estimate()
    assert not list(tmp_path.glob("out*")) and said == cutting.run() and said.bytes == (tmp_path / "out.pmtiles").stat().st_size and said.tiles == len(tiles_of(BOX, 0, 6))


async def test_a_dry_run_from_a_server_fetches_the_directories_and_no_tile(tmp_path: Path) -> None:
    server = await range_server(planet())
    said = await extract(server.url, tmp_path / "out.pmtiles", BOX, 6, dry_run=True)
    assert said.tiles == len(tiles_of(BOX, 0, 6)) and server.asked and all(last < data_offset(planet()) for _, last in server.asked) and not list(tmp_path.glob("out*"))


def test_a_cut_bigger_than_it_may_be_is_refused_before_a_tile_is_fetched(tmp_path: Path) -> None:
    with pytest.raises(CutError, match=r"the map would be \d+ MB, more than the 0 MB it may be"):
        cut_file(tmp_path, planet(), None, 6, max_bytes=100)
    assert not list(tmp_path.glob("out*"))


def test_the_box_may_hold_no_more_than_the_entries_a_cut_keeps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.pmtilesplan.MAX_TILE_ENTRIES", 10)
    with pytest.raises(CutError, match="more than 10 tile entries"):
        cut_file(tmp_path, planet(), None, 6)


# ---- sources that cannot be cut, or lie

@pytest.mark.parametrize(("data", "why"), [
    (archive(world(3), clustered=0), "not clustered"),
    (archive(world(3), version=2), "PMTiles version 2, not 3"),
    (archive(world(3), internal=3), "compressed with method 3"),
    (archive(world(3), min_zoom=5, max_zoom=2), "zooms 5 to 2 are not possible"),
    (archive(world(3), data_length=10**15), "tile data of the archive"),
    (archive(world(3), root_length=20000), "root directory of the archive"),
    (b"text" * 100, "not a PMTiles archive"),
])
def test_an_archive_that_cannot_be_cut_or_lies_about_itself_is_refused_in_words(tmp_path: Path, data: bytes, why: str) -> None:
    with pytest.raises(CutError, match=why):
        cut_file(tmp_path, data, None, 3)
    assert not list(tmp_path.glob("out*"))


def test_an_archive_whose_directory_names_a_tile_beyond_its_data_is_refused(tmp_path: Path) -> None:
    source = bytearray(archive({(0, 0, 0): b"world", (1, 0, 0): b"nw"}))
    lie = fields_of(bytes(source))
    source[int(lie["data_offset"]) - 0:] = b"w"                                          # (the data is cut short, the header still says its length: the sections no longer fit)
    with pytest.raises(CutError, match="is not inside"):
        cut_file(tmp_path, bytes(source), None, 1)


def test_numbers_that_claim_to_be_big_are_refused_by_what_they_are_not_by_an_allocation() -> None:
    with pytest.raises(FormatError, match="more than 1000 bytes"):
        unpack(gzip.compress(bytes(100_000)), GZIP, limit=1000)
    with pytest.raises(FormatError, match="does not unpack"):
        unpack(b"not gzip at all", GZIP, limit=1000)
    with pytest.raises(FormatError, match="cut short"):
        unpack(gzip.compress(b"abcdef" * 1000)[:-30], GZIP, limit=10_000)
    with pytest.raises(FormatError, match="does not hold the entries it says"):
        decode(_number(10**9))                                                          # (a billion entries, announced in a few bytes)
    with pytest.raises(FormatError, match="more than 64 bits"):
        decode(b"\x80" * 12)
    with pytest.raises(FormatError, match="middle of a number"):
        decode(b"\x01\x80")
    with pytest.raises(FormatError, match="not 3"):
        parse_header(b"PMTiles" + bytes([4]) + bytes(200))


def test_a_number_of_64_bits_or_more_is_refused_in_words() -> None:
    with pytest.raises(FormatError, match="more than 64 bits"):
        decode(_number(1) + _number(1 << 64) + _number(1) + _number(1) + _number(1))       # (ten bytes that hold 2**64: a varint of 70 bits)
    with pytest.raises(FormatError, match="a tile or an offset of more than 64 bits"):
        decode(_number(2) + _number(1 << 63) * 2 + _number(1) * 4 + _number(1) + _number(0))   # (two ids that are each below 2**64 and sum to it)
    with pytest.raises(FormatError, match="a tile or an offset of more than 64 bits"):
        decode(_number(2) + _number(1) * 2 + _number(1) * 2 + _number(5) * 2 + _number((1 << 64) - 1) + _number(0))    # (an offset that follows one just below 2**64)


def test_a_directory_of_more_leaves_than_a_cut_reads_is_refused_as_it_is_read() -> None:
    pointers = Entries()
    for i in range(1000):
        pointers.add(i, 0, 1, i)
    with pytest.raises(FormatError, match="more than 200000 leaf directories"):
        touched(pointers, [(0, 1000)], 0, 1000, 10)
    parts, leaves = touched(pointers, [(0, 1000)], 0, 1000, 1000)
    assert parts == [] and len(leaves) == 1000


@pytest.mark.parametrize("where", ["root", "leaf"])
def test_a_directory_that_unpacks_to_more_than_a_real_one_is_refused(tmp_path: Path, where: str) -> None:
    big = gzip.compress(bytes(5 * 1024 * 1024), mtime=0)                                # (5 MB of zeros in a few kB)
    root, leaves = (big, b"") if where == "root" else (directory([(0, 0, len(big), 0)]), big)
    with pytest.raises(CutError, match="unpacks to more than"):
        cut_file(tmp_path, archive_of(root, leaves, b"x", min_zoom=0, max_zoom=0), None, 0)


def test_a_content_range_of_more_digits_than_a_size_has_is_refused_in_words() -> None:
    class Answer:
        status = 206
        headers = {"Content-Range": "bytes 0-9/" + "9" * 5000, "Content-Length": "10"}
    with pytest.raises(CutError, match="answered bytes"):
        HttpSource("http://127.0.0.1:1/x.pmtiles", Halt())._check(Answer(), 0, 10)       # type: ignore[arg-type]


def test_a_file_that_ends_before_its_directories_do_is_said(tmp_path: Path) -> None:
    source = planet()
    (tmp_path / "source.pmtiles").write_bytes(source[:data_offset(source) + 10])
    with pytest.raises(CutError, match="is not inside its"):
        Cutting(str(tmp_path / "source.pmtiles"), tmp_path / "out.pmtiles", None, 6).run()
    with pytest.raises(CutError, match="map file nothere.pmtiles cannot be read"):
        Cutting(str(tmp_path / "nothere.pmtiles"), tmp_path / "out.pmtiles", None, 6).run()
    with pytest.raises(CutError, match="neither an http or https address nor a file"):
        Cutting("ftp://x/y.pmtiles", tmp_path / "out.pmtiles", None, 6).run()


# ---- the requests

def test_pieces_with_small_gaps_are_one_request_as_long_as_the_gaps_are_at_most_the_overfetch_of_the_data() -> None:
    lengths = array.array("I", [1000] * 20)
    sources = array.array("Q")
    at = 0
    for i in range(20):
        sources.append(at)
        at += 1000 + (10 if i < 15 else 4000 if i == 15 else 20_000)
    requests = _requests(sources, lengths, 0.05, 1 << 30)
    assert [(first, last) for _, _, first, last, _ in requests] == [(0, 16), (16, 17), (17, 18), (18, 19), (19, 20)], "the small gaps go, the 4 000 and the 20 000 byte ones do not fit the 1 000 bytes of the budget"
    assert requests[0][0] == 0 and requests[0][1] == sources[15] + 1000 and [r[4] for r in requests] == [0, 16000, 17000, 18000, 19000], "the place of each piece in the new data is the sum of the lengths before it"
    assert [(f, la) for _, _, f, la, _ in _requests(sources, lengths, 0.0, 1 << 30)][:2] == [(0, 1), (1, 2)], "no overfetch: no gap is taken"
    assert len(_requests(array.array("Q", [0, 1000, 2000]), array.array("I", [1000] * 3), 0.0, 2500)) == 2, "a request is at most the longest it may be"


# ---- servers that lie, fail or stand still

async def cut_from(server_url: str, tmp_path: Path, **options: object) -> object:
    return await asyncio.to_thread(Cutting(server_url, tmp_path / "out.pmtiles", BOX, 6, pauses=NOW, **options).run)       # type: ignore[arg-type]


async def test_a_cut_from_a_server_is_the_same_as_the_cut_from_a_file(tmp_path: Path) -> None:
    server = await range_server(planet())
    await cut_from(server.url, tmp_path)
    assert every_tile((tmp_path / "out.pmtiles").read_bytes()) == expected(planet(), BOX, 6) and not part_of(tmp_path / "out.pmtiles").exists()
    assert all(0 <= first <= last < len(planet()) for first, last in server.asked)


async def test_a_request_that_is_cut_short_or_answered_busy_is_made_again(tmp_path: Path) -> None:
    server = await range_server(planet())
    server.cut, server.busy = 2, 1
    await cut_from(server.url, tmp_path)
    assert every_tile((tmp_path / "out.pmtiles").read_bytes()) == expected(planet(), BOX, 6)
    assert server.cut == 0 and server.busy == 0 and server.cuts == 4, "the header was asked for three times in vain"


async def test_a_server_that_does_not_answer_is_told_as_unreachable_after_four_tries(tmp_path: Path) -> None:
    server = await range_server(planet())
    server.busy = 1000
    with pytest.raises(CutError, match="could not be reached"):
        await cut_from(server.url, tmp_path)
    assert server.cuts == 4 and not list(tmp_path.glob("out*"))


@pytest.mark.parametrize(("mode", "says"), [("whole", "200 to a range request and not 206"), ("wrong", "answered bytes"), ("missing", "answered 404 Not Found")])
async def test_a_server_that_cannot_give_ranges_is_refused_at_once(tmp_path: Path, mode: str, says: str) -> None:
    server = await range_server(planet())
    server.mode = mode
    with pytest.raises(CutError, match=says):
        await cut_from(server.url, tmp_path)
    assert server.cuts == 1, "not tried again"
    assert not list(tmp_path.glob("out*"))


async def test_an_archive_that_changes_while_it_is_read_is_refused() -> None:
    server = await range_server(planet())
    source = HttpSource(server.url, Halt(), NOW)
    await asyncio.to_thread(source.copy, 0, 127, lambda at, piece: None)
    server.data = planet() + b"more"
    with pytest.raises(CutError, match="changed while it was cut"):
        await asyncio.to_thread(source.copy, 127, 10, lambda at, piece: None)


async def test_a_stop_ends_a_cut_that_waits_for_a_server_and_removes_the_part(tmp_path: Path) -> None:
    server = await range_server(planet())
    server.hold_from = data_offset(planet())
    cutting = Cutting(server.url, tmp_path / "out.pmtiles", None, 6, pauses=NOW)
    work = asyncio.ensure_future(asyncio.to_thread(cutting.run))
    await until_started(lambda: server.holding > 0 and part_of(tmp_path / "out.pmtiles").exists())
    cutting.stop()
    with pytest.raises(CutError, match=STOPPED):
        await work
    await until_started(lambda: server.holding == 0)
    assert not list(tmp_path.glob("out*"))


async def test_a_stop_while_the_server_has_not_begun_to_answer_ends_the_cut_at_once(tmp_path: Path) -> None:
    """The header is read on a thread the stop does not wait for: the cut ends while the connection is still open, not when it times out."""
    server = await range_server(planet())
    server.mode = "mute"
    cutting = Cutting(server.url, tmp_path / "out.pmtiles", None, 6, pauses=NOW)
    work = asyncio.ensure_future(asyncio.to_thread(cutting.run))
    await until_started(lambda: server.holding > 0)
    cutting.stop()
    with pytest.raises(CutError, match=STOPPED):
        await work
    assert server.holding == 1, "the request that waits for its answer is still open: the cut did not wait for it"
    server.release.set()
    await until_started(lambda: server.holding == 0 and not [t for t in threading.enumerate() if t.name == "map-cut"])
    assert not list(tmp_path.glob("out*"))


async def test_the_size_told_grows_to_the_size_of_the_archive(tmp_path: Path) -> None:
    server = await range_server(planet())
    sizes: list[int] = []
    cut = await extract(server.url, tmp_path / "out.pmtiles", BOX, 6, on_size=sizes.append)
    await asyncio.sleep(0)
    assert sizes == sorted(sizes) and sizes[0] == data_offset((tmp_path / "out.pmtiles").read_bytes()) and sizes[-1] == cut.bytes == (tmp_path / "out.pmtiles").stat().st_size


async def test_a_stop_before_the_start_cuts_nothing(tmp_path: Path) -> None:
    server = await range_server(planet())
    cutting = Cutting(server.url, tmp_path / "out.pmtiles", None, 6)
    cutting.stop()
    with pytest.raises(CutError, match=STOPPED):
        cutting.run()
    assert server.asked == [] and not list(tmp_path.glob("out*"))


async def test_a_task_that_is_cancelled_stops_the_cut_and_waits_for_its_thread(tmp_path: Path) -> None:
    server = await range_server(planet())
    server.hold_from = data_offset(planet())
    task = asyncio.ensure_future(extract(server.url, tmp_path / "out.pmtiles", None, 6))
    await until_started(lambda: server.holding > 0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await until_started(lambda: server.holding == 0 and not [t for t in threading.enumerate() if t.name == "map-cut"])
    assert not list(tmp_path.glob("out*"))
