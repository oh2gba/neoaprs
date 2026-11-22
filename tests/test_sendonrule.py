"""A radio that comes on never stops anything (neoaprs/sendonrule.py `kept_in_force`), what a new
object or bulletin starts with (`start_set`), and the counts of the air under a slow radio's floor;
then the controller.
"""

import itertools
from dataclasses import replace
from pathlib import Path

from neoaprs.beaconrule import send_on_radios
from neoaprs.decay import ANNOUNCEMENT, BULLETIN, bulletin_wait_sec
from neoaprs.radiospec import RadioSpec
from neoaprs.sendonrule import Kept, ids_of, kept_in_force, start_set, text_of
from tests.support.clock import FixedClock
from tests.support.env import Env


def radio(
    id: int, kind: str = "fm", enabled: bool = True, position: int | None = None, type: str | None = None, **own: str
) -> RadioSpec:
    return RadioSpec(
        id,
        kind,
        type or {"fm": "dummy", "hf": "dummy-hf", "lora": "dummy-lora"}[kind],
        "",
        enabled,
        id if position is None else position,
        None,
        own,
    )  # type: ignore[arg-type]


ALL_UNTICKED = {"status": "false", "ask": "false", "local_info": "false"}


# ---- the rule


def test_a_second_radio_beside_the_one_that_carried_everything_ticks_that_one_and_carries_its_beacon_alone() -> None:
    before = (radio(1, **ALL_UNTICKED),)
    after = (*before, radio(2, "hf"))
    kept = kept_in_force(before, after, {"CAMP": (1,)}, {"BLN1": (1,)}, None)
    assert kept == Kept(((1, "status"), (1, "ask"), (1, "local_info")), {}, {}, 1), (
        "the status, Ask around and Local info stay on FM; the mail is stored where it went; objects and bulletins are on FM already"
    )
    assert not kept_in_force(before, after, {}, {}, 1).email, "a choice stored is the operator's"


def test_the_mail_moves_to_a_radio_internet_gateways_hear_that_comes_on_beside_one_they_do_not() -> None:
    hf_alone = (radio(1, "hf", **ALL_UNTICKED),)
    assert kept_in_force(hf_alone, (*hf_alone, radio(2)), {}, {}, None).email == 2, (
        "an HF station that adds FM sends its mail on FM, as 0.20.0 did"
    )
    assert kept_in_force(hf_alone, (*hf_alone, radio(2, "hf")), {}, {}, None).email == 1, (
        "a second HF radio: the mail stays where it went"
    )
    assert kept_in_force(hf_alone, (*hf_alone, radio(2)), {}, {}, 1).email is None, (
        "HF chosen by the operator and on: the operator's"
    )


def test_a_stale_mail_choice_is_overwritten_with_the_radio_the_mail_went_on_when_a_radio_comes_on() -> None:
    before = (radio(1, enabled=False), radio(2, "lora"), radio(3, "hf", enabled=False))
    after = (radio(1), radio(2, "lora"), radio(3, "hf", enabled=False))
    assert kept_in_force(before, after, {}, {}, 3).email == 2, (
        "the choice names a radio that is off: the mail stays on LoRa, where it went, not on FM's higher box"
    )
    assert kept_in_force(before, after, {}, {}, 1).email is None, "the choice comes on: the operator's"
    on_hf = (radio(1, enabled=False), radio(2, "hf"), radio(3, "lora", enabled=False))
    assert kept_in_force(on_hf, (radio(1), *on_hf[1:]), {}, {}, 3).email == 1, (
        "the mail went on HF, which internet gateways do not hear: FM, which comes on, takes it"
    )


def test_a_lone_radio_whose_beacon_tick_is_off_keeps_its_beacon_when_a_radio_is_added() -> None:
    kept = kept_in_force(
        (radio(1, beacon="false", **ALL_UNTICKED),),
        (radio(1, beacon="false", **ALL_UNTICKED), radio(2, "lora")),
        {},
        {},
        None,
    )
    assert (1, "beacon") in kept.ticks, (
        "the lone radio beaconed whatever its tick; the new radio's own tick does not stand in for it"
    )
    assert send_on_radios("beacon", (radio(1, beacon="true"), radio(2, "lora"))) == (1, 2), (
        "the new radio beacons too, by its own tick"
    )


