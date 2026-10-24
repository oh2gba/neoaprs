"""Update now through the page's socket: the topic `update` says whether this copy can update itself and how the update goes, `update_now` starts it for the announced version only and `update_cancel` ends its
download; a copy that cannot update itself refuses with a code. The release and the installer are fakes (tests/support/fakerelease.py): nothing reaches the network and nothing is installed. The restart of an
AppImage is the daemon's stop with the command line to run after it."""
import threading
from pathlib import Path

from neoaprs import stopfile
from neoaprs.services.selfupdate import SelfUpdate
from neoaprs.updateasset import RELEASES, url_allowed
from neoaprs.versions import InstallInfo, Update
from tests.support.env import Env
from tests.support.fakerelease import NAME, FakeInstaller, FakeRelease


async def started(tmp_path: Path, release: FakeRelease | None = None, installer: FakeInstaller | None = None) -> Env:
    e = Env(tmp_path / "data", web=True)
    if release is not None:
        e.ctl.selfupdate = SelfUpdate(InstallInfo("appimage", str(tmp_path / "NeoAPRS-0.6.7-x86_64.AppImage")), installer or FakeInstaller(tmp_path), e.ctl._announced, (RELEASES, url_allowed),
                                      release.fetch_sums, release.fetch)
    await e.start()
    e.ctl.updatecheck.latest = Update("0.7.0", "https://evil.example/NeoAPRS.AppImage", "")
    return e


async def test_a_copy_that_cannot_update_itself_says_so_in_the_topic_and_refuses_update_now(tmp_path: Path) -> None:
    e = await started(tmp_path)
    page = await e.ws()
    state = (await page.expect("state", "update"))["value"]
    assert state == {"supported": False, "state": "idle", "version": "", "percent": None, "downloaded": 0, "total": None, "problem": "", "detail": ""}
    await page.send({"cmd": "update_now", "version": "0.7.0"})
    error = await page.expect("error")
    assert (error["cmd"], error["code"]) == ("update_now", "update.unsupported")
    await page.send({"cmd": "update_cancel"})
    assert (await page.expect("error"))["code"] == "update.not_running"
    await e.stop()


async def test_update_now_is_told_step_by_step_to_every_page_and_fetches_only_from_the_release_of_the_announced_version(tmp_path: Path) -> None:
    release = FakeRelease()
    installer = FakeInstaller(tmp_path)
    e = await started(tmp_path, release, installer)
    page = await e.ws()
    other = await e.ws()
    await page.until(lambda: page.topics.get("update", {}).get("supported") is True)
    await page.send({"cmd": "update_now", "version": "0.6.9"})
    assert (await page.expect("error"))["code"] == "update.not_announced"
    await page.send({"cmd": "update_now", "version": "0.7.0"})
    await other.until(lambda: other.topics["update"]["state"] == "restarting")
    assert other.topics["update"] == {"supported": True, "state": "restarting", "version": "0.7.0", "percent": 100, "downloaded": len(release.body), "total": len(release.body), "problem": "", "detail": ""}
    assert release.asked == [f"{RELEASES}/v0.7.0/SHA256SUMS", f"{RELEASES}/v0.7.0/{NAME}"]           # (not the address the version page gave)
    assert [name for _, name, _ in installer.installed] == [NAME]
    await page.send({"cmd": "update_now", "version": "0.7.0"})
    assert (await page.expect("error"))["code"] == "update.busy"
    await e.stop()


async def test_a_download_is_cancelled_from_the_page(tmp_path: Path) -> None:
    gate = threading.Event()
    e = await started(tmp_path, FakeRelease(gate=gate))
    page = await e.ws()
    await page.send({"cmd": "update_now", "version": "0.7.0"})
    await page.until(lambda: page.topics.get("update", {}).get("percent") == 50)
    await page.send({"cmd": "update_cancel"})
    await page.until(lambda: page.topics["update"]["state"] == "idle")
    gate.set()
    await e.stop()


async def test_a_bad_checksum_is_an_error_in_the_topic(tmp_path: Path) -> None:
    release = FakeRelease(body=b"tampered")
    e = await started(tmp_path, release)
    page = await e.ws()
    await page.send({"cmd": "update_now", "version": "0.7.0"})
    await page.until(lambda: page.topics.get("update", {}).get("state") == "error")
    assert page.topics["update"]["problem"] == "checksum"
    await e.stop()


async def test_the_restart_of_an_appimage_is_the_daemons_stop_with_the_command_line_to_run_after_it(tmp_path: Path) -> None:
    e = await started(tmp_path)
    e.ctl.restart_into(["/home/ham/NeoAPRS.AppImage", "run"])
    assert e.ctl.reexec == ["/home/ham/NeoAPRS.AppImage", "run"]
    assert stopfile.requested(e.ctl.data_dir) and stopfile.restarting(e.ctl.data_dir)
    stopfile.clear(e.ctl.data_dir)
    await e.stop()
