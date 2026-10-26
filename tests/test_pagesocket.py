"""The page's WebSocket handler (neoaprs/web/pagesocket.py) on its own, behind a fake host (tests/support/fakepagehost.py): a frame that is no text, a command that raises, a push to a socket that has been
closed, a page that does not read and is cut off, and the count of what it holds. The socket in the whole daemon is in tests/test_web.py."""
import asyncio
import logging

import pytest
from tornado.websocket import WebSocketClientConnection, websocket_connect

from neoaprs.web.pagesocket import Socket, _looked_at
from tests.support.env import until
from tests.support.fakepagehost import FakePageHost, page_host


async def connected(host: FakePageHost) -> tuple[WebSocketClientConnection, Socket]:
    ws = await websocket_connect(host.url)
    await until(lambda: len(host.api.sockets) == 1)
    return ws, host.api.sockets[0]


async def test_a_text_frame_is_a_command_and_a_binary_frame_that_is_no_text_is_ignored() -> None:
    host = await page_host()
    ws, socket = await connected(host)
    await ws.write_message(b"\xff\xfe\xfd", binary=True)
    await ws.write_message(b'{"cmd": "ping"}', binary=True)                   # (a binary frame that is text is taken as text)
    await ws.write_message('{"cmd": "pong"}')
    await until(lambda: len(host.api.commands) == 2)
    assert host.api.commands == [(socket, '{"cmd": "ping"}'), (socket, '{"cmd": "pong"}')], "the one that was not text did not reach the Api, and the socket is open"
    ws.close()


async def test_a_command_that_nests_deeper_than_the_parser_can_follow_is_ignored_and_the_socket_stays_open() -> None:
    host = await page_host()
    ws, _ = await connected(host)
    host.api.fail = ("[", RecursionError())
    await ws.write_message("[" * 3000)
    await ws.write_message('{"cmd": "ping"}')
    await until(lambda: len(host.api.commands) == 1)
    assert host.api.sockets and host.api.detached == []
    ws.close()


async def test_a_push_to_a_socket_that_is_closing_is_dropped_and_the_page_is_forgotten_at_once(caplog: pytest.LogCaptureFixture) -> None:
    host = await page_host()
    ws, socket = await connected(host)
    socket.close()                                                              # the daemon's side begins to close; Tornado has not yet told the Api
    with caplog.at_level(logging.DEBUG, "neoaprs.web"):
        socket.send_json('{"type": "pong"}')
    assert host.api.detached[:1] == [socket], "forgotten now, so that the pushes that follow do not look for it"
    assert any("a push to the closed page" in r.getMessage() for r in caplog.records)
    assert await ws.read_message() is None                                      # the page sees the close, answers it, and Tornado then tells the Api again: that must do no harm
    ws.close()
    await until(lambda: len(host.api.detached) >= 2)


async def test_a_page_that_does_not_read_is_cut_off_when_its_buffer_is_full_and_the_others_are_not(caplog: pytest.LogCaptureFixture) -> None:
    host = await page_host()
    ws, socket = await connected(host)
    other = await websocket_connect(host.url)
    await until(lambda: len(host.api.sockets) == 2)
    stream = socket.ws_connection.stream                                          # type: ignore[union-attr]
    stream.max_write_buffer_size = 100
    with caplog.at_level(logging.WARNING, "neoaprs.web"):
        socket.send_json("x" * 1000)
    assert [r.getMessage() for r in caplog.records if "cut off" in r.getMessage()] == ["a page that does not read was cut off (127.0.0.1)"]
    assert stream.closed()
    assert await ws.read_message() is None, "the page sees its socket close"
    await other.write_message('{"cmd": "ping"}')
    await until(lambda: len(host.api.commands) == 1)
    assert not host.api.sockets[1].ws_connection.stream.closed()                  # type: ignore[union-attr]
    other.close()


async def test_what_the_socket_holds_that_the_page_has_not_read_is_counted_and_a_socket_without_a_stream_holds_nothing() -> None:
    host = await page_host()
    ws, socket = await connected(host)
    assert socket.buffered() == 0
    socket.ws_connection.stream._write_buffer.append(b"x" * 10)                 # type: ignore[union-attr]
    assert socket.buffered() == 10
    ws.close()
    await until(lambda: host.api.detached == [socket])                          # (the server's side is closed now)
    socket.ws_connection = None
    assert socket.buffered() == 0


async def test_the_socket_that_a_page_opens_is_a_proved_one_and_the_write_limit_is_set() -> None:
    from neoaprs.web.outbound import MAX_WRITE_BUFFER
    host = await page_host()
    ws, socket = await connected(host)
    assert host.proved == [socket.ws_connection.stream]                         # type: ignore[union-attr]
    assert socket.ws_connection.stream.max_write_buffer_size == MAX_WRITE_BUFFER    # type: ignore[union-attr]
    ws.close()


def test_the_look_at_a_write_that_was_cancelled_does_not_raise() -> None:
    loop = asyncio.new_event_loop()
    future: asyncio.Future[None] = loop.create_future()
    future.cancel()
    _looked_at(future)
    failed: asyncio.Future[None] = loop.create_future()
    failed.set_exception(ConnectionError("the page left"))
    _looked_at(failed)                                                          # (the exception is read: asyncio does not log it as never retrieved)
    loop.close()
