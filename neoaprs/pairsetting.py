"""Settings of the radio pairs.

Rows `pair/<low>/<high>/enabled` and `.../ssid`; a pair's call is the base call plus its SSID.
"""

import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from .callsign import MAX_SSID, CallsignError, format_call, parse_call
from .coded import CodedError, Param
from .configtypes import boolean, int_in
from .radiospec import RadioSpec, log_name, transmits
from .radiotype import RadioId

log = logging.getLogger("neoaprs.pairsetting")

PAIR_FIELDS = ("enabled", "ssid")
_KEY = re.compile(r"pair/([1-9][0-9]{0,8})/([1-9][0-9]{0,8})/(enabled|ssid)")
_DEFAULT_TEXT = {"enabled": "false", "ssid": ""}  # a pair with no row
_SSID = int_in(1, MAX_SSID)


@dataclass(frozen=True)
class PairSpec:
    """One pair of radios as its rows say: ids (low < high), whether enabled, and its SSID."""

    low: RadioId
    high: RadioId
    enabled: bool = False
    ssid: int | None = None

    def has(self, radio: RadioId) -> bool:
        return radio in (self.low, self.high)

    def other(self, radio: RadioId) -> RadioId:
        return self.high if radio == self.low else self.low


@dataclass(frozen=True)
class PairFields:
    """The field of `Config` that the pairs' rows are."""

    pairs: tuple[PairSpec, ...] = ()  # pairs with a stored row, by (low, high)


class PairError(CodedError):
    """A pair's value that a save refuses; `key` is the setting it is about."""

    def __init__(self, text: str, code: str, *, key: str, **params: Param) -> None:
        super().__init__(text, code, **params)
        self.key = key


def pair_key(a: RadioId, b: RadioId, field: str) -> str:
    return f"pair/{min(a, b)}/{max(a, b)}/{field}"


def pair_key_of(key: str) -> tuple[RadioId, RadioId, str] | None:
    """Return (low, high, field) a pair key names; None if it is no pair key."""
    found = _KEY.fullmatch(key)
    if found is None or int(found[1]) >= int(found[2]):
        return None
    return int(found[1]), int(found[2]), found[3]


def default_of(key: str) -> str:
    found = pair_key_of(key)
    return "" if found is None else _DEFAULT_TEXT[found[2]]


def _set(spec: PairSpec, field: str, text: str) -> PairSpec:
    """Return the pair with the field set from its text; raise CodedError if the text is bad."""
    if field == "enabled":
        return replace(spec, enabled=boolean(text))
    return replace(spec, ssid=None if not text.strip() else _SSID(text))


def pairs_from_rows(rows: Mapping[str, str]) -> tuple[PairSpec, ...]:
    """Return the pairs that have a row among the station's rows; a wrong value is logged."""
    found: dict[tuple[RadioId, RadioId], PairSpec] = {}
    for key, text in rows.items():
        if (named := pair_key_of(key)) is None:
            continue
        low, high, field = named
        spec = found.get((low, high), PairSpec(low, high))
        try:
            found[(low, high)] = _set(spec, field, text)
        except ValueError as e:
            found[(low, high)] = spec
            log.warning("%s: %s; the default %s is used", key, e, _DEFAULT_TEXT[field] or "(empty)")
    return tuple(found[pair] for pair in sorted(found))


