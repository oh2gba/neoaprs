"""Command handler of the chat: `chat_say`."""

from neoaprs.callsign import call_problem
from neoaprs.coded import CodedError, code_of

from .chatwire import ChatSay
from .dispatch import Ctx, UserError, command


@command(ChatSay)
async def chat_say(ctx: Ctx, cmd: ChatSay) -> None:
    # Not a transmission, so RX only does not matter; an unusable call is refused as the interlock does.
    if reason := call_problem(ctx.ctl.config.station_call):
        why, params = code_of(reason)
        raise UserError(f"{cmd.cmd}: nothing is sent: {reason}", "transmit.call", params={"why": why, **params})
    try:
        await ctx.ctl.chat.say(cmd.text)
    except CodedError as e:
        raise UserError(f"{cmd.cmd}: {e}", e.code, params=e.params) from None
