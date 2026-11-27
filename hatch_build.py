"""Build hook: a wheel has the encrypted-message modules only if built with NEOAPRS_ENCRYPTION=1.

pyproject.toml excludes ENCRYPTION from every wheel; the sdist always has them. A switched-on wheel
also needs the page built with the switch (ui/vite.config.ts), which the committed page is not."""

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SWITCH = "NEOAPRS_ENCRYPTION"
# Same list as `exclude` of the wheel in pyproject.toml.
ENCRYPTION = ("neoaprs/cipher.py", "neoaprs/services/keyring.py")
# A command only the page's code for keys sends: the page was built with the switch.
PAGE_MARK = b"message_key_new"


def switched_on(environ: dict[str, str] | os._Environ[str] = os.environ) -> bool:
    return environ.get(SWITCH, "") == "1"


def page_has_encryption(page: Path) -> bool:
    return any(PAGE_MARK in script.read_bytes() for script in (page / "assets").glob("*.js"))


class EncryptionSwitch(BuildHookInterface):  # type: ignore[type-arg]
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if not switched_on() or version == "editable":
            return
        if not page_has_encryption(Path(self.root) / "neoaprs" / "page"):
            raise RuntimeError(
                f"{SWITCH}=1, but neoaprs/page/ was built without encrypted messages: "
                f"run {SWITCH}=1 scripts/build-page in a clone of the repository, then build the wheel there"
            )
        build_data["force_include"].update({os.path.join(self.root, *path.split("/")): path for path in ENCRYPTION})
