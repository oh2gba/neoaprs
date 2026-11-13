"""scripts/verify-download.py checks a file of a release by hand as Update now does: the signature of SHA256SUMS for the release's version, then the file's SHA-256. The script is loaded with the test's own public key in
place of the project's; run as a program it believes the project's key alone, so a list the test signed does not pass."""
import hashlib
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from neoaprs.updateasset import sign
from tests.support.fakerelease import SEED, public

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "verify-download.py"
INSTALLER = "NeoAPRS-Setup-0.7.0.exe"


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("verify_download", str(SCRIPT))         # (a name with a dash is no module name to import)
    spec = importlib.util.spec_from_loader("verify_download", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setattr(module, "public_key", public)
    return module


def release(folder: Path, body: bytes = b"the installer", version: str = "0.7.0", signed_for: str | None = None, extra: str = "", name: str | None = None) -> Path:
    """A downloaded installer with SHA256SUMS and SHA256SUMS.sig beside it, the list signed with the test's key; `name` is the file's name in place of the installer's own."""
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / (name or f"NeoAPRS-Setup-{version}.exe")
    file.write_bytes(body)
    other = f"NeoAPRS-{version}-x86_64.AppImage" if file.name != f"NeoAPRS-{version}-x86_64.AppImage" else f"NeoAPRS-Setup-{version}.exe"
    sums = f"{hashlib.sha256(b'another file').hexdigest()}  {other}\n{hashlib.sha256(body).hexdigest()}  {file.name}\n{extra}".encode()
    (folder / "SHA256SUMS").write_bytes(sums)
    (folder / "SHA256SUMS.sig").write_text(sign(sums, signed_for or version, SEED), encoding="ascii")
    return file


def test_a_file_of_a_signed_release_is_the_releases(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = release(tmp_path)
    assert script.main([str(file)]) == 0
    assert capsys.readouterr().out.startswith(f"{INSTALLER} is the file of NeoAPRS 0.7.0: SHA256SUMS carries the project's signature")
    assert script.main([str(file), "--version", "0.7.0"]) == 0


def test_a_changed_file_is_not_the_releases(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = release(tmp_path)
    file.write_bytes(b"the installer, changed")
    assert script.main([str(file)]) == 1 and "is not the file of the release" in capsys.readouterr().err


@pytest.mark.parametrize(("make", "why"), [
    (lambda folder: release(folder, signed_for="0.6.9"), "is not the project's signature"),                      # the signature of another release's list
])
def test_a_list_that_is_not_this_releases_is_not_verified(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str], make: object, why: str) -> None:
    file = make(tmp_path)              # type: ignore[operator]
    assert script.main([str(file)]) == 1 and why in capsys.readouterr().err


def test_a_file_whose_name_carries_no_version_needs_the_version_given(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """NeoAPRS-Setup.exe with the signed list of the older 0.6.9 beside it, as a release written over with an older one's files would serve them: the list cannot say which release the file ought to be."""
    file = release(tmp_path, version="0.6.9", name="NeoAPRS-Setup.exe", extra=f"{hashlib.sha256(b'x').hexdigest()}  NeoAPRS-Setup-0.6.9.exe\n")
    assert script.main([str(file)]) == 1 and "the name NeoAPRS-Setup.exe carries no version: give the version" in capsys.readouterr().err
    assert script.main([str(file), "--version", "0.7.0"]) == 1 and "is not the project's signature" in capsys.readouterr().err
    assert script.main([str(file), "--version", "0.6.9"]) == 0 and "is the file of NeoAPRS 0.6.9" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["NeoAPRS-0.7.0-x86_64.AppImage", "NeoAPRS-0.7.0-arm64.dmg", "neoaprs_0.7.0_amd64.deb", "neoaprs_0.7.0_arm64.deb"])
def test_every_file_named_for_its_version_is_checked_for_that_version(script: ModuleType, tmp_path: Path, name: str) -> None:
    assert script.main([str(release(tmp_path, name=name))]) == 0
    assert script.main([str(release(tmp_path / "older", name=name, signed_for="0.6.9"))]) == 1


def test_a_version_given_by_hand_that_is_not_the_lists_is_not_verified(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = release(tmp_path)
    assert script.main([str(file), "--version", "0.7.1"]) == 1 and "as the list of v0.7.1" in capsys.readouterr().err
    assert script.main([str(file), "--version", "v0.7.0"]) == 1 and "is not a version of a release" in capsys.readouterr().err


def test_a_missing_signature_is_said_plainly(script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    file = release(tmp_path)
    (tmp_path / "SHA256SUMS.sig").unlink()
    assert script.main([str(file)]) == 1 and "SHA256SUMS.sig" in capsys.readouterr().err


def test_the_lists_may_be_named_and_need_not_be_beside_the_file(script: ModuleType, tmp_path: Path) -> None:
    file = release(tmp_path / "release")
    moved = tmp_path / "downloads" / file.name
    moved.parent.mkdir()
    file.rename(moved)
    assert script.main([str(moved), "--sums", str(tmp_path / "release" / "SHA256SUMS"), "--signature", str(tmp_path / "release" / "SHA256SUMS.sig")]) == 0


def test_run_as_a_program_it_believes_the_projects_key_alone(tmp_path: Path) -> None:
    file = release(tmp_path)
    done = subprocess.run([sys.executable, str(SCRIPT), str(file)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 1 and "NOT VERIFIED" in done.stderr and "is not the project's signature" in done.stderr
