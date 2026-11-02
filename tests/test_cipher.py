"""Encrypted messages (neoaprs/cipher.py): the key announcement and its reading, the shared key from either side, a sealed text that opens with the pair's key and with nothing else (another key, the
other direction, another station, a changed character, a cut packet), the room a message has, and the fingerprint."""
import pytest

from neoaprs import cipher
from neoaprs.aprsmessage import MAX_TEXT
from neoaprs.message import check_text

A = bytes(range(32))                                 # (any 32 bytes are an X25519 private key)
B = bytes(range(100, 132))


def test_a_key_pair_announces_its_public_key_in_one_message_and_the_text_reads_back() -> None:
    public = cipher.public_of(A)
    text = cipher.key_message(public)
    assert text.startswith("!K") and len(text) == 45 and len(public) == 32
    check_text(text)                                 # (a message can carry it: printable ASCII, under the limit, no | ~ {)
    assert cipher.key_of_message(text) == public
    assert cipher.key_of_message(text + " ") == public
    assert cipher.key_of_message("!Knot a key") is None and cipher.key_of_message("Hello") is None and cipher.key_of_message("!K" + "A" * 43 + "A") is None


def test_the_two_stations_derive_the_same_key_and_another_pair_derives_another() -> None:
    shared = cipher.shared_key(A, cipher.public_of(B))
    assert shared == cipher.shared_key(B, cipher.public_of(A)) and len(shared) == 32
    assert cipher.shared_key(A, cipher.public_of(bytes(32))) != shared


def test_a_sealed_text_fits_a_message_and_opens_from_the_other_side_with_the_text_inside() -> None:
    key = cipher.shared_key(A, cipher.public_of(B))
    text = "Moi, täällä kaikki ok 73"
    wire = cipher.seal(key, "OH2GBA", "OH2BEA-7", text)
    assert wire.startswith("!E") and len(wire) <= MAX_TEXT
    check_text(wire)
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", wire) == text
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", wire + " \r\n") == text


def test_the_longest_text_is_34_bytes_of_utf8_and_fills_a_message_to_the_brim() -> None:
    key = cipher.shared_key(A, cipher.public_of(B))
    longest = "x" * cipher.MAX_LOCKED
    wire = cipher.seal(key, "OH2GBA", "OH2BEA-7", longest)
    assert len(wire) == MAX_TEXT - 1 and cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", wire) == longest        # (48 bytes are 64 characters of base64; 49 would be 66, one over)
    with pytest.raises(cipher.CipherError) as over:
        cipher.seal(key, "OH2GBA", "OH2BEA-7", "ä" * 18)
    assert over.value.code == "lock.too_long" and over.value.params == {"length": 36, "max": 34}
    for bad in ("", "a\nb", "\x07"):
        with pytest.raises(cipher.CipherError) as refused:
            cipher.seal(key, "OH2GBA", "OH2BEA-7", bad)
        assert refused.value.code == "lock.unprintable"


def test_nothing_but_the_pairs_key_in_the_right_direction_opens_a_message() -> None:
    key = cipher.shared_key(A, cipher.public_of(B))
    wire = cipher.seal(key, "OH2GBA", "OH2BEA-7", "Hello", nonce=b"\1\2\3\4\5\6")
    assert cipher.open_sealed(key, "OH2BEA-7", "OH2GBA", wire) is None, "the other direction"
    assert cipher.open_sealed(key, "OH2GBA", "OH2XYZ", wire) is None, "another addressee"
    assert cipher.open_sealed(cipher.shared_key(A, cipher.public_of(bytes(32))), "OH2GBA", "OH2BEA-7", wire) is None, "another key"
    changed = wire[:-1] + ("A" if wire[-1] != "A" else "B")
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", changed) is None, "a changed character"
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", wire[:20]) is None, "a cut packet"
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", "!E!!not base64") is None and cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", "!Eabcd") is None
    assert cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", "Hello") is None, "no marker"
    assert cipher.is_locked(wire) and not cipher.is_locked("Hello")


def test_two_seals_of_one_text_differ_by_their_nonce_and_both_open() -> None:
    key = cipher.shared_key(A, cipher.public_of(B))
    first, second = (cipher.seal(key, "OH2GBA", "OH2BEA-7", "Same words") for _ in range(2))
    assert first != second and all(cipher.open_sealed(key, "OH2GBA", "OH2BEA-7", w) == "Same words" for w in (first, second))


def test_the_fingerprint_is_sixteen_hex_characters_in_four_groups_and_differs_between_keys() -> None:
    a, b = cipher.fingerprint(cipher.public_of(A)), cipher.fingerprint(cipher.public_of(B))
    assert len(a) == 19 and a.count(" ") == 3 and all(c in "0123456789ABCDEF" for c in a.replace(" ", "")) and a != b
    assert cipher.fingerprint(cipher.public_of(A)) == a


def test_a_new_private_key_is_32_random_bytes() -> None:
    first, second = cipher.new_private(), cipher.new_private()
    assert len(first) == 32 and first != second
