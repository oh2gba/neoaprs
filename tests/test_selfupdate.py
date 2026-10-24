"""Update now's job (neoaprs/services/selfupdate.py) with fake downloads and a fake installer: the steps, the addresses (built from the announced version alone), the check of the SHA-256 (good, bad, missing from
SHA256SUMS), a cancel, the refusals, and an install after which NeoAPRS does not restart. No test reaches the network."""
import asyncio
import hashlib
import threading
from pathlib import Path

import pytest

from neoaprs.services.selfupdate import SelfUpdate, UpdateNowError
from neoaprs.updateasset import RELEASES, url_allowed
from neoaprs.versions import InstallInfo
from tests.support.env import until
from tests.support.fakerelease import BODY, NAME, FakeInstaller, FakeRelease

def service(tmp_path: Path, release: FakeRelease, installer: FakeInstaller | None = None, latest: str | None = "0.7.0", grace: float = 30.0) -> tuple[SelfUpdate, list[str]]:
    job = SelfUpdate(InstallInfo("appimage", str(tmp_path / "NeoAPRS-0.6.7-x86_64.AppImage")), installer if installer is not None else FakeInstaller(tmp_path),
                     lambda: latest, (RELEASES, url_allowed), release.fetch_sums, release.fetch, restart_grace_sec=grace)
    states: list[str] = []
    job.changed.connect(lambda: states.append(job.status().state) if not states or states[-1] != job.status().state else None)
    return job, states


async def test_the_update_downloads_checks_installs_and_waits_for_the_restart(tmp_path: Path) -> None:
    release = FakeRelease()
    installer = FakeInstaller(tmp_path)
    job, states = service(tmp_path, release, installer)
    assert job.status().supported and job.status().state == "idle"
    job.begin("0.7.0")
    await until(lambda: job.status().state == "restarting")
    assert states == ["downloading", "verifying", "installing", "restarting"]
    assert installer.installed == [(BODY, NAME, "0.7.0")]
    assert release.asked == [f"{RELEASES}/v0.7.0/SHA256SUMS", f"{RELEASES}/v0.7.0/{NAME}"]
    status = job.status()
    assert (status.version, status.percent, status.downloaded, status.total, status.problem) == ("0.7.0", 100, len(BODY), len(BODY), "")
    assert not (tmp_path / f"{NAME}.part").exists()
    await job.stop()


async def test_a_file_whose_sha256_is_not_the_one_of_sha256sums_is_deleted_and_not_installed(tmp_path: Path) -> None:
    installer = FakeInstaller(tmp_path)
    job, states = service(tmp_path, FakeRelease(body=BODY + b"!"), installer)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert states == ["downloading", "verifying", "error"]
    assert job.status().problem == "checksum" and "is not the file of the release" in job.status().detail and "nothing is installed" in job.status().detail
    assert installer.installed == [] and list(tmp_path.iterdir()) == []


async def test_a_file_that_sha256sums_does_not_name_is_not_even_downloaded(tmp_path: Path) -> None:
    release = FakeRelease(sums=f"{hashlib.sha256(BODY).hexdigest()}  NeoAPRS-Setup-0.7.0.exe\n".encode())
    installer = FakeInstaller(tmp_path)
    job, _ = service(tmp_path, release, installer)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert job.status().problem == "no_checksum" and f"names no {NAME}" in job.status().detail
    assert release.asked == [f"{RELEASES}/v0.7.0/SHA256SUMS"] and installer.installed == []


async def test_a_download_that_fails_or_an_install_that_fails_is_an_error_that_says_why(tmp_path: Path) -> None:
    job, _ = service(tmp_path, FakeRelease(fail="the server answered 404 Not Found"))
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert (job.status().problem, job.status().detail) == ("download", "the server answered 404 Not Found")
    installer = FakeInstaller(tmp_path, fail="the new AppImage could not be put in place")
    job, _ = service(tmp_path, FakeRelease(), installer)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert job.status().problem == "install" and not (tmp_path / f"{NAME}.part").exists()
    job.begin("0.7.0")                         # (after an error it can be tried again)
    await until(lambda: job.status().state == "error")


async def test_a_cancel_ends_the_download_and_leaves_nothing(tmp_path: Path) -> None:
    gate = threading.Event()
    installer = FakeInstaller(tmp_path)
    job, states = service(tmp_path, FakeRelease(gate=gate), installer)
    job.begin("0.7.0")
    await until(lambda: job.status().percent == 50)
    job.cancel()
    assert job.status().state == "idle" and job.status().version == ""
    with pytest.raises(UpdateNowError) as busy:
        job.begin("0.7.0")                     # (the piece in flight ends first)
    assert busy.value.code == "update.busy"
    gate.set()
    await until(lambda: not (tmp_path / f"{NAME}.part").exists())
    await asyncio.sleep(0.05)
    assert installer.installed == [] and job.status().state == "idle" and states == ["downloading", "idle"]
    with pytest.raises(UpdateNowError) as none:
        job.cancel()
    assert none.value.code == "update.not_running"


async def test_an_install_after_which_neoaprs_does_not_restart_says_so(tmp_path: Path) -> None:
    job, _ = service(tmp_path, FakeRelease(), grace=0.05)
    job.begin("0.7.0")
    await until(lambda: job.status().state == "error")
    assert job.status().problem == "no_restart" and "has not restarted" in job.status().detail


@pytest.mark.parametrize(("latest", "asked", "code"), [
    (None, "0.7.0", "update.not_announced"),
    ("0.7.1", "0.7.0", "update.not_announced"),
    ("0.7", "0.7", "update.no_file"),
])
async def test_only_the_version_the_update_check_announced_is_installed(tmp_path: Path, latest: str | None, asked: str, code: str) -> None:
    release = FakeRelease()
    job, _ = service(tmp_path, release, latest=latest)
    with pytest.raises(UpdateNowError) as refused:
        job.begin(asked)
    assert refused.value.code == code and release.asked == [] and job.status().state == "idle"


async def test_a_copy_without_an_installer_or_with_a_folder_it_cannot_write_cannot_update_itself(tmp_path: Path) -> None:
    job = SelfUpdate(InstallInfo("deb", arch="arm64"), None, lambda: "0.7.0", (RELEASES, url_allowed))
    assert not job.status().supported
    with pytest.raises(UpdateNowError) as refused:
        job.begin("0.7.0")
    assert refused.value.code == "update.unsupported"
    job, _ = service(tmp_path, FakeRelease(), FakeInstaller(tmp_path, blocked="the folder cannot be written"))
    assert not job.status().supported
    with pytest.raises(UpdateNowError) as blocked:
        job.begin("0.7.0")
    assert blocked.value.code == "update.blocked" and blocked.value.params == {"reason": "the folder cannot be written"}


async def test_a_second_update_while_one_runs_is_refused(tmp_path: Path) -> None:
    gate = threading.Event()
    job, _ = service(tmp_path, FakeRelease(gate=gate))
    job.begin("0.7.0")
    with pytest.raises(UpdateNowError) as busy:
        job.begin("0.7.0")
    assert busy.value.code == "update.busy"
    gate.set()
    await until(lambda: job.status().state == "restarting")
    await job.stop()
