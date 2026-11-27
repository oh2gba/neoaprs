"""Tests for the radio an email goes out on (neoaprs/emailrule.py): the only radio that can send,
else the operator's choice (`email/radio`) while it can send, else the first radio that can send.
Also the registry and services: a mail goes out once and is refused only when no radio can send."""

import itertools
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from neoaprs import ax25
from neoaprs.config import DEFAULTS
from neoaprs.emailrule import email_radio, gateway_heard
from neoaprs.message import EMAIL_GATEWAY, MessagingError
from neoaprs.radiospec import RadioSpec, senders
from neoaprs.radiotype import FM_ID, HF_ID, Kind, RadioTypeError
from neoaprs.services.messageradio import station_radio
from neoaprs.services.radioset import ack_radio
from tests.support.clock import FixedClock
from tests.support.env import Env, idle_for, until, until_started
from tests.support.rig import ServiceRig
from tests.support.seamshapes import LiveShape, RegistryShape
from tests.support.stubtnc import StubTnc
from tests.support.wireworld import heard

GONE = datetime(2026, 11, 1, tzinfo=UTC)


def radio(
    id: int,
    kind: Kind = "fm",
    position: int | None = None,
    enabled: bool = True,
    type: str | None = None,
    removed: bool = False,
) -> RadioSpec:
    return RadioSpec(
        id,
        kind,
        type or {"fm": "kiss", "hf": "mercury", "lora": "dummy-lora"}[kind],
        "",
        enabled,
        id if position is None else position,
        GONE if removed else None,
    )


def heard_0_20_1(spec: RadioSpec) -> bool:
    """The previous rule's `emailrule.gateway_heard`, copied."""
    try:
        return spec.rtype.allowed.gateway_heard
    except RadioTypeError:
        return False


def as_0_20_1(specs: tuple[RadioSpec, ...], main_choice: int | None) -> int | None:
    """The previous rule, copied: the main radio (the chosen one while it is on and can send, else
    the first such by position) while internet gateways hear it, else the first enabled radio by
    position that they hear, else none (a mail was refused)."""
    heard = [spec.id for spec in senders(specs) if heard_0_20_1(spec)]
    on = [spec.id for spec in senders(specs)]
    main = main_choice if main_choice in on else on[0] if on else None
    if main is not None and main in heard:
        return main
    return heard[0] if heard else None


@pytest.mark.parametrize(("fm_on", "hf_on"), list(itertools.product((True, False), (True, False))))
def test_with_the_two_radios_of_today_it_is_the_fm_radio_while_it_is_on_and_the_mercury_radio_alone_carries_it_too(
    fm_on: bool, hf_on: bool
) -> None:
    config = replace(DEFAULTS, fm_enabled=fm_on, hf_enabled=hf_on)
    assert email_radio(config.radios, config.email_choice) == (FM_ID if fm_on else HF_ID if hf_on else None), (
        "FM while it is on; a station with HF alone sends its mail on HF"
    )
    assert as_0_20_1(config.radios, None) == (FM_ID if fm_on else None), (
        "what 0.20.1 gave: the one difference is the mail of a station whose only radio that sends is HF"
    )


