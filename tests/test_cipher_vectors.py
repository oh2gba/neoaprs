"""Known answers for the encrypted messages (neoaprs/cipher.py): fixed keys, the shared key, the key announcement, and a sealed message with a fixed nonce, each written down as a literal, so that a change in the
construction (the key derivation's info, the nonce layout, the tag length, the associated data, the base64 form) cannot go by unnoticed, and a message sent by one version opens in another. The X25519 keys and
the shared secret are the two parties' of RFC 7748, section 6.1; the rest was computed once and is also rebuilt here from the `cryptography` library alone."""
import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from neoaprs import cipher

ALICE = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
BOB = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
ALICE_PUBLIC = bytes.fromhex("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
BOB_PUBLIC = bytes.fromhex("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
X25519_SECRET = bytes.fromhex("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742")          # (RFC 7748: what each side gets from its private and the other's public key)
SHARED_KEY = bytes.fromhex("fc6a437282d78d66009fe0570f5d61f8ee21dfa17cb24634187a0ed77ffd62d7")          # (HKDF-SHA256 of that secret, no salt, info "NeoAPRS message key v1", 32 bytes)
NONCE = bytes.fromhex("000102030405")
TEXT = "Moi, täällä kaikki ok 73"
WIRE = "!EAAECAwQF+Fj0igdMBaCBLMrv9tYRiMyiCnTmWDYqokBNK3x+f4oS4cE"
KEY_TEXT = "!KhSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo"


def test_the_public_keys_and_the_announcement_of_a_key_are_what_they_were() -> None:
    assert cipher.public_of(ALICE) == ALICE_PUBLIC and cipher.public_of(BOB) == BOB_PUBLIC
    assert cipher.key_message(ALICE_PUBLIC) == KEY_TEXT and cipher.key_of_message(KEY_TEXT) == ALICE_PUBLIC
    assert cipher.fingerprint(ALICE_PUBLIC) == "300C 9C96 03B9 2A4B"


def test_the_shared_key_is_the_hkdf_of_the_x25519_secret_from_either_side() -> None:
    assert cipher.shared_key(ALICE, BOB_PUBLIC) == SHARED_KEY == cipher.shared_key(BOB, ALICE_PUBLIC)
    assert HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"NeoAPRS message key v1").derive(X25519_SECRET) == SHARED_KEY, "the derivation, written out again"


def test_a_message_sealed_with_a_fixed_nonce_is_the_text_it_was_and_opens_to_the_text() -> None:
    assert cipher.seal(SHARED_KEY, "OH2GBA", "OH2BEA-7", TEXT, NONCE) == WIRE
    assert cipher.open_sealed(SHARED_KEY, "OH2GBA", "OH2BEA-7", WIRE) == TEXT
    assert cipher.open_sealed(SHARED_KEY, "OH2BEA-7", "OH2GBA", WIRE) is None, "the calls are bound in, in their order"


def test_the_message_is_what_aes_256_gcm_makes_of_the_text_by_the_library_alone() -> None:
    """Six bytes of nonce and six of zero, the calls `FROM>TO` as associated data, the first eight bytes of GCM's tag at the end, base64 without padding after `!E`."""
    sealed = AESGCM(SHARED_KEY).encrypt(NONCE + bytes(6), TEXT.encode("utf-8"), b"OH2GBA>OH2BEA-7")
    body, tag = sealed[:-16], sealed[-16:-8]
    assert "!E" + base64.b64encode(NONCE + body + tag).decode("ascii").rstrip("=") == WIRE
