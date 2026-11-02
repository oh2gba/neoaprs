"""Encrypted messages between two stations, as text that rides in an ordinary APRS message (services/keyring.py keeps the keys, services/messaging.py sends and services/inbox.py opens).

Each station has one X25519 key pair. Its public key is announced as a message whose text is `!K` and the key in base64 (43 characters, no padding): `key_message` makes it, `key_of_message` reads it.
Two stations share one key: X25519 of one's private and the other's public key, through HKDF-SHA256 (`shared_key`). A message is `!E` and base64 of a 6-byte random nonce, the ciphertext and an 8-byte tag,
AES-256-GCM (`seal`); the sender's and the addressee's calls are bound in as associated data, so that a recording sent again under another call, or to another station, does not open. The text inside is
UTF-8 (a locked message may say ä and ö, which a plain message cannot) of at most MAX_LOCKED bytes: 67 characters of message text less the marker leave 65 for base64, which holds 48 bytes (49 would need 66), less the nonce and the tag.
A random nonce needs no counter and nothing kept between runs; six bytes repeat, by the birthday bound, after some sixteen million messages between one pair.

`open_sealed` gives the text or None: a text that does not open (another key, a tampered or truncated packet, another pair of calls) is nobody's business but the log's. The fingerprint of a key
(`fingerprint`) is 16 hex characters in four groups, the start of SHA-256 of the public key, for two operators to compare on voice. Nothing here does I/O: the random bytes come from `secrets`."""
import base64
import binascii
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from neoaprs.aprsmessage import MAX_TEXT
from neoaprs.coded import CodedError

KEY_MARK = "!K"                                      # the text of a message that announces the sender's public key: the marker and the key in base64
LOCK_MARK = "!E"                                     # the text of an encrypted message: the marker and the nonce, the ciphertext and the tag in base64
KEY_LEN = 32                                         # X25519 keys, private and public, are 32 bytes
NONCE_LEN = 6
TAG_LEN = 8
_GCM_NONCE_LEN = 12                                  # GCM takes 96 bits: the six random bytes and six of zero
_ROOM = (MAX_TEXT - len(LOCK_MARK)) * 6 // 8         # bytes that fit in the base64 of a message's text after the marker: 48
MAX_LOCKED = _ROOM - NONCE_LEN - TAG_LEN             # bytes of UTF-8 text an encrypted message carries: 34
_INFO = b"NeoAPRS message key v1"


class CipherError(CodedError):
    """A text that cannot be sealed: too long, or with a character a message cannot carry."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes | None:
    """The bytes of base64 without padding; None for text that is not that."""
    try:
        return base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None


# ---- keys
def new_private() -> bytes:
    """A new private key, 32 random bytes."""
    return X25519PrivateKey.generate().private_bytes_raw()


def public_of(private: bytes) -> bytes:
    return X25519PrivateKey.from_private_bytes(private).public_key().public_bytes_raw()


def fingerprint(public: bytes) -> str:
    """16 hex characters in four groups, `A1B2 C3D4 E5F6 0718`: the start of SHA-256 of the public key."""
    digest = hashlib.sha256(public).hexdigest()[:16].upper()
    return " ".join(digest[i:i + 4] for i in range(0, 16, 4))


def shared_key(private: bytes, peer_public: bytes) -> bytes:
    """The 32-byte key two stations share: X25519 of our private and their public key, through HKDF-SHA256. The same from either side."""
    secret = X25519PrivateKey.from_private_bytes(private).exchange(X25519PublicKey.from_public_bytes(peer_public))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(secret)


# ---- the key announcement
def key_message(public: bytes) -> str:
    """The text of the message that announces a public key: `!K` and 43 characters of base64."""
    return KEY_MARK + _b64(public)


def key_of_message(text: str) -> bytes | None:
    """The public key a message's text announces, None when the text is no announcement (another text, or a key of the wrong size)."""
    if not text.startswith(KEY_MARK):
        return None
    key = _unb64(text[len(KEY_MARK):].rstrip())
    return key if key is not None and len(key) == KEY_LEN else None


def is_locked(text: str) -> bool:
    """Whether a message's text is an encrypted message (it starts with the marker; whether it opens is another matter)."""
    return text.startswith(LOCK_MARK)


# ---- sealing and opening
def _aad(sender: str, addressee: str) -> bytes:
    return f"{sender}>{addressee}".encode("ascii", "replace")


def check_locked_text(text: str) -> bytes:
    """The UTF-8 of a text that is to be sealed. Raises CipherError when it is empty, has a control character, or is over MAX_LOCKED bytes (`lock.too_long`, with the length and the limit)."""
    if text == "" or not text.isprintable():
        raise CipherError("the text is empty, or has a character a message cannot carry", "lock.unprintable")
    data = text.encode("utf-8")
    if len(data) > MAX_LOCKED:
        raise CipherError(f"the text is {len(data)} bytes, at most {MAX_LOCKED} fit in an encrypted message", "lock.too_long", length=len(data), max=MAX_LOCKED)
    return data


def seal(key: bytes, sender: str, addressee: str, text: str, nonce: bytes | None = None) -> str:
    """The text of the message that carries `text` encrypted from `sender` to `addressee` with the pair's key: `!E` and base64 of the nonce, the ciphertext and the tag, at most MAX_TEXT characters.
    Raises CipherError as `check_locked_text` does. `nonce` is for the tests; else six random bytes."""
    data = check_locked_text(text)
    salt = secrets.token_bytes(NONCE_LEN) if nonce is None else nonce
    encryptor = Cipher(algorithms.AES(key), modes.GCM(salt + b"\0" * (_GCM_NONCE_LEN - NONCE_LEN), None, TAG_LEN)).encryptor()
    encryptor.authenticate_additional_data(_aad(sender, addressee))
    body = encryptor.update(data) + encryptor.finalize()
    return LOCK_MARK + _b64(salt + body + encryptor.tag[:TAG_LEN])


def open_sealed(key: bytes, sender: str, addressee: str, wire: str) -> str | None:
    """The text inside an encrypted message from `sender` to `addressee`, with the pair's key; None when it does not open: no marker, not base64, too short, another key, another pair of calls, tampered,
    or not UTF-8 inside."""
    if not is_locked(wire):
        return None
    data = _unb64(wire[len(LOCK_MARK):].rstrip())
    if data is None or len(data) < NONCE_LEN + TAG_LEN + 1:
        return None
    salt, body, tag = data[:NONCE_LEN], data[NONCE_LEN:-TAG_LEN], data[-TAG_LEN:]
    decryptor = Cipher(algorithms.AES(key), modes.GCM(salt + b"\0" * (_GCM_NONCE_LEN - NONCE_LEN), tag, TAG_LEN)).decryptor()
    decryptor.authenticate_additional_data(_aad(sender, addressee))
    try:
        text = (decryptor.update(body) + decryptor.finalize()).decode("utf-8")
    except (InvalidTag, UnicodeDecodeError):
        return None
    return text if text != "" and text.isprintable() else None
