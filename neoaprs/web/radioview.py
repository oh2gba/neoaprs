"""The row of the topic `radios`, from a radio's settings, live state and the resource table.

Also the devices a radio's settings name, used to refuse a save that names a device another radio
holds.
"""
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from neoaprs.cardlevels import CardLevels
from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.clock import iso
from neoaprs.coded import Param, code_of
from neoaprs.loraboard import TEXT_LINES
from neoaprs.radiospec import RadioSpec, log_name, number_in_kind
from neoaprs.radiotype import RadioId, RadioType, RadioTypeError, ResourceKind
from neoaprs.serialprobe import claim_value, keying_device
from neoaprs.source import Source
from neoaprs.tnc import Tnc
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
    def beacon(self) -> RadioBeacon: ...
    @property
    def driver(self) -> RadioCard: ...


def radio_row(spec: RadioSpec, specs: Sequence[RadioSpec], radio: RadioAtWork | None, claims: Claims, status: RadioStatus | None = None) -> dict[str, Any] | None:
    """Return the page's row of a radio, a removed one too; `radio` is None if it is not run.

    Return None for an unknown type (written by a newer program).
    """
    try:
        rtype = spec.rtype
    except RadioTypeError:
        return None
    line = None if radio is None or spec.removed else radio.line
    lines = [] if line is None else [{"at": iso(at), "text": text} for at, text in line.recent_lines(LINES_MAX)]
    card = None if line is None or radio is None else radio.driver.card
    return RadioRow.row(
        spec, enabled=spec.enabled and not spec.removed, number=number_in_kind(spec, specs), removed=spec.removed, dummy=rtype.dummy, state=radio_state(line),
        problem=radio_problem(spec, specs, line, claims), stats=stats_row(LineStats() if line is None else line.stats), lines=lines, limits={"max_frame": rtype.limits.max_frame, "beacon_min_min": rtype.limits.beacon_min_min},
        allowed=plain(rtype.allowed), can=plain(rtype.can), choices=_choices(spec, rtype), beacon=_beacon(spec, None if radio is None or spec.removed else radio.beacon),
        status=_status(spec, status),
        modem=None if line is None else modem_state(line), card=_card(card), holds=[{"resource": c.kind, "value": c.value} for c in claims.all() if c.holder == spec.id])


def _card(card: CardLevels | None) -> dict[str, Any]:
    """Return the row's sound card levels."""
    return {"tx": None, "rx": None, "read": True} if card is None else {"tx": card.levels.tx, "rx": card.levels.rx, "read": card.known}


def radio_state(line: Tnc | None) -> str:
    """Return the row's state: the line's, `connecting` in KISS entry, `stopped` if not run.

    A TNC is silent in KISS mode until it hears a packet, so usable counts as `connected` early.
    """
    if line is None:
        return Source.State.STOPPED.value
    if line.state is Source.State.CONNECTED and line.entering_kiss and not line.usable:
        return Source.State.CONNECTING.value
    return line.state.value


def _choices(spec: RadioSpec, rtype: RadioType) -> dict[str, Any]:
    """Return the radio's choices in force; a missing Send-on tick is false (beacon: true)."""
    def tick(key: str, without: bool = False) -> bool:
        return bool(spec.value(key)) if rtype.field(key) is not None else without
    return {"beacon": tick("beacon", True), "status": tick("status"), "ask": tick("ask"), "local_info": tick("local_info"),
            "path": str(spec.value("path")) if rtype.field("path") is not None else None, "digipeat": bool(spec.value("digipeat")) if rtype.field("digipeat") is not None else None}


def _beacon(spec: RadioSpec, beacon: RadioBeacon | None) -> dict[str, Any]:
    if beacon is None:
        return {"last_sent": None, "next_due": None, "interval_min": 0, "problem": None}
    why, params = code_of(beacon.problem)
    problem = None if not beacon.problem else _problem("transmit.off") if why == "transmit.off" else _problem("beacon.not_sent", why=why, **params)
    return {"last_sent": iso(beacon.last_sent), "next_due": iso(beacon.next_due), "interval_min": beacon.interval_min if spec.enabled else 0, "problem": problem}


