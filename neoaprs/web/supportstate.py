"""`state.json` of the support bundle: what the running daemon knows now, the state that a bundle made from the data folder alone cannot have (neoaprs/cli/supportmake.py). It is the values the page is told, built the same way
(neoaprs/web/views.py): the radio with its latest lines, the GPS, the beacon, the base map, the update, and beside them the serial ports with who holds them and what the process costs.

`live_state` runs on the loop, where the parts are read; the ports are listed in a thread."""
import asyncio
import logging
import os
import threading
from dataclasses import asdict
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.config import can_transmit
from neoaprs.controller import Controller
from neoaprs.radios import hf_is_mercury
from neoaprs.serialholders import held_by
from neoaprs.serialprobe import available_ports

from .api import Api
from .mapview import map_state
from .processmeter import resident_mb
from .secureside import SecureSide
from .updatewire import UpdateState
from .views import gps_state, tnc_state

log = logging.getLogger("neoaprs.web")


class LiveHost(Protocol):
    """What the state of the running daemon is read from: the WebServer."""
    controller: Controller
    api: Api
    address: str
    secure: SecureSide

    def bound_port(self) -> int: ...


def ports_with_holders() -> list[dict[str, Any]]:
    """The serial ports the system lists now, and who has each open (Linux; empty elsewhere). Nothing is opened."""
    return [{"device": p.device, "description": p.description, "hwid": p.hwid, "vid": p.vid, "pid": p.pid, "held_by": held_by(p.device)} for p in available_ports()]


def beacon_state(server: LiveHost) -> dict[str, Any]:
    ctl = server.controller
    beacon, c = ctl.beacon, ctl.config
    return {"interval_min": c.beacon_interval_min, "mobile": c.mobile, "last_sent": iso(beacon.last_sent), "last_reason": beacon.last_reason, "next_due": iso(beacon.next_due),
            "problem": beacon.problem, "transmit_blocked": can_transmit(c)}


def daemon_state(server: LiveHost) -> dict[str, Any]:
    ctl, api = server.controller, server.api
    now = ctl.clock()
    return {"pid": os.getpid(), "started_at": iso(api.started_at), "uptime_sec": int((now - api.started_at).total_seconds()), "rss_mb": resident_mb(), "threads": threading.active_count(),
            "tasks": len(asyncio.all_tasks()), "pages_open": len(api.clients), "database": None if ctl.db is None else ctl.db.stats()}


async def live_state(server: LiveHost) -> dict[str, Any]:
    ctl = server.controller
    rig, secure = ctl.rigstatus, server.secure.state.wire()
    state: dict[str, Any] = {
        "made_at": iso(ctl.clock()),
        "daemon": daemon_state(server),
        "web": {"address": server.address or "every interface", "port": server.bound_port(), "network": ctl.config.web_network, "https": secure},
        "tnc": tnc_state(ctl.tnc),
        "gps": gps_state(ctl.config, ctl.gps, ctl.beacon.mobile, ctl.beacon.next_due),
        "beacon": beacon_state(server),
        "rig": {"state": rig.rig_state, "last_text": rig.last_text, "last_sent": iso(rig.last_sent_at)},
        "map": map_state(ctl.mapfetch.status(), ctl.aloha.radius_km),
        "update": {"latest": None if ctl.updatecheck.latest is None else asdict(ctl.updatecheck.latest), "now": UpdateState.row(ctl.selfupdate.status())},
    }
    state["ports"] = await asyncio.to_thread(ports_with_holders)
    state["hf"] = await hf_state(ctl)
    return state


async def hf_state(ctl: Controller) -> dict[str, Any]:
    """The HF radio: its settings, its Tnc and, while it is the Mercury modem, every sound card Mercury lists (name, directions, id), so that a report says which device is the radio's even when the setting
    names one (the daemon lists them only when it chooses: OH2GAX's reports of 3 Nov 2026 had ids and no names)."""
    c = ctl.config
    try:
        cards = await asyncio.to_thread(ctl.mercury.sound_cards) if hf_is_mercury(c) else []
    except Exception:                                    # (a nice-to-have of the report: the bundle goes without it)
        log.exception("the sound cards could not be listed for the support report")
        cards = []
    return {"enabled": c.hf_enabled, "profile": c.hf_profile, "sound_card": c.mercury_sound_card, "keying": c.mercury_keying, "tnc": tnc_state(ctl.hf),
            "sound_cards": [{"name": s.name, "id": s.id, "records": s.capture, "plays": s.playback, "default": s.default} for s in cards]}
