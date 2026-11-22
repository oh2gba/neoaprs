"""Build hook: a wheel has the encrypted-message modules only if built with NEOAPRS_ENCRYPTION=1.

pyproject.toml excludes ENCRYPTION from every wheel; the sdist always has them."""

import os
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SWITCH = "NEOAPRS_ENCRYPTION"
# Same list as `exclude` of the wheel in pyproject.toml.
ENCRYPTION = ("neoaprs/cipher.py", "neoaprs/services/keyring.py")


def switched_on(environ: dict[str, str] | os._Environ[str] = os.environ) -> bool:
    return environ.get(SWITCH, "") == "1"


class EncryptionSwitch(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if switched_on() and version != "editable":
            build_data["force_include"].update({os.path.join(self.root, *path.split("/")): path for path in ENCRYPTION})
