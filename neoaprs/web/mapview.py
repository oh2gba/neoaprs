"""Value of the topic `map` (models in mapwire.py and layerwire.py)."""

from collections.abc import Iterable, Mapping
from typing import Any

from neoaprs.clock import iso
from neoaprs.layerthing import LayerState
from neoaprs.mapstate import Estimate, MapError, MapFile, MapStatus


def _file(file: MapFile | None) -> dict[str, Any] | None:
    if file is None:
        return None
    return {
        "name": file.name,
        "bytes": file.bytes,
        "modified": iso(file.modified),
        "bbox": list(file.bbox) if file.bbox else None,
        "min_zoom": file.min_zoom,
        "max_zoom": file.max_zoom,
        "build": file.build,
    }


def _estimate(estimate: Estimate | None) -> dict[str, Any] | None:
    if estimate is None:
        return None
    return {
        "bytes": estimate.bytes,
        "tiles": estimate.tiles,
        "radius_km": estimate.radius_km,
        "maxzoom": estimate.maxzoom,
        "box": list(estimate.box),
        "build": estimate.build,
    }


def _problem(problem: MapError | None) -> dict[str, Any] | None:
    return None if problem is None else {"code": problem.problem, "params": dict(problem.params)}


def layer_row(state: LayerState) -> dict[str, Any]:
    """Return a traffic layer as `MapLayer` has it; the receiver's address is left out."""
    receiver = (
        None
        if state.receiver is None
        else {"state": state.receiver.state, "things": state.receiver.things, "heard_at": iso(state.receiver.heard_at)}
    )
    return {
        "layer": state.layer,
        "source": state.source,
        "offered": list(state.offered),
        "receiver": receiver,
        "problem": state.problem,
    }


def map_state(
    status: MapStatus, aloha: Mapping[int, float] | None = None, layers: Iterable[LayerState] = ()
) -> dict[str, Any]:
    """Return the topic value; `aloha` maps radio id to its ALOHA circle radius."""
    return {
        "state": status.state,
        "step": status.step,
        "percent": status.percent,
        "downloaded": status.downloaded,
        "retry": None if status.retry is None else {"attempt": status.retry[0], "tries": status.retry[1]},
        "blocked": status.blocked_code,
        "problem": _problem(status.failure),
        "estimate": _estimate(status.estimate),
        "radius_km": status.radius_km,
        "maxzoom": status.maxzoom,
        "box": list(status.box) if status.box else None,
        "detail": _file(status.detail),
        "world": _file(status.world),
        "later": status.later,
        "aloha": [{"radio": radio, "km": km} for radio, km in (aloha or {}).items()],
        "layers": [layer_row(state) for state in layers],
    }
