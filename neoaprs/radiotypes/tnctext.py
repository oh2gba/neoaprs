"""The receive-only text radio: a Yaesu FTM on its data port, or a TNC in monitor mode.

It prints what it hears as text, not KISS (tncprofile.TNC_TEXT, tnctextreader.py), and sends
nothing (`Can.transmit` False); the "tnc" driver.
"""
from neoaprs.radiotype import RadioType
from neoaprs.radiotypes.common import FM_LIMITS, LISTENS, NOTHING_ALLOWED, fields_of
from neoaprs.radiotypes.serialtnc import BAUD, PORT
from neoaprs.tncprofile import TNC_TEXT

# LISTENS: a Terminal that only shows; no Find my radio, which writes a carriage return and KISS
# entries to the ports it tries. An empty Port is found by the radio's own search, which only
# listens.

TYPES: tuple[RadioType, ...] = (
    RadioType(TNC_TEXT.key, "fm", TNC_TEXT.name, f"radio.type.{TNC_TEXT.key}", TNC_TEXT.transport, "tnc", TNC_TEXT.key, fields_of((PORT, BAUD), NOTHING_ALLOWED, transmit=False), FM_LIMITS,
              NOTHING_ALLOWED, LISTENS, dummy=False),
)
