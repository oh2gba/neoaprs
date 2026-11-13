"""The path of a program of Windows (neoaprs/childenv.py, `windows_program`): built from the system's own folder, so that the program is the system's and not one of the same name in the folder of the running program or
the working folder. Nothing here needs Windows: the environment is the test's, and the path is made as a Windows path whatever the system running the test."""
import pytest

from neoaprs.childenv import windows_program


def test_a_program_of_system32_is_under_the_system_root_of_the_environment() -> None:
    assert windows_program("taskkill.exe", source={"SystemRoot": "D:\\WINNT"}) == "D:\\WINNT\\System32\\taskkill.exe"


def test_powershell_is_in_its_own_folder_below_system32() -> None:
    assert windows_program("WindowsPowerShell", "v1.0", "powershell.exe", source={"SYSTEMROOT": "C:\\Windows"}) == "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"


def test_explorer_is_in_the_system_folder_itself() -> None:
    assert windows_program("explorer.exe", system32=False, source={"SYSTEMROOT": "C:\\Windows"}) == "C:\\Windows\\explorer.exe"


@pytest.mark.parametrize("source, root", [({"WINDIR": "E:\\Win"}, "E:\\Win"), ({"SYSTEMROOT": "", "windir": "E:\\Win"}, "E:\\Win"), ({}, "C:\\Windows")])
def test_the_names_of_the_environment_are_found_in_any_case_and_the_system_folder_is_the_last_resort(source: dict[str, str], root: str) -> None:
    assert windows_program("taskkill.exe", source=source) == root + "\\System32\\taskkill.exe"


def test_the_path_is_absolute_so_the_program_is_never_looked_for_in_the_working_folder() -> None:
    for program in (windows_program("taskkill.exe", source={}), windows_program("explorer.exe", system32=False, source={})):
        assert program[1:3] == ":\\"


def test_the_process_environment_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYSTEMROOT", "F:\\Sys")
    assert windows_program("taskkill.exe") == "F:\\Sys\\System32\\taskkill.exe"
