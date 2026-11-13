"""The signature of a release's SHA256SUMS (neoaprs/updateasset.py, `signed_checksum`): the project's public key is pinned and in one place, a list is believed only with the signature of exactly the version
asked for, every way it can fail is the one problem `unverified` of Update now with the file never downloaded, NEOAPRS_UPDATE_KEY stands in only for a fake release, and the list stays what the programs from
before the signature read. Every key here is made by the test."""
import base64
import hashlib
import secrets
from pathlib import Path

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from neoaprs.services.selfinstall import release_key
from neoaprs.services.selfupdate import SelfUpdate
from neoaprs.updateasset import PUBLIC_KEY, RELEASES, Unverified, public_key, sign, signed_checksum, signed_message, url_allowed
from neoaprs.versions import InstallInfo
from tests.support.env import until
from tests.support.fakerelease import BODY, NAME, SEED, SUMS, FakeInstaller, FakeRelease, old_checksum_for, public

ROOT = Path(__file__).resolve().parent.parent
OTHER = hashlib.sha256(b"another file").hexdigest()
MINE = hashlib.sha256(BODY).hexdigest()


def raw(key: object) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)        # type: ignore[attr-defined, no-any-return]


def test_the_projects_public_key_is_pinned() -> None:
    assert PUBLIC_KEY == "y+tv2daKD9MoQhAL7NBZrNMl1/RvvCRoMU0QN8NwZyc="
    assert raw(public_key()) == base64.b64decode(PUBLIC_KEY) and len(base64.b64decode(PUBLIC_KEY)) == 32


def test_the_public_key_is_in_one_place_of_the_program() -> None:
    holders = [p.relative_to(ROOT).as_posix() for p in (ROOT / "neoaprs").rglob("*.py") if PUBLIC_KEY in p.read_text(encoding="utf-8")]
    assert holders == ["neoaprs/updateasset.py"]


@pytest.mark.parametrize("text", ["", "not base64!", base64.b64encode(bytes(31)).decode(), base64.b64encode(bytes(33)).decode()])
def test_a_public_key_that_is_not_32_bytes_of_base64_is_none(text: str) -> None:
    with pytest.raises(ValueError):
        public_key(text)


def test_a_list_signed_for_its_version_gives_the_files_sum() -> None:
    signature = sign(SUMS, "0.7.0", SEED).encode()
    assert len(base64.b64decode(signature.strip())) == 64
    assert signed_checksum(SUMS, signature, "0.7.0", NAME, public()) == MINE
    assert signed_message(SUMS, "0.7.0") == b"NeoAPRS SHA256SUMS v0.7.0\n" + SUMS


def bad(sums: bytes = SUMS, signature: bytes | None = None, version: str = "0.7.0", signed_for: str = "0.7.0", seed: bytes = SEED) -> str:
    """Why `signed_checksum` does not believe this list for 0.7.0 (it must not)."""
    with pytest.raises(Unverified) as refused:
        signed_checksum(sums, sign(sums, signed_for, seed).encode() if signature is None else signature, version, NAME, public())
    return str(refused.value)


def test_a_list_that_names_only_another_file_is_not_believed_for_it() -> None:
    assert "names no" in bad(f"{OTHER}  NeoAPRS-Setup-0.7.0.exe\n{OTHER}  {NAME}.sig\n".encode())


@pytest.mark.parametrize("second", [OTHER, MINE])
def test_a_list_that_names_a_file_twice_is_not_believed_even_with_the_same_sum(second: str) -> None:
    assert "twice" in bad(f"{MINE}  {NAME}\n{second}  {NAME}\n".encode())


def test_a_signature_over_a_different_list_does_not_hold() -> None:
    other = f"{OTHER}  {NAME}\n".encode()
    assert "not the project's signature" in bad(SUMS, sign(other, "0.7.0", SEED).encode())
    assert "not the project's signature" in bad(SUMS + b"\n", sign(SUMS, "0.7.0", SEED).encode())