def test_a_thing_whose_radios_are_all_off_while_one_carries_it_gets_that_one_when_another_comes_on() -> None:
    before = (radio(1), radio(2, "hf", enabled=False))
    after = (radio(1), radio(2, "hf"), radio(3, "lora"))
    kept = kept_in_force(
        before,
        (radio(1), radio(2, "hf", enabled=False), radio(3, "lora")),
        {"ONHF": (2,), "ONFM": (1,)},
        {"BLN1": (2,)},
        None,
    )
    assert (kept.objects, kept.bulletins) == ({"ONHF": (1, 2)}, {"BLN1": (1, 2)}), (
        "in force on FM alone before, on none after: ticked for FM, HF kept for its day"
    )
    assert kept_in_force(before, after, {"ONHF": (2,)}, {}, None).objects == {}, (
        "HF on again: in force on it, nothing to keep"
    )


def test_ticked_nowhere_by_the_operator_stays_so_and_a_change_of_ticks_alone_keeps_nothing() -> None:
    three = (radio(1, status="false"), radio(2, "hf", status="true"), radio(3, "lora"))
    assert not kept_in_force(
        three, (radio(1, status="false"), radio(2, "hf", status="false"), radio(3, "lora")), {}, {}, None
    ), "no radio came on: a tick is the operator's"
    off = (radio(1), radio(2, "hf", enabled=False, status="true"), radio(3, "lora"))
    assert not kept_in_force(three, off, {}, {}, None), (
        "a radio switched off stops what was ticked for it alone: no radio came on"
    )
    assert not kept_in_force(off, (*off, radio(4)), {}, {}, None).ticks, (
        "ticked nowhere before: nothing was in force, nothing is kept"
    )


def test_a_radio_that_comes_back_takes_back_what_was_ticked_for_it_and_only_what_went_on_the_other_alone_is_kept() -> (
    None
):
    both = (radio(1, status="false"), radio(2, "hf", status="true"))
    alone = (radio(1, status="false"), radio(2, "hf", enabled=False, status="true"))
    kept = kept_in_force(alone, both, {}, {}, None)
    assert kept.ticks == ((1, "ask"), (1, "local_info")), (
        "the status went on FM while HF was off; with HF back it goes on HF, as ticked; Ask around and Local info, ticked nowhere, stay on FM"
    )


def test_a_receive_only_radio_given_a_type_that_sends_comes_on_as_a_new_one_and_one_given_a_receive_only_type_keeps_nothing() -> (
    None
):
    before = (radio(1, **ALL_UNTICKED), radio(2, type="tnc-text"))
    assert kept_in_force(before, (radio(1, **ALL_UNTICKED), radio(2)), {}, {}, None).ticks == (
        (1, "status"),
        (1, "ask"),
        (1, "local_info"),
    )
    assert not kept_in_force((radio(1), radio(2)), (radio(1), radio(2, type="tnc-text")), {}, {}, None)


def four(key: str, rows: tuple[str | None, ...], missing: str | None) -> tuple[RadioSpec, ...]:
    """Four radios that send with these rows of `key` (None: no row, or `missing` written in its
    place), beside a monitor and a radio that is off, both ticked."""
    own = lambda text: {} if text is None and missing is None else {key: text or missing}  # noqa: E731
    sending = (
        radio(id, kind, **own(text))
        for id, kind, text in zip((1, 2, 3, 4), ("fm", "hf", "lora", "fm"), rows, strict=True)
    )
    return (
        *sending,
        radio(5, type="tnc-text", **dict.fromkeys(("status", "ask", "local_info"), "true")),
        radio(6, enabled=False, **dict.fromkeys(("status", "ask", "local_info"), "true")),
    )


