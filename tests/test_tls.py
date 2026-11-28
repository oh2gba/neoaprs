"""The certificates of the secure connection (neoaprs/web/tls.py): the authority made once, the
certificate of the computer and when it is made again. The clock is the test's."""

import ipaddress
import stat
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from neoaprs.web.tls import (
    CA_DAYS,
    CLOCK_SANE_AFTER,
    SERVER_DAYS,
    CertificateStore,
    TlsError,
    fingerprint_of,
    make_server,
    wanted_names,
)
from tests.support.clock import FixedClock

HOST = "raspberrypi"
LAN = "192.168.1.20"


def store(tmp_path: Path, clock: FixedClock | None = None) -> tuple[CertificateStore, FixedClock]:
    clock = clock or FixedClock()
    return CertificateStore(tmp_path / "tls", clock), clock


def server_cert(tmp_path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate((tmp_path / "tls" / "server.crt").read_bytes())


def ca_cert(tmp_path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate((tmp_path / "tls" / "ca.crt").read_bytes())


def san(cert: x509.Certificate) -> set[str]:
    value = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {*value.get_values_for_type(x509.DNSName), *(str(ip) for ip in value.get_values_for_type(x509.IPAddress))}


def test_the_names_are_this_computer_its_local_name_localhost_the_loopback_the_addresses_and_the_allowed_names_once_each() -> (
    None
):
    assert wanted_names(
        "RaspberryPi", [LAN, "127.0.0.1"], ["Pi.example.org.", "pi.example.org", "bad name", "ünï", "10.0.0.5"]
    ) == ("raspberrypi", "raspberrypi.local", "localhost", "127.0.0.1", "::1", LAN, "pi.example.org", "10.0.0.5")


def test_the_authority_is_made_with_a_name_ten_years_and_the_right_to_sign_certificates_and_nothing_else(
    tmp_path: Path,
) -> None:
    s, clock = store(tmp_path)
    certs = s.ensure(HOST, [LAN])
    ca = ca_cert(tmp_path)
    assert (
        ca.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == f"NeoAPRS local CA ({HOST})"
        and ca.issuer == ca.subject
    )
    basic = ca.extensions.get_extension_for_class(x509.BasicConstraints)
    assert basic.critical and basic.value.ca is True
    usage = ca.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.key_cert_sign is True and usage.digital_signature is False
    assert (ca.not_valid_after_utc - clock()).days in range(
        CA_DAYS - 1, CA_DAYS + 1
    ) and ca.not_valid_before_utc <= clock()
    assert certs.ca_der == ca.public_bytes(serialization.Encoding.DER) and certs.fingerprint == fingerprint_of(
        certs.ca_der
    )
    assert (
        len(certs.fingerprint) == 95
        and certs.fingerprint.count(":") == 31
        and certs.fingerprint == certs.fingerprint.upper()
    )


def test_the_certificate_of_the_computer_names_it_and_its_addresses_for_servers_for_less_than_825_days_and_is_signed_by_the_authority(
    tmp_path: Path,
) -> None:
    s, clock = store(tmp_path)
    certs = s.ensure(HOST, [LAN], ["pi.example.org"])
    cert = server_cert(tmp_path)
    assert san(cert) == {HOST, f"{HOST}.local", "localhost", "127.0.0.1", "::1", LAN, "pi.example.org"} and set(
        certs.names
    ) == san(cert)
    assert [u.dotted_string for u in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value] == [
        ExtendedKeyUsageOID.SERVER_AUTH.dotted_string
    ]
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days <= 825 and (
        cert.not_valid_after_utc - clock()
    ).days <= SERVER_DAYS
    cert.verify_directly_issued_by(ca_cert(tmp_path))
    assert certs.expires == cert.not_valid_after_utc


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no such modes")
def test_every_file_and_the_folder_are_for_the_owner_alone(tmp_path: Path) -> None:
    store(tmp_path)[0].ensure(HOST, [LAN])
    folder = tmp_path / "tls"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["ca.crt", "ca.key", "server.crt", "server.key"], "no leftovers"
    for path in folder.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path.name


def test_asked_again_with_nothing_changed_it_makes_nothing(tmp_path: Path) -> None:
    s, clock = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    before = {p.name: p.read_bytes() for p in (tmp_path / "tls").iterdir()}
    clock.advance(86400 * 100)
    assert s.ensure(HOST, [LAN]) == first
    assert {p.name: p.read_bytes() for p in (tmp_path / "tls").iterdir()} == before


def test_a_new_address_makes_a_new_certificate_and_the_authority_stays(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    old = server_cert(tmp_path).serial_number
    second = s.ensure(HOST, ["10.0.0.7"])
    cert = server_cert(tmp_path)
    assert cert.serial_number != old and "10.0.0.7" in san(cert) and "10.0.0.7" in second.names
    assert second.fingerprint == first.fingerprint and second.ca_der == first.ca_der, (
        "the devices that trust the authority still do"
    )
    cert.verify_directly_issued_by(ca_cert(tmp_path))


def test_a_new_host_name_makes_a_new_certificate_with_the_names_the_authority_covers_and_asked_again_nothing_new(
    tmp_path: Path,
) -> None:
    s, _ = store(tmp_path)
    s.ensure(HOST, [LAN])
    s.ensure("pi4", [LAN, "203.0.113.9"])
    names = san(server_cert(tmp_path))
    assert "pi4.local" in names and "pi4" not in names and "203.0.113.9" not in names, (
        "(the authority was made for raspberrypi and the local names: the bare new name is left out)"
    )
    serial = server_cert(tmp_path).serial_number
    s.ensure("pi4", [LAN, "203.0.113.9"])
    assert server_cert(tmp_path).serial_number == serial, "(no new certificate at every start for a name left out)"


def test_a_new_authority_may_sign_only_for_the_station_s_names_and_addresses_and_the_local_ones(
    tmp_path: Path,
) -> None:
    s, clock = store(tmp_path)
    s.ensure(HOST, [LAN, "203.0.113.9"], ["pi.example.org"])
    ca = ca_cert(tmp_path)
    limits = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert limits.critical and limits.value.excluded_subtrees is None
    permitted = limits.value.permitted_subtrees or []
    assert [n.value for n in permitted if isinstance(n, x509.DNSName)] == ["localhost", "local", HOST, "pi.example.org"]
    networks = {str(n.value) for n in permitted if isinstance(n, x509.IPAddress)}
    assert {"192.168.0.0/16", "10.0.0.0/8", "127.0.0.0/8", "::1/128", "fe80::/10", "203.0.113.9/32"} <= networks
    assert "0.0.0.0/0" not in networks and not any(n.startswith("203.0.113.0/") for n in networks)
    key = serialization.load_pem_private_key((tmp_path / "tls" / "ca.key").read_bytes(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    trust = Store([ca])
    at = clock() + timedelta(hours=1)

    def verified(name: str, cert: x509.Certificate) -> bool:
        subject = x509.IPAddress(ipaddress.ip_address(name)) if name[0].isdigit() else x509.DNSName(name)
        try:
            PolicyBuilder().store(trust).time(at).build_server_verifier(subject).verify(cert, [])
        except VerificationError:
            return False
        return True

    page = server_cert(tmp_path)
    assert all(verified(name, page) for name in (HOST, f"{HOST}.local", "pi.example.org", LAN, "203.0.113.9"))
    for foreign in ("www.example.com", "198.51.100.1"):
        _, cert = make_server(key, ca, foreign, (foreign,), clock())
        assert not verified(foreign, cert), f"(a stolen key of the authority signs nothing for {foreign})"


def test_an_authority_made_before_the_limits_keeps_working_and_signs_for_every_name_until_it_is_made_anew(
    tmp_path: Path,
) -> None:
    s, clock = store(tmp_path)
    s.ensure(HOST, [LAN])
    folder = tmp_path / "tls"
    key = serialization.load_pem_private_key((folder / "ca.key").read_bytes(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    old = ca_cert(tmp_path)
    unlimited = x509.CertificateBuilder(
        old.issuer,
        old.subject,
        old.public_key(),
        old.serial_number,
        old.not_valid_before_utc,
        old.not_valid_after_utc,
        [e for e in old.extensions if not isinstance(e.value, x509.NameConstraints)],
    ).sign(key, hashes.SHA256())
    (folder / "ca.crt").write_bytes(unlimited.public_bytes(serialization.Encoding.PEM))
    (folder / "server.crt").unlink()
    first = s.ensure("pi4", [LAN, "203.0.113.9"])
    assert first.ca_der == unlimited.public_bytes(serialization.Encoding.DER), "(not replaced: the devices trust it)"
    assert {"pi4", "203.0.113.9"} <= san(server_cert(tmp_path))
    for name in folder.iterdir():
        name.unlink()
    folder.rmdir()
    s.ensure("pi4", [LAN])
    assert ca_cert(tmp_path).extensions.get_extension_for_class(x509.NameConstraints).critical, (
        "(the folder moved away: the new authority is of the limited kind)"
    )


def test_a_certificate_with_30_days_left_is_made_again_and_one_with_more_is_not(tmp_path: Path) -> None:
    s, clock = store(tmp_path)
    s.ensure(HOST, [LAN])
    serial = server_cert(tmp_path).serial_number
    clock.advance(86400 * (SERVER_DAYS - 31))
    s.ensure(HOST, [LAN])
    assert server_cert(tmp_path).serial_number == serial
    clock.advance(86400 * 2)
    s.ensure(HOST, [LAN])
    renewed = server_cert(tmp_path)
    assert renewed.serial_number != serial and (renewed.not_valid_after_utc - clock()) > timedelta(days=SERVER_DAYS - 2)
    assert ca_cert(tmp_path).not_valid_after_utc > renewed.not_valid_after_utc


def test_the_authority_is_never_made_again_while_its_files_are_there_not_even_when_the_certificate_ran_out(
    tmp_path: Path,
) -> None:
    s, clock = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    clock.advance(86400 * 2000)
    assert s.ensure(HOST, [LAN]).ca_der == first.ca_der


def test_an_authority_whose_files_are_gone_is_made_again_and_the_certificate_with_it(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    (tmp_path / "tls" / "ca.key").unlink()
    second = s.ensure(HOST, [LAN])
    assert second.fingerprint != first.fingerprint
    server_cert(tmp_path).verify_directly_issued_by(ca_cert(tmp_path))
    (tmp_path / "tls" / "ca.crt").unlink()
    assert s.ensure(HOST, [LAN]).fingerprint != second.fingerprint


def test_a_certificate_of_another_authority_is_replaced(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    s.ensure(HOST, [LAN])
    other, _ = store(tmp_path.parent / (tmp_path.name + "-other"))
    other.ensure(HOST, [LAN])
    (tmp_path / "tls" / "server.crt").write_bytes(
        (tmp_path.parent / (tmp_path.name + "-other") / "tls" / "server.crt").read_bytes()
    )
    s.ensure(HOST, [LAN])
    server_cert(tmp_path).verify_directly_issued_by(ca_cert(tmp_path))


def test_a_server_certificate_that_cannot_be_read_is_made_again(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    s.ensure(HOST, [LAN])
    (tmp_path / "tls" / "server.crt").write_text("not a certificate")
    s.ensure(HOST, [LAN])
    assert LAN in san(server_cert(tmp_path))


def test_an_authority_file_that_cannot_be_read_is_not_replaced_and_the_text_says_what_to_do(tmp_path: Path) -> None:
    s, _ = store(tmp_path)
    s.ensure(HOST, [LAN])
    (tmp_path / "tls" / "ca.key").write_text("damaged")
    with pytest.raises(TlsError, match="move the folder"):
        s.ensure(HOST, [LAN])
    assert (tmp_path / "tls" / "ca.key").read_text() == "damaged"


def test_a_clock_that_is_not_set_makes_nothing(tmp_path: Path) -> None:
    s, clock = store(tmp_path)
    clock.set(CLOCK_SANE_AFTER - timedelta(days=1))
    with pytest.raises(TlsError, match="clock"):
        s.ensure(HOST, [LAN])
    assert not (tmp_path / "tls").exists()


def test_a_folder_that_cannot_be_made_is_an_error_with_the_reason(tmp_path: Path) -> None:
    (tmp_path / "tls").write_text("a file where the folder should be")
    with pytest.raises(TlsError, match="could not be written or read"):
        store(tmp_path)[0].ensure(HOST, [LAN])


def test_an_authority_with_30_days_left_is_made_again_and_the_certificate_with_it(tmp_path: Path) -> None:
    s, clock = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    clock.advance(86400 * (CA_DAYS - 31))
    assert s.ensure(HOST, [LAN]).ca_der == first.ca_der, "31 days left: the authority is kept"
    clock.advance(86400 * 2)
    second = s.ensure(HOST, [LAN])
    assert second.ca_der != first.ca_der
    assert server_cert(tmp_path).verify_directly_issued_by(ca_cert(tmp_path)) is None


def test_an_authority_that_ran_out_is_made_again(tmp_path: Path) -> None:
    s, clock = store(tmp_path)
    first = s.ensure(HOST, [LAN])
    clock.advance(86400 * (CA_DAYS + 10))
    assert s.ensure(HOST, [LAN]).ca_der != first.ca_der
