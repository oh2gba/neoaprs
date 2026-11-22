"""Keys for encrypted messages: our own key pair and the public key each station announced.

A station's first announced key is trusted; a different key is refused until it is forgotten.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from neoaprs import cipher
from neoaprs.callsign import CallsignError, normal_name
from neoaprs.clock import Clock, utcnow
from neoaprs.durable import fsync_file
from neoaprs.message import MessagingError, Seal
from neoaprs.messagelog import MessageLog
from neoaprs.signal import Signal

log = logging.getLogger("neoaprs.keyring")

FILE = "message.key"


def _b64(key: bytes) -> str:
    return cipher.key_message(key)[len(cipher.KEY_MARK) :]


def _station(call: str) -> str:
    try:
        return normal_name(call)
    except CallsignError as e:
        raise MessagingError.of(e) from None


class Keyring:
    def __init__(self, data_dir: Path, messagelog: MessageLog, clock: Clock = utcnow, allowed: bool = False) -> None:
        self._path = data_dir / FILE
        self.allowed = allowed
        self._log = messagelog
        self._clock = clock
        self._private: bytes | None = None
        # by call: the key the station announced and when it was heard
        self._peers: dict[str, tuple[bytes, datetime]] = {}
        self.changed: Signal[[str]] = Signal("keys_changed")
        self.own_changed: Signal[[]] = Signal("own_key_changed")

    async def load(self) -> None:
        """Read our key from its file and the stations' keys from the database."""
        self._private = self._read_own()
        self._peers = {}
        for call, (text, heard_at) in (await self._log.keys()).items():
            key = cipher.key_of_message(cipher.KEY_MARK + text)
            if key is None:
                log.warning("the key kept for %s is not a key: left out", call)
                continue
            self._peers[call] = (key, heard_at)
        if self.enabled:
            self.ensure_own()

    @property
    def enabled(self) -> bool:
        return self.allowed

    def refuse_unless_on(self) -> None:
        """Raise MessagingError (`lock.off`) while encrypted messages are not allowed."""
        if not self.enabled:
            raise MessagingError(
                "encrypted messages are not allowed: NeoAPRS was started without --encryption", "lock.off"
            )

    def _read_own(self) -> bytes | None:
        try:
            data = self._path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as e:
            log.error("%s could not be read: %s", self._path, e.strerror or e)
            return None
        if len(data) != cipher.KEY_LEN:
            log.error("%s is not a key (%d bytes): a new one is made when it is needed", self._path, len(data))
            return None
        return data

    def _write_own(self, private: bytes) -> None:
        """Write the key atomically, readable by the owner only (the mode is set before any write)."""
        tmp = self._path.with_name(self._path.name + ".new")
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(private)
        fsync_file(tmp)
        os.replace(tmp, self._path)

    def ensure_own(self) -> bytes:
        """Return our private key, making it if none exists. Raise MessagingError if unwritable."""
        if self._private is None:
            self.renew()
        assert self._private is not None
        return self._private

    def renew(self) -> None:
        """Replace our key pair. Raise MessagingError if the file cannot be written (old key stays)."""
        private = cipher.new_private()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._write_own(private)
        except OSError as e:
            raise MessagingError(f"the key could not be kept: {e.strerror or e}", "failed") from None
        self._private = private
        log.info("a new message key: %s", cipher.fingerprint(cipher.public_of(private)))
        self.own_changed.emit()

    def own_public(self) -> bytes | None:
        """Return our public key, None while no key has been made."""
        return None if self._private is None else cipher.public_of(self._private)

    def fingerprint(self) -> str:
        """Return the fingerprint of our key, empty while there is none."""
        public = self.own_public()
        return "" if public is None else cipher.fingerprint(public)

    def key_text(self) -> str:
        """Return the text of the message announcing our key (making the key if needed)."""
        return cipher.key_message(cipher.public_of(self.ensure_own()))

    def peers(self) -> dict[str, tuple[str, datetime]]:
        """Return call to (fingerprint, when heard) for every station whose key is kept."""
        return {call: (cipher.fingerprint(key), at) for call, (key, at) in self._peers.items()}

    def peer_key(self, call: str) -> bytes | None:
        return self._peers.get(_station(call), (None, None))[0]

    def shared_with(self, call: str) -> bytes | None:
        """Return the key shared with the station, None while either key is missing."""
        peer = self.peer_key(call)
        return None if peer is None or self._private is None else cipher.shared_key(self._private, peer)

    def _shared(self, call: str) -> bytes | None:
        """Return the shared key, None if a key is missing, the call invalid or the key unusable."""
        try:
            return self.shared_with(call)
        except (MessagingError, ValueError):
            return None

    def kind(self, text: str) -> Seal:
        """Classify a text by its marker: `key` announcement, `shut` sealed text, else plain."""
        return "key" if cipher.key_of_message(text) is not None else "shut" if cipher.is_locked(text) else ""

    def opened(self, sender: str, ours: str, text: str) -> tuple[str, Seal, str | None]:
        """Return (kept text, kind, text as received if different).

        A sealed text is opened with the shared key (`open`), or kept as received (`shut`).
        """
        seal = self.kind(text)
        if seal != "shut":
            return text, seal, None
        shared = self._shared(sender)
        try:
            station = normal_name(sender)
        except CallsignError:
            station = sender
        inside = None if shared is None else cipher.open_sealed(shared, station, ours, text)
        if inside is None:
            log.info(
                "an encrypted message from %s does not open here (%s)",
                sender,
                "no key" if shared is None else "another key, or damaged",
            )
            return text, "shut", None
        return inside, "open", text

    def sealed(self, ours: str, to: str, text: str) -> str:
        """Return the text to send as an encrypted message; raise MessagingError if not possible."""
        self.refuse_unless_on()
        shared = self._shared(to)
        if shared is None:
            raise MessagingError(f"no key from {to}: it has to send its key first", "lock.no_key", call=to)
        try:
            return cipher.seal(shared, ours, to, text)
        except cipher.CipherError as e:
            raise MessagingError(str(e), e.code, **e.params) from None

    async def taken(self, call: str, text: str, at: datetime) -> Seal:
        """Offer the key of an announcement to the ring and return its kind."""
        key = cipher.key_of_message(text)
        return "key" if key is None else await self.take(call, key, at)

    async def take(self, call: str, key: bytes, at: datetime) -> Seal:
        """Keep an announced key if none is kept (`key`); `key_other` if another is kept.

        An unusable key is never kept ("" returned). Raise MessagingError for an invalid call.
        """
        station = _station(call)
        if not cipher.is_usable_key(key):
            log.warning(
                "%s announced a key no shared key can be made with (%s): not taken", station, cipher.fingerprint(key)
            )
            return ""
        kept = self._peers.get(station)
        if kept is not None:
            if kept[0] == key:
                return "key"
            log.warning(
                "%s announced a key (%s) that differs from the one kept (%s): not taken; forget the old one if the station has a new key",
                station,
                cipher.fingerprint(key),
                cipher.fingerprint(kept[0]),
            )
            return "key_other"
        self._peers[station] = (key, at)
        if not await self._log.save_key(station, _b64(key), at):
            log.error("the key of %s could not be kept in the database: it is held until the daemon stops", station)
        log.info("%s announced its key: %s", station, cipher.fingerprint(key))
        self.changed.emit(station)
        return "key"

    async def forget(self, call: str) -> None:
        """Remove a station's key so its next announcement is taken. Raise MessagingError if none."""
        station = _station(call)
        if station not in self._peers:
            raise MessagingError(f"there is no key from {station}", "lock.no_key", call=station)
        if not await self._log.forget_key(station):
            raise MessagingError(f"the key of {station} could not be removed: the database would not take it", "failed")
        del self._peers[station]
        log.info("the key of %s is forgotten", station)
        self.changed.emit(station)
