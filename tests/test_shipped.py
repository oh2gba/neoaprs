"""What is shipped, as far as Linux can see it without a build: scripts/shipped-size, which prints what each download carries (over a made-up tree, and over a listing of the archive of a program of
PyInstaller), and the must-ship guard of the Windows folder (packaging/windows/must_ship.py and its list), which fails a build that lacks a file the app needs, shown failing on a made-up folder from
which one DLL is taken. The real folder is checked by the release workflow's Windows job, after PyInstaller."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.conftest import ROOT

SHIPPED = ROOT / "scripts" / "shipped-size"
MUST_SHIP = ROOT / "packaging" / "windows" / "must_ship.py"
LIST = ROOT / "packaging" / "windows" / "must-ship.txt"


def load(path: Path, name: str) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sizes() -> ModuleType:
    return load(SHIPPED, "shipped_size")


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    return load(MUST_SHIP, "must_ship")


def write(root: Path, files: dict[str, int]) -> Path:
    for name, size in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"x" * size)
    return root


# ---- the size printout ----

def test_a_tree_is_summed_by_group_with_its_largest_files_first(sizes: ModuleType, tmp_path: Path) -> None:
    tree = write(tmp_path / "NeoAPRS", {"neoaprs.exe": 300, "_internal/PIL/_avif.pyd": 7000, "_internal/PIL/_imaging.pyd": 2500, "_internal/python313.dll": 5900, "_internal/neoaprs/maps/world.pmtiles": 5700})
    if sys.platform != "win32":                                    # (a link needs a privilege on Windows)
        (tree / "link.dll").symlink_to(tree / "_internal" / "python313.dll")
    report = sizes.measure_tree(tree, depth=2)
    assert (report.total, report.files) == (21400, 5), "a link counts nothing: its file is counted where it is"
    assert report.groups == {"neoaprs.exe": 300, "_internal/PIL": 9500, "_internal/python313.dll": 5900, "_internal/neoaprs": 5700}
    assert report.largest[:2] == [(7000, "_internal/PIL/_avif.pyd"), (5900, "_internal/python313.dll")]
    assert sizes.measure_tree(tree).groups == {"neoaprs.exe": 300, "_internal": 21100}, "one folder deep by default"
    lines = sizes.tree_lines(report, "dist/NeoAPRS")
    assert lines[0] == "dist/NeoAPRS: 0.0 MB in 5 files (21400 bytes)" and lines[2].endswith("_internal/PIL")


def test_the_command_prints_a_tree_and_a_file_and_writes_the_step_summary(tmp_path: Path) -> None:
    tree = write(tmp_path / "AppDir", {"usr/lib/libbig.so": 2_500_000, "usr/bin/python3": 1_000_000})
    target = write(tmp_path, {"NeoAPRS-1.0.0-x86_64.AppImage": 1_200_000}) / "NeoAPRS-1.0.0-x86_64.AppImage"
    summary = tmp_path / "summary.md"
    done = subprocess.run([sys.executable, str(SHIPPED), "--title", "the tree", str(tree), str(target)], capture_output=True, text=True, timeout=60, env={**os.environ, "GITHUB_STEP_SUMMARY": str(summary)})
    assert done.returncode == 0, done.stderr
    assert "the tree: 3.5 MB in 2 files (3500000 bytes)" in done.stdout and "2.5 MB  usr" in done.stdout and "the tree: 1.2 MB (1200000 bytes)" in done.stdout
    text = summary.read_text(encoding="utf-8")
    assert "### the tree" in text and "| `usr/lib/libbig.so` | 2.5 MB |" in text and "**the tree**: 1.2 MB" in text


def test_a_name_that_must_be_absent_fails_when_it_is_there_and_a_path_that_is_not_there_is_said(tmp_path: Path) -> None:
    tree = write(tmp_path / "NeoAPRS", {"_internal/PIL/_avif.pyd": 10, "_internal/neoaprs/__init__.pyc": 10})
    there = subprocess.run([sys.executable, str(SHIPPED), "--depth", "2", "--absent", "_internal/PIL", str(tree)], capture_output=True, text=True, timeout=60)
    assert there.returncode == 1 and "_internal/PIL is in" in there.stderr and "must not be" in there.stderr
    (tree / "_internal" / "PIL" / "_avif.pyd").unlink()
    (tree / "_internal" / "PIL").rmdir()
    assert subprocess.run([sys.executable, str(SHIPPED), "--absent", "_internal/PIL", str(tree)], capture_output=True, timeout=60).returncode == 0
    gone = subprocess.run([sys.executable, str(SHIPPED), str(tmp_path / "gone")], capture_output=True, text=True, timeout=60)
    assert gone.returncode == 2 and "is not there" in gone.stderr


# The form of `pyi-archive_viewer -l -r` of PyInstaller 6 (utils/cliutils/archive_viewer.py): a heading for each archive, its column names, a line an entry. Made up after that form; the first dry run of
# the release workflow prints the real one, which replaces this one if it differs.
LISTING = """Contents of 'neoaprs.exe' (PKG/CArchive):
 position, length, uncompressed_length, is_compressed, typecode, name
 0, 215, 286, 1, 'm', 'struct'
 215, 1102, 2006, 1, 's', 'pyiboot01_bootstrap'
 1317, 9123456, 9123456, 0, 'z', 'PYZ.pyz'

