"""The radios on the wire: the row of the topic `radios` (neoaprs/web/tncwire.py `RadioRow`) made from a radio of the settings, what the registry runs of it and the station's table of resources; and the
devices a radio's settings name, as that table holds them (for the row's problem and for the refusal of a save that names a device another holds, neoaprs/web/confighandlers.py). Split from
neoaprs/web/views.py, whose `modem_state` it shares."""
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from neoaprs.claims import PORT_KINDS, Claims
from neoaprs.clock import iso
from neoaprs.config import RX_ONLY_REASONS
from neoaprs.loraboard import TEXT_LINES
from neoaprs.radiospec import RadioSpec, log_name, number_in_kind
from neoaprs.radiotype import RadioId, RadioType, RadioTypeError, ResourceKind
from neoaprs.serialprobe import claim_value, keying_device
from neoaprs.source import Source
from neoaprs.tnc import Tnc
from neoaprs.tncwatchdog import TncStats as LineStats

from .tncwire import RadioProblem, RadioRow, TncStats
from .views import LINES_MAX, modem_state
from .wirebase import plain


class RadioBeacon(Protocol):
    """What the topic `radios` reads of a radio's beacon (services/beacon.py)."""
    @property
    def last_sent(self) -> datetime | None: ...
    @property
    def next_due(self) -> datetime | None: ...
    @property
    def interval_min(self) -> int: ...
    @property
    def problem(self) -> str: ...


class RadioAtWork(Protocol):
    """What the topic `radios` reads of a radio at run time (radioregistry.LiveRadio): its line and its beacon."""
    @property
    def line(self) -> Tnc: ...
    @property
    def beacon(self) -> RadioBeacon: ...


def radio_row(spec: RadioSpec, specs: Sequence[RadioSpec], radio: RadioAtWork | None, claims: Claims) -> dict[str, Any] | None:
    """The page's row of a radio of the settings, a removed one too (`radio` is None for one the registry does not run: its line, beacon and modem say nothing); None for one of a type that is none (a row a newer program wrote)."""
    try:
        rtype = spec.rtype
    except RadioTypeError:
        return None
    line = None if radio is None or spec.removed else radio.line
    lines = [] if line is None else [{"at": iso(at), "text": text} for at, text in line.recent_lines(LINES_MAX)]
    return RadioRow.row(
        spec, enabled=spec.enabled and not spec.removed, number=number_in_kind(spec, specs), removed=spec.removed, dummy=rtype.dummy, state=radio_state(line),
        problem=radio_problem(spec, specs, line, claims), stats=TncStats.row(LineStats() if line is None else line.stats), lines=lines, limits={"max_frame": rtype.limits.max_frame, "beacon_min_min": rtype.limits.beacon_min_min},
        allowed=plain(rtype.allowed), can=plain(rtype.can), choices=_choices(spec, rtype), beacon=_beacon(spec, None if radio is None or spec.removed else radio.beacon),
        modem=None if line is None else modem_state(line), holds=[{"resource": c.kind, "value": c.value} for c in claims.all() if c.holder == spec.id])


def radio_state(line: Tnc | None) -> str:
    """The state of a radio's row: its line's; `connecting` while a TNC is being put into KISS mode and sends nothing yet (the entry sent, no KISS frame since, and the line not yet usable: its settling
    time, a command mode not yet answered), as any radio that is starting says; `stopped` for one the registry does not run. A line that is usable is `connected`, its first KISS frame or not: the page sends
    on it as the daemon does (a Kenwood or Kantronics TNC is silent in KISS mode until it hears a packet)."""
    if line is None:
        return Source.State.STOPPED.value
    if line.state is Source.State.CONNECTED and line.entering_kiss and not line.usable:
        return Source.State.CONNECTING.value
    return line.state.value


def _choices(spec: RadioSpec, rtype: RadioType) -> dict[str, Any]:
    has = {key: rtype.field(key) is not None for key in ("beacon", "path", "digipeat")}            # (the type's fields: a text monitor has no path and does not digipeat)
    return {"beacon": bool(spec.value("beacon")) if has["beacon"] else True, "path": str(spec.value("path")) if has["path"] else None, "digipeat": bool(spec.value("digipeat")) if has["digipeat"] else None}


def _beacon(spec: RadioSpec, beacon: RadioBeacon | None) -> dict[str, Any]:
    if beacon is None:
        return {"last_sent": None, "next_due": None, "interval_min": 0, "problem": None}
    problem = None if not beacon.problem else _problem("transmit.off") if beacon.problem in RX_ONLY_REASONS else _problem("beacon.not_sent", reason=beacon.problem)
    return {"last_sent": iso(beacon.last_sent), "next_due": iso(beacon.next_due), "interval_min": beacon.interval_min if spec.enabled else 0, "problem": problem}


