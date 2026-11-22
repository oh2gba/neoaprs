"""The resources the radios and the station hold, as one table.

Resources are serial ports, sound cards, keying lines, Mercury port pairs and the GPS port.
A claim is the value in force; searches leave out what others hold. No I/O.
"""
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .radiotype import RadioId, ResourceKind
from .signal import Signal

# The kinds whose value is a serial device: one device whatever the use.
PORT_KINDS: frozenset[ResourceKind] = frozenset({"serial", "keying", "gps"})


@dataclass(frozen=True)
class Claim:
    kind: ResourceKind
    value: str  # normalised by the adapter that names it
    holder: RadioId | None  # the radio that holds it; None: the station (GPS receiver)


def _same_kind(a: ResourceKind, b: ResourceKind) -> bool:
    """Whether a value of the one kind and the same value of the other are one resource."""
    return a == b or (a in PORT_KINDS and b in PORT_KINDS)


class Claims:
    def __init__(self) -> None:
        self.changed: Signal[[]] = Signal("claims.changed")  # a claim was held or released
        self._held: list[Claim] = []  # in the order they were held
        # Serial devices the settings name for enabled radios (set by the registry); named
        # devices are left out for others but never held, so radios stored with one port coexist.
        self.named: Callable[[], Iterable[Claim]] = tuple
        self.name_of: Callable[[RadioId], str] = lambda id: f"radio {id}"

    def hold(self, claim: Claim) -> Claim | None:
        """Hold the resource for the claim's holder.

        Return None if held now (or already), else the other holder's claim and change nothing.
        """
        other = next((c for c in self._held if c.holder != claim.holder and c.value == claim.value and _same_kind(c.kind, claim.kind)), None)
        if other is not None:
            return other
        if claim not in self._held:
            self._held.append(claim)
            self.changed.emit()
        return None

    def release(self, holder: RadioId | None, kind: ResourceKind | None = None) -> None:
        """Release what the holder holds: one kind, or everything when no kind is given."""
        kept = [c for c in self._held if not (c.holder == holder and (kind is None or c.kind == kind))]
        if len(kept) != len(self._held):
            self._held = kept
            self.changed.emit()

    def holder_of(self, kind: ResourceKind, value: str) -> RadioId | None:
        """Return the holder: a radio's id, or None for the station or an unheld resource."""
        return next((c.holder for c in self._held if c.value == value and _same_kind(c.kind, kind)), None)

    def held_by_others(self, holder: RadioId | None, kind: ResourceKind) -> frozenset[str]:
        """Return the values of this kind held, or named, by anyone but `holder`."""
        return frozenset(self.others(holder, kind))

    def others(self, holder: RadioId | None, kind: ResourceKind, named: bool = True) -> dict[str, RadioId | None]:
        """Return the values of this kind that belong to another holder, with whose.

        Held values count; with `named`, so do serial devices another enabled radio is set to.
        """
        found = {c.value: c.holder for c in self._held if c.holder != holder and _same_kind(c.kind, kind)}
        for c in self.named() if named and kind in PORT_KINDS else ():
            if c.holder != holder and _same_kind(c.kind, kind):
                found.setdefault(c.value, c.holder)
        return found

    def words(self, holder: RadioId | None) -> str:
        """Return who holds a resource as the log says it: a radio's name, or the GPS receiver."""
        return "the GPS receiver" if holder is None else self.name_of(holder)

    def all(self) -> tuple[Claim, ...]:
        """Every claim, in the order it was held."""
        return tuple(self._held)