@pytest.mark.parametrize("cut", [1, 4, 20])
def test_a_truncated_signature_does_not_hold(cut: int) -> None:
    whole = base64.b64decode(sign(SUMS, "0.7.0", SEED))
    assert bad(signature=base64.b64encode(whole[:-cut]))
    assert bad(signature=sign(SUMS, "0.7.0", SEED).encode()[:-cut - 2])


@pytest.mark.parametrize("signature", [b"", b"\n", b"not base64 at all", base64.b64encode(bytes(64)), base64.b64encode(bytes(range(65)))])
def test_a_signature_that_is_none_does_not_hold(signature: bytes) -> None:
    assert bad(signature=signature)


def test_an_empty_list_is_not_believed_even_signed() -> None:
    assert "empty" in bad(b"")
    assert "empty" in bad(b"\n\n")


def test_a_line_that_is_not_a_checksum_line_makes_the_list_unbelieved() -> None:
    assert "line 2" in bad(f"{MINE}  {NAME}\n# NeoAPRS 0.7.0\n".encode())
    assert "UTF-8" in bad(f"{MINE}  {NAME}\n".encode() + b"\xff\n")


def test_a_signed_list_of_an_older_release_offered_as_the_newer_one_does_not_hold() -> None:
    assert "list of v0.7.0" in bad(signed_for="0.6.9")
    assert "list of v0.7.0" in bad(signed_for="0.7.0-rc1")
    assert "list of v0.7.0" in bad(signed_for="0.7.00")


def test_a_list_signed_with_another_key_does_not_hold() -> None:
    assert "not the project's signature" in bad(seed=secrets.token_bytes(32))


def test_signing_takes_a_32_byte_seed_and_a_version_of_a_release() -> None:
    with pytest.raises(ValueError):
        sign(SUMS, "0.7.0", SEED[:31])
    with pytest.raises(ValueError):
        sign(SUMS, "v0.7.0", SEED)


def test_the_list_a_release_carries_is_read_by_the_programs_from_before_the_signature_unchanged() -> None:
    names = ["neoaprs-0.7.0.tar.gz", "neoaprs-0.7.0-py3-none-any.whl", "install.sh", "NeoAPRS-Setup-0.7.0.exe", NAME, "NeoAPRS-0.7.0-arm64.dmg", "neoaprs_0.7.0_amd64.deb", "neoaprs_0.7.0_arm64.deb",
             "NeoAPRS-Setup.exe", "NeoAPRS-x86_64.AppImage", "NeoAPRS-arm64.dmg", "neoaprs_amd64.deb", "neoaprs_arm64.deb"]
    sums = "".join(f"{hashlib.sha256(name.encode()).hexdigest()}  {name}\n" for name in sorted(names)).encode()       # (what `sha256sum -- *` writes)
    signature = sign(sums, "0.7.0", SEED).encode()
    for name in names:
        assert old_checksum_for(sums, name) == signed_checksum(sums, signature, "0.7.0", name, public()) == hashlib.sha256(name.encode()).hexdigest()
    assert b"SHA256SUMS" not in sums                     # (the signature is a file beside the list: the list is not changed by it)


def service(tmp_path: Path, release: FakeRelease, installer: FakeInstaller, key: bool = True) -> SelfUpdate:
    return SelfUpdate(InstallInfo("appimage", str(tmp_path / "NeoAPRS-0.6.7-x86_64.AppImage")), installer, lambda: "0.7.0", (RELEASES, url_allowed), release.fetch_sums, release.fetch,
                      key=public() if key else None)


def twice(sums: bytes) -> bytes:
    return sums + sums.splitlines(keepends=True)[-1]


