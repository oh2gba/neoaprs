"""The keys of encrypted messages (neoaprs/cipher.py): our own key pair, and the public key each station announced.

Our private key is the file `message.key` of the data folder, 32 raw bytes readable by the owner only, made the first time it is needed (the daemon started with --encryption, a key sent, a message
locked) and kept across runs; `renew` makes a new one in its place (the stations that have the old key must be sent the new one). The public key is announced to a station as a message by hand
(messaging.send_key: nothing is announced by itself); `fingerprint` is what the operators compare.

A station's key is taken on first hearing (`take`): the first key a station announces is kept, in the table `station_key` of the message log's database, and shown with its fingerprint; a later
announcement of the same key is nothing new; one of a different key is not taken (the message is kept as `key_other`, so that the operator sees it) until the key that is kept is forgotten (`forget`:
the operator's, when the station is known to have a new key). A key is kept whether or not encrypted messages are switched on: hearing a key costs nothing and the setting is about what we send.
This is trust on first use, and the trust is in the call as the air carries it, which anyone can write into a frame: a station that announces a key under another's call before the owner does holds that call's
key here until the operator forgets it, and the locked messages to that call open for it and not for the owner; the fingerprint beside each key is what the two operators compare on voice (or by any other way
they trust) before they rely on a key, and the one defence there is (neoaprs/cipher.py says the rest of what the scheme does not do). A key that is different from the one kept is never taken by itself for the
same reason: the first announcement may have been the owner's.
`changed` tells (call) when a station's key is set or forgotten, `own_changed` when our own key is new.

The flag --encryption of the daemon (`allowed`, `enabled`) governs sending: a locked message or a key goes out only when the daemon was started with it, and the page shows the feature only then. Amateur
regulations forbid encoding that hides the meaning of a transmission, so it is not there unless the operator starts the daemon that way, for the circumstances that allow it. What comes in is opened whenever the keys for it are here (`shared_with`), so that a message is never shown as base64 when it can be read."""
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
    return cipher.key_message(key)[len(cipher.KEY_MARK):]


def _station(call: str) -> str:
    try:
        return normal_name(call)
    except CallsignError as e:
        raise MessagingError(str(e)) from None


class Keyring:
    def __init__(self, data_dir: Path, messagelog: MessageLog, clock: Clock = utcnow, allowed: bool = False) -> None:
        self._path = data_dir / FILE
        self.allowed = allowed                                          # the daemon was started with --encryption
        self._log = messagelog
        self._clock = clock
        self._private: bytes | None = None
        self._peers: dict[str, tuple[bytes, datetime]] = {}            # the key each station announced and when it was heard, by call
        self.changed: Signal[[str]] = Signal("keys_changed")
        self.own_changed: Signal[[]] = Signal("own_key_changed")

    async def load(self) -> None:
        """Our key from its file, when there is one, and the stations' keys from the database."""
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

    # ---- the flag
    @property
    def enabled(self) -> bool:
        return self.allowed

    def refuse_unless_on(self) -> None:
        """Raises MessagingError (`lock.off`) while encrypted messages are not allowed."""
        if not self.enabled:
            raise MessagingError("encrypted messages are not allowed: the daemon was started without --encryption", "lock.off")

    # ---- our own key
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
        """The file whole or not at all, readable by the owner only (the mode is set before a byte is written)."""
        tmp = self._path.with_name(self._path.name + ".new")
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(private)
        fsync_file(tmp)
        os.replace(tmp, self._path)

    def ensure_own(self) -> bytes:
        """Our private key, made and kept when there is none yet. Raises MessagingError when the file cannot be written."""
        if self._private is None:
            self.renew()
        assert self._private is not None
        return self._private

    def renew(self) -> None:
        """A new key pair in place of the old (the stations that have the old key must be sent the new one). Raises MessagingError when the file cannot be written; the old key stays then."""
        private = cipher.new_private()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._write_own(private)
        except OSError as e:
            raise MessagingError(f"the key could not be kept: {e.strerror or e}") from None
        self._private = private
        log.info("a new message key: %s", cipher.fingerprint(cipher.public_of(private)))
        self.own_changed.emit()

    def own_public(self) -> bytes | None:
        """Our public key, None while no key has been made."""
        return None if self._private is None else cipher.public_of(self._private)

    def fingerprint(self) -> str:
        """The fingerprint of our key, empty while there is none."""
        public = self.own_public()
        return "" if public is None else cipher.fingerprint(public)

    def key_text(self) -> str:
        """The text of the message that announces our key (made when there is none yet)."""
        return cipher.key_message(cipher.public_of(self.ensure_own()))

    # ---- the stations' keys
    def peers(self) -> dict[str, tuple[str, datetime]]:
        """Every station whose key is kept: call to (fingerprint, when it was heard)."""
        return {call: (cipher.fingerprint(key), at) for call, (key, at) in self._peers.items()}

    def peer_key(self, call: str) -> bytes | None:
        return self._peers.get(_station(call), (None, None))[0]

    def shared_with(self, call: str) -> bytes | None:
        """The key we share with the station, None while either key is missing (ours is not made for this: a message that cannot be opened is shown shut)."""
        peer = self.peer_key(call)
        return None if peer is None or self._private is None else cipher.shared_key(self._private, peer)

    async def take(self, call: str, key: bytes, at: datetime) -> Seal:
        """A station announced a key: kept when it had none (`key`), nothing new when it is the one kept, not taken when another is kept (`key_other`; the operator forgets the old one first)."""
        station = _station(call)
        kept = self._peers.get(station)
        if kept is not None:
            if kept[0] == key:
                return "key"
            log.warning("%s announced a key (%s) that differs from the one kept (%s): not taken; forget the old one if the station has a new key", station, cipher.fingerprint(key), cipher.fingerprint(kept[0]))
            return "key_other"
        self._peers[station] = (key, at)
        if not await self._log.save_key(station, _b64(key), at):
            log.error("the key of %s could not be kept in the database: it is held until the daemon stops", station)
        log.info("%s announced its key: %s", station, cipher.fingerprint(key))
        self.changed.emit(station)
        return "key"

    async def forget(self, call: str) -> None:
        """The operator takes a station's key away (the station has a new one, or was never meant to have one): its next announcement is taken. Raises MessagingError when there is none, or the database would not take the removal."""
        station = _station(call)
        if station not in self._peers:
            raise MessagingError(f"there is no key from {station}", "lock.no_key", call=station)
        if not await self._log.forget_key(station):
            raise MessagingError(f"the key of {station} could not be removed: the database would not take it")
        del self._peers[station]
        log.info("the key of %s is forgotten", station)
        self.changed.emit(station)
