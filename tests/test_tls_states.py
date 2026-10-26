"""The states a server certificate can be found in (neoaprs/web/tls.py), each with the reason the log gives for making it again, and the files that cannot be used: a key that is not its certificate's, a certificate
that is not valid yet (the clock was set back), one that runs out in 30 days, one without names, a key of another kind, an authority whose key is of another kind, and a folder whose mode cannot be set. Real
generated certificates and a clock the test holds."""
import logging
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID

from neoaprs.web.tls import BACKDATE, RENEW_BEFORE_DAYS, SERVER_DAYS, CertificateStore, TlsError, _names_of, _pem_cert, _pem_key
from tests.support.clock import FixedClock
from tests.test_tls import HOST, LAN, ca_cert, san, server_cert, store

Change = Callable[[Path, FixedClock], None]
FOLDER = "tls"


def pem_of(private: ec.EllipticCurvePrivateKey | ed25519.Ed25519PrivateKey) -> bytes:
    return private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def another_key(folder: Path, clock: FixedClock) -> None:
    (folder / FOLDER / "server.key").write_bytes(_pem_key(ec.generate_private_key(ec.SECP256R1())))


def clock_set_back(folder: Path, clock: FixedClock) -> None:
    clock.advance(-86400 * 2)


def about_to_run_out(folder: Path, clock: FixedClock) -> None:
    clock.advance(86400 * (SERVER_DAYS - RENEW_BEFORE_DAYS + 1))


def without_names(folder: Path, clock: FixedClock) -> None:
    """The same key and the same authority, a certificate that names nothing."""
    ca_key = serialization.load_pem_private_key((folder / FOLDER / "ca.key").read_bytes(), None)
    key = serialization.load_pem_private_key((folder / FOLDER / "server.key").read_bytes(), None)
    assert isinstance(ca_key, ec.EllipticCurvePrivateKey) and isinstance(key, ec.EllipticCurvePrivateKey)
    ca = ca_cert(folder)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])).issuer_name(ca.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(clock() - BACKDATE).not_valid_after(clock() + timedelta(days=100)).sign(ca_key, hashes.SHA256()))
    (folder / FOLDER / "server.crt").write_bytes(_pem_cert(cert))


def key_of_another_kind(folder: Path, clock: FixedClock) -> None:
    (folder / FOLDER / "server.key").write_bytes(pem_of(ed25519.Ed25519PrivateKey.generate()))


@pytest.mark.parametrize("change, reason", [
    pytest.param(another_key, "it does not belong to its key", id="another key"),
    pytest.param(clock_set_back, "it is not valid yet", id="not valid yet"),
    pytest.param(about_to_run_out, "it runs out within 30 days", id="runs out"),
    pytest.param(without_names, "it does not name raspberrypi, raspberrypi.local, localhost, 127.0.0.1, ::1, 192.168.1.20", id="no names"),
    pytest.param(key_of_another_kind, "its key is of another kind", id="key of another kind"),
])
def test_a_server_certificate_in_that_state_is_made_again_and_the_log_says_why_and_the_authority_stays(
        tmp_path: Path, caplog: pytest.LogCaptureFixture, change: Change, reason: str) -> None:
    s, clock = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    serial = server_cert(tmp_path).serial_number
    change(tmp_path, clock)
    with caplog.at_level(logging.INFO, "neoaprs.web"):
        again = s.ensure(HOST, [LAN])
    assert any(r.getMessage().startswith("making the certificate of the page for") and r.getMessage().endswith(f": {reason}") for r in caplog.records), [r.getMessage() for r in caplog.records]
    assert again.ca_der == first.ca_der and server_cert(tmp_path).serial_number != serial
    server_cert(tmp_path).verify_directly_issued_by(ca_cert(tmp_path))
    assert {HOST, LAN} <= san(server_cert(tmp_path))
    caplog.clear()
    with caplog.at_level(logging.INFO, "neoaprs.web"):
        s.ensure(HOST, [LAN])
    assert not [r for r in caplog.records if "making the certificate" in r.getMessage()], "and what was made is good: the next look makes nothing"


def test_a_certificate_without_names_has_none_to_list() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "x")])
    now = FixedClock()()
    cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256())
    assert _names_of(cert) == ()


def test_an_authority_whose_key_is_of_another_kind_is_not_replaced_and_the_text_says_what_to_do(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    s.ensure(HOST, [LAN])
    (tmp_path / FOLDER / "ca.key").write_bytes(pem_of(ed25519.Ed25519PrivateKey.generate()))
    with pytest.raises(TlsError, match="not an elliptic-curve key; move the folder"):
        s.ensure(HOST, [LAN])
    assert b"BEGIN PRIVATE KEY" in (tmp_path / FOLDER / "ca.key").read_bytes()


def test_a_system_that_has_no_modes_for_a_folder_still_gets_its_certificates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(self: Path, mode: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(Path, "chmod", refused)
    certs = CertificateStore(tmp_path / FOLDER, FixedClock()).ensure(HOST, [LAN])
    assert certs.chain_file.is_file() and certs.key_file.is_file()