Contents of 'PYZ.pyz' (PYZ, embedded in 'neoaprs.exe'):
 typecode, position, length, name
 0, 17, 2100, 'neoaprs'
 0, 2117, 51234, 'neoaprs.web.server'
 0, 53351, 40000, 'PIL.Image'
 0, 93351, 3000, 'PIL'
 1, 96351, 120, 'tornado'
 0, 96471, 9000, 'tornado.web'
"""


def test_the_pyz_of_a_program_is_summed_by_top_package_from_the_recursive_listing(sizes: ModuleType) -> None:
    report = sizes.parse_listing(LISTING, "neoaprs.exe")
    assert (report.entries, report.total) == (6, 105454), "the PYZ's entries alone, not the program's own archive"
    assert report.packages == {"neoaprs": 53334, "PIL": 43000, "tornado": 9120}
    assert sizes.archive_lines(report)[0] == "neoaprs.exe: its PYZ is 0.1 MB in 6 modules (compressed, 105454 bytes)"
    assert sizes.present(["PIL", "PySide6"], archive=report) == ["PIL is in the archive of neoaprs.exe (0.0 MB)"]


def test_a_listing_without_its_pyz_or_with_columns_it_cannot_read_is_refused_and_not_counted_as_nothing(sizes: ModuleType) -> None:
    with pytest.raises(sizes.Unreadable, match="no PYZ part"):
        sizes.parse_listing(LISTING.split("\n\n")[0], "neoaprs.exe")
    with pytest.raises(sizes.Unreadable, match="no length and name"):
        sizes.parse_listing("Contents of 'PYZ.pyz' (PYZ):\n typecode, position, size, module\n 0, 1, 2, 'x'\n")
    with pytest.raises(sizes.Unreadable, match="does not fit its columns"):
        sizes.parse_listing("Contents of 'PYZ.pyz' (PYZ):\n typecode, position, length, name\n 0, 2, 'x'\n")


def test_the_viewer_is_asked_for_the_recursive_listing_and_its_failure_is_said(sizes: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    program = write(tmp_path, {"neoaprs.exe": 10}) / "neoaprs.exe"
    asked: list[list[str]] = []

    def viewer(argv: list[str]) -> str:
        asked.append(argv)
        return LISTING
    assert sizes.main(["--pyi-archive", "--viewer", "pyi-archive_viewer", "--absent", "PIL", str(program)], run=viewer) == 1
    assert asked == [["pyi-archive_viewer", "-l", "-r", str(program)]]
    out = capsys.readouterr()
    assert "neoaprs.exe: its PYZ is 0.1 MB in 6 modules" in out.out and "PIL is in the archive of neoaprs.exe" in out.err
    assert "module:" not in out.out, "the modules one by one only when asked"
    assert sizes.main(["--pyi-archive", "--modules", "--viewer", "v", str(program)], run=viewer) == 0
    listed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("  module: ")]
    assert listed == [f"  module: {name}" for name in ("PIL", "PIL.Image", "neoaprs", "neoaprs.web.server", "tornado", "tornado.web")], "every module, sorted, so that two builds' lists compare"

    def broken(argv: list[str]) -> str:
        raise sizes.Unreadable("pyi-archive_viewer ended with 1: not an archive")
    assert sizes.main(["--pyi-archive", "--viewer", "v", str(program)], run=broken) == 2
    assert "not an archive" in capsys.readouterr().err


# ---- the must-ship guard of the Windows folder ----

# A made-up dist/NeoAPRS with the files a real one has (by the names the measure of 0.18.2 reports, and pywebview's and clr_loader's copies for other processors, which must not stand in for the 64-bit
# ones); sizes do not matter here.
WINDOWS_TREE = [
    "neoaprs.exe", "neoaprsw.exe", "neoaprs-app.exe",
    "_internal/python313.dll", "_internal/VCRUNTIME140.dll", "_internal/VCRUNTIME140_1.dll", "_internal/libcrypto-3.dll", "_internal/libssl-3.dll", "_internal/sqlite3.dll", "_internal/libffi-8.dll",
    "_internal/_ssl.pyd", "_internal/_hashlib.pyd", "_internal/_sqlite3.pyd", "_internal/_ctypes.pyd", "_internal/_overlapped.pyd", "_internal/_asyncio.pyd", "_internal/_socket.pyd", "_internal/select.pyd",
    "_internal/base_library.zip", "_internal/_cffi_backend.cp313-win_amd64.pyd",
    "_internal/cryptography/hazmat/bindings/_rust.pyd", "_internal/pydantic_core/_pydantic_core.cp313-win_amd64.pyd",
    "_internal/pythonnet/runtime/Python.Runtime.dll", "_internal/clr_loader/ffi/dlls/amd64/ClrLoader.dll", "_internal/clr_loader/ffi/dlls/x86/ClrLoader.dll",
    "_internal/webview/lib/Microsoft.Web.WebView2.Core.dll", "_internal/webview/lib/Microsoft.Web.WebView2.WinForms.dll", "_internal/webview/lib/WebBrowserInterop.x64.dll",
    "_internal/webview/lib/WebBrowserInterop.x86.dll", "_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll", "_internal/webview/lib/runtimes/win-x86/native/WebView2Loader.dll",
    "_internal/webview/lib/runtimes/win-arm64/native/WebView2Loader.dll",
    "_internal/certifi/cacert.pem", "_internal/neoaprs/maps/basemap-world.pmtiles", "_internal/neoaprs/desktop/icon.ico", "_internal/neoaprs/page/index.html",
]


def windows_tree(root: Path) -> Path:
    """The made-up folder, with every file the committed list names besides (a line spelled otherwise than the made-up name is the same file: Windows ignores case)."""
    names = {name.lower(): name for name in WINDOWS_TREE}
    for line in load(MUST_SHIP, "must_ship").read_list(LIST.read_text(encoding="utf-8")):
        if not any(char in line for char in "*?["):
            names.setdefault(line.lower(), line)
    return write(root / "NeoAPRS", {name: 1 for name in names.values()})


def run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(MUST_SHIP), *args], capture_output=True, text=True, timeout=60)


def named(stderr: str, path: str) -> bool:
    """Whether the guard's failure names the file: by its path, or by the pattern of the list that it is the file of."""
    import fnmatch
    listed = [line[2:].lower() for line in stderr.splitlines() if line.startswith("  ")]
    return any(fnmatch.fnmatchcase(path.lower(), line) for line in listed)


