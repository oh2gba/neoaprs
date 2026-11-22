"""Encrypted messages are a switch of the build (hatch_build.py, neoaprs/services/keys.py): the
modules the switch leaves out are imported by nothing else, and a daemon without them treats every
message as plain, seals nothing and shows no key."""
import ast
import tomllib
from pathlib import Path

import pytest

from neoaprs.message import MessagingError
from neoaprs.messagelog import MessageLog
from neoaprs.services import keys
from neoaprs.services.keys import NoKeys, keyring_for
from tests.conftest import ROOT
from tests.support.env import Env
from tests.support.storedb import log_at
from tests.test_messaging import Rig

# read, not imported: it needs the build backend, which the tests' environment has not
HOOK = ROOT / "hatch_build.py"
ENCRYPTION: tuple[str, ...] = next(ast.literal_eval(node.value) for node in ast.parse(HOOK.read_text(encoding="utf-8")).body
                                   if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "ENCRYPTION")
MODULES = {"neoaprs.cipher", "neoaprs.services.keyring"}
# the one module that may reach them, and only when the build has them
SEAM = "neoaprs/services/keys.py"


def test_the_wheel_leaves_out_exactly_the_modules_the_hook_puts_back() -> None:
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert sorted(wheel["exclude"]) == sorted(ENCRYPTION)
    assert {path[:-3].replace("/", ".") for path in ENCRYPTION} == MODULES
    assert all((ROOT / path).is_file() for path in ENCRYPTION), "the code stays in the repository"


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_nothing_that_is_shipped_imports_the_modules_the_switch_leaves_out() -> None:
    reaching = []
    for path in sorted((ROOT / "neoaprs").rglob("*.py")):
        name = path.relative_to(ROOT).as_posix()
        if name in ENCRYPTION or name == SEAM:
            continue
        assert "from . import cipher" not in path.read_text(encoding="utf-8"), name
        if _imports(ast.parse(path.read_text(encoding="utf-8"))) & MODULES:
            reaching.append(name)
    assert reaching == []


async def test_a_build_without_the_cipher_gets_no_keys_and_one_with_it_the_key_ring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log, _, clock = await log_at(tmp_path, MessageLog)
    assert type(keyring_for(tmp_path, log, clock, True)).__name__ == "Keyring"
    monkeypatch.setattr(keys, "built_in", lambda: False)
    assert isinstance(keyring_for(tmp_path, log, clock, True), NoKeys)


async def test_without_keys_a_sealed_text_and_a_key_are_plain_messages_and_nothing_is_sealed_or_announced(tmp_path: Path) -> None:
    log, _, clock = await log_at(tmp_path, MessageLog)
    rig = Rig(log, clock, keyring=NoKeys())
    await rig.start()
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "!E" + "A" * 40, "31"))
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2GBA", "!K" + "A" * 43, "32"))
    rig.m.on_packet(rig.heard("OH2RDG-7", "OH2XYZ", "!E" + "B" * 40, "33"))
    await rig.settled()
    assert sorted((r.text[:2], r.seal, r.wire) for r in rig.m.records()) == [("!E", "", None), ("!E", "", None), ("!K", "", None)]
    for refused in (rig.m.send("OH2RDG-7", "hello", locked=True), rig.m.send_key("OH2RDG-7"), rig.m.keyring.forget("OH2RDG-7")):
        with pytest.raises(MessagingError) as e:
            await refused
        assert e.value.code == "lock.off"
    with pytest.raises(MessagingError):
        rig.m.keyring.renew()
    assert rig.m.keyring.fingerprint() == "" and rig.m.keyring.peers() == {} and not rig.m.keyring.enabled and not (tmp_path / "message.key").exists()


async def test_a_daemon_of_a_build_without_the_cipher_runs_and_shows_the_page_no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keys, "built_in", lambda: False)
    e = Env(tmp_path, web=True)
    await e.start()
    assert isinstance(e.ctl.keyring, NoKeys)
    page = await e.ws()
    await page.send({"cmd": "status"})
    assert (await page.expect("status"))["message_key"] == ""
    await page.send({"cmd": "message_key_new"})
    assert (await page.expect("error"))["code"] == "lock.off"
    await page.send({"cmd": "send_message", "to": "OH2RDG-7", "text": "hello", "locked": True})
    assert (await page.expect("error"))["code"] == "lock.off"
    await e.stop()
    assert not (tmp_path / "message.key").exists()


async def test_a_data_folder_with_keys_and_sealed_messages_is_read_by_a_build_without_the_cipher(tmp_path: Path) -> None:
    from tests.test_messaging_locked import PEER_PUBLIC, Rig as LockedRig
    log, _, clock = await log_at(tmp_path, MessageLog)
    before = LockedRig(tmp_path, log, clock)
    await before.start()
    assert await before.ring.take("OH2RDG-7", PEER_PUBLIC, clock()) == "key"
    sent = await before.m.send("OH2RDG-7", "locked text", locked=True)
    before.m.on_packet(before.heard("OH2RDG-7", "OH2GBA", before.peer_seals("an answer"), "41"))
    await before.settled()
    await before.m.stop()
    after = Rig(log, clock, keyring=NoKeys())
    await after.start()
    kept = {r.text: (r.seal, r.wire is not None) for r in after.m.records()}
    assert kept == {"locked text": ("open", True), "an answer": ("open", True)}, "what was read before stays readable; nothing is opened or sealed anew"
    assert (tmp_path / "message.key").exists(), "the key file is left alone"
    assert sent.wire is not None and not any(sent.text.encode() in frame.info for frame in after.tnc.sent), "a retry sends the ciphertext it kept, never the text"
