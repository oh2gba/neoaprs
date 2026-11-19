"""The settings of the pairs of radios (aprs-reference/cross-radio-digipeat-plan.md section 4.1): rows of the station's table under `pair/<low>/<high>/enabled` and `pair/<low>/<high>/ssid`, the pair's
call made of the station's base call and its SSID, and the rules a save holds them to. `PairFields` is a base of `Config`."""
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
_KEY = re.compile(r"pair/([1-9][0-9]*)/([1-9][0-9]*)/(enabled|ssid)")
_DEFAULT_TEXT = {"enabled": "false", "ssid": ""}       # the text of each field of a pair that has no row
_SSID = int_in(1, MAX_SSID)


@dataclass(frozen=True)
class PairSpec:
    """One pair of radios, as its rows say: its two radios by id (low < high), whether it passes, and its SSID (None while none is chosen)."""
    low: RadioId
    high: RadioId
    enabled: bool = False
    ssid: int | None = None

    def has(self, radio: RadioId) -> bool:
        return radio in (self.low, self.high)

    def other(self, radio: RadioId) -> RadioId:
        """The radio of the pair that is not this one."""
        return self.high if radio == self.low else self.low


@dataclass(frozen=True)
class PairFields:
    """The field of `Config` that the pairs' rows are."""
    pairs: tuple[PairSpec, ...] = ()      # every pair with a stored row, by (low, high)


class PairError(CodedError):
    """A pair's value that a save refuses: `key` is the one it is about (set_config makes a SettingError of it)."""

    def __init__(self, text: str, code: str, *, key: str, **params: Param) -> None:
        super().__init__(text, code, **params)
        self.key = key


def pair_key(a: RadioId, b: RadioId, field: str) -> str:
    """The row of the field of the pair of these two radios, whichever order they come in: `pair/<low>/<high>/<field>`."""
    return f"pair/{min(a, b)}/{max(a, b)}/{field}"


def pair_key_of(key: str) -> tuple[RadioId, RadioId, str] | None:
    """The two radios (low, high) and the field a pair key names; None for a key that is no pair key (low not below high among them)."""
    found = _KEY.fullmatch(key)
    if found is None or int(found[1]) >= int(found[2]):
        return None
    return int(found[1]), int(found[2]), found[3]


def default_of(key: str) -> str:
    """The text of a pair key that has no row: `false` for the Enable, empty for the SSID."""
    found = pair_key_of(key)
    return "" if found is None else _DEFAULT_TEXT[found[2]]


def _set(spec: PairSpec, field: str, text: str) -> PairSpec:
    """The pair with the field set from its text: the Enable a boolean, the SSID 1 to 15 or empty (None); CodedError as the settings' parsers raise it."""
    if field == "enabled":
        return replace(spec, enabled=boolean(text))
    return replace(spec, ssid=None if not text.strip() else _SSID(text))


def pairs_from_rows(rows: Mapping[str, str]) -> tuple[PairSpec, ...]:
    """The pairs that have a row among the station's rows, by (low, high); a wrong value is logged with its key and the field keeps its default."""
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
    """Both rows of each pair as text: `true` or `false`, and the SSID (`12`) or empty."""
    rows: dict[str, str] = {}
    for spec in pairs:
        rows[pair_key(spec.low, spec.high, "enabled")] = "true" if spec.enabled else "false"
        rows[pair_key(spec.low, spec.high, "ssid")] = "" if spec.ssid is None else str(spec.ssid)
    return rows


def changed_rows(before: Iterable[PairSpec], after: Iterable[PairSpec]) -> dict[str, str]:
    """The rows of `after` whose text differs from what `before` says (a pair `before` has not is its defaults): what a save writes."""
    was = rows_of(before)
    return {key: text for key, text in rows_of(after).items() if was.get(key, default_of(key)) != text}


def pair_of(pairs: Iterable[PairSpec], a: RadioId, b: RadioId) -> PairSpec:
    """The pair of these two radios as it is stored, else its defaults."""
    low, high = min(a, b), max(a, b)
    return next((spec for spec in pairs if (spec.low, spec.high) == (low, high)), PairSpec(low, high))


def may_pair(a: RadioSpec, b: RadioSpec) -> bool:
    """Whether the two radios may form a pair: two radios, both live, both of a type that transmits, and both Dummy or both real."""
    return a.id != b.id and not a.removed and not b.removed and transmits(a) and transmits(b) and a.rtype.dummy == b.rtype.dummy