OLD = [
    # (the radios, the stored main radio, the old result, the new result, why): every case of the
    # old table, with no choice of the email radio stored
    ((radio(1), radio(2, "hf")), None, 1, 1, "the first box, the FM one, which gateways hear"),
    (
        (radio(1, position=2), radio(2, "hf", position=1)),
        None,
        1,
        1,
        "the first box is HF: the first radio that gateways hear",
    ),
    ((radio(1), radio(2, "hf")), HF_ID, 1, 1, "HF stored as the main radio: the first radio that gateways hear"),
    ((radio(1, enabled=False), radio(2, "hf"), radio(3)), None, 3, 3, "radio 1 off: another FM radio that is on"),
    ((radio(1), radio(2, "hf"), radio(3, position=0)), None, 3, 3, "the first box is an FM radio: it, not radio 1"),
    ((radio(1), radio(3)), 3, 3, 3, "the stored main radio, which gateways hear"),
    (
        (radio(1, enabled=False), radio(2, "hf")),
        None,
        None,
        2,
        "HF alone can send: 0.20.1 refused the mail, now it goes on HF (one radio that sends: that one)",
    ),
    (
        (radio(1, type="no-such-type"), radio(2, "hf")),
        None,
        None,
        2,
        "a radio of a type that is not known sends nothing: HF alone, as above",
    ),
    (
        (radio(1, removed=True), radio(2, "hf"), radio(3, enabled=False)),
        None,
        None,
        2,
        "removed or off: HF alone, as above",
    ),
    ((radio(1, type="dummy"), radio(2, "hf")), None, 1, 1, "the Dummy packet radio is an FM radio here as well"),
    ((), None, None, None, "no radio at all"),
    (
        (radio(1, enabled=False), radio(2, "hf", enabled=False)),
        None,
        None,
        None,
        "no radio that is on: none, and the mail is refused",
    ),
    (
        (radio(1, type="tnc-text"), radio(2, "hf", type="dummy-hf", enabled=False)),
        None,
        None,
        None,
        "a monitor that only receives is no radio for a mail",
    ),
    (
        (radio(2, "hf"), radio(4, "hf", type="dummy-hf")),
        None,
        None,
        2,
        "two HF radios: 0.20.1 refused; now the first that can send, in the order of the boxes",
    ),
    (
        (radio(2, "hf", position=9), radio(4, "hf", type="dummy-hf")),
        None,
        None,
        4,
        "two HF radios, the other box first",
    ),
    (
        (radio(2, "hf", position=2), radio(4, "hf", type="dummy-hf", position=1)),
        4,
        None,
        4,
        "two HF radios, the second stored as the main radio: its box put first by migration 34, it",
    ),
    (
        (radio(1, type="tnc-text"), radio(2, "hf"), radio(5, "lora")),
        None,
        5,
        5,
        "a monitor, HF and LoRa: the LoRa radio, which gateways hear (station f of the design)",
    ),
    (
        (radio(1, enabled=False), radio(2, "hf"), radio(5, "lora")),
        1,
        5,
        5,
        "FM chosen and off, HF and LoRa on: LoRa (station d)",
    ),
]


@pytest.mark.parametrize(("specs", "main_choice", "before", "now", "why"), OLD)
def test_with_the_choice_the_update_writes_a_mail_goes_on_the_radio_it_went_on_in_0_20_1_and_where_it_was_refused_on_the_first_that_can_send(
    specs: tuple[RadioSpec, ...], main_choice: int | None, before: int | None, now: int | None, why: str
) -> None:
    assert as_0_20_1(specs, main_choice) == before, why
    assert email_radio(specs, before) == now, why
    if before is not None:
        assert now == before, "where 0.20.1 sent a mail, nothing moves"
    else:
        assert all(spec.kind == "hf" for spec in senders(specs)), (
            "the one difference: a station with no FM or LoRa radio on, whose mail was refused"
        )


SIX = (
    radio(1),
    radio(2, "hf"),
    radio(3, "lora"),
    radio(4, type="tnc-text"),
    radio(5, enabled=False),
    radio(6, "hf", type="dummy-hf", removed=True),
)

CHOSEN = [
    # (the radios, the choice `email/radio`, the radio, why)
    (SIX, 2, 2, "the choice: the Mercury radio (any radio that can send, whatever its modem)"),
    (SIX, 3, 3, "the choice: the LoRa radio"),
    (SIX, 1, 1, "the choice: the FM radio"),
    (SIX, 4, 1, "a monitor that only receives is no choice: the first that can send"),
    (SIX, 5, 1, "the radio chosen is off: the first that can send"),
    (SIX, 6, 1, "the radio chosen is removed: the first that can send"),
    (SIX, 99, 1, "an id that is no radio: the first that can send"),
    (
        (radio(1, enabled=False, position=1), radio(2, "hf", position=3), radio(3, "lora", position=2)),
        1,
        3,
        "the radio chosen is off: the first box that can send, the LoRa one",
    ),
    (
        (radio(1, enabled=False), radio(2, "hf"), radio(3, "lora", enabled=False)),
        3,
        2,
        "one radio that can send: that one, whatever is chosen",
    ),
    ((radio(1), radio(4, type="tnc-text")), 4, 1, "one radio that can send beside a monitor: that one"),
    (
        (radio(1, enabled=False), radio(2, "hf", enabled=False)),
        1,
        None,
        "no radio that can send is on: none, whatever is chosen",
    ),
]


