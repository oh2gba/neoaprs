"""What goes over the WebSocket: `hello`, `status`, the topics the page follows, and the commands of the page. See PROTOCOL.md. Every time is UTC ISO 8601.

The Api is the wiring of neoaprs/web/: it makes the hub and its topics (neoaprs/web/hub.py, neoaprs/web/topics.py) and the publisher (neoaprs/web/outbound.py), runs the status that is told every 10 s, opens and closes the pages
and gives each command a page sends to the dispatcher (neoaprs/web/dispatch.py, the handlers in neoaprs/web/handlers.py).
"""
import asyncio
import json
import logging
from typing import Any

from neoaprs import VERSION
from neoaprs.clock import iso
from neoaprs.controller import Controller
from neoaprs.tasks import TaskSet

from . import handlers  # noqa: F401  (importing the module registers the handlers)
from .dispatch import Dispatcher
from .hub import StateHub
from .hubwire import PROTOCOL
from .outbound import Publisher
from .processmeter import ProcessMeter
from .session import Client, Connection
from .topics import Topics

log = logging.getLogger("neoaprs.web")

STATUS_EVERY_SEC = 10.0


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


class Api:
    def __init__(self, controller: Controller, validate_out: bool | None = None) -> None:
        self.ctl = controller
        self.out = Publisher(validate_out)
        self.clients = self.out.connections             # the open pages, by their sockets
        self.hub = StateHub()
        self.topics = Topics(controller, self.hub, self._packet_sent)
        self.dispatcher = Dispatcher(controller, self.hub, self.status)
        self.started_at = controller.clock()
        self.meter = ProcessMeter()
        self.tasks = TaskSet(self._task_failed)

    @staticmethod
    def _task_failed(task: "asyncio.Task[Any]") -> None:
        log.error("web task %s failed: %r", task.get_name(), task.exception())

    # ---- lifecycle
    async def start(self) -> None:
        await self.topics.start()
        self.tasks.spawn(self._status_every_so_often(), "web-status")

    async def stop(self) -> None:
        self.hub.stop()
        self.topics.disconnect()
        await self.tasks.cancel_all()

    # ---- what the daemon is
    async def status(self) -> dict[str, Any]:
        c, beacon, rig = self.ctl.config, self.ctl.beacon, self.ctl.rigstatus
        cpu_percent, rss_mb = self.meter.sample()
        return {"type": "status", "version": VERSION, "started_at": iso(self.started_at), "packets": await self.ctl.packetlog.count(), "stations": len(self.ctl.stationbook),
                "call": c.station_call, "lat": c.station_lat, "lon": c.station_lon,
                "beacon_interval_min": c.beacon_interval_min, "beacon_last_sent": iso(beacon.last_sent), "beacon_next_due": iso(beacon.next_due),
                "station_status": rig.last_text, "rig_state": rig.rig_state,
                "cpu_percent": cpu_percent, "rss_mb": rss_mb, "uptime_sec": int((self.ctl.clock() - self.started_at).total_seconds())}

    def _packet_sent(self) -> None:
        """A packet of ours went out (the beacon, from the timer or a page): the pages are told the new status now, not at the next ten seconds."""
        if self.clients:
            self.tasks.spawn(self._tell_all(), "web-status")

    async def _tell_all(self) -> None:
        self.out.broadcast(await self.status())

    async def _status_every_so_often(self) -> None:
        while True:
            await asyncio.sleep(STATUS_EVERY_SEC)
            if self.clients:
                self.out.broadcast(await self.status())

    # ---- the pages
    def attach(self, client: Client, ip: str = "127.0.0.1") -> None:
        """A page opened: it is sent `hello`, every topic whole (it follows them from then on) and `status` (which waits for the database to count the packets)."""
        conn = self.out.open(client, ip)
        conn.send({"type": "hello", "protocol": PROTOCOL, "version": VERSION, "topics": list(self.hub.topics)})
        self.hub.attach(conn)
        self.tasks.spawn(self._tell_status(conn), "web-status")

    async def _tell_status(self, conn: Connection) -> None:
        conn.send(await self.status())

    def detach(self, client: Client) -> None:
        conn = self.clients.get(client)
        if conn is not None:
            self.hub.detach(conn)
        self.out.close(client)

    # ---- the commands
    def on_command(self, client: Client, text: str) -> None:
        conn = self.clients.get(client)
        if conn is None:                                          # the page left meanwhile
            return
        try:
            raw = json.loads(text, parse_constant=_no_constant)
        except (ValueError, RecursionError) as e:
            conn.error(f"That is not JSON ({str(e)[:80]})")
            return
        if not isinstance(raw, dict):
            conn.error("A command is a JSON object with a \"cmd\"")
            return
        self.tasks.spawn(self._run(conn, raw), "web-command")

    async def _run(self, conn: Connection, raw: dict[str, Any]) -> None:
        await self.dispatcher.run(conn, raw)