def rows_of(pairs: Iterable[PairSpec]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for spec in pairs:
        rows[pair_key(spec.low, spec.high, "enabled")] = "true" if spec.enabled else "false"
        rows[pair_key(spec.low, spec.high, "ssid")] = "" if spec.ssid is None else str(spec.ssid)
    return rows


def changed_rows(before: Iterable[PairSpec], after: Iterable[PairSpec]) -> dict[str, str]:
    """Return the rows of `after` that differ from `before` (a missing pair counts as default)."""
    was = rows_of(before)
    return {key: text for key, text in rows_of(after).items() if was.get(key, default_of(key)) != text}


def pair_of(pairs: Iterable[PairSpec], a: RadioId, b: RadioId) -> PairSpec:
    low, high = min(a, b), max(a, b)
    return next((spec for spec in pairs if (spec.low, spec.high) == (low, high)), PairSpec(low, high))


def may_pair(a: RadioSpec, b: RadioSpec) -> bool:
    """Return whether two live transmitting radios, both Dummy or both real, may form a pair."""
    return (
        a.id != b.id
        and not a.removed
        and not b.removed
        and transmits(a)
        and transmits(b)
        and a.rtype.dummy == b.rtype.dummy
    )


def offered(radios: Iterable[RadioSpec]) -> list[tuple[RadioId, RadioId]]:
    specs = sorted((spec for spec in radios if not spec.removed), key=lambda spec: spec.id)
    return [(a.id, b.id) for i, a in enumerate(specs) for b in specs[i + 1 :] if may_pair(a, b)]


def pair_values(radios: Iterable[RadioSpec], pairs: Iterable[PairSpec]) -> dict[str, str]:
    """Return both keys of every pair the radios may form, with the stored text or the default."""
    stored = tuple(pairs)
    return rows_of(pair_of(stored, low, high) for low, high in offered(radios))


def pair_defaults(radios: Iterable[RadioSpec]) -> dict[str, str]:
    return rows_of(PairSpec(low, high) for low, high in offered(radios))


def _station_ssid(station_call: str) -> int:
    """Return the SSID of the station call; 0 for none or an unparsable call."""
    try:
        return parse_call(station_call)[1]
    except CallsignError:
        return 0


def call_of(station_call: str, ssid: int | None) -> str:
    """Return the pair's call (`OH2GBA-12`); empty if the station call does not parse or no SSID."""
    try:
        base = parse_call(station_call)[0]
    except CallsignError:
        return ""
    return "" if ssid is None else format_call(base, ssid)


def own_calls(station_call: str, pairs: Iterable[PairSpec]) -> tuple[str, ...]:
    calls = [station_call, *(call_of(station_call, spec.ssid) for spec in pairs if spec.enabled)]
    return tuple(dict.fromkeys(call for call in calls if call))


def _taken(station_call: str, pairs: Iterable[PairSpec], pair: tuple[RadioId, RadioId]) -> set[int]:
    """Return the SSIDs another pair may not use."""
    return {
        _station_ssid(station_call),
        *(spec.ssid for spec in pairs if spec.enabled and spec.ssid is not None and (spec.low, spec.high) != pair),
    }


def free_ssid(station_call: str, pairs: Iterable[PairSpec], pair: tuple[RadioId, RadioId]) -> int | None:
    """Return the highest free SSID, preferably not one a disabled pair stores; None if none."""
    pairs = tuple(pairs)
    taken = _taken(station_call, pairs, pair)
    kept = {spec.ssid for spec in pairs if not spec.enabled and spec.ssid is not None and (spec.low, spec.high) != pair}
    free = [ssid for ssid in range(MAX_SSID, 0, -1) if ssid not in taken]
    return next((ssid for ssid in free if ssid not in kept), free[0] if free else None)


def _shown(station_call: str, ssid: int) -> str:
    return call_of(station_call, ssid) or f"-{ssid}"


def _checked_radios(key: str, radios: Sequence[RadioSpec], low: RadioId, high: RadioId) -> None:
    specs = [spec for id in (low, high) for spec in radios if spec.id == id]
    for spec in specs:
        if not transmits(spec):
            name = log_name(spec, radios)
            raise PairError(f"{key}: radio {name} only receives", "pair.receive_only", key=key, name=name)
    if len({spec.rtype.dummy for spec in specs}) > 1:
        raise PairError(f"{key}: a Dummy radio and a real one make no pair", "pair.dummy_and_real", key=key)


def _put(
    radios: Sequence[RadioSpec], found: dict[tuple[RadioId, RadioId], PairSpec], values: Mapping[str, str]
) -> tuple[set[tuple[RadioId, RadioId]], set[tuple[RadioId, RadioId]]]:
    """Put the values into `found`; return the pairs sent with an SSID, and those sent empty."""
    named: set[tuple[RadioId, RadioId]] = set()
    emptied: set[tuple[RadioId, RadioId]] = set()
    parts = {}
    for key in values:
        if (part := pair_key_of(key)) is None:
            raise PairError(f"{key}: no such pair setting", "setting.unknown", key=key)
        parts[key] = part
    for key, (low, high, _) in parts.items():
        _checked_radios(key, radios, low, high)
    for key, text in values.items():
        low, high, field = parts[key]
        try:
            spec = found[(low, high)] = _set(found.get((low, high), PairSpec(low, high)), field, text)
        except CodedError as e:
            raise PairError(f"{key}: {e}", e.code, key=key, **e.params) from None
        if field == "ssid":
            (named if spec.ssid is not None else emptied).add((low, high))
    return named, emptied


def _refuse_named(
    station_call: str,
    found: Mapping[tuple[RadioId, RadioId], PairSpec],
    named: set[tuple[RadioId, RadioId]],
    filled: set[tuple[RadioId, RadioId]],
) -> None:
    """Refuse an SSID sent for an enabled pair that is the station's or another pair's."""
    for pair in sorted(named):
        spec = found[pair]
        if not spec.enabled or spec.ssid is None:
            continue
        key, call = pair_key(*pair, "ssid"), _shown(station_call, spec.ssid)
        if spec.ssid == _station_ssid(station_call):
            raise PairError(f"{key}: {call} is the station's own call", "pair.call_is_station", key=key, call=call)
        if spec.ssid in _taken("", (other for other in found.values() if (other.low, other.high) not in filled), pair):
            raise PairError(f"{key}: {call} is the call of another pair", "pair.call_taken", key=key, call=call)


def _moving(
    station_call: str,
    pairs: Iterable[PairSpec],
    found: Mapping[tuple[RadioId, RadioId], PairSpec],
    candidates: set[tuple[RadioId, RadioId]],
) -> set[tuple[RadioId, RadioId]]:
    """Return the enabled pairs, sent with no SSID, whose stored SSID is missing or now taken."""
    enabled = [spec for spec in pairs if spec.enabled and spec.ssid is not None]
    holding: set[int] = set()
    moving: set[tuple[RadioId, RadioId]] = set()
    for pair in sorted(candidates):
        ssid = found[pair].ssid
        if (
            ssid is None
            or ssid == _station_ssid(station_call)
            or ssid in holding
            or any(spec.ssid == ssid for spec in enabled if (spec.low, spec.high) != pair)
        ):
            moving.add(pair)
        else:
            holding.add(ssid)
    return moving


def _fill(
    station_call: str, found: dict[tuple[RadioId, RadioId], PairSpec], filled: set[tuple[RadioId, RadioId]]
) -> None:
    """Give each of the `filled` pairs without a usable SSID the highest free one."""
    for pair in sorted(filled):
        spec = found[pair]
        others = [other for other in found.values() if (other.low, other.high) not in filled or other.ssid is not None]
        if spec.ssid is None or spec.ssid in _taken(station_call, others, pair):
            if (ssid := free_ssid(station_call, others, pair)) is None:
                key = pair_key(*pair, "enabled")
                raise PairError(f"{key}: every SSID from 1 to 15 is taken", "pair.no_free_call", key=key)
            found[pair] = replace(spec, ssid=ssid)


def with_pair_values(
    station_call: str,
    radios: Sequence[RadioSpec],
    pairs: tuple[PairSpec, ...],
    values: Mapping[str, str],
    *,
    was_call: str | None = None,
) -> tuple[PairSpec, ...]:
    """Return `pairs` with these pair keys put in, checked; raise PairError for a refusal.

    An enabled pair with no usable SSID gets the highest free one; unnamed pairs never change.
    """
    found = {(spec.low, spec.high): spec for spec in pairs}
    named, emptied = _put(radios, found, values)
    for pair in emptied:
        if found[pair].enabled:
            found[pair] = replace(
                found[pair], ssid=next((spec.ssid for spec in pairs if (spec.low, spec.high) == pair), None)
            )
    touched = {(found_key[0], found_key[1]) for key in values if (found_key := pair_key_of(key)) is not None}
    filled = _moving(
        station_call if was_call is None else was_call,
        pairs,
        found,
        {pair for pair in touched - named if found[pair].enabled},
    )
    _refuse_named(station_call, found, named, filled)
    _fill(station_call, found, filled)
    stored = {(spec.low, spec.high) for spec in pairs}
    return tuple(found[pair] for pair in sorted(found) if pair in stored or found[pair] != PairSpec(*pair))


def call_refusal(station_call: str, pairs: Iterable[PairSpec]) -> PairError | None:
    """Return a PairError if the station call's SSID is an enabled pair's."""
    ssid = _station_ssid(station_call)
    if ssid and any(spec.enabled and spec.ssid == ssid for spec in pairs):
        call = station_call
        return PairError(
            f"station/call: {call} is the call of a pair of your radios",
            "setting.call_of_pair",
            key="station/call",
            call=call,
        )
    return None


def without_radio(pairs: Iterable[PairSpec], radio: RadioId) -> tuple[PairSpec, ...]:
    return tuple(spec for spec in pairs if not spec.has(radio))
