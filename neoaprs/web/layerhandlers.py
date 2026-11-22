"""Command handler for `layer_look`: a page starts or stops looking at a map layer.

Imported by api.py, not handlers.py, because handlers.py may not import the layers
(tests/test_architecture.py).
"""
from .dispatch import Ctx, command
from .layerwire import LayerLook


@command(LayerLook)
async def layer_look(ctx: Ctx, cmd: LayerLook) -> None:
    # Never refused: a look at a layer with no source is kept and served once a source is chosen.
    if ctx.layers is not None:
        ctx.layers.look(ctx.conn, cmd.layer, cmd.on)
