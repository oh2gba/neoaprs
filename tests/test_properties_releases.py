"""Properties of the readers of a release: a signed SHA256SUMS gives back each file's checksum and any
change to the list or the signature is refused with Unverified; versions compare as an order for any
text; the version page, the frequencies file and a changelog of any content never raise.
"""

import base64
import hashlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from hypothesis import given
from hypothesis import strategies as st

from neoaprs.releasenotes import sections, sections_after
from neoaprs.updateasset import Unverified, checksums, public_key, sign, signed_checksum
from neoaprs.versions import compare_versions, is_dial, parse_frequencies, parse_update
from tests.support.mutation import json_bytes, mutated_bytes, mutated_json, mutated_text
from tests.test_releasenotes import CHANGELOG

_NAME = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-", min_size=1, max_size=30).filter(
    lambda n: n[0].isalnum()
)
_FILES = st.dictionaries(_NAME, st.binary(max_size=8), min_size=1, max_size=5)
_SEED = st.binary(min_size=32, max_size=32)
_VERSION = st.tuples(st.integers(0, 99), st.integers(0, 99), st.integers(0, 99)).map(lambda v: ".".join(map(str, v)))


def sums_of(files: dict[str, bytes]) -> bytes:
    return "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items()).encode()


def other_signature(changed: bytes, signature: bytes) -> bool:
    """Whether the changed text is not the same signature (base64 leaves the last bits of its last letter free)."""
    try:
        return base64.b64decode(changed.strip(), validate=True) != base64.b64decode(signature.strip())
    except ValueError:
        return True


def key_of(seed: bytes) -> Ed25519PublicKey:
    raw = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    return public_key(base64.b64encode(raw).decode())


@given(_FILES, _SEED, _VERSION)
def test_a_signed_list_gives_back_each_files_checksum(files: dict[str, bytes], seed: bytes, version: str) -> None:
    """signed_checksum of a list signed for the version gives the SHA-256 of each file it names."""
    sums, key = sums_of(files), key_of(seed)
    signature = sign(sums, version, seed).encode()
    for name, data in files.items():
        assert signed_checksum(sums, signature, version, name, key) == hashlib.sha256(data).hexdigest()


@given(_FILES, _SEED, _VERSION, st.data())
def test_any_change_to_the_list_or_its_signature_is_unverified(
    files: dict[str, bytes], seed: bytes, version: str, data: st.DataObject
) -> None:
    """A list or a signature changed in any way, or the signature of another version, is refused."""
    sums, key = sums_of(files), key_of(seed)
    signature = sign(sums, version, seed).encode()
    name = next(iter(files))
    changed_sums = data.draw(mutated_bytes(sums, changes=3).filter(lambda s: s != sums))
    changed_signature = data.draw(mutated_bytes(signature, changes=3).filter(lambda s: other_signature(s, signature)))
    for args in (
        (changed_sums, signature, version),
        (sums, changed_signature, version),
        (sums, signature, "9" + version),
    ):
        try:
            signed_checksum(*args, name, key)
        except Unverified:
            continue
        raise AssertionError(f"accepted {args!r}")


@given(st.one_of(st.binary(max_size=120), mutated_bytes(sums_of({"a.exe": b"1", "b.deb": b"2"}), changes=6)))
def test_any_bytes_as_a_checksum_list_are_checksums_or_unverified(sums: bytes) -> None:
    """Any bytes give file names with 64 lower-case hex digits each, or Unverified."""
    try:
        found = checksums(sums)
    except Unverified:
        return
    assert found and all(len(sha) == 64 and sha == sha.lower() for sha in found.values())


_ANY_VERSION = st.one_of(st.text(max_size=16), _VERSION, _VERSION.flatmap(mutated_text))


@given(_ANY_VERSION, _ANY_VERSION, _ANY_VERSION)
def test_versions_compare_as_an_order(a: str, b: str, c: str) -> None:
    """compare_versions of any texts is -1, 0 or 1, the other way round reversed, and transitive."""
    ab, bc, ac = compare_versions(a, b), compare_versions(b, c), compare_versions(a, c)
    assert ab in (-1, 0, 1) and compare_versions(b, a) == -ab and compare_versions(a, a) == 0
    if ab <= 0 and bc <= 0:
        assert ac <= 0


def test_a_version_of_thousands_of_digits_compares_without_a_value_error() -> None:
    """The version page may give a version too long for int(); it is still newer than 0.26.1."""
    update = parse_update(json_bytes({"version": "9" * 5000}))
    assert update is not None and compare_versions(update.version, "0.26.1") == 1
    assert compare_versions("1." + "0" * 5000 + "1", "1.2") == -1 and compare_versions("1.0", "1." + "0" * 5000) == 0


def test_a_digit_of_another_script_compares_without_a_value_error() -> None:
    assert compare_versions("1.²", "1.1") in (-1, 1)


REAL_UPDATE = {
    "version": "0.26.1",
    "url": "https://neo.oh2gba.eu/download",
    "message": "New",
    "hf_dial": "7.0541 MHz USB",
}
REAL_FREQUENCIES = {
    "frequencies": [{"band": "40 m", "dial": "7.0541 MHz USB"}, {"band": "20 m", "dial": "14.1070 MHz USB"}]
}


@given(st.one_of(mutated_json(REAL_UPDATE, changes=4).map(json_bytes), st.binary(max_size=60)))
def test_any_answer_of_the_version_page_is_an_update_or_none(body: bytes) -> None:
    """Any change to a real answer gives an update with an https address or none, a short note and a dial."""
    update = parse_update(body)
    if update is not None:
        assert update.url == "" or update.url.startswith("https://")
        assert len(update.message) <= 200 and (update.hf_dial == "" or is_dial(update.hf_dial))
        compare_versions(update.version, "0.26.1")


@given(st.one_of(mutated_json(REAL_FREQUENCIES, changes=4).map(json_bytes), st.binary(max_size=60)))
def test_any_frequencies_file_is_dials_or_none(body: bytes) -> None:
    """Any change to a real file gives at most five dials, each of one band, longest first, or None."""
    found = parse_frequencies(body)
    if found is not None:
        assert 1 <= len(found) <= 5 and all(is_dial(f.dial) for f in found)
        assert len({f.band for f in found}) == len(found)


@given(st.one_of(mutated_text(CHANGELOG, changes=6), st.text(max_size=200)), _ANY_VERSION, _ANY_VERSION)
def test_any_changelog_gives_its_sections_without_raising(text: str, installed: str, latest: str) -> None:
    """Any changelog, a real one damaged above all, gives sections between any two versions, newest first."""
    found = sections_after(text, installed, latest)
    assert all(compare_versions(a.version, b.version) >= 0 for a, b in zip(found, found[1:], strict=False))
    assert len(sections(text)) <= text.count("##")