@pytest.mark.parametrize(("specs", "chosen", "expected", "why"), CHOSEN)
def test_the_radio_chosen_in_the_email_tab_carries_the_mail_while_it_is_on_and_can_send(
    specs: tuple[RadioSpec, ...], chosen: int, expected: int | None, why: str
) -> None:
    assert email_radio(specs, chosen) == expected, why
    assert expected is None or expected in {spec.id for spec in senders(specs)}, "never a radio that cannot send"


def test_every_radio_that_can_send_may_be_chosen_and_no_other() -> None:
    can = [spec.id for spec in senders(SIX)]
    assert can == [1, 2, 3] and [email_radio(SIX, id) for id in can] == can, (
        "FM, Mercury and LoRa: each carries the mail when it is chosen"
    )
    assert {email_radio(SIX, id) for id in (4, 5, 6, 7)} == {1}, (
        "a monitor, a radio that is off, one removed and one that is none: not chosen"
    )


def test_what_gateways_hear_is_the_types_own() -> None:
    assert (
        gateway_heard(radio(1)),
        gateway_heard(radio(1, type="kiss-tcp")),
        gateway_heard(radio(2, "hf")),
        gateway_heard(radio(2, "hf", type="dummy-hf")),
    ) == (True, True, False, False)
    assert not gateway_heard(radio(1, type="no-such-type"))


# ---- the services: a mail goes on the email radio, none is a refusal with its reason


class Rig(ServiceRig):
    """The station's radios as the registry gives them over stub lines: `specs`, each on a line of
    its own (`lines`), the registry's email radio by the rule with the choice `chosen`
    (`email/radio`)."""

    def __init__(self, specs: tuple[RadioSpec, ...], chosen: int | None = None) -> None:
        super().__init__()
        self.lines = {spec.id: StubTnc() for spec in specs}
        self.radios = Registry([LiveShape(spec, specs, self.lines[spec.id]) for spec in specs], chosen)  # type: ignore[arg-type]


class Registry(RegistryShape):
    def __init__(self, radios: list[LiveShape], chosen: int | None) -> None:
        super().__init__(radios)
        self.chosen = chosen

    def email(self) -> LiveShape | None:
        specs = [r.spec for r in self.radios]
        return self.get(found) if (found := email_radio(specs, self.chosen)) is not None else None


def test_a_mail_goes_on_the_email_radio_and_is_refused_only_while_no_radio_that_can_send_is_on() -> None:
    rig = Rig((radio(1, enabled=False), radio(2, "hf"), radio(3)))
    assert station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY).id == 2, (
        "radio 1 off, none chosen: the first box that can send"
    )
    rig = Rig((radio(1, enabled=False), radio(2, "hf"), radio(3)), chosen=2)
    assert station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY).id == 2, (
        "the Mercury radio chosen: it carries the mail"
    )
    rig = Rig((radio(1, enabled=False), radio(2, "hf")))
    assert station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY).id == 2, (
        "the one radio that can send, of any kind"
    )
    rig = Rig((radio(1, enabled=False), radio(2, "hf", enabled=False)))
    with pytest.raises(MessagingError) as refused:
        station_radio(rig.radios, lambda: rig.config, EMAIL_GATEWAY)
    assert refused.value.code == "radio.none", (
        "no radio that can send is on: the refusal of every send (the page has its words)"
    )


def test_the_ack_of_a_mail_heard_on_a_radio_that_is_off_goes_on_the_email_radio_not_by_a_route_kept_for_the_gateway() -> (
    None
):
    rig = Rig((radio(1), radio(2, "hf"), radio(3, enabled=False)), chosen=2)
    mail = replace(heard(":OH2GBA   :got it{5", EMAIL_GATEWAY, ("OH2RCH-2*",)), via="rf", radio_id=3)
    assert getattr(ack_radio(rig.radios, mail, EMAIL_GATEWAY), "id", None) == 2, (
        "the radio chosen for email carries the gateway's ack"
    )
    other = replace(heard(":OH2GBA   :hi{6", "OH2ABC", ("OH2RCH-2*",)), via="rf", radio_id=3)
    assert getattr(ack_radio(rig.radios, other, "OH2ABC"), "id", None) == 1, (
        "any other station's: the radio a message to it takes"
    )
    came = replace(mail, radio_id=1)
    assert getattr(ack_radio(rig.radios, came, EMAIL_GATEWAY), "id", None) == 1, (
        "heard on a radio that sends: acked on it"
    )


