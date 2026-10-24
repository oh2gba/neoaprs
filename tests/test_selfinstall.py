"""How Update now puts the checked file in place (neoaprs/services/selfinstall.py, neoaprs/selfreplace.py): the installer's command line on Windows (built, never run), the AppImage renamed over the old one on
temporary files with the restart as a stand-in, the exec of the new file and the old one put back when it cannot start, the installer of each kind, the rehearsal of a simulated kind, and the desktop app that
waits for a daemon that restarts as a new version. Nothing here runs an installer or replaces a file of the machine."""
import os
import stat
import sys
from pathlib import Path

import pytest

from neoaprs import selfreplace, stopfile
from neoaprs.cli.installkind import detect_here, simulated
from neoaprs.instancelock import APP_LOCK_NAME, InstanceLock
from neoaprs.services.selfinstall import AppImageSwap, InstallError, Rehearsal, WindowsSetup, installer_for, installer_argv, release_source
from neoaprs.updateasset import RELEASES, url_allowed
from neoaprs.versions import InstallInfo


def test_the_installer_runs_silently_without_closing_apps_itself_and_says_what_to_start_again(tmp_path: Path) -> None:
    argv = installer_argv(Path(r"C:\Users\Ham\AppData\Local\NeoAPRS\update\NeoAPRS-Setup-0.7.0.exe"), Path(r"C:\Users\Ham\AppData\Local\NeoAPRS"), "app", Path(r"C:\Users\Ham\AppData\Local\NeoAPRS\update\install.log"))
    assert argv == [str(Path(r"C:\Users\Ham\AppData\Local\NeoAPRS\update\NeoAPRS-Setup-0.7.0.exe")), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS", "/CURRENTUSER", "/SP-",
                    f"/LOG={Path(r'C:\Users\Ham\AppData\Local\NeoAPRS\update\install.log')}", "/NEOAPRSRESTART=app", f"/NEOAPRSDATA={Path(r'C:\Users\Ham\AppData\Local\NeoAPRS')}"]


def test_the_windows_installer_is_moved_out_of_its_part_file_and_started_for_the_app_or_the_daemon(tmp_path: Path) -> None:
    started: list[list[str]] = []
    setup = WindowsSetup(tmp_path, started.append, app_running=lambda data: data == tmp_path)
    setup.folder.mkdir()
    part = setup.folder / "NeoAPRS-Setup-0.7.0.exe.part"
    part.write_bytes(b"MZ")
    setup.install(part, "NeoAPRS-Setup-0.7.0.exe", "0.7.0")
    installer = tmp_path / "update" / "NeoAPRS-Setup-0.7.0.exe"
    assert installer.read_bytes() == b"MZ" and not part.exists()
    assert started == [installer_argv(installer, tmp_path, "app", tmp_path / "update" / "install.log")]
    assert WindowsSetup(tmp_path, started.append, app_running=lambda data: False).command(installer)[-2] == "/NEOAPRSRESTART=daemon"
    assert setup.blocked() == ""


def test_the_app_counts_as_running_while_it_holds_its_lock_of_the_data_folder(tmp_path: Path) -> None:
    setup = WindowsSetup(tmp_path, lambda argv: None)
    assert setup.command(tmp_path / "x.exe")[-2] == "/NEOAPRSRESTART=daemon"
    lock = InstanceLock(tmp_path, APP_LOCK_NAME)
    lock.acquire()
    try:
        assert setup.command(tmp_path / "x.exe")[-2] == "/NEOAPRSRESTART=app"
    finally:
        lock.release()


def test_an_installer_that_cannot_be_started_is_an_install_error(tmp_path: Path) -> None:
    def refuse(argv: list[str]) -> None:
        raise OSError("access denied")
    setup = WindowsSetup(tmp_path, refuse, app_running=lambda data: False)
    setup.folder.mkdir()
    (setup.folder / "x.part").write_bytes(b"MZ")
    with pytest.raises(InstallError, match="the installer could not be started: access denied"):
        setup.install(setup.folder / "x.part", "NeoAPRS-Setup-0.7.0.exe", "0.7.0")


