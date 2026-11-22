"""Value of the topic `skeds` (model in skedwire.py)."""
from datetime import datetime
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.skeds import Sked
from neoaprs.versions import Frequency


class SkedSource(Protocol):
    @property
    def state(self) -> str: ...
    @property
    def fetched_at(self) -> datetime | None: ...
    @property
    def ours(self) -> frozenset[str]: ...

    def rows(self) -> list[Sked]: ...
    def frequencies(self) -> list[Frequency]: ...


def skeds_state(skeds: SkedSource) -> dict[str, Any]:
    """Return the topic value; `from` and `to` are the wire names of the start and end."""
    ours = skeds.ours
    return {"state": skeds.state, "fetched_at": iso(skeds.fetched_at), "frequencies": [{"band": f.band, "dial": f.dial} for f in skeds.frequencies()],
            "rows": [{"id": s.id, "call": s.call, "from": iso(s.start), "to": iso(s.end), "dial": s.dial, "note": s.note, "ours": s.id in ours} for s in skeds.rows()]}
