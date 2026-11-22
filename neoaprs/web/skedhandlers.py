"""Command handlers of the sked board: `skeds_wanted`, `sked_post` and `sked_delete`."""
from neoaprs.coded import CodedError, code_of
from neoaprs.callsign import call_problem
from neoaprs.skeds import clean_note, when

from .dispatch import Ctx, UserError, command
from .skedwire import SkedDelete, SkedPost, SkedsWanted


@command(SkedsWanted)
async def skeds_wanted(ctx: Ctx, cmd: SkedsWanted) -> None:
    # The service itself limits how often the board is read.
    ctx.ctl.skeds.wanted()


@command(SkedPost)
async def sked_post(ctx: Ctx, cmd: SkedPost) -> None:
    # Not a transmission, so RX only does not matter; an unusable call is refused as the interlock
    # does.
    if reason := call_problem(ctx.ctl.config.station_call):
        why, params = code_of(reason)
        raise UserError(f"{cmd.cmd}: nothing is sent: {reason}", "transmit.call", params={"why": why, **params})
    start, end = when(cmd.from_), when(cmd.to)
    assert start is not None and end is not None  # the model checked both
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
