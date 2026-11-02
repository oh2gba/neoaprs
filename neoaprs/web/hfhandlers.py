"""The commands of the HF radio's Tune and keying test (neoaprs/web/tncwire.py: `hf_tune`, `hf_key_test`), answered by the modem part (neoaprs/mercurymodem.py) through Mercury's own TUNE command. Registered with the
dispatcher as the handlers of neoaprs/web/handlers.py are, by being imported there."""
from neoaprs.coded import CodedError

from .dispatch import Ctx, UserError, command
from .tncwire import HfKeyTest, HfTune


@command(HfTune)
async def hf_tune(ctx: Ctx, cmd: HfTune) -> None:
    """The tune tone on (`on`) or off; refused while RX only is ticked, while the HF radio is not the Mercury modem running, and while a frame is on the air or the channel is busy."""
    if not cmd.on:
        await ctx.ctl.mercury.tune_stop()
        return
    if not ctx.ctl.config.station_transmit:
        raise UserError("hf_tune: RX only: nothing is sent", "transmit.off")
    try:
        await ctx.ctl.mercury.tune()
    except CodedError as e:
        raise UserError(f"hf_tune: {e}", e.code, params=e.params) from None


@command(HfKeyTest)
async def hf_key_test(ctx: Ctx, cmd: HfKeyTest) -> None:
    """Keys the radio for a second with next to no audio; the same refusals as `hf_tune`."""
    if not ctx.ctl.config.station_transmit:
        raise UserError("hf_key_test: RX only: nothing is sent", "transmit.off")
    try:
        await ctx.ctl.mercury.key_test()
    except CodedError as e:
        raise UserError(f"hf_key_test: {e}", e.code, params=e.params) from None
