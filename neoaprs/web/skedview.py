"""The topic `skeds` as the page is told it (neoaprs/web/skedwire.py): the state of the board, the dials the project suggests, and the skeds to come by the daemon's clock."""
from datetime import datetime
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.skeds import Sked
from neoaprs.versions import Frequency


class SkedSource(Protocol):
    """What of the sked service the topic reads."""
    @property
    def state(self) -> str: ...
    @property
    def fetched_at(self) -> datetime | None: ...
    @property
    def ours(self) -> frozenset[str]: ...

    def rows(self) -> list[Sked]: ...
    def frequencies(self) -> list[Frequency]: ...


def skeds_state(skeds: SkedSource) -> dict[str, Any]:
    """The value of the topic: `from` and `to` are the wire's own names of the two times."""
    ours = skeds.ours
    return {"state": skeds.state, "fetched_at": iso(skeds.fetched_at), "frequencies": [{"band": f.band, "dial": f.dial} for f in skeds.frequencies()],
            "rows": [{"id": s.id, "call": s.call, "from": iso(s.start), "to": iso(s.end), "dial": s.dial, "note": s.note, "ours": s.id in ours} for s in skeds.rows()]}
