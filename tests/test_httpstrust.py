"""The trust of the https requests (neoaprs/httpstrust.py): certifi's roots are loaded beside the system's, every opener of the program that goes out to the internet is built with it, and the Windows app carries certifi's list."""
import ssl
from pathlib import Path

import certifi

from neoaprs import httpstrust

ROOT = Path(__file__).resolve().parent.parent


def test_the_context_verifies_and_has_certifis_roots_beside_the_systems() -> None:
    context = httpstrust.https_context()
    assert context.verify_mode is ssl.CERT_REQUIRED and context.check_hostname
    bare = ssl.create_default_context()
    assert context.cert_store_stats()["x509_ca"] >= bare.cert_store_stats()["x509_ca"]
    alone = ssl.create_default_context(cafile=certifi.where())
    assert context.cert_store_stats()["x509_ca"] >= alone.cert_store_stats()["x509_ca"] > 100, "Mozilla's list is in"


def test_every_opener_that_goes_out_uses_it() -> None:
    for name in ("updatefetch.py", "updatedownload.py", "pmtilesarchive.py", "pmtilesrange.py"):
        text = (ROOT / "neoaprs" / name).read_text(encoding="utf-8")
        assert "urlopen(" not in text, name
        assert text.count("build_opener(https_handler()") == text.count("build_opener("), name


def test_the_windows_app_carries_certifis_list() -> None:
    assert 'collect_data_files("certifi")' in (ROOT / "packaging" / "windows" / "neoaprs.spec").read_text(encoding="utf-8")
