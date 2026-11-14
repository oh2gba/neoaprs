"""The developers' own runs are not counted: the update check sends `id=0` in place of the installation's number from a run of the source tree and while the row `update/not_counted` is true, the number of the installation is made and kept all the
same and is sent again when the row is taken away, an installed wheel, the AppImage, the .deb and the Windows program send their number, and no other request to the project's server carries an id. `neoaprs db` reads and sets the row."""
import re
import sqlite3
from pathlib import Path

import pytest

from neoaprs.cli import dbcmd, servicecmd
from neoaprs.cli.installkind import ENV_KIND, detect, detect_here, developers_run
from neoaprs.config import DEFAULTS, INSTALL_ID
from neoaprs.controller import Controller
from neoaprs.services.frequencies import ENV_URL as FREQUENCIES_URL_ENV, Frequencies
from neoaprs.services.skeds import ENV_URL as SKEDS_URL_ENV, Skeds
from neoaprs.services.updatecheck import NOT_COUNTED_ID, UpdateCheck
from neoaprs.store import DB_NAME
from neoaprs.versions import NOT_COUNTED, InstallInfo, InstallKind
from tests.support.env import remember_stop
from tests.support.fakeversionpage import version_page
from tests.support.storedb import store_at
from tests.test_dbcmd import db

NUMBER = re.compile(r"[0-9a-f]{32}")
ANSWER = b'{"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": ""}'


class Page:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def __call__(self, address: str, version: str, platform: str, install_id: str) -> bytes | None:
        self.ids.append(install_id)
        return ANSWER


def check(page: Page, memory: object = None, developer: bool = False) -> UpdateCheck:
    service = UpdateCheck(lambda: DEFAULTS, "0.1.0", "linux", page, environ={}, memory=memory, developer=developer)    # type: ignore[arg-type]
    remember_stop(service.stop)
    return service


