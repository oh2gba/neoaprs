"""Encrypted messages through messaging (neoaprs/services/messaging.py, services/inbox.py, with the keys of services/keyring.py): a locked message goes on the air as ciphertext and is kept as what was written, every
attempt sends the same bytes, the other station opens it; what is refused and why; our key announced by hand; a station's key taken when it comes in and a different one not; a sealed message to us opened,
or kept shut when it cannot be; what is overheard of other stations' locked traffic; and all of it read back after a restart."""
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import cipher
from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.services.keyring import Keyring
from tests.support.storedb import log_at
from tests.test_messaging import Rig as MessagingRig

PEER_PRIVATE = bytes(range(32))                      # the other station's key pair, which the test holds to play its side
PEER_PUBLIC = cipher.public_of(PEER_PRIVATE)
OTHER_PUBLIC = cipher.public_of(bytes(range(1, 33)))


class Rig(MessagingRig):
    def __init__(self, folder: Path, log: MessageLog, clock: object, encrypt: bool = True) -> None:
        self.folder = folder
        ring = Keyring(folder, log, clock, allowed=encrypt)  # type: ignore[arg-type]
        super().__init__(log, clock, keyring=ring)  # type: ignore[arg-type]
        self.ring = ring

    async def start(self) -> None:
        await self.ring.load()
        await super().start()

    def peer_shared(self) -> bytes:
        """The key the other station shares with us, worked out on its side."""
        public = self.ring.own_public()
        assert public is not None
        return cipher.shared_key(PEER_PRIVATE, public)

    def peer_seals(self, text: str, sender: str = "OH2RDG-7") -> str:
        """What the other station puts on the air for `text` to us."""
        return cipher.seal(self.peer_shared(), sender, "OH2GBA", text)


@pytest.fixture
async def rig(tmp_path: Path) -> Rig:
    log, _, clock = await log_at(tmp_path, MessageLog)
    r = Rig(tmp_path, log, clock)
    await r.start()
    return r


@pytest.fixture
def another(rig: Rig) -> Callable[..., Rig]:
    """A second messaging with its ring on the same folder and database, as after a restart of the daemon."""
    def make(encrypt: bool = True) -> Rig:
        return Rig(rig.folder, rig.log, rig.clock, encrypt)
    return make


async def with_peer_key(rig: Rig, call: str = "OH2RDG-7") -> None:
    assert await rig.ring.take(call, PEER_PUBLIC, rig.clock()) == "key"


# ---- sending
async def test_a_locked_message_goes_on_the_air_as_ciphertext_is_kept_as_what_was_written_and_opens_at_the_other_station(rig: Rig) -> None:
    await with_peer_key(rig)
    record = await rig.m.send("oh2rdg-7", "Moi, täällä ok", locked=True)
    [frame] = rig.tnc.sent
    wire = frame.info.decode()[11:].split("{")[0]
    assert frame.info.startswith(b":OH2RDG-7 :!E") and frame.info.endswith(b"{01}") and len(wire) <= 67
    assert record.text == "Moi, täällä ok" and record.seal == "open" and record.wire == wire and record.state == "sending" and record.attempts == 1
    assert cipher.open_sealed(rig.peer_shared(), "OH2GBA", "OH2RDG-7", wire) == "Moi, täällä ok"
    await rig.settled()
    [kept] = await rig.log.recent()
    assert kept.text == "Moi, täällä ok" and kept.wire == wire and kept.seal == "open"
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", ack="01"))
    assert rig.state().state == "acked"


async def test_every_attempt_of_a_locked_message_sends_the_same_bytes(rig: Rig) -> None:
    await with_peer_key(rig)
    await rig.m.send("OH2RDG-7", "Again", locked=True)
    await rig.pass_time(32)
    first, second = rig.tnc.sent
    assert first.info == second.info and rig.state().attempts == 2
    rig.m.cancel(1)
    rig.m.retry(1)
    assert rig.tnc.sent[2].info == first.info, "a retry too"


@pytest.mark.parametrize(("encrypt", "key", "text", "code", "params"), [
    (False, True, "Hello", "lock.off", {}),
    (True, False, "Hello", "lock.no_key", {"call": "OH2RDG-7"}),
    (True, True, "ä" * 18, "lock.too_long", {"length": 36, "max": 34}),
    (True, True, "a\tb", "lock.unprintable", {}),
])
async def test_a_locked_message_is_refused_with_the_reason_and_nothing_is_kept_or_sent(rig: Rig, encrypt: bool, key: bool, text: str, code: str, params: dict[str, object]) -> None:
    rig.ring.allowed = encrypt
    if key:
        await with_peer_key(rig)
    with pytest.raises(MessagingError) as refused:
        await rig.m.send("OH2RDG-7", text, locked=True)
    assert refused.value.code == code and refused.value.params == params
    assert rig.tnc.sent == [] and rig.m.records() == []


async def test_a_bulletin_cannot_be_locked(rig: Rig) -> None:
    with pytest.raises(MessagingError, match="bulletin"):
        await rig.m.send("BLN1", "Hello", locked=True)
    assert rig.tnc.sent == []


