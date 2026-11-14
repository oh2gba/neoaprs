"""The radio an email goes out on (neoaprs/emailrule.py, plan rule 3.5): the main radio while internet gateways hear its type, else the first enabled radio by position that they hear, else none; with the
two radios of today exactly what it was (the FM radio while it is on, else none); a radio of a type that is not known, one that is off and one that is removed are heard by no gateway. Then the registry and
the services: a mail goes on that radio, and is refused with its reason while there is none."""
import itertools
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from neoaprs.config import DEFAULTS
from neoaprs.emailrule import email_radio, gateway_heard
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.radiospec import RadioSpec, main_radio
from neoaprs.radiotype import FM_ID, HF_ID, Kind
from neoaprs.services.messageradio import station_radio
from tests.support.rig import ServiceRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.stubtnc import StubTnc

GONE = datetime(2026, 11, 1, tzinfo=UTC)


def radio(id: int, kind: Kind = "fm", position: int | None = None, enabled: bool = True, type: str | None = None, removed: bool = False) -> RadioSpec:
    return RadioSpec(id, kind, type or {"fm": "kiss", "hf": "mercury", "lora": "dummy-lora"}[kind], "", enabled, id if position is None else position, GONE if removed else None)


@pytest.mark.parametrize(("fm_on", "hf_on"), list(itertools.product((True, False), (True, False))))
def test_with_the_two_radios_of_today_it_is_the_fm_radio_while_it_is_on_else_none(fm_on: bool, hf_on: bool) -> None:
    config = replace(DEFAULTS, fm_enabled=fm_on, hf_enabled=hf_on)
    assert email_radio(config.radios, config.main_radio) == (FM_ID if fm_on else None), "a mail never goes over HF"


@pytest.mark.parametrize(("specs", "chosen", "expected", "why"), [
    ((radio(1), radio(2, "hf")), None, 1, "the main radio, the FM one, which gateways hear"),
    ((radio(1, position=2), radio(2, "hf", position=1)), None, 1, "the main radio is HF (first by position): the first one that gateways hear"),
    ((radio(1), radio(2, "hf")), HF_ID, 1, "the main radio chosen is HF: the first one that gateways hear"),
    ((radio(1, enabled=False), radio(2, "hf"), radio(3)), None, 3, "radio 1 off: another FM radio that is on"),
    ((radio(1), radio(2, "hf"), radio(3, position=0)), None, 3, "the main radio, the first by position, is an FM radio: it, not radio 1"),
    ((radio(1), radio(3)), 3, 3, "the main radio chosen, which gateways hear"),
    ((radio(1, enabled=False), radio(2, "hf")), None, None, "no radio that gateways hear is on: none"),
    ((radio(1, type="no-such-type"), radio(2, "hf")), None, None, "a radio of a type that is not known is heard by none"),
    ((radio(1, removed=True), radio(2, "hf"), radio(3, enabled=False)), None, None, "removed or off: none"),
    ((radio(1, type="dummy"), radio(2, "hf")), None, 1, "the Dummy FM radio is an FM radio here as well"),
    ((), None, None, "no radio at all"),
])
def test_the_main_radio_while_gateways_hear_it_else_the_first_on_that_they_hear_else_none(specs: tuple[RadioSpec, ...], chosen: int | None, expected: int | None, why: str) -> None:
    assert email_radio(specs, main_radio(specs, chosen)) == expected, why


def test_what_gateways_hear_is_the_types_own() -> None:
    assert (gateway_heard(radio(1)), gateway_heard(radio(1, type="kiss-tcp")), gateway_heard(radio(2, "hf")), gateway_heard(radio(2, "hf", type="dummy-hf"))) == (True, True, False, False)
    assert not gateway_heard(radio(1, type="no-such-type"))


# ---- the services: a mail goes on the email radio, none is a refusal with its reason

class Rig(ServiceRig):
    """The station's radios as the registry gives them over stub lines: `specs`, each on a line of its own (`lines`), the registry's email radio by the rule."""

    def __init__(self, specs: tuple[RadioSpec, ...]) -> None:
        super().__init__()
        self.lines = {spec.id: StubTnc() for spec in specs}
        self.radios = Registry([LiveShape(spec, specs, self.lines[spec.id]) for spec in specs])     # type: ignore[arg-type]


class Registry(RegistryShape):
    def email(self) -> LiveShape | None:
        specs = [r.spec for r in self.radios]
        return self.get(found) if (found := email_radio(specs, main_radio(specs, None))) is not None else None


def test_a_mail_goes_on_the_email_radio_and_is_refused_with_its_reason_while_there_is_none() -> None:
    rig = Rig((radio(1, enabled=False), radio(2, "hf"), radio(3)))
    assert station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY).id == 3, "radio 1 off: the other FM radio carries it"
    rig = Rig((radio(1, enabled=False), radio(2, "hf")))
    with pytest.raises(MessagingError) as refused:
        station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY)
    assert refused.value.code == "message.email_fm_off", "the refusal of today (its words and code are the page's until wave 4)"
