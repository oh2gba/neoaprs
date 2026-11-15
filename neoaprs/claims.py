"""The resources the radios and the station hold, as one table (plan §2, "Resources"): a serial port, a sound card, a keying line's port, a Mercury port pair, the GPS receiver's port. A claim is the value in
force, whether named in the settings, remembered from the last search, or chosen by the daemon; every search, every choice of the daemon's and every proposal to the page leaves out what the others hold
(`held_by_others`). The values are normalised by the adapter that names them (a device's resolved path, a sound card's id, the broadcast port of a Mercury pair as text), so equal text is the same thing.

A serial device is one resource whatever it is used for: a radio's port, a keying line (rts:/dtr: on that port) and the GPS receiver's port are claims of `PORT_KINDS`, and a claim of one of them is refused
while another holder has the same device as any of them, and is left out of a search for any of them. One holder may use one device in two ways (its claims are kept apart, so it lets go of one kind alone).

The rule of the station's serial devices, stated here once: a device that an enabled radio is set to (its port, its keying line's port) is that radio's, whether its line has opened it yet or not (it is unplugged,
waits its back-off, or starts a moment after another radio). The table reads those settings through `named` (the radio registry sets it: serialprobe.named_ports of the settings in force), and `others` gives what is
held by another or named by another's settings: what every search, Find my radio and the daemon's own choices leave out. A claim is still held only by its holder's open (or its choice): a named device is left out
by the others, never held for its radio, so that two radios stored with one port do not lock each other out.

One table for the station: the radio registry holds it. One search at a time is not here (it is a lock of the loop: RadioRegistry.search_lock). No I/O."""
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .radiotype import RadioId, ResourceKind
from .signal import Signal

PORT_KINDS: frozenset[ResourceKind] = frozenset({"serial", "keying", "gps"})     # the kinds whose value is a serial device: one device, whichever the use


@dataclass(frozen=True)
class Claim:
    kind: ResourceKind
    value: str                       # normalised by the adapter that names it
    holder: RadioId | None           # the radio that holds it; None: the station (the GPS receiver)


def _same_kind(a: ResourceKind, b: ResourceKind) -> bool:
    """Whether a value of the one kind and the same value of the other are one resource."""
    return a == b or (a in PORT_KINDS and b in PORT_KINDS)


class Claims:
    def __init__(self) -> None:
        self.changed: Signal[[]] = Signal("claims.changed")          # a claim was held or released
        self._held: list[Claim] = []                                   # in the order they were held
        self.named: Callable[[], Iterable[Claim]] = tuple              # the serial devices the settings in force name for the enabled radios, each as its radio's claim (not held: `others` reads them); set by the radio registry
        self.name_of: Callable[[RadioId], str] = lambda id: f"radio {id}"     # what the log calls a radio (the registry's name_of), for the words of who holds a device

    def hold(self, claim: Claim) -> Claim | None:
        """Holds the resource for the claim's holder: None when it is held now (or this claim was already); the other holder's claim when another holds the resource, and then nothing changes."""
        other = next((c for c in self._held if c.holder != claim.holder and c.value == claim.value and _same_kind(c.kind, claim.kind)), None)
        if other is not None:
            return other
        if claim not in self._held:
            self._held.append(claim)
            self.changed.emit()
        return None

    def release(self, holder: RadioId | None, kind: ResourceKind | None = None) -> None:
        """Lets go of what the holder holds: of this kind, or everything when no kind is named."""
        kept = [c for c in self._held if not (c.holder == holder and (kind is None or c.kind == kind))]
        if len(kept) != len(self._held):
            self._held = kept
            self.changed.emit()

    def holder_of(self, kind: ResourceKind, value: str) -> RadioId | None:
        """Who holds the resource: a radio's id, or None for the station and for a resource nobody holds (`all` tells the two apart)."""
        return next((c.holder for c in self._held if c.value == value and _same_kind(c.kind, kind)), None)

    def held_by_others(self, holder: RadioId | None, kind: ResourceKind) -> frozenset[str]:
        """The values of this kind that are anyone's but `holder`'s (`others`: held, or for a serial device named by another enabled radio's settings): what its search, a choice of the daemon's for it, or a
        proposal to the page leaves out."""
        return frozenset(self.others(holder, kind))

    def others(self, holder: RadioId | None, kind: ResourceKind, named: bool = True) -> dict[str, RadioId | None]:
        """The values of this kind that are another's, with whose: held by another holder (for a serial device, as any of PORT_KINDS), then, with `named`, the serial devices another enabled radio is set to
        and has not opened (the rule at the top). Without `named`, only what is held: what a radio that is set to a device itself may not open."""
        found = {c.value: c.holder for c in self._held if c.holder != holder and _same_kind(c.kind, kind)}
        for c in self.named() if named and kind in PORT_KINDS else ():
            if c.holder != holder and _same_kind(c.kind, kind):
                found.setdefault(c.value, c.holder)
        return found

    def words(self, holder: RadioId | None) -> str:
        """Who holds a resource, as the log and the Terminal say it: the radio's name ("FM 2"), or "the GPS receiver" for the station's own claim."""
        return "the GPS receiver" if holder is None else self.name_of(holder)

    def all(self) -> tuple[Claim, ...]:
        """Every claim, in the order it was held."""
        return tuple(self._held)
