"""Failing tests of suspected bugs in Send feedback / logs of 0.17.x (the bug hunt of 4 Nov 2026). Each fails on v0.17.4; not for merging as it is."""
import json
import sys

import pytest

from neoaprs.mercuryhelper import list_sound_cards
from neoaprs.web import supportstate
from tests.test_support_send import PAGE, lan, send, served  # noqa: F401


def test_a_sound_card_list_the_locale_cannot_decode_is_no_failure() -> None:
    cards = list_sound_cards([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b\"capture devices:\\ndevice: name: '\\xff\\xfe'  id: 'plughw:1,0'\\n\")"])
    assert isinstance(cards, list)


@pytest.mark.expects_errors
async def test_a_note_with_a_lone_surrogate_is_sent_not_told_offline(tmp_path, monkeypatch) -> None:          # type: ignore[no-untyped-def]
    e, fake = await served(tmp_path, monkeypatch)
    code, answer = await send(e, body='{"page": %s, "note": "hi \\ud83d"}' % json.dumps(PAGE))
    assert answer.get("reason") != "offline" and fake.requests, f"{code} {answer}: nothing reached the server, and the operator is told there is no internet"


@pytest.mark.expects_errors
async def test_the_logs_are_sent_when_the_sound_cards_cannot_be_listed(tmp_path, monkeypatch) -> None:           # type: ignore[no-untyped-def]
    e, fake = await served(tmp_path, monkeypatch)
    monkeypatch.setattr(supportstate, "hf_is_mercury", lambda c: True)

    def undecodable() -> list[object]:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    monkeypatch.setattr(e.ctl.mercury, "sound_cards", undecodable)
    code, answer = await send(e)
    assert code != 500 and fake.requests, f"{code} {answer}: the whole bundle failed for a nice-to-have"