async def test_a_run_from_the_source_tree_sends_0_and_keeps_its_own_number(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    page = Page()
    await check(page, store, developer=True).check()
    assert page.ids == ["0"] and NOT_COUNTED_ID == "0"
    assert NUMBER.fullmatch(await store.setting(INSTALL_ID) or ""), "the installation's number is made and kept all the same"


async def test_an_installation_sends_its_number(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    page = Page()
    await check(page, store).check()
    assert NUMBER.fullmatch(page.ids[0]) and page.ids[0] == await store.setting(INSTALL_ID)


async def test_the_row_switches_to_0_at_the_next_question_and_taking_it_away_gives_the_number_back(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    page = Page()
    service = check(page, store)
    await service.check()
    number = page.ids[0]
    assert await store.put_setting(NOT_COUNTED, "true")
    await service.check()
    assert await store.put_setting(NOT_COUNTED, "false")
    await service.check()
    assert await store.put_setting(NOT_COUNTED, "TRUE")
    await service.check()
    assert page.ids == [number, "0", number, "0"] and await store.setting(INSTALL_ID) == number


async def test_a_row_that_is_not_true_or_false_is_taken_for_false(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    page = Page()
    for text in ("", "maybe", "0x"):
        assert await store.put_setting(NOT_COUNTED, text)
        await check(page, store).check()
    assert all(NUMBER.fullmatch(i) for i in page.ids) and len(page.ids) == 3


async def test_the_switch_on_a_source_run_made_before_the_number_exists_still_keeps_the_number_for_later(tmp_path: Path) -> None:
    store = await store_at(tmp_path / "neoaprs.sqlite")
    assert await store.put_setting(NOT_COUNTED, "true")
    page = Page()
    await check(page, store).check()
    assert page.ids == ["0"]
    assert await store.put_setting(NOT_COUNTED, "false")
    await check(page, store).check()
    assert page.ids[1] == await store.setting(INSTALL_ID) and NUMBER.fullmatch(page.ids[1])


@pytest.mark.parametrize("kind, counted", [("source", False), ("pip", True), ("uv-tool", True), ("appimage", True), ("deb", True), ("windows-installer", True), ("macos-app", True)])
def test_only_the_source_tree_is_a_developers_run_the_other_kinds_are_installations(kind: InstallKind, counted: bool, tmp_path: Path) -> None:
    assert Controller(tmp_path, install=InstallInfo(kind)).updatecheck.developer is (not counted)


def test_a_wheel_installed_with_uv_tool_is_not_taken_for_a_checkout(tmp_path: Path) -> None:
    tool = tmp_path / "share" / "uv" / "tools" / "neoaprs"
    tool.mkdir(parents=True)
    assert detect(False, None, str(tool), None, False, {}).kind == "uv-tool"
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    assert detect(False, None, str(tmp_path / "venv"), clone, False, {}).kind == "source"
    assert detect(False, None, str(tmp_path / "venv"), tmp_path / "unpacked tarball", False, {}).kind == "pip"


@pytest.mark.parametrize("simulated", ["deb", "appimage /home/ham/NeoAPRS.AppImage", "windows-installer", "macos-app", "pip"])
def test_a_clone_that_simulates_another_kind_is_still_a_developers_run_and_a_real_install_is_not(simulated: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    monkeypatch.setattr(servicecmd, "source_tree", lambda: clone)
    install = detect_here(tmp_path, {ENV_KIND: simulated})
    assert install.kind != "source" and developers_run(install), "the screenshots' simulated kinds ask from a clone"
    monkeypatch.setattr(servicecmd, "source_tree", lambda: None)
    assert not developers_run(InstallInfo(install.kind)) and developers_run(InstallInfo("source"))


async def test_the_question_is_the_only_request_that_carries_an_id(tmp_path: Path) -> None:
    fake = await version_page({"version": "0.2.0", "url": "https://oh2gba.github.io/neoaprs/", "message": ""})
    notes: list[str] = []

    async def changelog(url: str, version: str, platform: str, limit: int) -> bytes | None:
        notes.append(url)
        return b"# Changelog\n\n## 0.2.0\n\n- A thing.\n"

    service = UpdateCheck(lambda: DEFAULTS, "0.1.0", "linux", Page(), environ={}, fetch_url=changelog)
    await service.check()
    await service.release_notes("0.2.0")
    frequencies = Frequencies("0.1.0", "linux", environ={FREQUENCIES_URL_ENV: fake.url}, first_sec=3600.0)
    await frequencies.ask()
    skeds = Skeds("0.1.0", "linux", lambda: DEFAULTS, environ={SKEDS_URL_ENV: fake.url}, first_sec=3600.0)
    await skeds.ask()
    seen = [path for path, _ in fake.requests]
    assert len(seen) == 2 and not any("id=" in path for path in seen) and notes and not any("id=" in url for url in notes)


def test_neoaprs_db_sets_and_reads_the_row_and_refuses_anything_but_true_or_false(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    assert db("set", NOT_COUNTED, "yes", data=data) == 0 and capsys.readouterr().out.strip() == f"{NOT_COUNTED} = true"
    assert db("get", NOT_COUNTED, data=data) == 0 and capsys.readouterr().out.strip() == "true"
    assert db("set", NOT_COUNTED, "maybe", data=data) == 2 and NOT_COUNTED in capsys.readouterr().err
    assert db("get", NOT_COUNTED, data=data) == 0 and capsys.readouterr().out.strip() == "true"
    assert db("set", NOT_COUNTED, "false", data=data) == 0
    assert db("set", INSTALL_ID, "0" * 32, data=data) == 2, "the installation's number is not set by hand: it is not a setting"
    assert (data / DB_NAME).is_file()


def test_neoaprs_db_get_prints_the_number_of_this_installation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    assert db("set", "station/call", "OH2GBA", data=data) == 0
    with sqlite3.connect(data / DB_NAME) as connection:
        connection.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (INSTALL_ID, "0123456789abcdef0123456789abcdef"))
    capsys.readouterr()
    assert db("get", INSTALL_ID, data=data) == 0 and capsys.readouterr().out.strip() == "0123456789abcdef0123456789abcdef"
    assert db("get", "no/such", data=data) == 2
    assert dbcmd.PROG == "neoaprs db"
