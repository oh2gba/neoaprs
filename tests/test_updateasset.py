"""Update now's decisions that need no I/O (neoaprs/updateasset.py): the file of the release for each kind of install and architecture, its address built from the version alone, the hosts a download may go
to, and the line of SHA256SUMS that names the file."""
import hashlib

import pytest

from neoaprs.updateasset import RELEASES, asset_name, asset_url, checksum_for, release_version, url_allowed


@pytest.mark.parametrize(("kind", "arch", "name"), [
    ("windows-installer", "", "NeoAPRS-Setup-0.7.0.exe"),
    ("appimage", "", "NeoAPRS-0.7.0-x86_64.AppImage"),
    ("deb", "amd64", "neoaprs_0.7.0_amd64.deb"),
    ("deb", "arm64", "neoaprs_0.7.0_arm64.deb"),
    ("deb", "", None),                                   # (a machine the release has no package for)
    ("deb", "armhf", None),
    ("uv-tool", "", "neoaprs-0.7.0-py3-none-any.whl"),
    ("pip", "", "neoaprs-0.7.0-py3-none-any.whl"),
    ("source", "", None),
])
def test_the_file_of_the_release_for_each_kind_and_architecture(kind: str, arch: str, name: str | None) -> None:
    assert asset_name(kind, "0.7.0", arch) == name        # type: ignore[arg-type]


@pytest.mark.parametrize("version", ["0.7.0", "1.0.0-rc1", "10.20.30", "1.0.0-beta.2"])
def test_a_release_version_is_digits_and_dots_with_an_optional_suffix(version: str) -> None:
    assert release_version(version)
    assert asset_name("appimage", version) == f"NeoAPRS-{version}-x86_64.AppImage"


@pytest.mark.parametrize("version", ["", "1.0", "1", "0.7.0/../../evil", "0.7.0?x=1", "0.7.0#a", "v0.7.0", "0.7.0 ", "0.7.0+build", "0.7.0-", "１.0.0", "0.7.0\n"])
def test_a_version_that_is_not_plainly_one_builds_no_file_and_no_address(version: str) -> None:
    assert not release_version(version)
    assert asset_name("windows-installer", version) is None
    with pytest.raises(ValueError):
        asset_url(version, "SHA256SUMS")


def test_the_address_is_the_github_release_of_the_tag_of_the_version_and_nothing_else() -> None:
    assert RELEASES == "https://github.com/oh2gba/neoaprs/releases/download"
    assert asset_url("0.7.0", "NeoAPRS-Setup-0.7.0.exe") == "https://github.com/oh2gba/neoaprs/releases/download/v0.7.0/NeoAPRS-Setup-0.7.0.exe"
    assert asset_url("0.7.0", "SHA256SUMS") == "https://github.com/oh2gba/neoaprs/releases/download/v0.7.0/SHA256SUMS"
    for name in ("../x", "a/b", "", "x?y", ".hidden", "x\n"):
        with pytest.raises(ValueError):
            asset_url("0.7.0", name)


@pytest.mark.parametrize(("url", "ok"), [
    ("https://github.com/oh2gba/neoaprs/releases/download/v0.7.0/SHA256SUMS", True),
    ("https://objects.githubusercontent.com/github-production-release-asset/1/2?X-Amz=1", True),
    ("https://release-assets.githubusercontent.com/github-production-release-asset/1/2?sig=1", True),
    ("https://GitHub.com/oh2gba/neoaprs/releases/download/v0.7.0/x", True),
    ("https://github.com:443/x", True),
    ("http://github.com/oh2gba/neoaprs/releases/download/v0.7.0/x", False),
    ("https://github.com.evil.example/x", False),
    ("https://evil.example/github.com/x", False),
    ("https://user@github.com/x", False),
    ("https://github.com:8443/x", False),
    ("ftp://github.com/x", False),
    ("file:///etc/passwd", False),
    ("https://oh2gba.github.io/neoaprs/", False),             # (the version page's own address is no source of files)
    ("https://[::1]:x/", False),
])
def test_a_download_may_go_only_to_github_over_https(url: str, ok: bool) -> None:
    assert url_allowed(url) is ok


SUM = hashlib.sha256(b"the installer").hexdigest()
OTHER = hashlib.sha256(b"something else").hexdigest()


def test_the_line_of_sha256sums_that_names_the_file_gives_its_sum() -> None:
    sums = f"{OTHER}  neoaprs-0.7.0-py3-none-any.whl\n{SUM}  NeoAPRS-Setup-0.7.0.exe\n{OTHER}  install.sh\n".encode()
    assert checksum_for(sums, "NeoAPRS-Setup-0.7.0.exe") == SUM
    assert checksum_for(f"{SUM.upper()} *NeoAPRS-Setup-0.7.0.exe\r\n".encode(), "NeoAPRS-Setup-0.7.0.exe") == SUM        # (the binary mode of sha256sum, and a Windows line end)


def test_a_file_that_sha256sums_does_not_name_or_names_twice_with_two_sums_has_none() -> None:
    sums = f"{SUM}  NeoAPRS-Setup-0.7.0.exe\n".encode()
    assert checksum_for(sums, "NeoAPRS-0.7.0-x86_64.AppImage") is None
    assert checksum_for(sums, "NeoAPRS-Setup-0.7.0.ex") is None
    assert checksum_for(f"{SUM}  NeoAPRS-Setup-0.7.0.exe.sig\n".encode(), "NeoAPRS-Setup-0.7.0.exe") is None
    assert checksum_for(b"", "NeoAPRS-Setup-0.7.0.exe") is None
    assert checksum_for(f"{SUM[:-1]}  NeoAPRS-Setup-0.7.0.exe\n".encode(), "NeoAPRS-Setup-0.7.0.exe") is None
    assert checksum_for(f"{SUM}  NeoAPRS-Setup-0.7.0.exe\n{OTHER}  NeoAPRS-Setup-0.7.0.exe\n".encode(), "NeoAPRS-Setup-0.7.0.exe") is None
    assert checksum_for(f"{SUM}  NeoAPRS-Setup-0.7.0.exe\n{SUM}  NeoAPRS-Setup-0.7.0.exe\n".encode(), "NeoAPRS-Setup-0.7.0.exe") == SUM
