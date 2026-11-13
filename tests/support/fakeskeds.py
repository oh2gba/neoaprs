"""A small stand-in for the sked server of the project (server/neo/api/v1/skeds.php and the file skeds.json), on a free port of the loopback: no test reaches the real one.

    server = await skeds_server()                       # no board yet: GET /skeds.json is a 404, as before the first post
    monkeypatch.setenv("NEOAPRS_SKEDS_URL", server.url)
    server.rows = [...]                                 # the board's rows, as the server writes them (id, call, from, to, dial, note)
    server.raw = b"<html>"                              # sent for the board instead of the JSON
    server.refuse = ("rate", 429)                       # every post is refused with this reason and status
    server.posts                                        # every request body posted, as the JSON the daemon sent
    server.gets                                         # every request line of a GET, with its headers
It keeps what it was told: an add is a row of the board with the token that posted it, a remove with another token is `not_yours`, the answer carries the board as the real server's does."""
import asyncio
import json
from typing import Any

from tests.support.env import remember_stop
from tests.support.loopbackserver import LoopbackServer


class FakeSkeds(LoopbackServer):
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] | None = None          # None: no board yet
        self.closed = False
        self.raw: bytes | None = None
        self.refuse: tuple[str, int] | None = None
        self.owners: dict[str, str] = {}                        # id -> the token that posted it
        self.posts: list[dict[str, Any]] = []
        self.gets: list[tuple[str, dict[str, str]]] = []
        self.counter = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/skeds.json"

    def board(self) -> dict[str, Any]:
        return {"v": 1, "written": "2026-11-13T17:02:11Z", "closed": self.closed, "skeds": self.rows or []}

    def _answer(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.posts.append(body)
        if self.refuse is not None:
            return self.refuse[1], {"ok": False, "reason": self.refuse[0]}
        rows = self.rows if self.rows is not None else []
        if body.get("action") == "add":
            self.counter += 1
            ident = f"{self.counter:012x}"
            rows.append({"id": ident, "call": body["call"], "from": body["from"], "to": body["to"], "dial": body["dial"], "note": body.get("note", "")})
            self.owners[ident] = body["token"]
            self.rows = sorted(rows, key=lambda r: (r["from"], r["id"]))
            return 200, {"ok": True, "id": ident, "board": self.board()}
        if body.get("action") == "remove":
            if any(r["id"] == body["id"] for r in rows) and self.owners.get(body["id"]) != body["token"]:           # (a row nobody here posted is nobody's: the moderator's)
                return 403, {"ok": False, "reason": "not_yours"}
            self.rows = [r for r in rows if r["id"] != body["id"]]
            return 200, {"ok": True, "board": self.board()}
        return 400, {"ok": False, "reason": "bad_request"}

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
            headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
            body = await reader.readexactly(int(headers.get("content-length", "0")))
            method, path = head[0].split(" ")[:2]
            if method == "POST":
                status, data = self._answer(json.loads(body))
                sent = json.dumps(data).encode()
            else:
                self.gets.append((head[0], headers))
                status = 404 if self.rows is None else 200
                sent = self.raw if self.raw is not None else json.dumps(self.board()).encode()
            writer.write(f"HTTP/1.0 {status} X\r\nContent-Type: application/json\r\nContent-Length: {len(sent)}\r\n\r\n".encode() + sent)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()


async def skeds_server() -> FakeSkeds:
    """A started fake sked server, stopped when the test is over."""
    server = await FakeSkeds().start()
    remember_stop(server.stop)
    return server
