"""`state.json` of the support bundle: what the running daemon knows now, beyond the data folder.

The values are built as the page's topics are (views.py), plus the serial ports with their holders
and the process cost. `live_state` runs on the loop; the ports are listed in a thread.
"""

import asyncio
import logging
import os
import threading
from dataclasses import asdict
from typing import Any, Protocol

from neoaprs.clock import iso
from neoaprs.config import can_transmit
from neoaprs.controller import Controller
from neoaprs.direwolfmodem import DirewolfModem
from neoaprs.mercurymodem import Mercury
from neoaprs.serialholders import held_by
from neoaprs.serialprobe import available_ports
from neoaprs.tnc import Tnc

from .api import Api
from .mapview import map_state
from .processmeter import resident_mb
from .secureside import SecureSide
from .updatewire import UpdateState
from .tncwire import stats_row
from .views import LINES_MAX, NO_PLAN, gps_state, igate_state, modem_state

log = logging.getLogger("neoaprs.web")


class LiveHost(Protocol):
    controller: Controller
    api: Api
    address: str
    secure: SecureSide

    def bound_port(self) -> int: ...


def ports_with_holders() -> list[dict[str, Any]]:
    """Return the listed serial ports and who has each open (Linux only). Nothing is opened."""
    return [
        {
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "vid": p.vid,
            "pid": p.pid,
            "held_by": held_by(p.device),
        }
        for p in available_ports()
    ]


def beacon_state(server: LiveHost) -> dict[str, Any]:
    """Return the beacon settings.

    Also the latest send, the soonest next send and the first problem of the radios.
    """
    ctl = server.controller
    c, beacons = ctl.config, [radio.beacon for radio in ctl.radios.beaconing()]
    sent = [beacon for beacon in beacons if beacon.last_sent is not None]
    latest = max(sent, key=lambda beacon: beacon.last_sent or beacon.clock(), default=None)
    due = [at for beacon in beacons if (at := beacon.next_due) is not None]
    return {
        "interval_min": c.beacon_interval_min,
        "mobile": c.mobile,
        "last_sent": None if latest is None else iso(latest.last_sent),
        "last_reason": "" if latest is None else latest.last_reason,
        "next_due": iso(min(due, default=None)),
        "problem": next((beacon.problem for beacon in beacons if beacon.problem), ""),
        "transmit_blocked": can_transmit(c),
    }


def line_state(tnc: Tnc) -> dict[str, Any]:
    """Return a radio's line.

    State, problem, port and speed, counters, last watchdog action and latest lines.
    """
    return {
        "state": tnc.state.value,
        "problem": tnc.problem,
        "last_error": tnc.last_error,
        "path": tnc.path,
        "baud": tnc.baud,
        "dummy": tnc.is_dummy,
        "modem": modem_state(tnc),
        "readings": list(tnc.profile.readings),
        "describe": tnc.describe(),
        "searching": tnc.searching,
        "silent_since": iso(tnc.silent_since),
        "stats": stats_row(tnc.stats),
        "last_watchdog_action": tnc.last_watchdog_action,
        "last_watchdog_at": iso(tnc.last_watchdog_at),
        "lines": [{"at": iso(at), "text": text} for at, text in tnc.recent_lines(LINES_MAX)],
    }


def daemon_state(server: LiveHost) -> dict[str, Any]:
    ctl, api = server.controller, server.api
    now = ctl.clock()
    return {
        "pid": os.getpid(),
        "started_at": iso(api.started_at),
        "uptime_sec": int((now - api.started_at).total_seconds()),
        "rss_mb": resident_mb(),
        "threads": threading.active_count(),
        "tasks": len(asyncio.all_tasks()),
        "pages_open": len(api.clients),
        "database": None if ctl.db is None else ctl.db.stats(),
    }


