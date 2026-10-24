"""The `map` topic's value, made from the map service's status (the models are in neoaprs/web/mapwire.py)."""
from typing import Any

from neoaprs.clock import iso
from neoaprs.mapstate import Estimate, MapFile, MapStatus


def _file(file: MapFile | None) -> dict[str, Any] | None:
    if file is None:
        return None
    return {"name": file.name, "bytes": file.bytes, "modified": iso(file.modified), "bbox": list(file.bbox) if file.bbox else None, "min_zoom": file.min_zoom, "max_zoom": file.max_zoom, "build": file.build}


def _estimate(estimate: Estimate | None) -> dict[str, Any] | None:
    if estimate is None:
        return None
    return {"bytes": estimate.bytes, "tiles": estimate.tiles, "radius_km": estimate.radius_km, "maxzoom": estimate.maxzoom, "box": list(estimate.box), "build": estimate.build}


def map_state(status: MapStatus, aloha_km: float | None = None) -> dict[str, Any]:
    return {"state": status.state, "step": status.step, "percent": status.percent, "downloaded": status.downloaded, "note": status.note, "blocked": status.blocked, "problem": status.problem, "estimate": _estimate(status.estimate),
            "radius_km": status.radius_km, "maxzoom": status.maxzoom, "box": list(status.box) if status.box else None, "detail": _file(status.detail), "world": _file(status.world), "aloha_km": aloha_km}
