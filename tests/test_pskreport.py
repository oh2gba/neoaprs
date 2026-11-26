"""The datagrams of PSK Reporter's upload protocol (neoaprs/pskreport.py), byte for byte against the
example of pskdev.html and against cases checked by hand."""

import re

import pytest

from neoaprs import pskreport
from neoaprs.aprslocator import grid_centre, grid_of
from neoaprs.pskreport import Receiver, Report, Template
from tests.support.files import fixture_text
from tests.support.pskdecode import Collector
from tests.test_scripts import load_script


def example() -> bytes:
    lines = [line for line in fixture_text("pskreporter/example-datagram.txt").splitlines() if not line.startswith("#")]
    return bytes.fromhex(" ".join(lines))


def test_the_example_datagram_of_pskdev_is_made_byte_for_byte() -> None:
    receiver = Receiver("N1DQ", "FN42hn", "Homebrew v5.6")
    reports = [
        Report("N1DQ", 14070567, 1200960084, mode="PSK"),
        Report("KB1MBX", 14070987, 1200960104, mode="PSK"),
    ]
    page = Template(0x9993, pskreport.SENDER.fields)  # (the page's first sender option, under its id)
    made = pskreport.datagram(1200960114, 1, 0, receiver, reports, (pskreport.RECEIVER, page), (page,))
    assert made == example() and len(made) == 172


def test_the_four_sender_templates_by_what_a_report_carries() -> None:
    assert pskreport.template_for(Report("OH2A", 1, 0)) is pskreport.SENDER
    assert pskreport.template_for(Report("OH2A", 1, 0, locator="KP20le")) is pskreport.SENDER_WITH_LOCATOR
    assert pskreport.template_for(Report("OH2A", 1, 0, snr=-3)) is pskreport.SENDER_WITH_SNR
    assert pskreport.template_for(Report("OH2A", 1, 0, locator="KP20le", snr=4)) is pskreport.SENDER_WITH_BOTH
    assert [t.id for t in pskreport.TEMPLATES] == [0x9992, 0x9A01, 0x9A02, 0x9A03, 0x9A04]


def test_the_templates_of_pskdev_are_its_bytes() -> None:
    receiver = (
        "00 03 00 24 99 92 00 03 00 01 80 02 FF FF 00 00 76 8F 80 04 FF FF 00 00 76 8F 80 08 FF FF 00 00 76 8F 00 00"
    )
    with_locator = (
        "00 02 00 34 9A 02 00 06 80 01 FF FF 00 00 76 8F 80 05 00 04 00 00 76 8F 80 0A FF FF 00 00 76 8F"
        " 80 0B 00 01 00 00 76 8F 80 03 FF FF 00 00 76 8F 00 96 00 04"
    )
    assert pskreport.template_set(pskreport.RECEIVER) == bytes.fromhex(receiver)
    # (the page's second sender option, under an id of its own)
    assert pskreport.template_set(pskreport.SENDER_WITH_LOCATOR) == bytes.fromhex(with_locator)
    # the page's sNR templates without its iMD
    assert pskreport.template_set(pskreport.SENDER_WITH_BOTH) == bytes.fromhex(
        "00 02 00 3C 9A 04 00 07 80 01 FF FF 00 00 76 8F 80 05 00 04 00 00 76 8F 80 06 00 01 00 00 76 8F"
        " 80 0A FF FF 00 00 76 8F 80 0B 00 01 00 00 76 8F 80 03 FF FF 00 00 76 8F 00 96 00 04"
    )


def test_a_record_with_a_locator_and_a_negative_snr_by_hand() -> None:
    report = Report("OH2A", 28180000, 1795000000, locator="KP20le", snr=-12)
    assert pskreport.record(report) == bytes.fromhex(
        "04 4F 48 32 41  01 AD FE 20  F4  07 4E 45 4F 41 50 52 53  01  06 4B 50 32 30 6C 65  6A FD 86 C0"
    )


def test_a_record_without_locator_or_snr_by_hand() -> None:
    assert pskreport.record(Report("OH2A", 7050000, 1795000000)) == bytes.fromhex(
        "04 4F 48 32 41  00 6B 93 10  07 4E 45 4F 41 50 52 53  01  6A FD 86 C0"
    )


@pytest.mark.parametrize(("snr", "byte"), [(200, 0x7F), (-200, 0x80), (0, 0x00), (127, 0x7F)])
def test_the_snr_is_clamped_to_a_signed_byte(snr: int, byte: int) -> None:
    assert pskreport.record(Report("OH2A", 7050000, 0, snr=snr))[9] == byte