@pytest.mark.parametrize("release", [
    FakeRelease(signature=b""),                                                                          # no SHA256SUMS.sig
    FakeRelease(signature=sign(SUMS, "0.7.0", SEED).encode()[:40]),                                      # truncated
    FakeRelease(signature=sign(SUMS, "0.7.0", secrets.token_bytes(32)).encode()),                        # another key
    FakeRelease(signature=sign(f"{OTHER}  {NAME}\n".encode(), "0.7.0", SEED).encode()),                 # over another list
    FakeRelease(version="0.6.9"),                                                                        # the signed list of an older release
    FakeRelease(sums=b""),                                                                               # empty, and signed
    FakeRelease(sums=twice(SUMS)),                                                                       # the file named twice, and signed
    FakeRelease(sums=f"{OTHER}  NeoAPRS-Setup-0.7.0.exe\n".encode()),                                   # another file only, and signed
], ids=["no-signature", "truncated", "another-key", "another-list", "downgrade", "empty", "doubled", "another-file"])
async def test_every_way_the_check_fails_is_the_one_problem_unverified_and_nothing_is_downloaded(tmp_path: Path, release: FakeRelease) -> None:
    release.asked.clear()
    installer = FakeInstaller(tmp_path)
    job = service(tmp_path, release, installer)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert job.status().problem == "unverified" and "could not be checked" in job.status().detail and "nothing is installed" in job.status().detail
    assert release.asked == [f"{RELEASES}/v0.7.0/SHA256SUMS", f"{RELEASES}/v0.7.0/SHA256SUMS.sig"] and installer.installed == []
    assert list(tmp_path.iterdir()) == []
    await job.stop()


async def test_update_now_believes_the_projects_key_and_no_other_by_default(tmp_path: Path) -> None:
    installer = FakeInstaller(tmp_path)
    job = service(tmp_path, FakeRelease(), installer, key=False)         # (signed with the test's own key, not the project's)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert job.status().problem == "unverified" and installer.installed == []
    await job.stop()


TEST_KEY = base64.b64encode(raw(Ed25519PrivateKey.generate().public_key())).decode()
FAKE = {"NEOAPRS_UPDATE_FROM": "http://127.0.0.1:9/releases", "NEOAPRS_UPDATE_TEST": "1"}


def test_the_key_of_neoaprs_update_key_is_taken_only_with_the_fake_release_of_this_computer() -> None:
    assert base64.b64encode(raw(release_key({**FAKE, "NEOAPRS_UPDATE_KEY": TEST_KEY}))).decode() == TEST_KEY
    assert base64.b64encode(raw(release_key({"NEOAPRS_UPDATE_FROM": "http://127.0.0.1:9/releases", "NEOAPRS_INSTALL_KIND": "appimage", "NEOAPRS_UPDATE_KEY": TEST_KEY}))).decode() == TEST_KEY


@pytest.mark.parametrize("environ", [
    {"NEOAPRS_UPDATE_KEY": TEST_KEY},                                                                            # GitHub: only the project's key
    {"NEOAPRS_UPDATE_KEY": TEST_KEY, "NEOAPRS_UPDATE_TEST": "1"},
    {"NEOAPRS_UPDATE_KEY": TEST_KEY, "NEOAPRS_UPDATE_FROM": "http://127.0.0.1:9/releases"},                      # no switch: GitHub
    {"NEOAPRS_UPDATE_KEY": TEST_KEY, "NEOAPRS_UPDATE_FROM": "http://example.org/releases", "NEOAPRS_UPDATE_TEST": "1"},
    {**FAKE, "NEOAPRS_UPDATE_KEY": "not a key"},
    {**FAKE, "NEOAPRS_UPDATE_KEY": base64.b64encode(bytes(31)).decode()},
    FAKE,
    {},
], ids=["github", "test-switch-alone", "no-switch", "not-this-computer", "not-a-key", "short-key", "no-key", "nothing"])
def test_anything_else_is_the_projects_key(environ: dict[str, str]) -> None:
    assert raw(release_key(environ)) == base64.b64decode(PUBLIC_KEY)
