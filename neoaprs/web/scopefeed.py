"""The pages that have the HF radio's scope open (`hf_scope`, neoaprs/web/tncwire.py): each is sent the rows of the waterfall the modem part makes (neoaprs/mercuryscoping.py) while it asks, and the modem is told whether any page
wants them, so that they are made only while one is looked at. A row is a binary frame (neoaprs/mercuryscope.py `row_frame`); a page whose socket holds more than the hub's `BEHIND` of what it has not read is sent no row, which it
would only add to the wait. A page that leaves is forgotten."""
from neoaprs.mercurymodem import Mercury
from neoaprs.mercuryscope import ScopeRow, row_frame

from .hub import BEHIND
from .session import Connection


class ScopeFeed:
    def __init__(self, modem: Mercury) -> None:
        self._modem = modem
        self._pages: set[Connection] = set()

    @property
    def pages(self) -> int:
        return len(self._pages)

    def ask(self, conn: Connection, on: bool) -> None:
        """This page wants the rows (or no more of them). A page that has left meanwhile is not taken (its command ran after it closed: the command is a task, and the close came in the same read)."""
        if on and conn.closed:
            return
        (self._pages.add if on else self._pages.discard)(conn)
        self._modem.want_scope(bool(self._pages))

    def forget(self, conn: Connection) -> None:
        """The page left."""
        if conn in self._pages:
            self.ask(conn, False)

    def row(self, row: ScopeRow) -> None:
        """A row of the waterfall of the modem part, sent as a binary frame to every page that asked and is not behind."""
        if not self._pages:
            return
        data = row_frame(row)
        for conn in list(self._pages):
            if conn.buffered() <= BEHIND:
                conn.send_binary(data)