def appimage_world(tmp_path: Path) -> tuple[Path, Path, list[list[str]], AppImageSwap]:
    image = tmp_path / "Apps" / "NeoAPRS-0.6.7-x86_64.AppImage"
    image.parent.mkdir()
    image.write_bytes(b"old version")
    image.chmod(0o755)
    part = image.parent / "NeoAPRS-0.7.0-x86_64.AppImage.part"
    part.write_bytes(b"new version")
    restarts: list[list[str]] = []
    return image, part, restarts, AppImageSwap(image, ["run", "--data", "/home/ham/data"], restarts.append)


def test_the_new_appimage_is_renamed_over_the_old_one_which_is_kept_beside_it_and_the_same_file_starts_again(tmp_path: Path) -> None:
    image, part, restarts, swap = appimage_world(tmp_path)
    assert swap.folder == image.parent and swap.blocked() == ""
    swap.install(part, "NeoAPRS-0.7.0-x86_64.AppImage", "0.7.0")
    assert image.read_bytes() == b"new version" and not part.exists()
    assert stat.S_IMODE(image.stat().st_mode) & 0o111 == 0o111
    assert (image.parent / (image.name + ".old")).read_bytes() == b"old version"
    assert restarts == [[str(image), "run", "--data", "/home/ham/data"]]


def test_the_old_appimage_is_copied_where_the_file_system_has_no_hard_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image, part, _, swap = appimage_world(tmp_path)

    def no_link(src: object, dst: object) -> None:
        raise OSError("operation not permitted")
    monkeypatch.setattr(os, "link", no_link)
    swap.install(part, "NeoAPRS-0.7.0-x86_64.AppImage", "0.7.0")
    assert (image.parent / (image.name + ".old")).read_bytes() == b"old version" and image.read_bytes() == b"new version"


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="the rights of a folder on POSIX, which root ignores")
def test_an_appimage_in_a_folder_its_user_cannot_write_cannot_update_itself(tmp_path: Path) -> None:
    image, part, restarts, swap = appimage_world(tmp_path)
    part.unlink()
    image.parent.chmod(0o555)
    try:
        assert "cannot be written by this user" in swap.blocked()
    finally:
        image.parent.chmod(0o755)


def test_a_rename_that_fails_leaves_the_old_appimage_and_does_not_restart(tmp_path: Path) -> None:
    image, part, restarts, swap = appimage_world(tmp_path)
    part.unlink()
    with pytest.raises(InstallError, match="could not be put in the place of NeoAPRS-0.6.7-x86_64.AppImage"):
        swap.install(part, "NeoAPRS-0.7.0-x86_64.AppImage", "0.7.0")
    assert image.read_bytes() == b"old version" and restarts == []


def test_the_new_file_is_executed_with_the_arguments_and_the_old_one_is_put_back_when_it_cannot_start(tmp_path: Path) -> None:
    image, part, _, swap = appimage_world(tmp_path)
    swap.install(part, "NeoAPRS-0.7.0-x86_64.AppImage", "0.7.0")
    calls: list[tuple[str, list[str], bytes]] = []
    selfreplace.reexec([str(image), "run"], lambda path, argv: calls.append((path, argv, Path(path).read_bytes())), close=lambda: None)
    assert calls == [(str(image), [str(image), "run"], b"new version")]

    def first_fails(path: str, argv: list[str]) -> None:
        calls.append((path, argv, Path(path).read_bytes()))
        if len(calls) == 2:
            raise OSError("exec format error")
    selfreplace.reexec([str(image), "run"], first_fails, close=lambda: None)
    assert calls[1:] == [(str(image), [str(image), "run"], b"new version"), (str(image), [str(image), "run"], b"old version")]
    assert not (image.parent / (image.name + ".old")).exists()


def test_once_the_new_version_runs_the_old_appimage_goes(tmp_path: Path) -> None:
    image = tmp_path / "NeoAPRS.AppImage"
    old = tmp_path / "NeoAPRS.AppImage.old"
    image.write_bytes(b"new")
    old.write_bytes(b"old")
    selfreplace.remove_old(str(image))
    assert not old.exists() and image.exists()
    selfreplace.remove_old(None)
    assert not selfreplace.restore(image)


