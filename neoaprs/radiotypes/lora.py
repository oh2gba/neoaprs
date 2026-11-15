"""The LoRa APRS boards (aprs-reference/lora-plan.md section 3.2): a board whose firmware takes the LoRa packet of text apart and hands the computer KISS or TNC2 text, reached on the network (`lora-tcp`,
the kind's default: the CA2RXU iGate at home on WiFi, whose list of heard packets says each packet's signal), on USB or Bluetooth (`lora-serial`: a device, `bt://` or `ble://`), or a CA2RXU iGate's log on
USB (`lora-console`), which says each packet with its signal and takes nothing, so that the radio only receives. The "tnc" driver; the line is read by loraboard.py.

What the kind may do and cannot do is common.py's (`LORA_LIMITS`, `LORA_ALLOWED`, `LORA_PATH`). The frequency and the modem's settings are the board's own: no firmware lets a program set them safely (the
iGate takes them only on its own page, whose write replaces every setting and restarts it; KISS has no command for them), so no field is offered for them. No Find: an open may restart a board, and a board
in KISS says nothing until it hears a packet; no search either (tncprofile `search`)."""
from dataclasses import replace

from neoaprs.configvalues import host_name
from neoaprs.radiotype import Allowed, Can, Field, RadioType
from neoaprs.radiotypes.common import LORA_ALLOWED, LORA_LIMITS, LORA_PATH, fields_of
from neoaprs.radiotypes.kisstcp import TCP_HOST, TCP_PORT
from neoaprs.radiotypes.serialtnc import BAUD, PORT
from neoaprs.tncprofile import LORA_CONSOLE, LORA_SERIAL, LORA_TCP, Profile

TERMINAL = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)
LISTENS = replace(TERMINAL, transmit=False)          # a radio that only receives (`Can.transmit` False): no rule picks it to send on, and its line is never written to
NOTHING_GOES_OUT = Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False)     # a radio that only receives: no path, beacon or gateway of ours on it


def host_or_empty(text: str) -> str:
    """The board's address, or "" while none is typed: the radio then waits for it and opens nothing."""
    return host_name(text) if text.strip() else ""


BOARD_HOST = replace(TCP_HOST, parse=host_or_empty, default="")      # a board on the network is never on this computer: no address until the operator types the board's


def _board(profile: Profile, fields: tuple[Field, ...], allowed: Allowed = LORA_ALLOWED, can: Can = TERMINAL) -> RadioType:
    return RadioType(profile.key, "lora", profile.name, f"radio.type.{profile.key}", profile.transport, "tnc", profile.key, fields, LORA_LIMITS, allowed, can, dummy=False, recommended_path=LORA_PATH)


TYPES: tuple[RadioType, ...] = (
    _board(LORA_TCP, fields_of((BOARD_HOST, TCP_PORT), LORA_ALLOWED)),
    _board(LORA_SERIAL, fields_of((PORT, BAUD), LORA_ALLOWED)),
    _board(LORA_CONSOLE, fields_of((PORT, BAUD), NOTHING_GOES_OUT, transmit=False), NOTHING_GOES_OUT, LISTENS),      # (where it is reached, and nothing of what goes out: nothing does)
)