@pytest.mark.parametrize("call", ["ÖH2A", "OH2A​"])
def test_text_that_is_not_ascii_is_refused(call: str) -> None:
    with pytest.raises(ValueError):
        pskreport.record(Report(call, 7050000, 0))
    with pytest.raises(ValueError):
        pskreport.receiver_set(Receiver(call, "KP20le", "NeoAPRS 0.24.0"))


def test_every_set_is_padded_to_four_and_the_header_has_the_whole_length() -> None:
    receiver = Receiver("OH2GBA", "KP20le", "NeoAPRS 0.24.0")
    reports = [Report("OH2A", 28180000, 1795000000, "KP20le", 3), Report("OH2BCD", 28180000, 1795000001)]
    made = pskreport.datagram(1795000100, 7, 0xDEADBEEF, receiver, reports, pskreport.TEMPLATES)
    assert len(made) % 4 == 0 and int.from_bytes(made[2:4], "big") == len(made)
    read = Collector().read(made)
    assert (read.sent_at, read.sequence, read.session) == (1795000100, 7, 0xDEADBEEF)
    assert read.templates == [t.id for t in pskreport.TEMPLATES]
    assert read.receivers == [
        {"receiverCallsign": "OH2GBA", "receiverLocator": "KP20le", "decodingSoftware": "NeoAPRS 0.24.0"}
    ]
    assert read.senders == [
        {
            "senderCallsign": "OH2BCD",
            "frequency": 28180000,
            "mode": "NEOAPRS",
            "informationSource": 1,
            "flowStartSeconds": 1795000001,
        },
        {
            "senderCallsign": "OH2A",
            "frequency": 28180000,
            "sNR": 3,
            "mode": "NEOAPRS",
            "informationSource": 1,
            "senderLocator": "KP20le",
            "flowStartSeconds": 1795000000,
        },
    ]


def test_a_full_datagram_stays_within_1200_bytes_and_says_how_many_fit() -> None:
    receiver = Receiver("OH2GBA", "KP20le", "NeoAPRS 0.24.0")
    reports = [Report(f"OH{i % 10}A{i:02d}", 28180000, 1795000000 + i, "KP20le", i % 20 - 10) for i in range(100)]
    for templates in ((), pskreport.TEMPLATES):
        count = pskreport.fitting(receiver, reports, templates)
        assert 10 < count < 100
        assert len(pskreport.datagram(0, 0, 0, receiver, reports[:count], templates)) <= pskreport.MAX_DATAGRAM
        assert len(pskreport.datagram(0, 0, 0, receiver, reports[: count + 1], templates)) > pskreport.MAX_DATAGRAM


@pytest.mark.parametrize(
    ("lat", "lon", "grid"),
    [(60.17, 24.94, "KP20le"), (42.35, -71.06, "FN42li"), (-33.87, 151.21, "QF56od"), (0.0, 0.0, "JJ00aa")],
)
def test_a_position_as_a_six_character_locator(lat: float, lon: float, grid: str) -> None:
    assert grid_of(lat, lon) == grid
    centre = grid_centre(grid)
    assert abs(centre[0] - lat) < 1 / 24 and abs(centre[1] - lon) < 1 / 12


def test_the_edges_of_the_world_are_still_a_locator() -> None:
    for lat, lon in ((90.0, 180.0), (-90.0, -180.0), (89.999, 179.999)):
        assert re.fullmatch(r"[A-R]{2}\d\d[a-x]{2}", grid_of(lat, lon))


def test_the_probe_prints_the_datagram_it_would_send_and_sends_nothing_on_a_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = load_script("pskreporter-probe")
    args = ["127.0.0.1:9", "--call", "oh2gba", "--locator", "KP20le", "--dial", "28.1800 MHz USB", "--dry-run"]
    assert probe.main([*args, "--heard", "OH2ABC/KP20le/-7", "--heard", "OH2DEF"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].endswith("2 reports, not sent")
    read = Collector().read(bytes.fromhex(" ".join(lines[:-1])))
    assert read.receivers[0]["receiverCallsign"] == "OH2GBA" and read.templates == [t.id for t in pskreport.TEMPLATES]
    assert [(s["senderCallsign"], s.get("senderLocator"), s.get("sNR")) for s in read.senders] == [
        ("OH2DEF", None, None),
        ("OH2ABC", "KP20le", -7),
    ]
