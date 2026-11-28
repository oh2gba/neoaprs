"""What a Mercury radio's settings choose: its own sound card and keying, and what the page proposes.

The serial ports that key no other radio, and the card and keying proposed while the settings are empty.
"""

from collections.abc import Sequence

from .claims import Claims
from .config import Config
from .mercury import SerialPort, SoundCard, propose_keying, propose_sound_card
from .radiotype import HF_ID, RadioId
from .radiotypes import kind_field
from .serialprobe import PortInfo, claim_value, named_ports, offered_ports


def system_serial_ports() -> list[SerialPort]:
    """Return the machine's serial ports. For a thread."""
    return [SerialPort(p.device, p.vid, p.pid) for p in offered_ports()]


def left_out(config: Config, but: RadioId) -> tuple[str, ...]:
    """Return the serial ports that key no radio of `but` (others', remembered, GPS, skipped)."""
    named = tuple(c.value for c in named_ports(config, off_too=True) if c.holder != but)
    return tuple(
        dict.fromkeys(
            v
            for v in (
                *named,
                *(claim_value(p) for p in (config.serial_last_port, config.gps_device, *config.serial_skip_paths)),
            )
            if v
        )
    )


def own_choice(config: Config, holder: RadioId) -> tuple[str, str, int]:
    """Return the radio's own sound card, keying and gain; "", "" and 0 where it has none."""
    spec = config.radio(holder)
    if spec is None or spec.removed or kind_field(spec.kind, "sound_card") is None:
        return "", "", 0
    return str(spec.value("sound_card")), str(spec.value("keying")), int(spec.value("tx_gain_db"))


def proposal(
    cards: Sequence[SoundCard],
    ports: Sequence[PortInfo],
    config: Config,
    *,
    claims: Claims | None = None,
    holder: RadioId = HF_ID,
) -> tuple[str, str]:
    """Return the card (id) and keying the page proposes while the settings are empty."""
    serial, held_cards = (
        (claims.held_by_others(holder, "serial"), claims.held_by_others(holder, "sound_card"))
        if claims is not None
        else (frozenset[str](), frozenset[str]())
    )
    card = propose_sound_card([c for c in cards if c.id not in held_cards])
    leave = left_out(config, holder)
    return card, propose_keying(
        cards,
        card,
        [
            SerialPort(p.device, p.vid, p.pid)
            for p in ports
            if (key := claim_value(p.device)) not in leave and (not serial or key not in serial)
        ],
    )
