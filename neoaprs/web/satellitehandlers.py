"""Command handler for `satellite_look`: a page starts, changes or stops looking at the satellites layer.

Imported by api.py, not handlers.py, because handlers.py may not import the layers
(tests/test_architecture.py).
"""

from .dispatch import Ctx, command
from .satellitewire import SatelliteLook


@command(SatelliteLook)
async def satellite_look(ctx: Ctx, cmd: SatelliteLook) -> None:
    # Never refused: a look before the file has come is kept and served once it does.
    if ctx.satellites is not None:
        ctx.satellites.look(ctx.conn, cmd.on, frozenset(cmd.cards))
