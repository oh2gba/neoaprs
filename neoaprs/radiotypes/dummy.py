"""The Dummy radios: no radio, no port, the traffic made up by the program.

The FM Dummy uses the "tnc" driver (dummyscene.py), the HF Dummy the "mercury" driver
(dummyhfscene.py). Each is last of its kind in the page's list.
"""

from neoaprs.radiotype import Can, RadioType
from neoaprs.radiotypes.common import FM_ALLOWED, FM_LIMITS, HF_ALLOWED, HF_LIMITS, fields_of
from neoaprs.tncprofile import DUMMY, DUMMY_HF

# the Terminal shows the made-up traffic
DUMMY_CAN = Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=False)

TYPES: tuple[RadioType, ...] = (
    RadioType(
        DUMMY.key,
        "fm",
        DUMMY.name,
        f"radio.type.{DUMMY.key}",
        DUMMY.transport,
        "tnc",
        DUMMY.key,
        fields_of((), FM_ALLOWED),
        FM_LIMITS,
        FM_ALLOWED,
        DUMMY_CAN,
        dummy=True,
    ),
    RadioType(
        DUMMY_HF.key,
        "hf",
        DUMMY_HF.name,
        f"radio.type.{DUMMY_HF.key}",
        DUMMY_HF.transport,
        "mercury",
        DUMMY_HF.key,
        fields_of((), HF_ALLOWED),
        HF_LIMITS,
        HF_ALLOWED,
        # no spectrum: the suggested dials only
        Can(find=False, terminal=True, tune=False, key_test=False, scope=False, tx_gain=False, frequencies=True),
        dummy=True,
    ),
)