# ---- the whole daemon: frames counted per radio


async def test_a_daemon_with_fm_and_mercury_sends_a_mail_and_a_message_to_a_new_call_on_the_first_box_and_the_email_tabs_choice_moves_the_mail_alone(
    tmp_path: Path,
) -> None:
    # (no `email/radio`: a station that chose nothing)
    e = Env(tmp_path, clock=FixedClock(), web=True, settings={"hf/enabled": "true", "hf/profile": "dummy-hf"})
    # (no program: the Dummy Mercury radio works without its speaker)
    e.mercury._finder = lambda: None
    out: list[tuple[int | None, bytes]] = []
    e.ctl.radio_packet.connect(
        lambda p: out.append((p.radio_id, ax25.decode(p.raw).info[:10])) if p.direction == "out" else None
    )
    # (one frame after the other with no pause; the clock stands still, so no message is sent a
    # second time)
    e.ctl.messaging.tick_sec, e.ctl.messaging.pace.spacing_sec = 0.02, 0.0
    await e.start()
    await until(lambda: e.tnc.usable and e.hf.usable)
    page = await e.ws()
    await page.until(lambda: "radios" in page.topics and "config" in page.topics)
    sent = lambda: Counter(  # noqa: E731
        (id, "mail" if info == b":EMAIL-2  " else "new")
        for id, info in out
        if info.startswith((b":EMAIL-2  ", b":OH2NEW"))
    )
    mail, new = "mail", "new"

    async def status() -> tuple[int | None, int | None]:
        before = len(page.of("status"))
        await page.send({"cmd": "status"})
        await page.until(lambda: len(page.of("status")) > before)
        return page.of("status")[-1]["unheard_radio"], page.of("status")[-1]["email_radio"]

    async def send_both(total: int) -> None:
        """A mail, and a message to a call no radio heard (a new call each time: a message waits
        behind one to the same station that is still on its way; a mail waits for none)."""
        await page.send({"cmd": "send_message", "to": "EMAIL-2", "text": "jane@example.org hello"})
        await page.send({"cmd": "send_message", "to": f"OH2NEW-{total}", "text": "hello"})
        await until(lambda: sum(sent().values()) == total)

    assert page.topics["config"]["radio_values"]["email/radio"] == "" and await status() == (1, 1)
    await send_both(2)
    assert sent() == Counter({(1, mail): 1, (1, new): 1}), "both on FM, the first box: one frame each"

    # (the select of the E-mail tab: the Mercury radio)
    await page.send({"cmd": "set_config", "values": {"email/radio": "2"}})
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == "2")
    assert (
        await status() == (1, 2)
        and e.ctl.config.email_choice == 2
        and (await e.ctl.store.settings())["email/radio"] == "2"
    )
    await send_both(4)
    assert sent() == Counter({(1, mail): 1, (2, mail): 1, (1, new): 2}), (
        "the mail once on the Mercury radio and not on FM; the message to a call no radio heard where it went"
    )

    for number, (wrong, code) in enumerate((("9", "radio.unknown"), ("x", "setting.not_whole")), start=1):
        await page.send({"cmd": "set_config", "values": {"email/radio": wrong}})
        await page.until(lambda number=number: len(page.of("error")) == number)
        assert (page.of("error")[-1]["key"], page.of("error")[-1]["code"]) == ("email/radio", code)
    assert e.ctl.config.email_choice == 2, "a refused choice changes nothing"

    # (no choice stored again: the first box that can send)
    await page.send({"cmd": "set_config", "values": {"email/radio": ""}})
    await page.until(lambda: page.topics["config"]["radio_values"]["email/radio"] == "")
    assert await status() == (1, 1)
    # (radio 1's box moved last: the Mercury radio's is the first)
    await page.send({"cmd": "radio_change", "radio": 1, "position": 9})
    await page.until(lambda: page.topics["radios"]["1"]["position"] == 9)
    assert await status() == (2, 2), "the order of the boxes moves the call no radio heard and a mail of no choice"
    await send_both(6)
    assert sent() == Counter({(1, mail): 1, (2, mail): 2, (1, new): 2, (2, new): 1})
    await page.send({"cmd": "radio_change", "radio": 1, "enabled": False})
    await page.until(lambda: not page.topics["radios"]["1"]["enabled"])
    assert await status() == (2, 2), "one radio that can send: the mail and everything else on it"
    await e.stop()


