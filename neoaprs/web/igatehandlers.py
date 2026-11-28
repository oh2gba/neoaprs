"""Command handler for `igate_look`: a page starts or stops looking at the lines put on APRS-IS.

Importing this module registers it; handlers.py imports it.
"""

from .dispatch import Ctx, command
from .igatewire import IgateLook


@command(IgateLook)
async def igate_look(ctx: Ctx, cmd: IgateLook) -> None:
    # Never refused: a look while Send what I hear is off is answered with the (empty) list.
    if ctx.igate is not None:
        ctx.igate.look(ctx.conn, cmd.on)
