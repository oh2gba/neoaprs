"""Encrypted messages between two stations, carried as the text of an ordinary APRS message.

X25519 key agreement, HKDF-SHA256, AES-256-GCM with the two calls as associated data.
"""

import base64
import binascii
import hashlib
import secrets

from neoaprs.aprsmessage import MAX_TEXT
from neoaprs.coded import CodedError

KEY_MARK = "!K"
LOCK_MARK = "!E"
KEY_LEN = 32
NONCE_LEN = 6
TAG_LEN = 8
_GCM_NONCE_LEN = 12  # 96 bits: the six random bytes, padded with zeros
_ROOM = (MAX_TEXT - len(LOCK_MARK)) * 6 // 8
MAX_LOCKED = _ROOM - NONCE_LEN - TAG_LEN  # bytes of UTF-8 text per message
_INFO = b"NeoAPRS message key v1"


class CipherError(CodedError):
    """A text that cannot be sealed."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes | None:
    """Decode unpadded base64; return None if invalid."""
    try:
        return base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None


# `cryptography` is imported where used: a daemon without --encryption never loads it.
def new_private() -> bytes:
    """Return a new private key."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    return X25519PrivateKey.generate().private_bytes_raw()


def public_of(private: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    return X25519PrivateKey.from_private_bytes(private).public_key().public_bytes_raw()


def fingerprint(public: bytes) -> str:
    """Return the SHA-256 of the key as 16 hex characters in groups of four."""
    digest = hashlib.sha256(public).hexdigest()[:16].upper()
    return " ".join(digest[i : i + 4] for i in range(0, 16, 4))


def shared_key(private: bytes, peer_public: bytes) -> bytes:
    """Return the key two stations share; raise ValueError for an unusable public key."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    secret = X25519PrivateKey.from_private_bytes(private).exchange(X25519PublicKey.from_public_bytes(peer_public))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(secret)


def is_usable_key(public: bytes) -> bool:
    """Return whether a shared key can be made with this public key (not zeros or low order)."""
    if len(public) != KEY_LEN:
        return False
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

    try:
        X25519PrivateKey.generate().exchange(X25519PublicKey.from_public_bytes(public))
    except ValueError:
        return False
    return True


def key_message(public: bytes) -> str:
    """Return the text of the message announcing a public key."""
    return KEY_MARK + _b64(public)


def key_of_message(text: str) -> bytes | None:
    """Return the public key a text announces, or None."""
    if not text.startswith(KEY_MARK):
        return None
    key = _unb64(text[len(KEY_MARK) :].rstrip())
    return key if key is not None and len(key) == KEY_LEN else None


def is_locked(text: str) -> bool:
    """Return whether a text is an encrypted message."""
    return text.startswith(LOCK_MARK)


def _aad(sender: str, addressee: str) -> bytes:
    return f"{sender}>{addressee}".encode("ascii", "replace")


def check_locked_text(text: str) -> bytes:
    """Return the UTF-8 of a text to seal; raise CipherError if unfit."""
    if text == "" or not text.isprintable():
        raise CipherError("the text is empty, or has a character a message cannot carry", "lock.unprintable")
    data = text.encode("utf-8")
    if len(data) > MAX_LOCKED:
        raise CipherError(
            f"the text is {len(data)} bytes, at most {MAX_LOCKED} fit in an encrypted message",
            "lock.too_long",
            length=len(data),
            max=MAX_LOCKED,
        )
    return data


def seal(key: bytes, sender: str, addressee: str, text: str, nonce: bytes | None = None) -> str:
    """Return the message text carrying `text` encrypted from `sender` to `addressee`.

    Raise CipherError as `check_locked_text` does. `nonce` is for tests.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    data = check_locked_text(text)
    salt = secrets.token_bytes(NONCE_LEN) if nonce is None else nonce
    encryptor = Cipher(
        algorithms.AES(key), modes.GCM(salt + b"\0" * (_GCM_NONCE_LEN - NONCE_LEN), None, TAG_LEN)
    ).encryptor()
    encryptor.authenticate_additional_data(_aad(sender, addressee))
    body = encryptor.update(data) + encryptor.finalize()
    return LOCK_MARK + _b64(salt + body + encryptor.tag[:TAG_LEN])


def open_sealed(key: bytes, sender: str, addressee: str, wire: str) -> str | None:
    """Return the plain text of an encrypted message, or None if it fails authentication."""
    if not is_locked(wire):
        return None
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    data = _unb64(wire[len(LOCK_MARK) :].rstrip())
    if data is None or len(data) < NONCE_LEN + TAG_LEN + 1:
        return None
    salt, body, tag = data[:NONCE_LEN], data[NONCE_LEN:-TAG_LEN], data[-TAG_LEN:]
    decryptor = Cipher(
        algorithms.AES(key), modes.GCM(salt + b"\0" * (_GCM_NONCE_LEN - NONCE_LEN), tag, TAG_LEN)
    ).decryptor()
    decryptor.authenticate_additional_data(_aad(sender, addressee))
    try:
        text = (decryptor.update(body) + decryptor.finalize()).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError):
        return None
    return text if text != "" and text.isprintable() else None