# ---- six radios that send, a monitor and one that is off, on a clock that is held: frames counted
# per radio


class Station:
    """A daemon on made-up radios (radio 1 a Dummy packet radio, radio 2 a Dummy Mercury radio, then
    `more` by type), a page on its socket, and every frame of ours with the radio it went on. The
    clock stands still until a test moves it, so a message goes out once."""

    def __init__(self, tmp_path: Path) -> None:
        self.clock = FixedClock()
        self.e = Env(
            tmp_path,
            clock=self.clock,
            radio=False,
            web=True,
            settings={
                "tnc/profile": "dummy",
                "hf/enabled": "true",
                "hf/profile": "dummy-hf",
                "messages/alert": "false",
            },
        )
        # (no program: a Dummy Mercury radio works without its speaker)
        self.e.mercury._finder = lambda: None
        self.out: list[tuple[int | None, str]] = []
        self.e.ctl.radio_packet.connect(
            lambda p: (
                self.out.append((p.radio_id, ax25.decode(p.raw).info.decode("latin-1").split("{")[0]))
                if p.direction == "out"
                else None
            )
        )
        self.e.ctl.messaging.tick_sec, self.e.ctl.messaging.pace.spacing_sec = 0.01, 0.0

    async def start(self, *more: str, senders: tuple[int, ...]) -> None:
        await self.e.start(connected=False)
        for type in more:
            await self.e.ctl.add_radio(type)
        await until_started(lambda: all(r.usable for r in self.e.ctl.radios.all() if r.id in senders))
        self.page = await self.e.ws()
        await self.page.until(lambda: "radios" in self.page.topics and "config" in self.page.topics)

    def on(self, text: str) -> list[int | None]:
        """The radios our frames with this text went on, in the order they went."""
        return [radio for radio, info in self.out if text in info]

    async def status(self) -> tuple[int | None, int | None]:
        before = len(self.page.of("status"))
        await self.page.send({"cmd": "status"})
        await self.page.until(lambda: len(self.page.of("status")) > before)
        return self.page.of("status")[-1]["unheard_radio"], self.page.of("status")[-1]["email_radio"]

    async def choose(self, value: str) -> None:
        """The select of the Email tab: `email/radio` over the page's socket."""
        await self.page.send({"cmd": "set_config", "values": {"email/radio": value}})
        await self.page.until(lambda: self.page.topics["config"]["radio_values"]["email/radio"] == value)

    async def say(self, to: str, text: str) -> None:
        await self.page.send({"cmd": "send_message", "to": to, "text": text})


MAIL, NEW, CQ = ":EMAIL-2  :", ":OH2NEW", ":CQ       :"