# Each file the app cannot start or run without, as the made-up folder spells it: the guard fails without it, whatever the list says, though another copy of the same DLL is still there.
NEEDED = ("_internal/VCRUNTIME140.dll", "_internal/VCRUNTIME140_1.dll", "_internal/sqlite3.dll", "_internal/libffi-8.dll", "_internal/_ssl.pyd", "_internal/_hashlib.pyd", "_internal/_sqlite3.pyd",
          "_internal/_ctypes.pyd", "_internal/_overlapped.pyd", "_internal/_asyncio.pyd", "_internal/_socket.pyd", "_internal/select.pyd", "_internal/_cffi_backend.cp313-win_amd64.pyd",
          "_internal/pydantic_core/_pydantic_core.cp313-win_amd64.pyd", "_internal/clr_loader/ffi/dlls/amd64/ClrLoader.dll", "_internal/webview/lib/Microsoft.Web.WebView2.Core.dll",
          "_internal/webview/lib/Microsoft.Web.WebView2.WinForms.dll", "_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll", "_internal/neoaprs/desktop/icon.ico")


def test_the_list_holds_what_the_app_can_never_run_without(guard: ModuleType) -> None:
    """The measure's never-drop names: the C runtime, python313.dll, the OpenSSL DLLs, cryptography's native module, pythonnet's runtime, clr_loader, pywebview's DLLs; the standard library's modules the
    daemon and the app start with; and the data the app reads at once: Python's frozen standard library, the root certificates, the world map, the tray's icon."""
    lines = guard.read_list(LIST.read_text(encoding="utf-8"))
    for pattern in guard.NEVER_DROP:
        assert guard.covers(lines, pattern), f"{pattern} is not in {LIST.name}"
    for needed in ("vcruntime140", "python313.dll", "libcrypto-3", "libssl-3", "_rust.pyd", "python.runtime.dll", "webview/lib", "pythonnet", "clr_loader", "base_library.zip", "cacert.pem", "basemap-world.pmtiles",
                   "icon.ico", "_sqlite3.pyd", "_overlapped.pyd", "_ctypes.pyd", "_pydantic_core"):
        assert any(needed in pattern for pattern in guard.NEVER_DROP), needed
    assert LIST.read_text(encoding="utf-8").endswith("\n") and all(line == line.strip() for line in lines)


