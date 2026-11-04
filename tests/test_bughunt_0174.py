"""Failing tests of suspected bugs in 0.17.x (the bug hunt of 4 Nov 2026, v0.16.0..v0.17.4). Each test asserts what the operator should get; it fails on v0.17.4. Not for merging as it is: each goes
with its fix, into the test file of its part."""
import json
from dataclasses import replace

from neoaprs import mercury
from neoaprs.config import DEFAULTS, MESSAGE_RADIOS
from neoaprs.radios import Radios
from neoaprs.station import Station
from neoaprs.stationbook import StationBook
from neoaprs.clock import utc

T0 = utc(2026, 11, 4, 7, 30)
BOTH = replace(DEFAULTS, fm_enabled=True, hf_enabled=True)

# Windows numbers a second device of the same name per kind ("2- USB Audio CODEC"), each kind on its own: a radio once plugged into another USB port, or a second radio with the same codec, leaves the
# playing and the recording device of one card with different prefixes.
WINDOWS_PREFIXED = ("playback devices:\n"
                    "device: name: 'Speakers (Realtek High Definition Audio)'  id: '{0.0.0.00000000}.{aaaa}'  (system default)\n"
                    "device: name: 'Speakers (2- USB Audio CODEC)'  id: '{0.0.0.00000000}.{ca03}'\n"
                    "device: name: 'Headphones (Realtek High Definition Audio)'  id: '{0.0.0.00000000}.{bbbb}'\n"
                    "capture devices:\n"
                    "device: name: 'Microphone (USB Audio CODEC)'  id: '{0.0.1.00000000}.{2301}'\n"
                    "device: name: 'Microphone (Realtek High Definition Audio)'  id: '{0.0.1.00000000}.{cccc}'  (system default)\n")


def test_a_windows_radio_whose_two_devices_carry_different_numbers_is_still_one_card_and_the_one_chosen() -> None:
    cards = mercury.parse_sound_cards(WINDOWS_PREFIXED)
    radio = [c for c in cards if "USB Audio CODEC" in c.name]
    assert len(radio) == 1 and radio[0].playback and radio[0].capture, f"the radio's two devices are one card: {[(c.name, c.id) for c in cards]}"
    assert mercury.choose_sound_card(cards) == radio[0].id, f"chosen instead: {mercury.choose_sound_card(cards)!r} (the computer's own headphones and microphone)"


def _book() -> StationBook:
    book = StationBook()
    book.seed([Station("OH2GAX-2", first_heard=T0, last_heard=T0, heard_fm=40, heard_hf=21)])
    return book


def test_a_forgotten_station_does_not_get_its_old_radio_back_at_the_next_restart() -> None:
    rows: dict[str, str] = {}
    book = _book()
    r = Radios(object(), object(), lambda: BOTH, book, lambda text: rows.update({MESSAGE_RADIOS: text}))          # type: ignore[arg-type]
    assert r.choose("OH2GAX-2", "hf")
    assert book.forget("OH2GAX-2"), "the operator forgets the station (Forget on its card)"
    book.seed([Station("OH2GAX-2", first_heard=T0, last_heard=T0, heard_fm=1)])                           # heard again: a station of no choice, messaged on FM
    assert book.get("OH2GAX-2").message_radio == ""                                                        # type: ignore[union-attr]
    again = _book()                                                                                       # the daemon restarted: the book seeded from the packets, the choices from the row
    Radios(object(), object(), lambda: BOTH, again, lambda text: None).restore(rows.get(MESSAGE_RADIOS))   # type: ignore[arg-type]
    assert again.get("OH2GAX-2").message_radio == "", f"the row still says {json.loads(rows[MESSAGE_RADIOS])}: the forgotten choice is back after the restart"     # type: ignore[union-attr]