async def test_with_six_radios_a_monitor_and_one_off_every_radio_that_sends_carries_the_mail_when_it_is_chosen_and_nothing_else_moves(
    tmp_path: Path,
) -> None:
    """The registry itself with radios of every kind: a mail, a message to a call no radio heard and
    a text to CQ at each step, each one frame on one radio. The mail follows the choice and nothing
    else does; a monitor or a radio that is off may be stored and is no choice; the order of the
    boxes moves the call no radio heard; a message heard on the monitor or on a radio off since is
    acked on that radio, a query heard there is not answered; not one frame on the monitor or on the
    radio that is off."""
    senders_, monitor, off = (1, 2, 3, 4, 5, 6), 7, 8
    s = Station(tmp_path)
    await s.start("dummy", "dummy-hf", "dummy-lora", "dummy-hf", "tnc-text", "dummy", senders=senders_)
    e = s.e
    assert await e.ctl.change_radio(off, enabled=False)
    assert [(spec.id, spec.kind, spec.enabled) for spec in e.ctl.config.live_radios] == [
        (1, "fm", True),
        (2, "hf", True),
        (3, "fm", True),
        (4, "hf", True),
        (5, "lora", True),
        (6, "hf", True),
        (7, "fm", True),
        (8, "fm", False),
    ]
    sent = lambda prefix: Counter(radio for radio, info in s.out if info.startswith(prefix))  # noqa: E731
    count = 0

    async def three() -> None:
        nonlocal count
        count += 1
        await s.say("EMAIL-2", f"jane@example.org {count}")
        await s.say(f"OH2NEW-{count}", "hello")
        await s.say("CQ", f"anyone {count}")
        await until(lambda: sum((sent(MAIL) + sent(NEW) + sent(CQ)).values()) == 3 * count)
        await idle_for(0.1)
        assert sum((sent(MAIL) + sent(NEW) + sent(CQ)).values()) == 3 * count, "each once, on one radio"

    assert await s.status() == (1, 1), "nothing stored: the first box, an FM radio, for both"
    await three()
    mails: Counter[int | None] = Counter({1: 1})
    assert (sent(MAIL), sent(NEW), sent(CQ)) == (mails, Counter({1: 1}), Counter({1: 1}))
    for chosen in senders_:
        await s.choose(str(chosen))
        assert await s.status() == (1, chosen)
        await three()
        mails[chosen] += 1
        assert sent(MAIL) == mails and set(sent(NEW)) == {1} and set(sent(CQ)) == {1}, (
            f"the mail on radio {chosen} alone, whatever its modem; the call no radio heard and CQ where they went"
        )
    # (the page offers neither; `neoaprs db set` may store one)
    for stored in (monitor, off):
        await s.choose(str(stored))
        assert await s.status() == (1, 1), "a monitor, a radio that is off: no choice"
        await three()
        mails[1] += 1
        assert sent(MAIL) == mails
    await s.choose("5")
    assert await e.ctl.change_radio(5, enabled=False)
    assert await s.status() == (1, 1), "the radio chosen is off: as with none chosen"
    await three()
    mails[1] += 1
    assert await e.ctl.change_radio(5, enabled=True)
    await until_started(lambda: e.ctl.radios.get(5).usable)  # type: ignore[union-attr]
    assert await s.status() == (1, 5), "on again: the choice was kept"
    await three()
    mails[5] += 1
    assert sent(MAIL) == mails
    for number, (wrong, code) in enumerate(
        (("99", "radio.unknown"), ("0", "setting.range"), ("Packet", "setting.not_whole")), start=1
    ):
        await s.page.send({"cmd": "set_config", "values": {"email/radio": wrong}})
        await s.page.until(lambda number=number: len(s.page.of("error")) == number)
        assert (s.page.of("error")[-1]["key"], s.page.of("error")[-1]["code"]) == ("email/radio", code)
    assert e.ctl.config.email_choice == 5, "a refused choice changes nothing"

    await s.choose("")
    # (radio 1's box moved last: a Mercury radio's box is the first)
    assert await e.ctl.change_radio(1, position=20)
    assert await s.status() == (2, 2), "a call no radio heard and the mail, none chosen, on the first box that can send"
    news, cqs = sent(NEW), sent(CQ)
    await three()
    mails[2] += 1
    assert sent(MAIL) == mails and sent(NEW) - news == Counter({2: 1}) and sent(CQ) - cqs == Counter({2: 1})

    before = len(s.out)
    for source, info, came in (
        ("OH7MON", ":OH2GBA   :hi{7", monitor),
        ("OH7ASK", ":OH2GBA   :?APRSP", monitor),
        ("OH7OFF", ":OH2GBA   :hi{8", off),
        ("OH7ASKS", ":OH2GBA   :?APRSP", off),
        ("OH7LOR", ":OH2GBA   :hi{9", 5),
    ):
        e.ctl.radio_packet.emit(replace(heard(info, source, at=s.clock()), radio_id=came))
    await until(lambda: len(s.out) == before + 3)
    await idle_for(0.2)
    assert sorted(s.out[before:], key=str) == [
        (2, ":OH7MON   :ack7"),
        (2, ":OH7OFF   :ack8"),
        (5, ":OH7LOR   :ack9"),
    ], (
        "an ack on the radio the message came on; where that one sends nothing or is off, on the radio a message to the station takes; no answer to the two queries"
    )

    await s.choose("3")
    assert await s.status() == (2, 3)
    assert await e.ctl.remove_radio(3)
    await s.page.until(lambda: s.page.topics["config"]["radio_values"]["email/radio"] == "")
    assert await s.status() == (2, 2), "the radio chosen is removed: none chosen, the first box that can send"
    await three()
    mails[2] += 1
    assert sent(MAIL) == mails == Counter({1: 5, 2: 3, 3: 1, 4: 1, 5: 2, 6: 1}) and (sent(NEW), sent(CQ)) == (
        Counter({1: 11, 2: 2}),
        Counter({1: 11, 2: 2}),
    ), "13 mails, 13 messages, 13 texts to CQ: one frame each"
    assert not any(radio in (monitor, off) for radio, _ in s.out), (
        "never a frame on the monitor or on the radio that is off"
    )
    await e.stop()


