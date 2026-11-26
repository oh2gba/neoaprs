"""The row of the topic `radios`, from a radio's settings, live state and the resource table.

The state and problem are radiohealth.py's decision, only formatted here; the devices a radio's
settings name are passed on from there to the handlers that refuse a save naming a held one.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from neoaprs.cardlevels import CardLevels
from neoaprs.claims import Claims
from neoaprs.clock import iso
from neoaprs.coded import Param, code_of
from neoaprs.radiohealth import claimed_value as claimed_value
from neoaprs.radiohealth import devices as devices
from neoaprs.radiohealth import held_elsewhere as held_elsewhere
from neoaprs.radiohealth import holder_id as holder_id
from neoaprs.radiohealth import holder_name as holder_name
from neoaprs.radiohealth import line_of, radio_health
from neoaprs.radiohealth import one_device as one_device
from neoaprs.radiohealth import removed_name as removed_name
from neoaprs.radiospec import RadioSpec, number_in_kind
from neoaprs.radiotype import RadioId, RadioType, RadioTypeError
from neoaprs.tnc import Tnc
from neoaprs.tnchealth import RadioHealth
from neoaprs.tncwatchdog import TncStats as LineStats

from .tncwire import RadioProblem, RadioRow, stats_row
from .views import LINES_MAX, modem_state
from .wirebase import plain


class RadioBeacon(Protocol):
    @property
    def last_sent(self) -> datetime | None: ...
    @property
    def next_due(self) -> datetime | None: ...
    @property
    def interval_min(self) -> int: ...
    @property
    def problem(self) -> str: ...


class RadioStatus(Protocol):
    def on_radio(self, id: RadioId) -> tuple[datetime | None, datetime | None, int]: ...


class RadioCard(Protocol):
    @property
    def card(self) -> CardLevels | None: ...


class RadioAtWork(Protocol):
    @property
    def line(self) -> Tnc: ...
    @property
    def driver_key(self) -> str: ...
    @property
    def beacon(self) -> RadioBeacon: ...
    @property
    def driver(self) -> RadioCard: ...


def radio_row(
    spec: RadioSpec,
    specs: Sequence[RadioSpec],
    radio: RadioAtWork | None,
    claims: Claims,
    status: RadioStatus | None = None,
) -> dict[str, Any] | None:
    """Return the page's row of a radio, a removed one too; `radio` is None if it is not run.

    Return None for an unknown type (written by a newer program).
    """
    try:
        rtype = spec.rtype
    except RadioTypeError:
        return None
    line = line_of(spec, radio)
    health = radio_health(spec, specs, radio, claims)
    lines = [] if line is None else [{"at": iso(at), "text": text} for at, text in line.recent_lines(LINES_MAX)]
    card = None if line is None or radio is None else radio.driver.card
    return RadioRow.row(
        spec,
        enabled=spec.enabled and not spec.removed,
        number=number_in_kind(spec, specs),
        removed=spec.removed,
        dummy=rtype.dummy,
        state=health.state.value,
        problem=problem_row(health),
        stats=stats_row(LineStats() if line is None else line.stats),
        lines=lines,
        limits={"max_frame": rtype.limits.max_frame, "beacon_min_min": rtype.limits.beacon_min_min},
        allowed=plain(rtype.allowed),
        can=plain(rtype.can),
        choices=_choices(spec, rtype),
        beacon=_beacon(spec, None if radio is None or spec.removed else radio.beacon),
        status=_status(spec, status),
        modem=None if line is None else modem_state(line),
        card=_card(card),
        holds=[{"resource": c.kind, "value": c.value} for c in claims.all() if c.holder == spec.id],
    )


def _card(card: CardLevels | None) -> dict[str, Any]:
    """Return the row's sound card levels."""
    return (
        {"tx": None, "rx": None, "read": True}
        if card is None
        else {"tx": card.levels.tx, "rx": card.levels.rx, "read": card.known}
    )


def _choices(spec: RadioSpec, rtype: RadioType) -> dict[str, Any]:
    """Return the radio's choices in force; a missing Send-on tick is false (beacon: true)."""

    def tick(key: str, without: bool = False) -> bool:
        return bool(spec.value(key)) if rtype.field(key) is not None else without

    return {
        "beacon": tick("beacon", True),
        "status": tick("status"),
        "ask": tick("ask"),
        "local_info": tick("local_info"),
        "path": str(spec.value("path")) if rtype.field("path") is not None else None,
        "digipeat": bool(spec.value("digipeat")) if rtype.field("digipeat") is not None else None,
    }


def _beacon(spec: RadioSpec, beacon: RadioBeacon | None) -> dict[str, Any]:
    if beacon is None:
        return {"last_sent": None, "next_due": None, "interval_min": 0, "problem": None}
    why, params = code_of(beacon.problem)
    problem = (
        None
        if not beacon.problem
        else _problem("transmit.off")
        if why == "transmit.off"
        else _problem("beacon.not_sent", why=why, **params)
    )
    return {
        "last_sent": iso(beacon.last_sent),
        "next_due": iso(beacon.next_due),
        "interval_min": beacon.interval_min if spec.enabled else 0,
        "problem": problem,
    }


def _status(spec: RadioSpec, status: RadioStatus | None) -> dict[str, Any]:
    last, due, minutes = (None, None, 0) if status is None or spec.removed else status.on_radio(spec.id)
    return {"last_sent": iso(last), "next_due": iso(due), "interval_min": minutes}


def _problem(what: str, **params: Param) -> dict[str, Any]:
    """Return a RadioProblem row: a code and its parameters (not a refusal)."""
    return RadioProblem.row(None, code=what, params=params)


def problem_row(health: RadioHealth) -> dict[str, Any] | None:
    """Return the row's problem: the decision's code and parameters, or None."""
    return None if health.code is None else _problem(health.code, **health.params)