async def live_state(server: LiveHost) -> dict[str, Any]:
    ctl = server.controller
    rig, secure = ctl.rigstatus, server.secure.state.wire()
    state: dict[str, Any] = {
        "made_at": iso(ctl.clock()),
        "daemon": daemon_state(server),
        "web": {
            "address": server.address or "every interface",
            "port": server.bound_port(),
            "network": ctl.config.web_network,
            "https": secure,
        },
        "gps": gps_state(
            ctl.config,
            ctl.gps,
            NO_PLAN if (moving := ctl.moving_beacon()) is None else moving.mobile,
            None if moving is None else moving.next_due,
        ),
        "beacon": beacon_state(server),
        "igate": igate_state(ctl.config, ctl.igate),
        "rig": {"state": rig.rig_state, "last_text": rig.last_text, "last_sent": iso(rig.last_sent_at)},
        "map": map_state(ctl.mapfetch.status(), ctl.aloha.radii),
        "layers": ctl.layers.support_rows(),
        "send_on": {
            "objects": {name: list(radios) for name, radios in ctl.ownobjects.radio_sets().items()},
            "bulletins": {slot: list(radios) for slot, radios in ctl.ownbulletins.radio_sets().items()},
        },
        "update": {
            "latest": None if ctl.updatecheck.latest is None else asdict(ctl.updatecheck.latest),
            "now": UpdateState.row(ctl.selfupdate.status()),
            "detail": ctl.selfupdate.status().detail,
        },
    }
    state["ports"] = await asyncio.to_thread(ports_with_holders)
    listed: dict[int, list[dict[str, Any]]] = {}
    state["radios"] = await radios_state(ctl, listed)
    return state


async def sound_cards(modem: Mercury | DirewolfModem, listed: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Return the sound cards the modem lists, once per report (cached in `listed`).

    A failure is logged and gives an empty list.
    """
    if id(modem) not in listed:
        try:
            cards = await asyncio.to_thread(modem.sound_cards)
        except Exception:
            log.exception("the sound cards could not be listed for the support report")
            cards = []
        listed[id(modem)] = [
            {"name": s.name, "id": s.id, "records": s.capture, "plays": s.playback, "default": s.default} for s in cards
        ]
    return listed[id(modem)]


def mercury_state(modem: Mercury, line: Tnc) -> dict[str, Any]:
    """Return what tells a deaf modem: frames heard, its stalls and restarts, its device lines."""
    stall = modem.stall
    crashed_at, crash_lines = modem.crash()
    return {
        "frames_in": line.stats.packets,
        "last_frame": iso(line.stats.last_packet),
        "snr": modem.snr,
        "capture_stalls": stall.stalls,
        "last_stall_at": iso(stall.last_stall_at),
        "restarts_for_stalls": stall.restarts,
        "last_restart_at": iso(stall.last_restart_at),
        "device_lines": modem.device_lines,
        "crashed_at": iso(crashed_at),
        "crash_lines": crash_lines,
    }


async def radios_state(ctl: Controller, listed: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Return every radio by position, with its line and beacon.

    An enabled modem radio also has its sound cards.
    """
    out: list[dict[str, Any]] = []
    for radio in ctl.radios.all():
        spec, beacon = radio.spec, radio.beacon
        entry: dict[str, Any] = {
            "id": radio.id,
            "kind": spec.kind,
            "type": spec.type,
            "name": radio.name,
            "enabled": spec.enabled,
            "tnc": line_state(radio.line),
            "beacon": {
                "last_sent": iso(beacon.last_sent),
                "last_reason": beacon.last_reason,
                "next_due": iso(beacon.next_due),
                "problem": beacon.problem,
            },
        }
        modem = radio.driver.modem
        if spec.enabled and modem is not None and radio.rtype.transport == "modem":
            entry["sound_cards"] = await sound_cards(modem, listed)
        if spec.enabled and isinstance(modem, Mercury):
            entry["mercury"] = {**mercury_state(modem, radio.line), **ctl.pskreporter.state(radio.id)}
        out.append(entry)
    return out