def test_the_list_names_nothing_of_pillow(guard: ModuleType) -> None:
    """Pillow is not shipped (the tray is given icon.ico as it is, and the spec excludes PIL), so the list names none of it: its lines went in the commit that left it out."""
    lines = guard.read_list(LIST.read_text(encoding="utf-8"))
    assert not [line for line in lines if "/pil/" in line.lower() or line.lower().startswith("_internal/pil")], "no line of Pillow"


def test_the_list_is_the_one_a_real_build_made(guard: ModuleType) -> None:
    """The committed list is what `must_ship.py --write` printed for a real build of the release workflow: every .dll and .pyd by its name, no pattern. A list written by hand, like the never-drop names
    alone, lets most needed DLLs go without a failure, so this fails until the real one is in."""
    text = LIST.read_text(encoding="utf-8")
    lines = guard.read_list(text)
    assert "Until the list of a real build replaces this one" not in text, "packaging/windows/must-ship.txt is still the never-drop names alone: put in the list of the first release dry run"
    assert [line for line in lines if guard.is_pattern(line)] == [], "a real build's list has every file by its name"
    assert len(lines) > len(guard.NEVER_DROP)


def test_a_folder_with_every_file_passes_and_one_without_a_needed_file_fails_naming_it(tmp_path: Path) -> None:
    tree = windows_tree(tmp_path)
    passed = run_guard(str(LIST), str(tree))
    assert passed.returncode == 0, passed.stderr
    assert "every file of must-ship.txt is in" in passed.stdout
    for gone in ("_internal/libssl-3.dll", "_internal/pythonnet/runtime/Python.Runtime.dll", "_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll",
                 "_internal/clr_loader/ffi/dlls/amd64/ClrLoader.dll", "_internal/base_library.zip", "_internal/neoaprs/desktop/icon.ico"):
        copy = windows_tree(tmp_path / gone.replace("/", "_"))
        (copy / gone).unlink()
        failed = run_guard(str(LIST), str(copy))
        assert failed.returncode == 1 and "lacks" in failed.stderr and named(failed.stderr, gone), (gone, failed.stderr)