# ---- our key
async def test_our_key_is_announced_by_hand_as_an_ordinary_message_and_only_while_the_setting_is_on(rig: Rig) -> None:
    record = await rig.m.send_key("oh2rdg-7")
    [frame] = rig.tnc.sent
    assert frame.info == f":OH2RDG-7 :{rig.ring.key_text()}{{01}}".encode() and record.seal == "key" and record.text == rig.ring.key_text() and record.wire is None
    assert cipher.key_of_message(record.text) == rig.ring.own_public()
    rig.ring.allowed = False
    with pytest.raises(MessagingError) as off:
        await rig.m.send_key("OH2RDG-7")
    assert off.value.code == "lock.off" and len(rig.tnc.sent) == 1
    rig.ring.allowed = True
    with pytest.raises(MessagingError, match="own call"):
        await rig.m.send_key("OH2GBA")


# ---- receiving
async def test_a_key_a_station_announces_is_taken_and_acked_and_a_different_one_later_is_shown_and_not_taken(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", cipher.key_message(PEER_PUBLIC), "12"))
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack12"]
    await rig.settled()
    [record] = rig.m.records()
    assert record.seal == "key" and record.text == cipher.key_message(PEER_PUBLIC) and record.state == "received"
    assert rig.ring.peer_key("OH2RDG-7") == PEER_PUBLIC
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", cipher.key_message(OTHER_PUBLIC), "13"))
    await rig.settled()
    other = rig.state(2)
    assert other.seal == "key_other" and rig.ring.peer_key("OH2RDG-7") == PEER_PUBLIC and rig.tnc.lines()[-1].endswith(":ack13")


async def test_a_sealed_message_to_us_is_opened_kept_with_the_text_inside_and_acked_and_a_copy_is_not_kept_again(rig: Rig) -> None:
    await with_peer_key(rig)
    wire = rig.peer_seals("Terve, kuuluuko?")
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", wire, "21"))
    assert rig.tnc.lines() == ["OH2GBA>APZNEO,WIDE1-1,WIDE2-1::OH2RDG-7 :ack21"]
    await rig.settled()
    [record] = rig.m.records()
    assert record.text == "Terve, kuuluuko?" and record.seal == "open" and record.wire == wire and record.state == "received"
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", wire, "21"))
    await rig.settled()
    assert len(rig.m.records()) == 1, "a digipeater's copy is the same message"
    [kept] = await rig.log.recent()
    assert kept == record


async def test_a_sealed_message_that_does_not_open_here_is_kept_shut_as_it_came(rig: Rig, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="neoaprs.messaging")
    rig.ring.ensure_own()
    stranger = cipher.seal(cipher.shared_key(PEER_PRIVATE, OTHER_PUBLIC), "OH2RDG-7", "OH2GBA", "for somebody else")
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", stranger, "31"))
    await rig.settled()
    [record] = rig.m.records()
    assert record.seal == "shut" and record.text == stranger and record.wire is None and "does not open here (no key)" in caplog.text
    await with_peer_key(rig)
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", stranger, "32"))
    await rig.settled()
    assert rig.state(2).seal == "shut" and "another key, or damaged" in caplog.text


async def test_what_is_overheard_of_other_stations_locked_traffic_is_shut_and_a_key_they_announce_is_not_taken(rig: Rig) -> None:
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", cipher.seal(cipher.shared_key(PEER_PRIVATE, OTHER_PUBLIC), "OH2AAA", "OH2BBB", "theirs"), "5"))
    rig.m.on_packet(rig.heard("OH2AAA", "OH2BBB", cipher.key_message(PEER_PUBLIC), "6"))
    await rig.settled()
    sealed, key = rig.m.records()
    assert sealed.state == "overheard" and sealed.seal == "shut" and key.seal == "key" and rig.ring.peer_key("OH2AAA") is None and rig.tnc.sent == []


async def test_a_plain_message_is_as_it_was(rig: Rig) -> None:
    await with_peer_key(rig)
    record = await rig.m.send("OH2RDG-7", "plain words")
    assert record.seal == "" and record.wire is None and rig.tnc.sent[0].info == b":OH2RDG-7 :plain words{01}"
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "plain answer", "7"))
    await rig.settled()
    assert rig.state(2).seal == "" and rig.state(2).text == "plain answer"


# ---- a restart
async def test_the_messages_come_back_with_what_they_are_after_a_restart(rig: Rig, another: Callable[..., Rig]) -> None:
    await with_peer_key(rig)
    sent = await rig.m.send("OH2RDG-7", "Kept", locked=True)
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", rig.peer_seals("Back"), "41"))
    await rig.settled()
    await rig.m.stop()
    again = another()
    await again.start()
    first, second = again.m.records()
    assert (first.seal, first.text, first.wire) == ("open", "Kept", sent.wire) and (second.seal, second.text) == ("open", "Back")
    assert again.ring.peer_key("OH2RDG-7") == PEER_PUBLIC and again.ring.fingerprint() == rig.ring.fingerprint()
    await again.pass_time(32)
    assert again.tnc.sent[-1].info.startswith(f":OH2RDG-7 :{sent.wire}".encode()), "the attempt after the restart sends the same bytes"
    await again.m.stop()
