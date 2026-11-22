"""The switch of the build for encrypted messages: a wheel has them only when it is built with NEOAPRS_ENCRYPTION=1.

pyproject.toml leaves the modules of ENCRYPTION out of every wheel; with the switch on, this hook puts them back. A wheel without them runs as a daemon that knows nothing of encrypted messages
(neoaprs/services/keys.py). The sdist always has them: it is the source."""
import os
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SWITCH = "NEOAPRS_ENCRYPTION"
ENCRYPTION = ("neoaprs/cipher.py", "neoaprs/services/keyring.py")      # the same list as `exclude` of the wheel in pyproject.toml (tests/test_build_switch.py holds the two together)


def switched_on(environ: dict[str, str] | os._Environ[str] = os.environ) -> bool:
    return environ.get(SWITCH, "") == "1"


class EncryptionSwitch(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if switched_on() and version != "editable":
            build_data["force_include"].update({os.path.join(self.root, *path.split("/")): path for path in ENCRYPTION})
