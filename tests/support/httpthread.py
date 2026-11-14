"""A small HTTP server of a test, served on a thread of its own."""
import socketserver
import threading

ACCEPT_SEC = 1.0


def serve(server: socketserver.BaseServer) -> threading.Thread:
    """Starts `serve_forever` on a daemon thread and gives the thread back. The listening socket gets a time limit first: `serve_forever` asks whether a connection waits and then takes it, and a connection
    that is gone between the two leaves a listening socket without a limit in `accept` for ever, where `shutdown` then waits for ever too (seen once, 14 November 2026: the suite in the container stood
    still in a fixture's teardown). With a limit the wait ends, the server looks again, and the sockets it hands out are without a limit as before."""
    server.socket.settimeout(ACCEPT_SEC)        # type: ignore[attr-defined]     # (every server of the tests is a TCPServer, which has the socket)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
