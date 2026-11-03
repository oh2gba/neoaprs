"""The commands of the HF radio's Tune and keying test (neoaprs/web/tncwire.py: `hf_tune`, `hf_key_test`), answered by the modem part (neoaprs/mercurymodem.py) through Mercury's own TUNE command, and of its Allow button (`hf_allow_firewall`). Registered with the
dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there."""
from neoaprs.coded import CodedError
from neoaprs.config import can_transmit

from .dispatch import Ctx, UserError, command
from .tncwire import HfAllowFirewall, HfKeyTest, HfScope, HfTune


def _may_transmit(ctx: Ctx, name: str) -> None:
    """The transmit interlock as every other transmission has it: receive only, and a call that may be sent under (a tone with no identification is a transmission too)."""
    config = ctx.ctl.config
    if not config.station_transmit:
        raise UserError(f"{name}: RX only: nothing is sent", "transmit.off")
    if reason := can_transmit(config):
        raise UserError(f"{name}: {reason}")


@command(HfTune)
async def hf_tune(ctx: Ctx, cmd: HfTune) -> None:
    """The tune tone on (`on`) or off; refused while RX only is ticked, while the HF radio is not the Mercury modem running, and while a frame is on the air or the channel is busy."""
    if not cmd.on:
        await ctx.ctl.mercury.tune_stop()
        return
    _may_transmit(ctx, "hf_tune")
    try:
        await ctx.ctl.mercury.tune()
    except CodedError as e:
        raise UserError(f"hf_tune: {e}", e.code, params=e.params) from None


@command(HfKeyTest)
async def hf_key_test(ctx: Ctx, cmd: HfKeyTest) -> None:
    """Keys the radio for a second with next to no audio; the same refusals as `hf_tune`."""
    _may_transmit(ctx, "hf_key_test")
    try:
        await ctx.ctl.mercury.key_test()
    except CodedError as e:
        raise UserError(f"hf_key_test: {e}", e.code, params=e.params) from None


@command(HfAllowFirewall)
async def hf_allow_firewall(ctx: Ctx, cmd: HfAllowFirewall) -> None:
    """Makes the Windows Firewall rule that keeps the network from Mercury and, when it does, starts the HF radio the usual way. Nothing is answered with an error: what did not happen is in the log and the status line."""
    if await ctx.ctl.mercury.allow_firewall():
        ctx.ctl.start_hf()


@command(HfScope)
async def hf_scope(ctx: Ctx, cmd: HfScope) -> None:
    """This page wants the pictures of the HF radio's audio (or no more of them); nothing is refused, since a page asks when it shows the scope and the modem may not be up yet."""
    if ctx.scope is not None:
        ctx.scope.ask(ctx.conn, cmd.on)
