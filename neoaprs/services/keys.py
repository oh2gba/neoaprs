"""Key interface of encrypted messages (`Keys`), and its stand-in `NoKeys` for builds without them.

`cipher.py` and `keyring.py` are in a wheel only when it is built with NEOAPRS_ENCRYPTION=1.
Without them `keyring_for` returns `NoKeys`: every text is a plain message and nothing is sealed."""
import importlib.util
import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol

from neoaprs.clock import Clock
from neoaprs.message import MessagingError, Seal
from neoaprs.messagelog import MessageLog
from neoaprs.signal import Signal

log = logging.getLogger("neoaprs.keyring")


class Keys(Protocol):
    changed: Signal[[str]]
    own_changed: Signal[[]]

    @property
    def enabled(self) -> bool: ...
    async def load(self) -> None: ...
    def refuse_unless_on(self) -> None: ...
    def renew(self) -> None: ...
    def fingerprint(self) -> str: ...
    def key_text(self) -> str: ...
    def peers(self) -> dict[str, tuple[str, datetime]]: ...
    async def forget(self, call: str) -> None: ...
    def kind(self, text: str) -> Seal: ...
    def opened(self, sender: str, ours: str, text: str) -> tuple[str, Seal, str | None]: ...
    def sealed(self, ours: str, to: str, text: str) -> str: ...
    async def taken(self, call: str, text: str, at: datetime) -> Seal: ...


def _not_built() -> MessagingError:
    return MessagingError("encrypted messages are not in this build of NeoAPRS", "lock.off")


class NoKeys:
    """Keys of a build without encrypted messages: every text is plain, sealing is refused."""
    enabled = False

    def __init__(self) -> None:
        self.changed: Signal[[str]] = Signal("keys_changed")
        self.own_changed: Signal[[]] = Signal("own_key_changed")

    async def load(self) -> None:
        return None

    def refuse_unless_on(self) -> None:
        raise _not_built()

    def renew(self) -> None:
        raise _not_built()

    def fingerprint(self) -> str:
        return ""

    def key_text(self) -> str:
        raise _not_built()

    def peers(self) -> dict[str, tuple[str, datetime]]:
        return {}

    async def forget(self, call: str) -> None:
        raise _not_built()

    def kind(self, text: str) -> Seal:
        return ""

    def opened(self, sender: str, ours: str, text: str) -> tuple[str, Seal, str | None]:
        return text, "", None

    def sealed(self, ours: str, to: str, text: str) -> str:
        raise _not_built()

    async def taken(self, call: str, text: str, at: datetime) -> Seal:
        return ""


def built_in() -> bool:
    """Return whether this build contains the cipher module."""
    return importlib.util.find_spec("neoaprs.cipher") is not None


def keyring_for(data_dir: Path, messagelog: MessageLog, clock: Clock, allowed: bool) -> Keys:
    """Return the real key ring if built in (`allowed`: --encryption given), else `NoKeys`."""
    built = built_in()
    log.info("encrypted messages: %s", "not in this build" if not built else "allowed (--encryption)" if allowed else "off (the daemon was started without --encryption)")
    if not built:
        return NoKeys()
    from neoaprs.services.keyring import Keyring
    return Keyring(data_dir, messagelog, clock, allowed=allowed)