def _status(spec: RadioSpec, status: RadioStatus | None) -> dict[str, Any]:
    last, due, minutes = (None, None, 0) if status is None or spec.removed else status.on_radio(spec.id)
    return {"last_sent": iso(last), "next_due": iso(due), "interval_min": minutes}


def _problem(what: str, **params: Param) -> dict[str, Any]:
    """Return a RadioProblem row: a code and its parameters (not a refusal)."""
    return RadioProblem.row(None, code=what, params=params)


def radio_problem(spec: RadioSpec, specs: Sequence[RadioSpec], line: Tnc | None, claims: Claims) -> dict[str, Any] | None:
    """Return why an enabled radio is not connected, as a RadioProblem code, or None.

    A connected LoRa board that sends text lines is a problem (`radio.text_lines`).
    """
    if line is None or spec.removed or not spec.enabled:
        return None
    if line.state is Source.State.CONNECTED:
        return _problem("radio.text_lines") if line.why_unusable() == TEXT_LINES else None
    if (held := _held_elsewhere(spec, specs, spec.rtype, claims)) is not None:
        return held
    modem = modem_state(line)
    if modem is not None and modem.get("test"):
        # Tune or the keying test has the radio; the line is down meanwhile.
        return None
    if modem is not None and modem["state"] == "waiting" and modem["reason"]:
        return _problem(f"modem.{modem['reason']}")
    if line.state is Source.State.SILENT:
        return _problem("radio.silent", since=iso(line.silent_since) or "")
    if line.searching:
        return _problem("radio.searching")
    return _problem("radio.not_connected", name=log_name(spec, specs))


def claimed_value(kind: str, text: str) -> str:
    """Return the value a setting holds in the resource table (claims.py); "" for none."""
    return (claim_value(keying_device(text) if kind == "keying" else text) or "") if kind in PORT_KINDS else text.strip()


def devices(spec: RadioSpec) -> list[tuple[str, ResourceKind, str]]:
    """Return (field key, device kind, value) for each non-empty device the settings name."""
    try:
        fields = spec.rtype.fields
    except RadioTypeError:
        return []
    found = ((f.key, f.claims, claimed_value(f.claims, spec.settings.get(f.key, f.default))) for f in fields if f.claims)
    return [(key, kind, value) for key, kind, value in found if kind is not None and value]


def one_device(a: ResourceKind, b: ResourceKind) -> bool:
    """Return True if the two kinds name one device (any serial port use counts as one)."""
    return a == b or (a in PORT_KINDS and b in PORT_KINDS)


def removed_name(id: RadioId, specs: Sequence[RadioSpec]) -> str | None:
    """Return the log name of a removed radio, or None if it is not removed or unknown."""
    spec = next((s for s in specs if s.id == id), None)
    return None if spec is None or not spec.removed else log_name(spec, specs)


def holder_id(holder: RadioId | None, specs: Sequence[RadioSpec]) -> RadioId:
    """Return the holder's radio id for the ports' `held_by`.

    0 for the GPS receiver or an unknown holder.
    """
    return holder if holder is not None and any(s.id == holder for s in specs) else 0


def holder_name(holder: RadioId | None, specs: Sequence[RadioSpec]) -> str:
    """Return the holder's log name, or `GPS` for the receiver or an unknown holder."""
    named = next((s for s in specs if s.id == holder), None)
    return "GPS" if named is None else log_name(named, specs)


def held_elsewhere(spec: RadioSpec, specs: Sequence[RadioSpec], claims: Claims) -> tuple[str, str, str, RadioId] | None:
    """Return (field key, device kind, holder name, holder id) for the first device another holds.

    Return None if there is none.
    """
    for key, kind, value in devices(spec):
        holder = next((c for c in claims.all() if c.holder != spec.id and c.value == value and one_device(c.kind, kind)), None)
        if holder is not None:
            return key, kind, holder_name(holder.holder, specs), holder_id(holder.holder, specs)
    return None


def _held_elsewhere(spec: RadioSpec, specs: Sequence[RadioSpec], rtype: RadioType, claims: Claims) -> dict[str, Any] | None:
    """Return a `radio.resource_held` problem for the first device held by another, else None."""
    held = held_elsewhere(spec, specs, claims)
    return None if held is None else _problem("radio.resource_held", resource=held[1], holder=held[2], held_by=held[3])