def offered(radios: Iterable[RadioSpec]) -> list[tuple[RadioId, RadioId]]:
    """Every two live radios that may pair, by (low, high)."""
    specs = sorted((spec for spec in radios if not spec.removed), key=lambda spec: spec.id)
    return [(a.id, b.id) for i, a in enumerate(specs) for b in specs[i + 1:] if may_pair(a, b)]


def pair_values(radios: Iterable[RadioSpec], pairs: Iterable[PairSpec]) -> dict[str, str]:
    """Both keys of every pair the radios may form, with the stored text or the default: what the topic `config` tells beside the radios' own settings."""
    stored = tuple(pairs)
    return rows_of(pair_of(stored, low, high) for low, high in offered(radios))


def pair_defaults(radios: Iterable[RadioSpec]) -> dict[str, str]:
    """The same keys as pair_values with their defaults."""
    return rows_of(PairSpec(low, high) for low, high in offered(radios))


def _station_ssid(station_call: str) -> int:
    """The SSID of the station call; 0 for none, and for a call that does not parse."""
    try:
        return parse_call(station_call)[1]
    except CallsignError:
        return 0


def call_of(station_call: str, ssid: int | None) -> str:
    """The pair's call: the station's base call with the pair's SSID (`OH2GBA-12`); empty while the station call does not parse or the pair has no SSID."""
    try:
        base = parse_call(station_call)[0]
    except CallsignError:
        return ""
    return "" if ssid is None else format_call(base, ssid)


def own_calls(station_call: str, pairs: Iterable[PairSpec]) -> tuple[str, ...]:
    """The station call and the call of every enabled pair, each once; an empty one is left out."""
    calls = [station_call, *(call_of(station_call, spec.ssid) for spec in pairs if spec.enabled)]
    return tuple(dict.fromkeys(call for call in calls if call))


def _taken(station_call: str, pairs: Iterable[PairSpec], pair: tuple[RadioId, RadioId]) -> set[int]:
    """The SSIDs another pair may not have: the station call's, and those of the enabled pairs other than `pair`."""
    return {_station_ssid(station_call), *(spec.ssid for spec in pairs if spec.enabled and spec.ssid is not None and (spec.low, spec.high) != pair)}


def free_ssid(station_call: str, pairs: Iterable[PairSpec], pair: tuple[RadioId, RadioId]) -> int | None:
    """The highest SSID from 15 down that is neither the station's nor that of another enabled pair; None when every one is taken."""
    taken = _taken(station_call, pairs, pair)
    return next((ssid for ssid in range(MAX_SSID, 0, -1) if ssid not in taken), None)


def _shown(station_call: str, ssid: int) -> str:
    """The pair call a refusal names: `-12` while the station has no call."""
    return call_of(station_call, ssid) or f"-{ssid}"


def _checked_radios(key: str, radios: Sequence[RadioSpec], low: RadioId, high: RadioId) -> None:
    """A pair of a radio that only receives, or of a Dummy radio and a real one, is refused under `key` (the radios are there: confighandlers refused any other)."""
    specs = [spec for id in (low, high) for spec in radios if spec.id == id]
    for spec in specs:
        if not transmits(spec):
            name = log_name(spec, radios)
            raise PairError(f"{key}: radio {name} only receives", "pair.receive_only", key=key, name=name)
    if len({spec.rtype.dummy for spec in specs}) > 1:
        raise PairError(f"{key}: a Dummy radio and a real one make no pair", "pair.dummy_and_real", key=key)


def _put(radios: Sequence[RadioSpec], found: dict[tuple[RadioId, RadioId], PairSpec], values: Mapping[str, str]) -> tuple[set[tuple[RadioId, RadioId]], set[tuple[RadioId, RadioId]]]:
    """The values put into `found`, each checked in the order of the refusals' table (no pair key, a radio that only receives, a Dummy radio beside a real one, then each value's own parse); the pairs whose
    SSID was sent with a value, and those whose SSID was sent empty."""
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


def _refuse_named(station_call: str, found: Mapping[tuple[RadioId, RadioId], PairSpec], named: set[tuple[RadioId, RadioId]], filled: set[tuple[RadioId, RadioId]]) -> None:
    """An SSID sent for an enabled pair that is the station's own, or that another enabled pair keeps (one whose SSID this save chooses again moves), is refused under its key."""
    for pair in sorted(named):
        spec = found[pair]
        if not spec.enabled or spec.ssid is None:
            continue
        key, call = pair_key(*pair, "ssid"), _shown(station_call, spec.ssid)
        if spec.ssid == _station_ssid(station_call):
            raise PairError(f"{key}: {call} is the station's own call", "pair.call_is_station", key=key, call=call)
        if spec.ssid in _taken("", (other for other in found.values() if (other.low, other.high) not in filled), pair):
            raise PairError(f"{key}: {call} is the call of another pair", "pair.call_taken", key=key, call=call)


