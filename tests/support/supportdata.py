"""A data folder for the tests of the support bundle: a migrated database with settings (an access key among them) and a few packets, and logs of the sizes a test asks for.

    data = fake_folder(tmp_path)                    # tmp_path/data with neoaprs.sqlite, neoaprs.log and neoaprs-app.log
    fake_folder(tmp_path, app_log=False)            # no app log
    zip_members(path)                               # {name: text} of a bundle
"""
import zipfile
from pathlib import Path

from neoaprs import aprsparse, ax25
from neoaprs.clock import utc
from neoaprs.kiss import KissDecoder
from neoaprs.packet import Packet, Undecoded
from neoaprs.packetcodec import packet_row
from neoaprs.packetsql import insert_packet
from neoaprs.store import DB_NAME
from neoaprs.storesql import write_settings
from tests.support.files import fixture_bytes
from tests.support.migrated import opened

KEY = "k7m2-x9pq-4hrt"
SETTINGS = {"station/call": "OH2GBA", "station/lat": "60.17", "station/lon": "24.94", "tnc/profile": "kenwood-tnc2", "beacon/interval_min": "60", "web/key": KEY, "web/network": "true",
            "beacon/last_sent_at": "2026-10-21T11:00:00.000000Z", "ui/theme": "dark"}
T0 = utc(2026, 10, 21, 12, 0, 0)


def log_line(second: int, level: str, text: str) -> str:
    return f"2026-10-21 12:{second // 60:02d}:{second % 60:02d}Z  {level}  {text}\n"


def packets(count: int) -> list[Packet]:
    out: list[Packet] = []
    for frame in KissDecoder().feed(fixture_bytes("kiss/thd7-2026-10-21.bin")):
        f = ax25.decode(frame.payload)
        source, destination = str(f.source), str(f.destination)
        out.append(Packet(T0, "in", frame.payload, source, destination, tuple(str(a) for a in f.path), f.info, aprsparse.parse(f.info, source, destination, T0)))
    return out[:count]


def fake_folder(tmp_path: Path, packet_count: int = 5, undecoded: int = 2, settings: dict[str, str] | None = None, app_log: bool = True, log_lines: int = 40) -> Path:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    s = opened(data / DB_NAME)
    try:
        write_settings(s.db, SETTINGS if settings is None else settings)
        for packet in packets(packet_count):
            insert_packet(s.db, packet_row(packet))
        base = packets(1)[0]
        for n in range(undecoded):
            bad = Packet(T0, "in", base.raw, base.source, base.destination, base.path, base.info, Undecoded(f"too short {n}", "!60"))
            insert_packet(s.db, packet_row(bad))
    finally:
        s.close()
    lines = [log_line(0, "INFO", "NeoAPRS 0.9.0 starting, data in " + str(data))]
    lines += [log_line(n, "WARNING" if n % 7 == 0 else "INFO", f"line {n} of the log") for n in range(1, log_lines)]
    (data / "neoaprs.log").write_text("".join(lines), encoding="utf-8")
    if app_log:
        (data / "neoaprs-app.log").write_text("2026-10-21 14:00:00  INFO  NeoAPRS app on the data folder\n", encoding="utf-8")
    return data


def zip_members(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as bundle:
        return {name: bundle.read(name).decode("utf-8") for name in bundle.namelist()}
