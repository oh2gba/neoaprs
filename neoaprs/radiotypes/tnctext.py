"""The receive-only text radio: a Yaesu FTM on its data port, or a TNC in its own monitor mode, that gives no KISS and prints what it hears as text (aprs-reference/text-monitor-plan.md). The "tnc" driver
with the profile that reads text (tncprofile.TNC_TEXT, tnctextreader.py): the line, the search of an empty Port (which only listens), the claims, the Terminal and the reopen are the Tnc's as for any serial TNC.

It sends nothing (`Can.transmit` False): no rule picks it to send on, and its line is never written to. So it is allowed no path, no digipeater, no SmartBeaconing; it is no email radio and no shared channel
whose ALOHA circle is worked out; its fields are the port and the speed, and no beacon tick. What it hears goes to the map, the log, the station book and the iGate as from any radio."""
from neoaprs.radiotype import Allowed, Can, RadioType
from neoaprs.radiotypes.common import FM_LIMITS, fields_of
from neoaprs.radiotypes.serialtnc import BAUD, PORT
from neoaprs.tncprofile import TNC_TEXT

NOTHING_ALLOWED = Allowed(paths=False, digipeat=False, smart_beacon=False, gateway_heard=False, shared_channel=False)
LISTENS = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False, transmit=False)
# (a Terminal that only shows; no Find my radio, which writes a carriage return and the KISS entries to the ports it tries: an empty Port is found by the radio's own search, which only listens)

TYPES: tuple[RadioType, ...] = (
    RadioType(TNC_TEXT.key, "fm", TNC_TEXT.name, f"radio.type.{TNC_TEXT.key}", TNC_TEXT.transport, "tnc", TNC_TEXT.key, fields_of((PORT, BAUD), NOTHING_ALLOWED, transmit=False), FM_LIMITS,
              NOTHING_ALLOWED, LISTENS, dummy=False),
)
