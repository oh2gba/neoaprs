"""A small HTTP server of a test, served on a thread of its own."""
import socketserver
import threading

ACCEPT_SEC = 1.0


def serve(server: socketserver.BaseServer) -> threading.Thread:
    """Start `serve_forever` on a daemon thread and return the thread.

    The listening socket gets a time limit first: a connection that is gone between `serve_forever`
    asking whether one waits and taking it would leave `accept` blocked forever, and `shutdown` with
    it.
    """
    # Every server of the tests is a TCPServer, which has the socket.
    server.socket.settimeout(ACCEPT_SEC)  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
