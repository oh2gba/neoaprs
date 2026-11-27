"""The WebSocket client's inflating of compressed messages (neoaprs/websocketclient.py)."""

import pytest

from neoaprs.websocketclient import Inflater, WebSocketError


def test_a_compressed_message_that_does_not_inflate_is_a_websocket_error() -> None:
    with pytest.raises(WebSocketError):
        Inflater("permessage-deflate").message(b"\xff\xfe not deflate at all")
