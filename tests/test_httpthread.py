"""The helper that serves a test's small HTTP server on a thread."""
import http.server
import threading
import time
import urllib.request

from tests.support.httpthread import ACCEPT_SEC, serve


def test_the_listening_socket_has_a_limit_the_connections_have_none_and_a_shutdown_ends() -> None:
    limits: list[float | None] = []

    class Answer(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            limits.append(self.request.gettimeout())
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args: object) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    thread = serve(server)
    try:
        assert server.socket.gettimeout() == ACCEPT_SEC, "accept never waits for ever for a connection that is gone"
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/", timeout=5) as answer:     # noqa: S310
            assert answer.read() == b"ok"
        assert limits == [None], "a connection the server hands out is as it was: without a limit"
    finally:
        began = time.monotonic()
        ended = threading.Thread(target=server.shutdown, daemon=True)
        ended.start()
        ended.join(5)
        server.server_close()
    assert not ended.is_alive() and time.monotonic() - began < 5, "the shutdown ends"
    thread.join(5)
    assert not thread.is_alive()
