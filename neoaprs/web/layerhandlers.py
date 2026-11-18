"""The command of the map's layers of traffic (neoaprs/web/layerwire.py): `layer_look`, by which a page says it looks at a layer or no more (neoaprs/web/layerfeed.py). Registered with the dispatcher by being
imported in neoaprs/web/api.py (neoaprs/web/handlers.py may not import a module of the layers: tests/test_architecture.py, the wall)."""
from .dispatch import Ctx, command
from .layerwire import LayerLook


@command(LayerLook)
async def layer_look(ctx: Ctx, cmd: LayerLook) -> None:
    """Never refused: a look at a layer whose source is none stands, and is served once a source is chosen."""
    if ctx.layers is not None:
        ctx.layers.look(ctx.conn, cmd.layer, cmd.on)