async def test_on_a_fake_clock_a_mail_has_its_two_attempts_on_one_radio_and_a_new_choice_or_its_radio_switched_off_moves_the_next_attempt(
    tmp_path: Path,
) -> None:
    """Half an hour of the daemon's clock for each mail, a minute at a time: FM (1), Mercury (2),
    LoRa (3), a second Mercury radio (4) and a monitor (5)."""
    s = Station(tmp_path)
    await s.start("dummy-lora", "dummy-hf", "tnc-text", senders=(1, 2, 3, 4))
    e = s.e

    async def half_an_hour(sent: dict[str, int], then: Callable[[], Awaitable[object]] | None = None) -> None:
        """`then` is done once the first frame of each text is out (it goes while the clock stands),
        then the half hour passes, and the wait ends when every text has gone out as often as `sent`
        says: a busy runner is waited for and never raced."""
        if then is not None:
            await until(lambda: all(s.on(text) for text in sent))
            await then()
        for _ in range(30):
            s.clock.advance(60)
            await idle_for(0.03)
        await until(lambda: all(len(s.on(text)) >= times for text, times in sent.items()))

    await s.say("EMAIL-2", "jane@example.org one")
    await s.say("OH2SLOW", "one")
    await s.say("CQ", "cq one")
    await half_an_hour({"jane@example.org one": 2, ":OH2SLOW  :one": 4, "cq one": 1})
    assert (s.on("jane@example.org one"), s.on(":OH2SLOW  :one"), s.on("cq one")) == ([1, 1], [1, 1, 1, 1], [1]), (
        "nothing stored: the mail twice, the message to a call no radio heard four times, the text to CQ once, all on the first box"
    )
    await s.choose("2")
    await s.say("EMAIL-2", "jane@example.org two")
    await half_an_hour({"jane@example.org two": 2})
    assert s.on("jane@example.org two") == [2, 2], "the Mercury radio chosen: both attempts on it"
    await s.say("EMAIL-2", "jane@example.org three")
    await half_an_hour({"jane@example.org three": 2}, lambda: s.choose("4"))
    assert s.on("jane@example.org three") == [2, 4], (
        "another radio chosen after the first attempt: the second on that one"
    )
    await s.say("EMAIL-2", "jane@example.org four")
    await half_an_hour({"jane@example.org four": 2}, lambda: e.ctl.change_radio(4, enabled=False))
    assert s.on("jane@example.org four") == [4, 1], (
        "the radio chosen switched off after the first attempt: the second on the radio of no choice"
    )
    assert Counter(radio for radio, info in s.out if "jane@" in info) == Counter({1: 3, 2: 3, 4: 2}) and Counter(
        radio for radio, _ in s.out
    ) == Counter({1: 8, 2: 3, 4: 2}), "four mails, eight frames; nothing on LoRa or the monitor"
    await e.stop()
