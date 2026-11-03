"""The pages that have the HF radio's scope open (`hf_scope`, neoaprs/web/tncwire.py): each is sent the pictures the modem part makes (neoaprs/mercuryscoping.py) while it asks, and the modem is told whether any page wants
them, so that the pictures are made only while one is looked at. A page that leaves is forgotten."""
from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import ScopeFrame

from .session import Connection


class ScopeFeed:
    def __init__(self, modem: Mercury) -> None:
        self._modem = modem
        self._pages: set[Connection] = set()

    @property
    def pages(self) -> int:
        return len(self._pages)

    def ask(self, conn: Connection, on: bool) -> None:
        """This page wants the pictures (or no more of them)."""
        (self._pages.add if on else self._pages.discard)(conn)
        self._modem.want_scope(bool(self._pages))

    def forget(self, conn: Connection) -> None:
        """The page left."""
        if conn in self._pages:
            self.ask(conn, False)

    def frame(self, frame: ScopeFrame, tx: bool) -> None:
        """A picture of the modem part, told to every page that asked."""
        message = {"type": "hf_scope", "bins": list(frame.bins), "level": frame.level, "tx": tx}
        for conn in list(self._pages):
            conn.send(message)
