"""The certificates of the secure connection (`web/https`): a local CA and a server certificate.

Files in `tls/` of the data folder, owner-only: the CA (ten years, kept while its files exist)
and the server certificate (at most 800 days; Apple's limit is 825). Keys are never served.
"""

import hashlib
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from neoaprs.clock import utc

from .addresses import as_address

log = logging.getLogger("neoaprs.web")

CA_DAYS = 3650
SERVER_DAYS = 800
RENEW_BEFORE_DAYS = 30
# A device whose clock is a little behind still accepts a certificate made a moment ago.
BACKDATE = timedelta(days=1)
# A computer with no real-time clock starts at its last shutdown date or 1970; a certificate made
# then would be expired for every device.
CLOCK_SANE_AFTER = utc(2025, 1, 1)
NAME_MAX = 64  # longest common name
Names = tuple[str, ...]


class TlsError(Exception):
    """The certificates could not be made or read.

    `clock` is True when the computer's clock is not set.
    """

    def __init__(self, text: str, clock: bool = False) -> None:
        super().__init__(text)
        self.clock = clock


@dataclass(frozen=True)
class Certificates:
    ca_der: bytes
    fingerprint: str  # SHA-256 of ca_der, "AB:CD:..."
    chain_file: Path
    key_file: Path
    names: Names  # names and addresses the server certificate covers
    expires: datetime


def fingerprint_of(der: bytes) -> str:
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def wanted_names(host: str, addresses: Iterable[str], more: Iterable[str] = ()) -> Names:
    """Return the names the server certificate must cover, each once.

    A name that cannot go in a certificate is left out.
    """
    names: list[str] = []
    for item in (host, f"{host}.local" if host else "", "localhost", "127.0.0.1", "::1", *addresses, *more):
        item = item.strip().lower().rstrip(".")
        address = as_address(item)
        if address is not None:
            item = str(address)
        elif not item or not item.isascii() or not item.isprintable() or " " in item or len(item) > 253:
            continue
        if item not in names:
            names.append(item)
    return tuple(names)


def _general_names(names: Names) -> list[x509.GeneralName]:
    out: list[x509.GeneralName] = []
    for name in names:
        address = as_address(name)
        out.append(x509.DNSName(name) if address is None else x509.IPAddress(address))
    return out


def _names_of(cert: x509.Certificate) -> Names:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return ()
    return (
        *(n.lower() for n in san.get_values_for_type(x509.DNSName)),
        *(str(ip) for ip in san.get_values_for_type(x509.IPAddress)),
    )


def _write_private(path: Path, data: bytes) -> None:
    """Write the file atomically, with the owner-only mode set before any byte is written."""
    tmp = path.with_name(path.name + ".new")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def _pem_cert(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _builder(
    subject: x509.Name, issuer: x509.Name, key: ec.EllipticCurvePrivateKey, now: datetime, days: int
) -> x509.CertificateBuilder:
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - BACKDATE)
        .not_valid_after(now + timedelta(days=days))
    )


