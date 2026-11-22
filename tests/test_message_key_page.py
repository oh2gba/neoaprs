"""The page's side of the key of encrypted messages (neoaprs/web/handlers.py `message_key_new`, neoaprs/web/api.py `status`): the fingerprint is reported and a new key made only while the daemon was started with
the encryption flag; a key file left by an earlier run with the flag is nothing to the page without it."""
from pathlib import Path

from neoaprs.services.keyring import Keyring
from tests.support.env import Env


async def test_the_page_sees_the_fingerprint_and_makes_a_new_key_only_while_encryption_is_on(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    page = await e.ws()
    ring = e.ctl.keyring
    assert isinstance(ring, Keyring)
    ring.allowed = True                                               # (an earlier run with the flag)
    ring.ensure_own()
    first = ring.fingerprint()
    assert first
    ring.allowed = False                                              # (this run is without it; the key file is still there)
    await page.send({"cmd": "status"})
    assert (await page.expect("status"))["message_key"] == ""
    await page.send({"cmd": "message_key_new"})
    assert (await page.expect("error"))["code"] == "lock.off"
    assert ring.fingerprint() == first, "no new key was made"
    ring.allowed = True
    await page.send({"cmd": "message_key_new"})
    await page.until(lambda: any(s["message_key"] not in ("", first) for s in page.of("status")))          # (a status of the ten-second timer, built before the key, may arrive first: the one that carries the new key is waited for)
    made = ring.fingerprint()
    assert made and made != first
    await e.stop()
