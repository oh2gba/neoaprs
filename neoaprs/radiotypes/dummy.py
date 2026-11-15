"""The Dummy radios: no radio, no port, the traffic made up by the program (dummyscene.py round the station, dummyhfscene.py the distant HF stations). Each is last of its kind in the page's list. The FM Dummy has the "tnc" driver
with the dummy line, the HF Dummy the "mercury" driver (the Mercury program is its speaker)."""
from neoaprs.radiotype import Can, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, HF_ALLOWED, HF_LIMITS, fields_of
from neoaprs.tncprofile import DUMMY, DUMMY_HF

DUMMY_CAN = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)        # (the Terminal shows the made-up traffic, as any radio's shows its line)

TYPES: tuple[RadioType, ...] = (
    RadioType(DUMMY.key, "fm", DUMMY.name, f"radio.type.{DUMMY.key}", DUMMY.transport, "tnc", DUMMY.key, fields_of((), FM_ALLOWED), FM_LIMITS, FM_ALLOWED, DUMMY_CAN, dummy=True),
    RadioType(DUMMY_HF.key, "hf", DUMMY_HF.name, f"radio.type.{DUMMY_HF.key}", DUMMY_HF.transport, "mercury", DUMMY_HF.key, fields_of((), HF_ALLOWED), HF_LIMITS, HF_ALLOWED,
              Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=True), dummy=True),     # no spectrum: the suggested dials only
)