def make_ca(host: str, now: datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NeoAPRS"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"NeoAPRS local CA ({host})"[:NAME_MAX]),
        ]
    )
    cert = (
        _builder(name, name, key, now, CA_DAYS)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def make_server(
    ca_key: ec.EllipticCurvePrivateKey, ca: x509.Certificate, host: str, names: Names, now: datetime
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NeoAPRS"),
            x509.NameAttribute(NameOID.COMMON_NAME, (host or "neoaprs")[:NAME_MAX]),
        ]
    )
    cert = (
        _builder(subject, ca.subject, key, now, SERVER_DAYS)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(_general_names(names)), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _public_bytes(key: PublicKeyTypes) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def renewal_reason(
    cert: x509.Certificate, key: ec.EllipticCurvePrivateKey, ca: x509.Certificate, names: Names, now: datetime
) -> str:
    """Return why the server certificate must be remade, or "" when it is good."""
    try:
        cert.verify_directly_issued_by(ca)
    except (InvalidSignature, ValueError, TypeError):
        return "it was not signed by the authority in the folder"
    if _public_bytes(cert.public_key()) != _public_bytes(key.public_key()):
        return "it does not belong to its key"
    if cert.not_valid_after_utc - now < timedelta(days=RENEW_BEFORE_DAYS):
        return "it runs out within 30 days"
    if cert.not_valid_before_utc > now:
        return "it is not valid yet"
    if missing := [n for n in names if n not in _names_of(cert)]:
        return f"it does not name {', '.join(missing)}"
    return ""


class CertificateStore:
    """Keep the certificates in `folder`.

    `ensure` is blocking (files, key generation): call it from a thread.
    """

    def __init__(self, folder: Path, clock: Callable[[], datetime]) -> None:
        self.folder = folder
        self._clock = clock

    def _path(self, name: str) -> Path:
        return self.folder / name

    def ensure(self, host: str, addresses: Iterable[str], more: Iterable[str] = ()) -> Certificates:
        now = self._clock()
        if now < CLOCK_SANE_AFTER:
            raise TlsError("the clock of this computer is not set; the secure connection starts when it is", clock=True)
        try:
            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                self.folder.chmod(0o700)
            except OSError:
                pass  # a system without such modes
            ca_key, ca = self._ca(host, now)
            names = wanted_names(host, addresses, more)
            key, cert = self._server(ca_key, ca, host, names, now)
        except OSError as e:
            raise TlsError(f"the certificates in {self.folder} could not be written or read: {e}") from e
        der = ca.public_bytes(serialization.Encoding.DER)
        return Certificates(
            der,
            fingerprint_of(der),
            self._path("server.crt"),
            self._path("server.key"),
            _names_of(cert),
            cert.not_valid_after_utc,
        )

    def _ca(self, host: str, now: datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        key_file, cert_file = self._path("ca.key"), self._path("ca.crt")
        if not (key_file.is_file() and cert_file.is_file()):
            log.info("making NeoAPRS's certificate authority in %s", self.folder)
            key, cert = make_ca(host, now)
            _write_private(key_file, _pem_key(key))
            _write_private(cert_file, _pem_cert(cert))
            return key, cert
        # A file that exists but cannot be read is not replaced: devices that trust it would not
        # trust a new one.
        try:
            loaded = serialization.load_pem_private_key(key_file.read_bytes(), None)
            cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
        except ValueError as e:
            raise TlsError(
                f"{key_file} or {cert_file} cannot be read ({e}); move the folder {self.folder} away to make new ones"
            ) from e
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise TlsError(
                f"{key_file} is not an elliptic-curve key; move the folder {self.folder} away to make new ones"
            )
        if cert.not_valid_after_utc - now < timedelta(days=RENEW_BEFORE_DAYS):
            log.warning(
                "NeoAPRS's certificate authority in %s runs out within %d days; a new one is made, and the devices have to trust it again",
                self.folder,
                RENEW_BEFORE_DAYS,
            )
            key, cert = make_ca(host, now)
            _write_private(key_file, _pem_key(key))
            _write_private(cert_file, _pem_cert(cert))
            return key, cert
        return loaded, cert

    def _server(
        self, ca_key: ec.EllipticCurvePrivateKey, ca: x509.Certificate, host: str, names: Names, now: datetime
    ) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        key_file, cert_file = self._path("server.key"), self._path("server.crt")
        reason = "it is not there"
        if key_file.is_file() and cert_file.is_file():
            try:
                loaded = serialization.load_pem_private_key(key_file.read_bytes(), None)
                cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
                if isinstance(loaded, ec.EllipticCurvePrivateKey):
                    reason = renewal_reason(cert, loaded, ca, names, now)
                    if not reason:
                        return loaded, cert
                else:
                    reason = "its key is of another kind"
            except ValueError as e:
                reason = f"it cannot be read ({e})"
        log.info("making the certificate of the page for %s: %s", ", ".join(names), reason)
        key, cert = make_server(ca_key, ca, host, names, now)
        _write_private(key_file, _pem_key(key))
        _write_private(cert_file, _pem_cert(cert))
        return key, cert