def test_a_radio_with_no_row_is_a_radio_whose_row_says_false_for_every_rule_that_reads_a_tick() -> None:
    """The page sends the tick pressed alone, so a radio may have no row where another has one: no
    rule may tell the two apart (each of four radios that send with no row, false or true; and a
    fifth radio added, or the one that was off switched on)."""
    grows = (lambda specs: (*specs, radio(7, "lora")), lambda specs: (*specs[:5], replace(specs[5], enabled=True)))
    for key in ("status", "ask", "local_info"):
        for rows in itertools.product((None, "false", "true"), repeat=4):
            stored, falses = four(key, rows, None), four(key, rows, "false")
            assert send_on_radios(key, stored) == send_on_radios(key, falses), (key, rows)
            for grow in grows:
                assert kept_in_force(stored, grow(stored), {}, {}, None) == kept_in_force(
                    falses, grow(falses), {}, {}, None
                ), (key, rows)


def test_what_a_new_thing_starts_with() -> None:
    six = (radio(1), radio(2, "hf"), radio(3, "lora", position=0), radio(4, enabled=False), radio(5, type="tnc-text"))
    assert start_set((), six) == (3,), "nothing saved yet: the first box that can send"
    assert start_set((1, 2), six) == (1, 2) and start_set((4, 2), six) == (2, 4), (
        "the radios of the one saved last, an off one with them while one of them is on"
    )
    assert start_set((4,), six) == (3,), (
        "the one saved last went on a radio that is off alone: the first box that can send"
    )
    assert start_set((4,), (radio(1, enabled=False), radio(4, enabled=False))) == (4,) and start_set(
        (), (radio(2, "hf", enabled=False),)
    ) == (2,), "none on: the radio the thing will go on"
    assert start_set((7,), (radio(2, "hf"),)) == (2,) and start_set((), ()) == (1,), (
        "one radio that can send: that one; no radio at all: radio 1, the first the station will have"
    )
    assert (ids_of("3,1"), ids_of(""), ids_of("x"), text_of((3, 1, 3))) == ((1, 3), (), (), "1,3")


# ---- the air: the floor of a slow radio


