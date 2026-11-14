"""The WebSocket client (neoaprs/websocketclient.py) and the link to Mercury's UI interface that is made of it (neoaprs/mercuryui.py), against a fake server that speaks as Mercury's does (tests/support/fakemercuryui.py):
the handshake and its refusals, whole messages in both kinds, the commands and their answers, the spectrum feed asked for only while it is wanted, the link opened again after it dropped, and a server that is not there told
once."""
import asyncio
import logging
import struct

import pytest

from neoaprs.mercuryscope import parse_spectrum
from neoaprs.mercuryui import MercuryUi
from neoaprs.source import Backoff
from neoaprs.websocketclient import BINARY, CLOSE, PING, TEXT, WebSocketClient, WebSocketError, accept_of, frame
from tests.support.env import until
from tests.support.fakemercuryui import FakeUi

QUICK = Backoff([0.05, 0.05])


def test_the_accept_key_is_the_one_of_rfc_6455() -> None:
    assert accept_of("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_a_frame_is_final_with_its_length_in_the_shortest_form_and_masked_when_given_a_mask() -> None:
    assert frame(TEXT, b"hi") == b"\x81\x02hi"
    assert frame(BINARY, bytes(200))[:4] == b"\x82\x7e\x00\xc8"
    assert frame(BINARY, bytes(70000))[:10] == b"\x82\x7f" + struct.pack(">Q", 70000)
    masked = frame(TEXT, b"abcd", b"\x01\x02\x03\x04")
    assert masked == b"\x81\x84\x01\x02\x03\x04" + bytes(x ^ y for x, y in zip(b"abcd", b"\x01\x02\x03\x04\x01\x02\x03\x04", strict=False))


async def test_the_client_reads_text_and_binary_messages_and_sends_commands_that_are_answered() -> None:
    ui = FakeUi(status_sec=10.0)
    await ui.start()
    try:
        client = await WebSocketClient.connect("127.0.0.1", ui.port, "/websocket")
        is_text, data = await asyncio.wait_for(client.recv(), 3)  # type: ignore[misc]
        assert is_text and b'"type": "status"' in data, "the server tells its status when a client connects"
        await client.send_text('{"command": "set_tx_gain", "value": "3"}')
        assert await asyncio.wait_for(client.recv(), 3) == (True, b'{"status":"ok"}')
        await client.send_text('{"command": "nonsense"}')
        assert await asyncio.wait_for(client.recv(), 3) == (True, b'{"status":"error","code":-1}')
        await client.send_text("{")
        assert await asyncio.wait_for(client.recv(), 3) == (True, b'{"error":"malformed command JSON"}')
        await client.send_text('{"command": "set_waterfall", "value": "on"}')
        assert await asyncio.wait_for(client.recv(), 3) == (True, b'{"status":"ok"}')
        got = await asyncio.wait_for(client.recv(), 3)
        assert got is not None and not got[0] and parse_spectrum(got[1]) is not None, "then the spectrum, as binary frames"
        client.close()
        assert ui.commands == [("set_tx_gain", "3"), ("nonsense", ""), ("set_waterfall", "on")]
    finally:
        await ui.aclose()


async def raw_server(reply: bytes, then: bytes = b"") -> tuple[asyncio.Server, int]:
    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(reply + then)
        await writer.drain()
        await asyncio.sleep(0.2)
        writer.close()
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_a_server_that_does_not_upgrade_or_answers_for_another_key_is_refused() -> None:
    server, port = await raw_server(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
    with pytest.raises(WebSocketError, match="did not upgrade"):
        await WebSocketClient.connect("127.0.0.1", port)
    server.close()
    server, port = await raw_server(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: AAAA\r\n\r\n")
    with pytest.raises(WebSocketError, match="not the one for this key"):
        await WebSocketClient.connect("127.0.0.1", port)
    server.close()
    server, port = await raw_server(b"")
    with pytest.raises(WebSocketError, match="closed the connection"):
        await WebSocketClient.connect("127.0.0.1", port)
    server.close()


async def test_a_port_with_nothing_on_it_is_an_oserror() -> None:
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()
    with pytest.raises(OSError):
        await WebSocketClient.connect("127.0.0.1", port)


class Upgrading:
    """A raw server that upgrades whatever key it is sent and then writes the given frames."""

    def __init__(self, frames: bytes) -> None:
        self.frames = frames
        self.server: asyncio.Server | None = None
        self.port = 0
        self.received = b""

    async def start(self) -> None:
        async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            head = (await reader.readuntil(b"\r\n\r\n")).decode()
            key = next(line.split(":", 1)[1].strip() for line in head.split("\r\n") if line.lower().startswith("sec-websocket-key"))
            writer.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept_of(key)}\r\n\r\n".encode() + self.frames)
            await writer.drain()
            try:
                self.received = await asyncio.wait_for(reader.read(100), 1.0)
            except TimeoutError:
                pass
            writer.close()
        self.server = await asyncio.start_server(serve, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]


async def test_fragments_are_joined_a_ping_is_answered_a_close_ends_it_and_a_message_that_is_too_long_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neoaprs.websocketclient.MAX_MESSAGE", 100)
    first = b"\x01\x03abc"                                                # a text frame, not final
    last = b"\x80\x03def"                                                 # its continuation, final
    ping = b"\x89\x02hi"
    long = b"\x82\x7e" + struct.pack(">H", 300) + bytes(300)                # 300 bytes: more than the 100 allowed
    short = b"\x82\x02ok"
    close = b"\x88\x02\x03\xe8"
    server = Upgrading(first + ping + last + long + short + close)
    await server.start()
    client = await WebSocketClient.connect("127.0.0.1", server.port)
    assert await asyncio.wait_for(client.recv(), 3) == (True, b"abcdef"), "the ping between the fragments is answered and the fragments are one message"
    assert await asyncio.wait_for(client.recv(), 3) == (False, b"ok"), "the long message is skipped"
    assert await asyncio.wait_for(client.recv(), 3) is None and client.closed
    await until(lambda: len(server.received) >= 2)
    assert server.received[:2] == bytes([0x8A, 0x82]), "the pong is a masked frame, as a client's are"
    client.close()
    assert server.server is not None
    server.server.close()


async def test_a_frame_with_extension_bits_is_a_protocol_error() -> None:
    server = Upgrading(b"\xc1\x01x")
    await server.start()
    client = await WebSocketClient.connect("127.0.0.1", server.port)
    with pytest.raises(WebSocketError, match="extension"):
        await client.recv()
    client.close()
    assert server.server is not None
    server.server.close()


# ---- the link to Mercury's UI

class Link:
    def __init__(self, ui: FakeUi) -> None:
        self.texts: list[str] = []
        self.spectra = 0
        self.states: list[bool] = []
        self.ui = MercuryUi("127.0.0.1", ui.port, self.texts.append, self._binary, self.states.append, backoff=Backoff([0.05, 0.05]))

    def _binary(self, data: bytes) -> None:
        if parse_spectrum(data) is not None:
            self.spectra += 1


async def test_the_link_reads_the_status_and_asks_for_no_spectrum_until_it_is_wanted() -> None:
    fake = FakeUi(status_sec=0.05, spectrum_sec=0.02)
    await fake.start()
    link = Link(fake)
    link.ui.start()
    try:
        await until(lambda: link.ui.connected and len(link.texts) >= 2)
        assert link.states == [True] and '"tx_gain_db"' in link.texts[0]
        await until(lambda: ("set_waterfall", "off") in fake.commands)
        await asyncio.sleep(0.2)
        assert link.spectra == 0 and not fake.waterfall, "nothing is sent while nobody wants the spectrum"
        link.ui.waterfall(True)
        await until(lambda: link.spectra >= 3)
        assert fake.waterfall
        link.ui.waterfall(False)
        await until(lambda: not fake.waterfall)
        seen = link.spectra
        await asyncio.sleep(0.2)
        assert link.spectra <= seen + 1, "and none after it is switched off again"
    finally:
        await link.ui.stop()
        await fake.aclose()
    assert not link.ui.connected


async def test_the_gain_is_sent_while_the_link_is_open_and_refused_while_it_is_not() -> None:
    fake = FakeUi(status_sec=10.0)
    await fake.start()
    link = Link(fake)
    assert link.ui.tx_gain(3) is False, "not started"
    link.ui.start()
    try:
        await until(lambda: link.ui.connected)
        assert link.ui.tx_gain(-4) is True
        await until(lambda: fake.gain_db == -4.0)
        assert ("set_tx_gain", "-4") in fake.commands
    finally:
        await link.ui.stop()
        await fake.aclose()


async def test_a_link_that_dropped_is_opened_again_and_what_is_wanted_is_asked_for_again() -> None:
    fake = FakeUi(status_sec=10.0, spectrum_sec=0.02)
    await fake.start()
    link = Link(fake)
    link.ui.start()
    try:
        await until(lambda: link.ui.connected)
        link.ui.waterfall(True)
        await until(lambda: fake.waterfall)
        fake.waterfall = False                                          # (a Mercury that came up again knows nothing of it)
        fake.drop()
        await until(lambda: link.states == [True, False, True])
        await until(lambda: fake.waterfall and link.spectra > 0)
        assert fake.connections == 2
    finally:
        await link.ui.stop()
        await fake.aclose()


async def test_a_server_that_is_not_there_is_told_once_and_the_link_opens_when_it_comes(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeUi(status_sec=10.0)
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    fake.port = probe.sockets[0].getsockname()[1]
    probe.close()
    await probe.wait_closed()
    link = Link(fake)
    with caplog.at_level(logging.DEBUG, logger="neoaprs.mercury"):
        link.ui.start()
        retried = lambda: [r for r in caplog.records if r.levelno == logging.DEBUG and f"UI interface on port {fake.port}:" in r.getMessage()]  # noqa: E731
        await until(lambda: len(retried()) >= 2, 15.0)                   # (attempts, not a time: a refused connection takes Windows about 2 s, Linux none)
        told = [r for r in caplog.records if r.levelno == logging.INFO and "cannot be reached" in r.getMessage()]
        assert len(told) == 1 and not link.ui.connected and link.states == [], "one line in the log for any number of attempts"
        await fake.start()
        await until(lambda: link.ui.connected)
    await link.ui.stop()
    await fake.aclose()


async def test_a_server_that_is_no_websocket_is_the_same_as_none() -> None:
    fake = FakeUi(upgrade=False)
    await fake.start()
    link = Link(fake)
    link.ui.start()
    await asyncio.sleep(0.3)
    assert not link.ui.connected and link.states == []
    await link.ui.stop()
    await fake.aclose()


@pytest.mark.expects_errors
async def test_a_handler_that_fails_does_not_end_the_link(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeUi(status_sec=0.05)
    await fake.start()

    def broken(text: str) -> None:
        raise ValueError("nope")
    ui = MercuryUi("127.0.0.1", fake.port, broken, lambda data: None, lambda up: None, backoff=QUICK)
    ui.start()
    try:
        with caplog.at_level(logging.ERROR, logger="neoaprs.mercury"):
            await until(lambda: ui.connected)
            await until(lambda: any("could not be handled" in r.getMessage() for r in caplog.records))
        assert ui.connected and any("could not be handled" in r.getMessage() for r in caplog.records)
    finally:
        await ui.stop()
        await fake.aclose()
    caplog.clear()


def test_the_opcodes_are_the_ones_of_the_rfc() -> None:
    assert (TEXT, BINARY, CLOSE, PING) == (1, 2, 8, 9)


async def test_the_fake_ui_ends_at_once_with_a_connection_that_has_asked_for_nothing_yet() -> None:
    """The fake modem's UI server closes every connection when it ends: one that connected a moment before and has sent nothing kept a dying fake Mercury alive until the client gave up (Windows, under load)."""
    ui = FakeUi(port=0)
    await ui.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", ui.port)
    try:
        await asyncio.sleep(0.05)                                           # the server has taken the connection and waits for its first line
        await asyncio.wait_for(ui.aclose(), 1.0)
        assert await asyncio.wait_for(reader.read(), 1.0) == b"", "the connection is closed from the server's side"
    finally:
        writer.close()
