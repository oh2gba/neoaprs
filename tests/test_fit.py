"""The one fit function (services/radioset.py `fit`, plan §2) on radios of the types as a test writes them (tests/support/seamshapes.py): the path is dropped on a radio that may carry none, the radio's own path is
taken when none is given (the recommended path of the station's symbol when it is empty, none for DIRECT), the comment is cut to the 123 bytes of the Mercury radio and the report itself never, a radio with a frame cap
and a path cuts the comment by what the path takes too, and what makes no frame is a SendError. The sender builds every frame of ours by it, for the radio it goes on."""
import logging
from dataclasses import replace

import pytest

from neoaprs import ax25
from neoaprs.config import DEFAULTS, Config
from neoaprs.radiospec import log_name
from neoaprs.radiotype import FM_ID, HF_ID
from neoaprs.services.radioset import NO_RADIO, SendError, fit, fixed_prefix
from neoaprs.services.sender import Sender
from tests.support.seamshapes import FrozenAir, RegistryShape, frozen_air

STATION: Config = replace(DEFAULTS, station_call="OH2GBA", station_lat=60.17, station_lon=24.94, beacon_path="WIDE1-1,WIDE2-1", hf_enabled=True)
POSITION = b"!6010.20N/02456.40E-"
LONG = POSITION + b"a comment that is long enough to be cut on the HF radio, " * 3


def radio(config: Config, id: int) -> FrozenAir:
    """The station's radio of the id, named as the registry names it (radiospec.log_name)."""
    spec = config.radio(id)
    assert spec is not None
    return replace(frozen_air(spec), name=log_name(spec, config.radios))


def capped(air: FrozenAir, max_frame: int) -> FrozenAir:
    """The radio with a frame cap of its own, whatever its type carries."""
    return replace(air, limits=replace(air.limits, max_frame=max_frame))


# ---- the path

def test_a_radio_that_may_carry_no_path_sends_every_frame_direct_whatever_path_is_asked() -> None:
    hf = radio(STATION, HF_ID)
    assert not hf.allowed.paths
    for path in (None, (), ("WIDE1-1",), ("OH2RCH-2", "WIDE2-1")):
        assert fit(hf, STATION, b">status", path).path == (), path


def test_the_fm_radio_takes_the_path_given_and_its_own_when_none_is() -> None:
    fm = radio(STATION, FM_ID)
    assert fit(fm, STATION, b">status", ("OH2RCH-2",)).path_text == "OH2RCH-2"
    assert fit(fm, STATION, b">status", ()).path == (), "an empty path given is no digipeater"
    assert fit(fm, STATION, b">status", None).path_text == "WIDE1-1,WIDE2-1", "the radio's own path: beacon/path of the FM radio"


@pytest.mark.parametrize(("beacon_path", "table", "code", "expected"), [("", "/", "-", "WIDE2-2"), ("", "/", ">", "WIDE1-1,WIDE2-1"), ("DIRECT", "/", ">", ""), ("OH2RCH-2,WIDE2-1", "/", "-", "OH2RCH-2,WIDE2-1")])
def test_the_radios_own_path_when_empty_is_the_recommended_one_of_the_stations_symbol_and_direct_is_none(beacon_path: str, table: str, code: str, expected: str) -> None:
    config = replace(STATION, beacon_path=beacon_path, station_symbol_table=table, station_symbol_code=code)
    frame = fit(radio(config, FM_ID), config, b">status", None)
    assert frame.path_text == expected and frame.path == tuple(ax25.Address.parse(c) for c in config.beacon_path_calls), "the same as the station's beacon/path of today"


# ---- the frame's size

def test_on_the_hf_radio_the_comment_is_cut_to_123_bytes_the_report_is_kept_and_the_log_says_so_with_the_radios_name(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.radioset")
    hf = radio(STATION, HF_ID)
    frame = fit(hf, STATION, LONG, None)
    assert hf.max_frame == 123 and len(ax25.encode(frame)) == 123 and frame.path == ()
    assert frame.info == LONG[:len(frame.info)] and len(frame.info) > fixed_prefix(LONG), "the end of the comment is cut, the position is whole"
    over = len(ax25.encode(replace(frame, info=LONG))) - 123
    assert [r.getMessage() for r in caplog.records] == [f"Mercury: a frame of ours is {over} bytes more than the radio carries (123): its comment is cut: {frame.tnc2()}"]


def test_a_radio_with_a_cap_and_a_path_cuts_the_comment_by_what_the_path_takes_too() -> None:
    fm = capped(radio(STATION, FM_ID), 123)
    with_path, direct = fit(fm, STATION, LONG, ("WIDE1-1", "WIDE2-1")), fit(fm, STATION, LONG, ())
    assert with_path.path_text == "WIDE1-1,WIDE2-1" and len(ax25.encode(with_path)) == len(ax25.encode(direct)) == 123
    assert len(direct.info) - len(with_path.info) == 2 * 7, "two digipeaters are 14 bytes of the frame, taken from the comment"


def test_a_frame_that_fits_and_a_radio_without_a_cap_send_the_frame_whole(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, "neoaprs.radioset")
    fm = radio(STATION, FM_ID)
    assert fm.max_frame is None and fit(fm, STATION, LONG, None).info == LONG
    assert fit(radio(STATION, HF_ID), STATION, POSITION + b"short", None).info == POSITION + b"short"
    assert caplog.records == [], "nothing was cut, nothing is said"


# ---- what makes no frame

def test_what_makes_no_frame_is_a_send_error() -> None:
    fm, hf = radio(STATION, FM_ID), radio(STATION, HF_ID)
    with pytest.raises(SendError, match="more than the 256"):
        fit(fm, STATION, b"x" * (ax25.MAX_INFO + 1), None)
    with pytest.raises(SendError, match="not enough"):
        fit(hf, STATION, b"T#005," + b"1," * 60, None)                          # (telemetry has no comment to cut)
    with pytest.raises(SendError):
        fit(fm, STATION, b">x", tuple(["WIDE1-1"] * 9))                         # (more than the 8 digipeaters of AX.25)
    with pytest.raises(SendError):
        fit(fm, replace(STATION, station_call="not a call"), b">x", None)


# ---- the sender builds its frames by it

def test_the_senders_frame_is_the_fit_for_its_radio_and_the_first_that_can_send_when_none_is_named() -> None:
    fm, hf = radio(STATION, FM_ID), radio(STATION, HF_ID)
    sender = Sender(RegistryShape([fm, hf]), lambda: STATION)              # type: ignore[list-item]
    for air in (fm, hf):
        assert sender.frame(LONG, None, air) == fit(air, STATION, LONG, None)
        assert sender.frame(LONG, ("OH2RCH-2",), air) == fit(air, STATION, LONG, ("OH2RCH-2",))
    assert sender.frame(LONG, None) == fit(fm, STATION, LONG, None), "the first radio that can send, the FM radio"
    only_hf = replace(STATION, fm_enabled=False)
    assert Sender(RegistryShape([radio(only_hf, FM_ID), radio(only_hf, HF_ID)]), lambda: only_hf).frame(LONG, None).path == ()      # type: ignore[list-item]


def test_without_a_radio_the_sender_makes_no_frame_and_sends_nothing() -> None:
    sender = Sender(RegistryShape([]), lambda: STATION)
    with pytest.raises(SendError, match=NO_RADIO):
        sender.frame(b">x", None)
    assert not sender.send(b">x", None) and sender.problem == NO_RADIO
    assert not sender.ready("bulletin") and sender.problem == NO_RADIO
