"""The commands of the sked board (neoaprs/web/skedwire.py): `skeds_wanted`, `sked_post` and `sked_delete`, answered by the sked service (neoaprs/services/skeds.py). Registered with the dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there."""
from neoaprs.coded import CodedError
from neoaprs.callsign import call_problem
from neoaprs.skeds import clean_note, when

from .dispatch import Ctx, UserError, command
from .skedwire import SkedDelete, SkedPost, SkedsWanted


@command(SkedsWanted)
async def skeds_wanted(ctx: Ctx, cmd: SkedsWanted) -> None:
    """The page shows the Skeds tab: the board is read again if it is time (the service keeps the 15 minutes between two reads)."""
    ctx.ctl.skeds.wanted()


@command(SkedPost)
async def sked_post(ctx: Ctx, cmd: SkedPost) -> None:
    """Posts a sked of our call. It is no transmission, so RX only does not matter; a call that may not be used (none set, a placeholder) is refused as the transmit interlock does."""
    if reason := call_problem(ctx.ctl.config.station_call):
        raise UserError(f"{cmd.cmd}: {reason}")
    start, end = when(cmd.from_), when(cmd.to)
    assert start is not None and end is not None                      # (the model checked both)
    try:
        await ctx.ctl.skeds.post(start, end, cmd.dial, clean_note(cmd.note))
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None


@command(SkedDelete)
async def sked_delete(ctx: Ctx, cmd: SkedDelete) -> None:
    try:
        await ctx.ctl.skeds.delete(cmd.id)
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None