def test_the_list_made_from_a_build_names_every_dll_and_pyd_and_the_data_and_then_holds_that_build(guard: ModuleType, tmp_path: Path) -> None:
    tree = windows_tree(tmp_path)
    made = tmp_path / "must-ship.txt"
    done = run_guard("--write", str(made), str(tree))
    assert done.returncode == 0, done.stderr
    lines = guard.read_list(made.read_text(encoding="utf-8"))
    assert lines == sorted(lines, key=str.lower) and "_internal/VCRUNTIME140.dll" in lines and "_internal/clr_loader/ffi/dlls/x86/ClrLoader.dll" in lines, "spelled as in the folder"
    assert {line for line in lines if not line.lower().endswith((".dll", ".pyd"))} == {"_internal/base_library.zip", "_internal/certifi/cacert.pem", "_internal/neoaprs/maps/basemap-world.pmtiles",
                                                                                          "_internal/neoaprs/desktop/icon.ico"}
    assert "neoaprs.exe" not in lines and "_internal/neoaprs/page/index.html" not in lines
    assert all(guard.covers(lines, pattern) for pattern in guard.NEVER_DROP)
    assert run_guard(str(made), str(tree)).returncode == 0
    (tree / "_internal" / "webview" / "lib" / "WebBrowserInterop.x86.dll").unlink()
    failed = run_guard(str(made), str(tree))
    assert failed.returncode == 1 and "_internal/webview/lib/WebBrowserInterop.x86.dll" in failed.stderr, "a DLL of the build that went is a failure, though it is not one of the never-drop names"


def test_no_list_is_made_of_a_folder_that_lacks_a_never_drop_file_and_the_names_it_has_are_printed(tmp_path: Path) -> None:
    tree = windows_tree(tmp_path)
    (tree / "_internal" / "python313.dll").unlink()
    done = run_guard("--write", str(tmp_path / "list.txt"), str(tree))
    assert done.returncode == 1 and "_internal/python313.dll" in done.stderr and not (tmp_path / "list.txt").exists()
    assert "_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll\n" in done.stdout, "the folder's own names, to set the never-drop ones by"


def test_the_never_drop_files_are_checked_whatever_the_list_says_and_no_other_copy_stands_in(guard: ModuleType, tmp_path: Path) -> None:
    short = "# a list that lost its lines\n_internal/base_library.zip\n"
    assert guard.check(short, windows_tree(tmp_path / "whole")) == ([], guard.unlisted(guard.read_list(short), guard.files_of(tmp_path / "whole" / "NeoAPRS")))
    for gone in (*NEEDED, "_internal/cryptography/hazmat/bindings/_rust.pyd"):
        tree = windows_tree(tmp_path / gone.replace("/", "_"))
        (tree / gone).unlink()
        missing, _ = guard.check(short, tree)
        assert [line for line in missing if guard.fnmatch.fnmatchcase(gone.lower(), line)], f"{gone} went and the guard let it"


def test_a_new_dll_is_named_without_failing(tmp_path: Path) -> None:
    full = windows_tree(tmp_path / "full")
    made = tmp_path / "made.txt"
    assert run_guard("--write", str(made), str(full)).returncode == 0
    write(full, {"_internal/bleak/BleakWinRT.dll": 1})
    noticed = run_guard(str(made), str(full))
    assert noticed.returncode == 0 and "_internal/bleak/bleakwinrt.dll is in the folder and not in made.txt" in noticed.stdout