def _moving(station_call: str, pairs: Iterable[PairSpec], found: Mapping[tuple[RadioId, RadioId], PairSpec], candidates: set[tuple[RadioId, RadioId]]) -> set[tuple[RadioId, RadioId]]:
    """Of the pairs this save leaves enabled with no SSID sent, those that get a new one: no SSID stored, or the stored one is the station's before the save, or that of a pair enabled before the save
    (or of a pair of these that comes first and keeps it). The others keep the SSID they hold."""
    enabled = [spec for spec in pairs if spec.enabled and spec.ssid is not None]
    holding: set[int] = set()
    moving: set[tuple[RadioId, RadioId]] = set()
    for pair in sorted(candidates):
        ssid = found[pair].ssid
        if ssid is None or ssid == _station_ssid(station_call) or ssid in holding or any(spec.ssid == ssid for spec in enabled if (spec.low, spec.high) != pair):
            moving.add(pair)
        else:
            holding.add(ssid)
    return moving


def _fill(station_call: str, found: dict[tuple[RadioId, RadioId], PairSpec], filled: set[tuple[RadioId, RadioId]]) -> None:
    """Each of the `filled` pairs that has no SSID, or one that is not free, gets the highest free one (its Enable is refused when none is)."""
    for pair in sorted(filled):
        spec = found[pair]
        others = [other for other in found.values() if (other.low, other.high) not in filled or other.ssid is not None]
        if spec.ssid is None or spec.ssid in _taken(station_call, others, pair):
            if (ssid := free_ssid(station_call, others, pair)) is None:
                key = pair_key(*pair, "enabled")
                raise PairError(f"{key}: every SSID from 1 to 15 is taken", "pair.no_free_call", key=key)
            found[pair] = replace(spec, ssid=ssid)


def with_pair_values(station_call: str, radios: Sequence[RadioSpec], pairs: tuple[PairSpec, ...], values: Mapping[str, str], *, was_call: str | None = None) -> tuple[PairSpec, ...]:
    """`pairs` with these pair keys put in, checked: a key that is no pair key, a radio that only receives, a Dummy radio beside a real one, a value that is none of the field's, and an SSID sent that is the
    station's or another enabled pair's are refused (PairError). A pair the values name that the save leaves enabled with no SSID sent (an empty one keeps the stored SSID) gets the highest free SSID from 15
    down when it has none stored, or the stored one is the station's (`was_call`, the station call before the save; `station_call` when not given) or another pair's before the save; a pair whose stored SSID
    is free keeps it, so a save that takes that SSID is refused. When none is free, its Enable is refused. A pair the values do not name is never changed; a pair left at its defaults that had no row gets none."""
    found = {(spec.low, spec.high): spec for spec in pairs}
    named, emptied = _put(radios, found, values)
    for pair in emptied:
        if found[pair].enabled:
            found[pair] = replace(found[pair], ssid=next((spec.ssid for spec in pairs if (spec.low, spec.high) == pair), None))
    touched = {(found_key[0], found_key[1]) for key in values if (found_key := pair_key_of(key)) is not None}
    filled = _moving(station_call if was_call is None else was_call, pairs, found, {pair for pair in touched - named if found[pair].enabled})
    _refuse_named(station_call, found, named, filled)
    _fill(station_call, found, filled)
    stored = {(spec.low, spec.high) for spec in pairs}
    return tuple(found[pair] for pair in sorted(found) if pair in stored or found[pair] != PairSpec(*pair))


def call_refusal(station_call: str, pairs: Iterable[PairSpec]) -> PairError | None:
    """`setting.call_of_pair` under station/call when the station call's SSID is that of an enabled pair; None when it is none's."""
    ssid = _station_ssid(station_call)
    if ssid and any(spec.enabled and spec.ssid == ssid for spec in pairs):
        call = station_call
        return PairError(f"station/call: {call} is the call of a pair of your radios", "setting.call_of_pair", key="station/call", call=call)
    return None


def without_radio(pairs: Iterable[PairSpec], radio: RadioId) -> tuple[PairSpec, ...]:
    """The pairs that do not have this radio (it was removed)."""
    return tuple(spec for spec in pairs if not spec.has(radio))
