"""What goes over the WebSocket: `hello`, `status`, the topics and the commands (see PROTOCOL.md).

The Api wires neoaprs/web/ together: it makes the hub, the topics and the publisher, broadcasts the
status every 10 s, opens and closes pages and passes each command to the dispatcher.
"""
import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from neoaprs import VERSION
from neoaprs.beaconrule import station_interval
from neoaprs.clock import iso
from neoaprs.controller import Controller
from neoaprs.radioregistry import unavailable_types
from neoaprs.tasks import TaskSet, every

from . import handlers, layerhandlers  # noqa: F401  (importing the modules registers the handlers)
from .dispatch import Dispatcher
from .hub import StateHub
from .hubwire import PROTOCOL
from .outbound import Publisher
from .pageerrors import PageErrors
from .processmeter import ProcessMeter
from .session import Client, Connection
from .topics import Topics

log = logging.getLogger("neoaprs.web")

STATUS_EVERY_SEC = 10.0


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


class Api:
    def __init__(self, controller: Controller, validate_out: bool | None = None, reach: Callable[[], list[str]] = list, secure: Callable[[], dict[str, Any]] | None = None, page: str = "") -> None:
        self.ctl = controller
        self.page = page  # build of the served page, sent in hello
        self.out = Publisher(validate_out)
        self.clients = self.out.connections  # open pages by socket
        self.hub = StateHub()
        self.topics = Topics(controller, self.hub, self._packet_sent, reach, secure, tell=self.out.broadcast)
        self.page_errors = PageErrors(controller.clock)
        self.dispatcher = Dispatcher(controller, self.hub, self.status, page_errors=self.page_errors, scopes=self.topics.scopes, levels=self.topics.levels, layers=self.topics.layers)
        self.started_at = controller.clock()
        self.meter = ProcessMeter()
        self.tasks = TaskSet(log, "web")

    # lifecycle
    async def start(self) -> None:
        await self.topics.start()
        self.tasks.spawn(every(STATUS_EVERY_SEC, self._status_round, "the status broadcast"), "web-status")

    async def stop(self) -> None:
        self.hub.stop()
        self.page_errors.stop()
        self.topics.disconnect()
        await self.tasks.cancel_all()

    # status
    async def status(self) -> dict[str, Any]:
        c, rig = self.ctl.config, self.ctl.rigstatus
        sent = [at for radio in self.ctl.radios.all() if (at := radio.beacon.last_sent) is not None]
        due = [at for radio in self.ctl.radios.beaconing() if (at := radio.beacon.next_due) is not None]
        cpu_percent, rss_mb = self.meter.sample()
        return {"type": "status", "version": VERSION, "started_at": iso(self.started_at), "packets": await self.ctl.packetlog.count(), "stations": len(self.ctl.stationbook),
                "call": c.station_call, "lat": c.station_lat, "lon": c.station_lon,
                "beacon_interval_min": station_interval(c.beacon_interval_min, c.radios), "beacon_last_sent": iso(max(sent, default=None)), "beacon_next_due": iso(min(due, default=None)),
                "unheard_radio": c.unheard_radio, "email_radio": None if (email := self.ctl.radios.email()) is None else email.id, "unavailable_types": list(unavailable_types()),
                "new_object_radios": list(self.ctl.ownobjects.new_radios()), "new_bulletin_radios": list(self.ctl.ownbulletins.new_radios()),
                "station_status": rig.last_text, "station_status_last_sent": iso(rig.last_sent_at), "rig_state": rig.rig_state,
                "update": None if (latest := self.ctl.updatecheck.latest) is None else {"version": latest.version, "url": latest.url, "message": latest.message},
                # A key file left from a run with encryption on counts for nothing while it is off.
                "message_key": self.ctl.keyring.fingerprint() if self.ctl.keyring.enabled else "",
                "cpu_percent": cpu_percent, "rss_mb": rss_mb, "uptime_sec": int((self.ctl.clock() - self.started_at).total_seconds())}

    def _packet_sent(self) -> None:
        """Broadcast the status now, after a packet of ours went out or the radios changed."""
        if self.clients:
            self.tasks.spawn(self._tell_all(), "web-status")

    async def _tell_all(self) -> None:
        self.out.broadcast(await self.status())

    async def _status_round(self) -> None:
        if self.clients:
            self.out.broadcast(await self.status())

    # pages
    def attach(self, client: Client, ip: str = "127.0.0.1", local: bool = False) -> None:
        """Send a new page `hello`, every topic whole and `status`.

        `local` is True for a page on this computer.
        """
        conn = self.out.open(client, ip)
        conn.local = local
        conn.send({"type": "hello", "protocol": PROTOCOL, "version": VERSION, "page": self.page, "install": asdict(self.ctl.install), "local": local, "topics": list(self.hub.topics)})
        self.hub.attach(conn)
        self.tasks.spawn(self._tell_status(conn), "web-status")

    async def _tell_status(self, conn: Connection) -> None:
        conn.send(await self.status())

    def detach(self, client: Client) -> None:
        conn = self.clients.get(client)
        if conn is not None:
            self.hub.detach(conn)
            self.page_errors.forget(conn)
            self.topics.scopes.forget(conn)
            self.topics.levels.forget(conn)
            self.topics.layers.forget(conn)
        self.out.close(client)

    # commands
    def on_command(self, client: Client, text: str) -> None:
        conn = self.clients.get(client)
        if conn is None:  # the page left meanwhile
            return
        try:
            raw = json.loads(text, parse_constant=_no_constant)
        except (ValueError, RecursionError) as e:
            conn.error(f"That is not JSON ({str(e)[:80]})", code="not_json")
            return
        if not isinstance(raw, dict):
            conn.error("A command is a JSON object with a \"cmd\"", code="not_object")
            return
        self.tasks.spawn(self._run(conn, raw), "web-command")

    async def _run(self, conn: Connection, raw: dict[str, Any]) -> None:
        await self.dispatcher.run(conn, raw)