def test_case_is_ignored_as_windows_ignores_it_and_a_pattern_must_match_one_file(guard: ModuleType) -> None:
    files = ["_internal/vcruntime140.dll", "_internal/webview/lib/runtimes/win-x64/native/webview2loader.dll"]
    assert guard.missing(["_internal/VCRUNTIME140.dll", "_internal/webview/lib/*.dll"], files) == []
    assert guard.missing(["_internal/clr_loader/*.dll", "_internal/libssl-3.dll"], files) == ["_internal/clr_loader/*.dll", "_internal/libssl-3.dll"]
    assert json.dumps(guard.NEVER_DROP) == json.dumps(tuple(pattern.lower() for pattern in guard.NEVER_DROP)), "the names are written in lower case, as they are compared"
    assert [pattern for pattern in guard.NEVER_DROP if guard.is_pattern(pattern) and not pattern.endswith(("-3*.dll", "-*.dll", "*.pyd"))] == [], "a * stands only for a version in a name"


# ---- who imports what the spec leaves out ----

# The form of PyInstaller's warn file (build/neoaprs/warn-neoaprs.txt): a line a module it did not take, with every module that imports it and how.
WARN = """
This file lists modules PyInstaller was not able to find. This does not necessarily
mean these modules are required for running your program.

missing module named pwd - imported by posixpath (delayed, conditional, optional), shutil (delayed, optional), pathlib._local (optional)
excluded module named _frozen_importlib - imported by importlib (optional), importlib.abc (optional), zipimport (top-level)
excluded module named PIL - imported by pystray._xorg (top-level), pystray._gtk (top-level), pystray._appindicator (top-level), pystray._darwin (top-level)
excluded module named PIL.Image - imported by pystray._darwin (top-level)
excluded module named tkinter - imported by webview.platforms.tk (top-level)
"""
PYSTRAY_ELSEWHERE = ("pystray._xorg", "pystray._gtk", "pystray._appindicator", "pystray._darwin")


def test_an_excluded_module_imported_only_by_other_systems_backends_passes_and_its_importers_are_said(guard: ModuleType, tmp_path: Path) -> None:
    assert guard.importers_of(WARN, "PIL") == list(PYSTRAY_ELSEWHERE)
    assert guard.importers_of(WARN, "PySide6") == []
    warn = write(tmp_path, {"warn-neoaprs.txt": 0}) / "warn-neoaprs.txt"
    warn.write_text(WARN.replace("\n", "\r\n"), encoding="utf-8", newline="")
    done = run_guard("--excluded", str(warn), "PIL", *PYSTRAY_ELSEWHERE)
    assert done.returncode == 0, done.stderr
    assert "PIL is excluded, and imported by pystray._xorg, pystray._gtk, pystray._appindicator, pystray._darwin" in done.stdout


def test_an_excluded_module_that_the_app_imports_fails_naming_its_importer(tmp_path: Path) -> None:
    warn = write(tmp_path, {"warn-neoaprs.txt": 0}) / "warn-neoaprs.txt"
    warn.write_text(WARN.replace("pystray._darwin (top-level)\n", "pystray._darwin (top-level), webview.platforms.winforms (delayed, conditional)\n", 1), encoding="utf-8")
    done = run_guard("--excluded", str(warn), "PIL", *PYSTRAY_ELSEWHERE)
    assert done.returncode == 1 and "webview.platforms.winforms" in done.stderr and "pystray._xorg" not in done.stderr


def test_a_file_that_is_no_record_of_pyinstaller_is_refused_and_not_read_as_nobody_imports_it(tmp_path: Path) -> None:
    other = write(tmp_path, {"warn.txt": 0}) / "warn.txt"
    other.write_text("W: no module named PIL (conditional import by pystray._xorg)\n", encoding="utf-8")
    for path in (other, tmp_path / "gone.txt"):
        done = run_guard("--excluded", str(path), "PIL", *PYSTRAY_ELSEWHERE)
        assert done.returncode == 2 and "cannot tell who imports PIL" in done.stderr, path
