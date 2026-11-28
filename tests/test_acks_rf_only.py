"""An ack that should go RF only but whose path has no room for RFONLY (neoaprs/services/acks.py): it
goes without it, and the log says so once for the message."""

import logging
from dataclasses import replace

import pytest

from neoaprs import ax25
from neoaprs.config import Config
from neoaprs.interlock import Interlock
from neoaprs.services.acks import Acks
from neoaprs.services.common import our_frame

from tests.support.stubtnc import StubTnc
from tests.test_messaging import LineAir, StubPick

FULL = tuple(ax25.Address.parse(f"OH2RC{n}") for n in range(ax25.MAX_PATH))


def test_an_ack_with_no_room_for_rfonly_goes_without_it_and_the_log_says_so_once_a_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = Config.from_data({"station/call": "OH2GBA"})
    tnc = StubTnc()
    pick = StubPick([LineAir(tnc, lambda: config)])
    acks = Acks(
        lambda: pick, Interlock(lambda: config), lambda info, to, radio: replace(our_frame(config, (), info), path=FULL)
    )  # type: ignore[arg-type]
    with caplog.at_level(logging.INFO, logger="neoaprs.messaging"):
        for msg_id in ("12", "12", "13"):
            acks.send("OH2ABC", msg_id, rf_only=True)
    assert [f.path_text for f in tnc.sent] == [",".join(str(a) for a in FULL)] * 3
    said = [r.getMessage() for r in caplog.records if "RFONLY" in r.getMessage()]
    assert len(said) == 2 and all(r.levelno == logging.INFO for r in caplog.records if "RFONLY" in r.getMessage())
    assert "12" in said[0] and "13" in said[1]