def schedule(plan_floor: int, plan: object) -> list[int]:
    """The minutes of a bulletin's sends from the first, by its plan and the floor of its radios."""
    at, sent, out = 0, 1, [0]
    while (wait := bulletin_wait_sec(plan, sent, at, plan_floor)) is not None:  # type: ignore[arg-type]
        at, sent = at + wait, sent + 1
        out.append(at // 60)
    return out


def test_a_bulletin_is_14_frames_on_fm_and_10_where_a_radio_it_goes_on_is_slow_and_an_announcement_74_on_either() -> (
    None
):
    assert schedule(0, BULLETIN) == [0, 2, 6, *range(26, 227, 20)] and len(schedule(0, BULLETIN)) == 14
    assert schedule(1800, BULLETIN) == [0, 2, 6, *range(36, 217, 30)] and len(schedule(1800, BULLETIN)) == 10, (
        "the early repeats stay; then every 30 minutes"
    )
    assert len(schedule(0, ANNOUNCEMENT)) == len(schedule(1800, ANNOUNCEMENT)) == 74, (
        "hourly is longer than the floor: unchanged"
    )


# ---- the controller: in the transaction of every change of the radios


async def test_the_controller_writes_what_a_radio_that_comes_on_keeps_and_a_save_of_ticks_alone_writes_nothing_else(
    tmp_path: Path,
) -> None:
    e = Env(tmp_path, clock=FixedClock(), radio=False, settings={"tnc/profile": "dummy"})
    await e.start(connected=False)
    try:
        ctl = e.ctl
        assert [s.id for s in ctl.config.live_radios] == [1] and all(
            key not in ctl.config.radios[0].settings for key in ALL_UNTICKED
        )
        ctl.ownobjects.set("CAMP", "object", 60.2, 24.9, "/", "r", "ours", radios=(1,))
        added = await ctl.add_radio("dummy-hf", enabled=False)
        assert added == 2 and not any(key in ctl.config.radio(1).settings for key in ALL_UNTICKED), (
            "added off: nothing came on"
        )  # type: ignore[union-attr]
        assert await ctl.change_radio(2, enabled=True)
        stored = {s.id: dict(s.settings) for s in await ctl.store.radios()}
        assert {key: stored[1].get(key) for key in ALL_UNTICKED} == dict.fromkeys(ALL_UNTICKED, "true") and not any(
            key in stored[2] for key in ALL_UNTICKED
        ), "switched on: radio 1 keeps what it carried"
        assert (
            ctl.config.radio(1).settings["status"] == "true"
            and ctl.config.email_choice == 1
            and (await ctl.store.settings())["email/radio"] == "1"
        )  # type: ignore[union-attr]
        assert await ctl.save_radio_settings(1, {"status": "false"})
        assert (await ctl.store.radios())[0].settings["status"] == "false", "a tick of the operator's: not undone"
        assert await ctl.change_radio(1, enabled=False) and await ctl.change_radio(1, enabled=True)
        assert (await ctl.store.radios())[0].settings["status"] == "false", (
            "radio 1 off and on again beside radio 2: the status went on radio 2 alone, which still sends: nothing kept"
        )
        assert ctl.ownobjects.get("CAMP").radios == (1,)  # type: ignore[union-attr]
    finally:
        await e.stop()


async def test_an_object_on_a_radio_that_is_off_while_the_other_carries_it_gets_that_one_when_a_third_comes(
    tmp_path: Path,
) -> None:
    e = Env(
        tmp_path,
        clock=FixedClock(),
        radio=False,
        settings={"tnc/profile": "dummy", "hf/enabled": "true", "hf/profile": "dummy-hf"},
    )
    e.mercury._finder = lambda: None
    await e.start(connected=False)
    try:
        ctl = e.ctl
        ctl.ownobjects.set("ONHF", "object", 60.2, 24.9, "/", "r", "ours", radios=(2,))
        ctl.ownbulletins.post("BLN1", "net", (2,))
        assert await ctl.change_radio(2, enabled=False)
        assert [r.id for r in ctl.sender.radios_for((2,))] == [1], "one radio on: it carries the object"
        assert await ctl.add_radio("dummy-lora") == 3
        assert (ctl.ownobjects.get("ONHF").radios, ctl.ownbulletins.get("BLN1").radios) == ((1, 2), (1, 2))  # type: ignore[union-attr]
        await e.settled()
        rows = await ctl.db.read(
            lambda db: (
                db.execute("SELECT radios FROM own_object").fetchall(),
                db.execute("SELECT radios FROM own_bulletin").fetchall(),
            )
        )  # type: ignore[union-attr]
        assert rows == ([("1,2",)], [("1,2",)]), "written in the transaction of the change, and again from memory"
        assert await ctl.remove_radio(2)
        assert (ctl.ownobjects.get("ONHF").radios, ctl.ownbulletins.get("BLN1").radios) == ((1,), (1,)), (
            "a removed radio leaves every set"
        )  # type: ignore[union-attr]
    finally:
        await e.stop()


def test_a_radio_added_on_the_command_line_keeps_in_force_what_the_daemons_add_would(tmp_path: Path) -> None:
    from neoaprs.cli.dbcmd import main as db_main
    from tests.support.migrated import opened

    data = tmp_path / "data"
    data.mkdir()
    opened(data / "neoaprs.sqlite").close()
    assert (
        db_main(["--data", str(data), "radios", "add", "dummy"]) == 0
        and db_main(["--data", str(data), "radios", "add", "dummy-hf"]) == 0
    )
    s = opened(data / "neoaprs.sqlite")
    try:
        assert {
            (int(r), str(k)): str(v)
            for r, k, v in s.db.execute(
                "SELECT radio_id, key, value FROM radio_setting WHERE key IN ('status', 'ask', 'local_info')"
            )
        } == {(1, "status"): "true", (1, "ask"): "true", (1, "local_info"): "true"}
        assert s.db.execute("SELECT value FROM settings WHERE key = 'email/radio'").fetchone() == ("1",)
    finally:
        s.close()
