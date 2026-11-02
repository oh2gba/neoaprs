"""The keys of encrypted messages (neoaprs/services/keyring.py): our own key made when it is first needed and kept in a file only the owner reads, read again at the next start, made anew on request; the
key a station announces taken on first hearing and kept in the database, a different one refused until the old is forgotten, and the flag --encryption that governs sending."""
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import cipher
from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.services.keyring import FILE, Keyring
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.storedb import store_at

PEER = cipher.public_of(bytes(range(32)))
OTHER = cipher.public_of(bytes(range(1, 33)))


class Rig:
    def __init__(self, folder: Path, log: MessageLog, clock: FixedClock, encrypt: bool = True) -> None:
        self.log, self.clock = log, clock
        self.ring = Keyring(folder, log, clock, allowed=encrypt)
        self.changed: list[str] = []
        self.own: int = 0
        self.ring.changed.connect(self.changed.append)
        self.ring.own_changed.connect(lambda: setattr(self, "own", self.own + 1))


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    clock = FixedClock()
    store = await store_at(tmp_path / DB_NAME, clock)
    assert store.db is not None
    r = Rig(tmp_path, MessageLog(store.db, clock), clock, encrypt=False)
    await r.ring.load()
    return r


@pytest.fixture
def restart(rig: Rig, tmp_path: Path) -> Callable[[bool], Rig]:
    """A second ring on the same folder and database, as after a restart of the daemon."""
    def make(encrypt: bool = True) -> Rig:
        return Rig(tmp_path, rig.log, rig.clock, encrypt)
    return make


async def test_there_is_no_key_until_one_is_needed_and_then_it_is_kept_in_a_file_only_the_owner_reads(rig: Rig, tmp_path: Path) -> None:
    assert rig.ring.fingerprint() == "" and rig.ring.own_public() is None and not (tmp_path / FILE).exists()
    rig.ring.allowed = True
    text = rig.ring.key_text()
    public = cipher.key_of_message(text)
    assert public is not None and rig.ring.own_public() == public and rig.ring.fingerprint() == cipher.fingerprint(public) and rig.own == 1
    kept = tmp_path / FILE
    assert kept.read_bytes() == rig.ring.ensure_own() and len(kept.read_bytes()) == 32
    if sys.platform != "win32":
        assert kept.stat().st_mode & 0o777 == 0o600
    assert rig.ring.key_text() == text and rig.own == 1, "asked again, the same key"


async def test_the_key_is_read_again_at_the_next_start_and_a_new_one_replaces_it_on_request(rig: Rig, restart: Callable[[bool], Rig]) -> None:
    rig.ring.allowed = True
    first = rig.ring.fingerprint() or rig.ring.key_text() and rig.ring.fingerprint()
    again = restart(True)
    await again.ring.load()
    assert again.ring.fingerprint() == first and again.own == 0
    again.ring.renew()
    assert again.ring.fingerprint() != first and again.own == 1
    third = restart(True)
    await third.ring.load()
    assert third.ring.fingerprint() == again.ring.fingerprint()


async def test_a_daemon_started_with_the_flag_makes_the_key_at_the_start_so_that_its_fingerprint_is_there_to_compare(rig: Rig, tmp_path: Path, restart: Callable[[bool], Rig]) -> None:
    assert rig.ring.fingerprint() == "" and not (tmp_path / FILE).exists(), "started without the flag: no key"
    allowed = restart(True)
    await allowed.ring.load()
    assert allowed.ring.fingerprint() != "" and (tmp_path / FILE).exists() and allowed.own == 1
    without = restart(False)
    await without.ring.load()
    assert without.ring.fingerprint() == allowed.ring.fingerprint(), "the key that is there is read whether or not the flag is given"


async def test_a_file_that_is_no_key_is_left_and_a_new_key_is_made_when_needed(rig: Rig, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / FILE).write_bytes(b"short")
    await rig.ring.load()
    assert rig.ring.fingerprint() == "" and "is not a key (5 bytes)" in caplog.text
    rig.ring.allowed = True
    assert rig.ring.fingerprint() == "" and rig.ring.key_text().startswith("!K") and len((tmp_path / FILE).read_bytes()) == 32