def _problem(what: str, **params: str | int) -> dict[str, Any]:
    """A RadioProblem of the row: the code (one of RadioProblemCode) and the values of its sentence. Not a refusal: scripts/errorcodes.py leaves it out of the page's list of refusals."""
    return RadioProblem.row(None, code=what, params=params)


def radio_problem(spec: RadioSpec, specs: Sequence[RadioSpec], line: Tnc | None, claims: Claims) -> dict[str, Any] | None:
    """Why an enabled radio is not connected, as a code (RadioProblem): a device it is set to use that another holds, its modem's reason, a silent line, a search, else not connected; for one that is connected
    only a LoRa board that sends text lines, which takes nothing until it is set to KISS (`radio.text_lines`); None while it is connected otherwise, off or removed."""
    if line is None or spec.removed or not spec.enabled:
        return None
    if line.state is Source.State.CONNECTED:
        return _problem("radio.text_lines") if line.why_unusable() == TEXT_LINES else None
    if (held := _held_elsewhere(spec, specs, spec.rtype, claims)) is not None:
        return held
    modem = modem_state(line)
    if modem is not None and modem.get("test"):
        return None                                              # (Tune or the keying test has the radio: the box shows the test, never a problem; a sound-card modem's line is down meanwhile)
    if modem is not None and modem["state"] == "waiting" and modem["reason"]:
        return _problem(f"modem.{modem['reason']}")
    if line.state is Source.State.SILENT:
        return _problem("radio.silent", since=iso(line.silent_since) or "")
    if line.searching:
        return _problem("radio.searching")
    return _problem("radio.not_connected", name=log_name(spec, specs))


def claimed_value(kind: str, text: str) -> str:
    """The value a radio's setting holds in the station's table of resources (claims.py): a serial port as its claim compares it, the port of a keying on a serial line (vox and cm108 hold none), a sound card as
    it is named; "" for none."""
    return (claim_value(keying_device(text) if kind == "keying" else text) or "") if kind in PORT_KINDS else text.strip()     # (a serial device as serialprobe.device_claims reads it: one rule)


def devices(spec: RadioSpec) -> list[tuple[str, ResourceKind, str]]:
    """The devices the radio's settings name, as the station's table holds them: each field's key, the kind of device and its value; none for a field left empty and for a radio of a type that is none."""
    try:
        fields = spec.rtype.fields
    except RadioTypeError:
        return []
    found = ((f.key, f.claims, claimed_value(f.claims, spec.settings.get(f.key, f.default))) for f in fields if f.claims)
    return [(key, kind, value) for key, kind, value in found if kind is not None and value]


def one_device(a: ResourceKind, b: ResourceKind) -> bool:
    """Whether a value of the one kind and the same value of the other are one device (a serial port, whatever it is used for: claims.PORT_KINDS)."""
    return a == b or (a in PORT_KINDS and b in PORT_KINDS)


def removed_name(id: RadioId, specs: Sequence[RadioSpec]) -> str | None:
    """The log's name of the radio of the id while the settings keep it as removed; None for a radio that is not removed, or none."""
    spec = next((s for s in specs if s.id == id), None)
    return None if spec is None or not spec.removed else log_name(spec, specs)


def holder_id(holder: RadioId | None, specs: Sequence[RadioSpec]) -> RadioId:
    """Who holds a device, as the ports' `held_by` says it: the radio's id, 0 for the GPS receiver (or a holder that is no radio of the settings)."""
    return holder if holder is not None and any(s.id == holder for s in specs) else 0


def holder_name(holder: RadioId | None, specs: Sequence[RadioSpec]) -> str:
    """The name of who holds a device, as the refusals and the problems say it: the radio's log name, `GPS` for the receiver (or a holder that is no radio of the settings)."""
    named = next((s for s in specs if s.id == holder), None)
    return "GPS" if named is None else log_name(named, specs)


def held_elsewhere(spec: RadioSpec, specs: Sequence[RadioSpec], claims: Claims) -> tuple[str, str, str, RadioId] | None:
    """The first device the radio's settings name that another radio or the GPS receiver holds: its field's key, the kind of device, the holder's name (`GPS` for the receiver) and its id (0 for the receiver);
    None when none is."""
    for key, kind, value in devices(spec):
        holder = next((c for c in claims.all() if c.holder != spec.id and c.value == value and one_device(c.kind, kind)), None)
        if holder is not None:
            return key, kind, holder_name(holder.holder, specs), holder_id(holder.holder, specs)
    return None


def _held_elsewhere(spec: RadioSpec, specs: Sequence[RadioSpec], rtype: RadioType, claims: Claims) -> dict[str, Any] | None:
    """`radio.resource_held` for the first device the radio's settings name that another holds, with the holder's name and id; None when none is."""
    held = held_elsewhere(spec, specs, claims)
    return None if held is None else _problem("radio.resource_held", resource=held[1], holder=held[2], held_by=held[3])