def test_each_kind_gets_its_installer_on_its_own_system_and_the_others_none(tmp_path: Path) -> None:
    restart = lambda argv: None                    # noqa: E731
    windows = installer_for(InstallInfo("windows-installer"), tmp_path, restart, {}, platform="win32")
    assert isinstance(windows, WindowsSetup) and windows.folder == tmp_path / "update"
    assert installer_for(InstallInfo("windows-installer"), tmp_path, restart, {}, platform="linux") is None
    image = installer_for(InstallInfo("appimage", "/home/ham/NeoAPRS.AppImage"), tmp_path, restart, {}, ["app"], platform="linux")
    assert isinstance(image, AppImageSwap) and image.appimage == Path("/home/ham/NeoAPRS.AppImage") and image.argv == ["app"]
    assert installer_for(InstallInfo("appimage", ""), tmp_path, restart, {}, platform="linux") is None
    for kind in ("deb", "uv-tool", "pip", "source"):
        assert installer_for(InstallInfo(kind, arch="amd64"), tmp_path, restart, {}, platform="linux") is None       # type: ignore[arg-type]


def test_a_simulated_kind_is_rehearsed_the_file_deleted_and_nothing_installed(tmp_path: Path) -> None:
    environ = {"NEOAPRS_INSTALL_KIND": "appimage"}
    rehearsal = installer_for(InstallInfo("appimage", "/home/ham/NeoAPRS.AppImage"), tmp_path, lambda argv: pytest.fail("restarted"), environ, platform="linux")
    assert isinstance(rehearsal, Rehearsal) and rehearsal.folder == tmp_path / "update"
    assert installer_for(InstallInfo("windows-installer"), tmp_path, lambda argv: None, environ, platform="linux").__class__ is Rehearsal
    assert installer_for(InstallInfo("deb", arch="arm64"), tmp_path, lambda argv: None, {"NEOAPRS_INSTALL_KIND": "deb"}, platform="linux") is None
    rehearsal.folder.mkdir()
    part = rehearsal.folder / "x.part"
    part.write_bytes(b"new")
    rehearsal.install(part, "NeoAPRS-0.7.0-x86_64.AppImage", "0.7.0")
    assert list(rehearsal.folder.iterdir()) == []


def test_the_files_come_from_github_and_from_a_fake_server_only_for_a_simulated_kind() -> None:
    assert release_source({}) == (RELEASES, url_allowed)
    assert release_source({"NEOAPRS_UPDATE_FROM": "http://127.0.0.1:9/releases"}) == (RELEASES, url_allowed)
    base, allowed = release_source({"NEOAPRS_UPDATE_FROM": "http://127.0.0.1:9/releases/", "NEOAPRS_INSTALL_KIND": "appimage"})
    assert base == "http://127.0.0.1:9/releases"
    assert allowed("http://127.0.0.1:9/releases/v9.9.9/SHA256SUMS") and not allowed("https://github.com/x") and not allowed("http://127.0.0.1:9/other")


@pytest.mark.parametrize(("text", "info"), [
    ("deb", InstallInfo("deb", "", False, "amd64")),
    ("deb arm64 service", InstallInfo("deb", "", True, "arm64")),
    ("appimage /home/ham/NeoAPRS-0.6.7-x86_64.AppImage", InstallInfo("appimage", "/home/ham/NeoAPRS-0.6.7-x86_64.AppImage", False, "")),
    ("windows-installer", InstallInfo("windows-installer")),
    ("source service", InstallInfo("source", "", True, "")),
    ("", None),
    ("flatpak", None),
])
def test_a_simulated_install_kind_is_read_from_its_words(text: str, info: InstallInfo | None) -> None:
    assert simulated(text) == info


def test_the_simulated_kind_wins_over_what_the_daemon_finds(tmp_path: Path) -> None:
    assert detect_here(tmp_path, {"NEOAPRS_INSTALL_KIND": "uv-tool service"}) == InstallInfo("uv-tool", "", True, "")
    found = simulated("appimage")
    assert found is not None and found.appimage.endswith("-x86_64.AppImage")


def test_the_note_of_a_restart_is_fresh_for_a_while(tmp_path: Path) -> None:
    assert not stopfile.restarting(tmp_path)
    stopfile.mark_restart(tmp_path)
    assert stopfile.restarting(tmp_path)
    mtime = (tmp_path / stopfile.RESTART_NAME).stat().st_mtime
    assert not stopfile.restarting(tmp_path, now=mtime + stopfile.RESTART_FRESH_SEC + 1)
    stopfile.clear_restart(tmp_path)
    assert not stopfile.restarting(tmp_path)