async def test_the_first_key_a_station_announces_is_kept_and_a_different_one_is_not_taken_until_the_old_is_forgotten(rig: Rig, restart: Callable[[bool], Rig]) -> None:
    assert rig.ring.peer_key("OH2BEA-7") is None and rig.ring.peers() == {}
    assert await rig.ring.take("oh2bea-7", PEER, rig.clock()) == "key"
    assert rig.ring.peer_key("OH2BEA-7") == PEER and rig.ring.peers() == {"OH2BEA-7": (cipher.fingerprint(PEER), rig.clock())} and rig.changed == ["OH2BEA-7"]
    assert await rig.ring.take("OH2BEA-7", PEER, rig.clock()) == "key", "the same key again is nothing new"
    assert await rig.ring.take("OH2BEA-7", OTHER, rig.clock()) == "key_other"
    assert rig.ring.peer_key("OH2BEA-7") == PEER and rig.changed == ["OH2BEA-7"]
    again = restart(True)
    await again.ring.load()
    assert again.ring.peer_key("OH2BEA-7") == PEER, "kept in the database"
    await again.ring.forget("OH2BEA-7")
    assert again.ring.peer_key("OH2BEA-7") is None and again.changed == ["OH2BEA-7"]
    with pytest.raises(MessagingError) as none:
        await again.ring.forget("OH2BEA-7")
    assert none.value.code == "lock.no_key" and none.value.params == {"call": "OH2BEA-7"}
    assert await again.ring.take("OH2BEA-7", OTHER, rig.clock()) == "key" and again.ring.peer_key("OH2BEA-7") == OTHER
    third = restart(True)
    await third.ring.load()
    assert third.ring.peer_key("OH2BEA-7") == OTHER


async def test_the_shared_key_needs_both_keys_and_is_the_same_from_either_side(rig: Rig) -> None:
    assert rig.ring.shared_with("OH2BEA-7") is None
    await rig.ring.take("OH2BEA-7", PEER, rig.clock())
    assert rig.ring.shared_with("OH2BEA-7") is None, "no key of ours yet"
    rig.ring.allowed = True
    ours = rig.ring.ensure_own()
    shared = rig.ring.shared_with("OH2BEA-7")
    assert shared is not None and shared == cipher.shared_key(bytes(range(32)), cipher.public_of(ours))
    assert rig.ring.shared_with("OH2XYZ") is None


async def test_the_flag_governs_sending(rig: Rig) -> None:
    assert not rig.ring.enabled
    with pytest.raises(MessagingError) as off:
        rig.ring.refuse_unless_on()
    assert off.value.code == "lock.off"
    rig.ring.allowed = True
    assert rig.ring.enabled
    rig.ring.refuse_unless_on()


async def test_a_call_that_is_none_is_refused(rig: Rig) -> None:
    with pytest.raises(MessagingError):
        await rig.ring.take("", PEER, rig.clock())
    with pytest.raises(MessagingError):
        rig.ring.peer_key("not a call!")


async def test_a_key_no_shared_key_can_be_made_with_is_never_kept(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    """All zeros (and the few low-order points) give the library nothing to derive a key from: kept, such a key would fail every message to and from the station."""
    assert not cipher.is_usable_key(bytes(32)) and not cipher.is_usable_key(b"\x01" + bytes(31)) and cipher.is_usable_key(PEER) and not cipher.is_usable_key(PEER[:31])
    assert await rig.ring.take("OH2PEER", bytes(32), rig.clock()) == "" and rig.ring.shared_with("OH2PEER") is None and rig.changed == []
    assert "no shared key can be made with" in caplog.text
    assert await rig.ring.take("OH2PEER", PEER, rig.clock()) == "key", "a good key after a bad one is taken as the first"
