"""The Mercury for Windows that NeoAPRS builds itself, as far as it can be held on any system without MinGW or a Windows machine: scripts/build-mercury's Windows options (the make commands, the folder it stages, the check
of the program's import table, which reads a PE file by itself), packaging/windows/bundle_mercury.py (the tarball of the release workflow's job `mercury-windows` into the app folder, and nothing that is not the pinned
Mercury's), and packaging/windows/smoke_mercury.py (the reading of `netstat -ano` and the verdict on the program's sockets, the Windows half of the check that it listens on 127.0.0.1 only). The workflow's wiring is in
tests/test_release.py; the cross compile itself is done by the release workflow's job, and the Windows job starts the program it makes."""
import importlib.machinery
import importlib.util
import io
import re
import struct
import subprocess
import sys
import tarfile
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import mercury
from tests.conftest import ROOT

SCRIPT = ROOT / "scripts" / "build-mercury"
LOOPBACK_PATCH = ROOT / "packaging" / "mercury" / "loopback.patch"


def load(name: str, path: Path) -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build() -> types.ModuleType:
    return load("build_mercury_windows", SCRIPT)


@pytest.fixture(scope="module")
def bundle() -> types.ModuleType:
    return load("bundle_mercury", ROOT / "packaging" / "windows" / "bundle_mercury.py")


@pytest.fixture(scope="module")
def smoke() -> types.ModuleType:
    return load("smoke_mercury", ROOT / "packaging" / "windows" / "smoke_mercury.py")


def make_pe(imports: list[str], machine: int = 0x8664, version: bool = True, delay: list[str] | None = None) -> bytes:
    """A PE32+ file with one section that holds an import table naming `imports` (and a delay-load table naming `delay`) and, when asked, the pinned version's text: what the check reads, and no more."""
    section_rva, section_raw = 0x1000, 0x400
    body = bytearray()

    def table(names: list[str], size: int, name_at: int) -> int:
        start = len(body)
        body.extend(bytes(size * (len(names) + 1)))
        for index, name in enumerate(names):
            at = len(body)
            body.extend(name.encode("ascii") + b"\0")
            struct.pack_into("<I", body, start + size * index + name_at, section_rva + at)
        return section_rva + start

    imports_rva = table(imports, 20, 12)
    delay_rva = table(delay, 32, 4) if delay else 0
    if version:
        body.extend(f"Rhizomatica Mercury Version {mercury.VERSION}\0".encode("ascii"))
    optional = bytearray(240)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<I", optional, 112 + 8 * 1, imports_rva)
    struct.pack_into("<I", optional, 112 + 8 * 13, delay_rva)
    coff = struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, len(optional), 0x22)
    section = struct.pack("<8sIIIIIIHHI", b".rdata", len(body), section_rva, len(body), section_raw, 0, 0, 0, 0, 0x40000040)
    head = bytearray(0x40)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)
    out = bytes(head) + b"PE\0\0" + coff + bytes(optional) + section
    return out + bytes(section_raw - len(out)) + bytes(body)


# ---- scripts/build-mercury --windows

def test_the_windows_build_is_made_the_way_mercurys_own_windows_target_makes_it_with_nothing_but_hamlib_and_the_tls_left_out(build: types.ModuleType) -> None:
    objects, program = build.make_commands(windows=True)
    for command in (objects, program):
        assert command[0] == "make" and command[1].startswith("-j")
        assert {"OS=Windows_NT", "CC=x86_64-w64-mingw32-gcc", "AR=x86_64-w64-mingw32-ar", "HAVE_HAMLIB=0", "WS_TLS=0", f"GIT_HASH={mercury.SOURCE_COMMIT[:8]}"} <= set(command)
        assert {"HAMLIB_CFLAGS=", "HAMLIB_LDFLAGS=", "WS_TLS_CFLAGS=", "WS_TLS_LDFLAGS="} <= set(command)
        assert not any(word.startswith(("HAVE_HIDAPI", "HIDAPI_")) for word in command), "hidapi stays in: it keys a CM108 chip on Windows"
        assert not any(word.startswith("FFAUDIO_LINKFLAGS") for word in command), "the Makefile's own Windows link flags (DirectSound, Winsock, the runtime's threads, linked in) are used"
        assert "EXTRA_LDFLAGS=-s -static" in command, "stripped, and no DLL of MinGW asked for"
        assert not any(word.startswith("MERCURY_HOST") for word in command), "the standalone program (the default) carries the UI interface's websocket server, which the HF box's scope and Transmit level read, on Windows as on Linux"
    assert objects[-1] == "internal_deps" and program[-1] == "mercury.exe", "the objects first, then the link: two makes, because the two goals would run side by side"
    (linux,) = build.make_commands(windows=False)
    if sys.platform == "linux":
        assert "HAVE_HIDAPI=0" in linux and "OS=Windows_NT" not in linux and "mercury.exe" not in linux, "the Linux command is as it was"


def test_the_windows_tarball_is_named_for_the_version_and_the_64_bit_pc(build: types.ModuleType) -> None:
    assert build.tarball_name(system="win32") == f"mercury-{mercury.VERSION}-windows-x86_64.tar.gz"
    assert build.tarball_name("aarch64", "win32") == f"mercury-{mercury.VERSION}-windows-x86_64.tar.gz", "built on whatever machine, for the 64-bit PC"
    assert build.machine_name("arm64", "win32") == "x86_64"
    assert build.tarball_name("x86_64", "linux") == f"mercury-{mercury.VERSION}-linux-x86_64.tar.gz"
    assert build.tarball_name("arm64", "darwin") == f"mercury-{mercury.VERSION}-macos-arm64.tar.gz"


def test_the_usage_names_the_windows_option_and_it_is_refused_with_install_and_off_linux(build: types.ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    done = subprocess.run([sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "--windows" in done.stdout and "MinGW-w64" in done.stdout
    assert build.main(["--windows", "--install"]) == 1
    assert "--install" in capsys.readouterr().err or sys.platform != "linux"


def test_a_missing_cross_compiler_is_said_before_anything_is_fetched_or_built(build: types.ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    if sys.platform != "linux":
        pytest.skip("the cross build is made on Linux")
    monkeypatch.setattr(build.shutil, "which", lambda tool: None if tool == "x86_64-w64-mingw32-gcc" else f"/usr/bin/{tool}")
    monkeypatch.setattr(build, "fetch_source", lambda: pytest.fail("nothing is fetched before the tools are known to be there"))
    assert build.main(["--windows"]) == 1
    assert "x86_64-w64-mingw32-gcc is not installed" in capsys.readouterr().err


def test_the_loopback_patch_covers_the_listeners_and_the_web_pages_socket_and_the_build_checks_both(build: types.ModuleType) -> None:
    text = LOOPBACK_PATCH.read_text(encoding="utf-8")
    assert "--- a/gui_interface/websocket/mercury_websocket.c" in text and '+    opts.bind_addr = "127.0.0.1";' in text and "-    opts.bind_addr = NULL;" in text
    script = SCRIPT.read_text(encoding="utf-8")
    assert "WEBSOCKET_BIND not in" in script and "WEBSOCKET_FILE" in script, "the build looks for the bind after the patch"
    assert "no firewall rule" in text.lower() or "firewall rule to stand in" in text, "the patch says that no firewall rule stands in for it any more"


def test_the_patches_apply_to_the_pinned_source_for_windows_too_when_the_archive_is_at_hand(build: types.ModuleType, tmp_path: Path) -> None:
    archive = build.cache_dir() / f"mercury-{mercury.VERSION}-{mercury.SOURCE_COMMIT[:8]}.tar.gz"
    if not archive.is_file() or build.sha256(archive) != mercury.SOURCE_SHA256 or sys.platform == "win32":
        pytest.skip("the pinned source archive is in the build cache after any build of Mercury")
    tree = build.unpack(archive, tmp_path / "work")
    build.apply_patches(tree, windows=True)
    assert 'opts.bind_addr = "127.0.0.1"' in (tree / build.WEBSOCKET_FILE).read_text(encoding="utf-8")
    assert "INADDR_ANY" not in (tree / build.LISTENERS_FILE).read_text(encoding="utf-8")
    assert "audio:tx_leadin_ms" in (tree / build.LEADIN_FILE).read_text(encoding="utf-8")
    assert 'LoadLibraryW(L"dsound.dll")' in (tree / build.DSOUND_FILE).read_text(encoding="utf-8") and "-ldsound" not in (tree / "Makefile").read_text(encoding="utf-8"), "DirectSound is loaded on first use, not linked"
    assert "pulse_stub" not in (tree / "audioio" / "ffaudio" / "ffaudio" / "pulse.c").read_text(encoding="utf-8"), "the stub over PulseAudio is for Linux only"
    assert (tree / build.HIDAPI_DIR / "src" / "hid.c").is_file() and (tree / build.HIDAPI_DIR / "LICENSE.txt").is_file(), "the vendored hidapi and its licence are in the source"


def test_the_import_table_of_a_program_is_read_and_a_dll_that_does_not_come_with_windows_is_refused(build: types.ModuleType, tmp_path: Path) -> None:
    program = tmp_path / "mercury.exe"
    ok = ["KERNEL32.dll", "WS2_32.dll", "ole32.dll", "USER32.dll", "msvcrt.dll", "api-ms-win-crt-runtime-l1-1-0.dll"]
    program.write_bytes(make_pe(ok, delay=["SETUPAPI.dll"]))
    machine, names = build.pe_imports(program)
    assert machine == 0x8664 and names == [*ok, "SETUPAPI.dll"], "the delay-loaded ones too"
    assert build.check_windows(tmp_path).startswith("imports: ")
    for foreign in ("libwinpthread-1.dll", "libgcc_s_seh-1.dll", "libhamlib-4.dll", "libusb-1.0.dll", "libssl-3-x64.dll", "msvcr100.dll"):
        program.write_bytes(make_pe([*ok, foreign]))
        with pytest.raises(build.BuildError, match=re.escape(foreign)):
            build.check_windows(tmp_path)
    program.write_bytes(make_pe(ok, delay=["libwinpthread-1.dll"]))
    with pytest.raises(build.BuildError, match="libwinpthread"):
        build.check_windows(tmp_path)
    program.write_bytes(make_pe([*ok, "DSOUND.dll"]))                    # (Windows's own, but on an N edition it needs the missing ResampleDmo.dll and the program never starts)
    with pytest.raises(build.BuildError, match="Media Feature Pack"):
        build.check_windows(tmp_path)


def test_a_program_for_another_machine_or_of_another_version_or_no_program_is_refused(build: types.ModuleType, tmp_path: Path) -> None:
    program = tmp_path / "mercury.exe"
    program.write_bytes(make_pe(["KERNEL32.dll"], machine=0xAA64))
    with pytest.raises(build.BuildError, match="not for x86-64 Windows"):
        build.check_windows(tmp_path)
    program.write_bytes(make_pe(["KERNEL32.dll"], version=False))
    with pytest.raises(build.BuildError, match=re.escape(f"Mercury {mercury.VERSION}")):
        build.check_windows(tmp_path)
    for junk in (b"", b"MZ", b"\x7fELF" + bytes(100), b"MZ" + bytes(0x80)):
        program.write_bytes(junk)
        with pytest.raises(ValueError):
            build.pe_imports(program)


def test_the_windows_folder_holds_the_program_the_licences_and_the_source_offer_and_nothing_else(build: types.ModuleType, tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    (tree / build.HIDAPI_DIR).mkdir(parents=True)
    (tree / "mercury.exe").write_bytes(make_pe(["KERNEL32.dll"]))
    (tree / "LICENSE").write_text("GPL", encoding="utf-8")
    (tree / "LICENSE-freedv").write_text("LGPL", encoding="utf-8")
    (tree / build.HIDAPI_DIR / "LICENSE.txt").write_text("hidapi", encoding="utf-8")
    (tree / build.HIDAPI_DIR / "LICENSE-bsd.txt").write_text("bsd", encoding="utf-8")
    folder = build.stage_windows(tree, tmp_path / "out", 0.0)
    assert sorted(path.name for path in folder.iterdir()) == ["LICENSE", "LICENSE-freedv", "LICENSE-hidapi-bsd.txt", "LICENSE-hidapi.txt", "SOURCE.txt", "mercury.exe"]
    offer = (folder / "SOURCE.txt").read_text(encoding="utf-8")
    for fact in (mercury.SOURCE_URL, mercury.SOURCE_COMMIT, mercury.SOURCE_SHA256, f"Mercury {mercury.VERSION}", "OS=Windows_NT", "x86_64-w64-mingw32-gcc", "loopback.patch", "leadin.patch", "hidapi", "winpthreads"):
        assert fact in offer, fact
    assert "hamlib and OpenSSL are not in this build" in offer
    assert "watterson" not in offer, "the simulator is not part of the Windows folder"
    (tree / build.HIDAPI_DIR / "LICENSE.txt").unlink()
    with pytest.raises(build.BuildError, match="licence has to travel"):
        build.stage_windows(tree, tmp_path / "out2", 0.0)
    tarball = build.make_tarball(folder, tmp_path, "win32")
    assert tarball.name == f"mercury-{mercury.VERSION}-windows-x86_64.tar.gz"
    with tarfile.open(tarball) as tar:
        assert sorted(tar.getnames()) == ["mercury", *sorted(f"mercury/{path.name}" for path in folder.iterdir())]


# ---- packaging/windows/bundle_mercury.py

def make_tarball(path: Path, **override: bytes | None) -> Path:
    """The tarball the build makes (or a bad one: a member with the bytes given, or None to leave it out), at `path`."""
    offer = f"Mercury {mercury.VERSION}, Rhizomatica's HF modem\nCommit: {mercury.SOURCE_COMMIT}\nSHA-256 of the source archive: {mercury.SOURCE_SHA256}\n".encode()
    members: dict[str, bytes | None] = {"mercury.exe": b"MZ program", "SOURCE.txt": offer, "LICENSE": b"GPL text", "LICENSE-freedv": b"LGPL", "LICENSE-hidapi.txt": b"hidapi"}
    members.update(override)
    with tarfile.open(path, "w:gz") as tar:
        folder = tarfile.TarInfo("mercury")
        folder.type = tarfile.DIRTYPE
        tar.addfile(folder)
        for name, data in members.items():
            if data is not None:
                info = tarfile.TarInfo(name if "/" in name else f"mercury/{name}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return path


def test_bundle_mercury_has_no_pins_of_its_own_and_fetches_nothing() -> None:
    source = (ROOT / "packaging" / "windows" / "bundle_mercury.py").read_text(encoding="utf-8")
    assert "from neoaprs import mercury" in source and "mercury.SOURCE_SHA256" in source and "mercury.SOURCE_COMMIT" in source and "mercury.VERSION" in source
    assert "urllib" not in source and "https://" not in source and "http://" not in source and not re.search(r"\b[0-9a-f]{64}\b", source), "the pins are in neoaprs/mercury.py and nowhere else"
    assert "WINDOWS_URL" not in source and "WINDOWS_SHA256" not in source


def test_bundle_mercury_puts_the_program_and_the_licences_in_bin_mercury(bundle: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    archive = make_tarball(tmp_path / bundle.tarball_name())
    monkeypatch.setattr(sys, "argv", ["bundle_mercury.py", str(tmp_path / "NeoAPRS"), str(archive)])
    assert bundle.main() == 0
    folder = tmp_path / "NeoAPRS" / "bin" / "mercury"
    assert sorted(p.name for p in folder.iterdir()) == ["LICENSE", "LICENSE-freedv", "LICENSE-hidapi.txt", "SOURCE.txt", "mercury.exe"]
    assert (folder / "mercury.exe").read_bytes() == b"MZ program" and (folder / "LICENSE").read_bytes() == b"GPL text"
    assert "mercury.exe (10 bytes)" in capsys.readouterr().out
    (folder / "stale.dll").write_bytes(b"old")
    assert bundle.main() == 0 and not (folder / "stale.dll").exists(), "a folder of an earlier run is made again, not added to"


def test_bundle_mercury_refuses_what_is_not_the_pinned_mercury_for_windows_and_keeps_nothing(bundle: types.ModuleType, tmp_path: Path) -> None:
    refused: list[tuple[str, dict[str, bytes | None], str]] = [
        ("a member out of the folder", {"../evil.dll": b"x"}, "outside the folder"),
        ("a DLL beside the program", {"libwinpthread-1.dll": b"MZ"}, "not a file the app takes"),
        ("a file in a folder inside it", {"mercury/lib/x.txt": b"x"}, "not a file the app takes"),
        ("no program", {"mercury.exe": None}, "lacks mercury.exe"),
        ("no licence", {"LICENSE": None}, "lacks mercury.exe, SOURCE.txt or LICENSE"),
        ("a program that is not one", {"mercury.exe": b"\x7fELF"}, "not a program for Windows"),
        ("a source offer of another Mercury", {"SOURCE.txt": b"Mercury 0.0.1, built"}, "not a Mercury built from the pinned source"),
    ]
    for number, (what, override, message) in enumerate(refused):
        (tmp_path / str(number)).mkdir()
        archive = make_tarball(tmp_path / str(number) / bundle.tarball_name(), **override)
        folder = tmp_path / f"out-{number}"
        with pytest.raises(SystemExit, match=message):
            bundle.unpack(archive, folder)
        assert not folder.exists(), f"{what}: nothing is kept"
    other = make_tarball(tmp_path / "mercury-0.0.1-windows-x86_64.tar.gz")
    with pytest.raises(SystemExit, match="is not mercury-"):
        bundle.unpack(other, tmp_path / "out-name")
    assert not (tmp_path / "out-name").exists()


# ---- packaging/windows/smoke_mercury.py

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1136
  TCP    127.0.0.1:8100         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8300         0.0.0.0:0              KUUNTELEE       4242
  TCP    127.0.0.1:8301         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8100         127.0.0.1:50321        ESTABLISHED     4242
  TCP    [::]:445               [::]:0                 LISTENING       4
  TCP    [::1]:9000             [::]:0                 LISTENING       4242
  UDP    0.0.0.0:5353           *:*                                    900
"""


def test_the_netstat_table_is_read_for_the_listeners_of_one_process_whatever_the_language_of_windows(smoke: types.ModuleType) -> None:
    assert smoke.listening(NETSTAT, 4242) == {8100: {"127.0.0.1"}, 8300: {"127.0.0.1"}, 8301: {"127.0.0.1"}, 9000: {"::1"}}, "an established connection and the state's word do not matter; an IPv6 address has its brackets off"
    assert smoke.listening(NETSTAT, 1136) == {135: {"0.0.0.0"}} and smoke.listening(NETSTAT, 7) == {} and smoke.listening("", 1) == {}


def test_the_verdict_wants_every_port_and_the_loopback_alone(smoke: types.ModuleType) -> None:
    ports = {8100, 8300, 8301}
    assert smoke.verdict({8100: {"127.0.0.1"}, 8300: {"127.0.0.1"}, 8301: {"127.0.0.1"}}, ports) == ""
    assert smoke.verdict({8100: {"127.0.0.1"}, 8300: {"127.0.0.1"}}, ports) == "not listening yet on [8301]"
    assert "0.0.0.0" in smoke.verdict({8100: {"0.0.0.0"}, 8300: {"127.0.0.1"}, 8301: {"127.0.0.1"}}, ports)
    assert "::" in smoke.verdict({8100: {"127.0.0.1", "::"}, 8300: {"127.0.0.1"}, 8301: {"127.0.0.1"}}, ports), "a port that listens on the loopback and elsewhere too is refused"
    assert smoke.verdict({9000: {"0.0.0.0"}, 8100: {"127.0.0.1"}, 8300: {"127.0.0.1"}, 8301: {"127.0.0.1"}}, ports) == "", "a socket of the program on a port that is not one of the three is not this check's"


class Child:
    pid = 4242

    def __init__(self, ends_with: int | None = None) -> None:
        self.ends_with = ends_with
        self.returncode = ends_with

    def poll(self) -> int | None:
        return self.ends_with


def tables(*rows: str) -> Callable[[], str]:
    """A reader of the table that gives each of `rows` in turn, the last one for ever."""
    remaining = list(rows)
    return lambda: remaining.pop(0) if len(remaining) > 1 else remaining[0]


def line(address: str, port: int) -> str:
    return f"  TCP    {address}:{port}         0.0.0.0:0              LISTENING       4242\n"


def test_the_watch_waits_for_the_three_ports_and_gives_the_verdict_on_them(smoke: types.ModuleType) -> None:
    ports = {8100, 8300, 8301}
    up = "".join(line("127.0.0.1", p) for p in sorted(ports))
    problem, found = smoke.watch(Child(), ports, tables("", line("127.0.0.1", 8100), up), wait_sec=5.0, pause_sec=0.0)
    assert problem == "" and set(found) == ports
    wide = line("0.0.0.0", 8100) + line("127.0.0.1", 8300) + line("127.0.0.1", 8301)
    problem, _ = smoke.watch(Child(), ports, tables(wide), wait_sec=5.0, pause_sec=0.0)
    assert "not 127.0.0.1" in problem and "0.0.0.0" in problem, "said at once, without waiting out the time"


def test_the_watch_gives_up_when_the_program_ends_or_the_time_is_over(smoke: types.ModuleType) -> None:
    ports = {8100, 8300, 8301}
    problem, _ = smoke.watch(Child(ends_with=3), ports, tables(""), wait_sec=5.0, pause_sec=0.0)
    assert problem == "the program ended with 3"
    problem, found = smoke.watch(Child(), ports, tables(line("127.0.0.1", 8100)), wait_sec=0.05, pause_sec=0.01)
    assert problem == "not listening yet on [8300, 8301]" and set(found) == {8100}


def test_the_smoke_test_is_a_script_that_says_what_it_is_and_the_free_ports_are_a_set_of_four(smoke: types.ModuleType) -> None:
    done = subprocess.run([sys.executable, str(ROOT / "packaging" / "windows" / "smoke_mercury.py"), "--help"], check=False, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "127.0.0.1" in done.stdout and "netstat" in done.stdout
    broadcast, control, data, ui = smoke.free_ports()
    assert control == broadcast + 200 and data == control + 1 and ui == broadcast + mercury.UI_OFFSET, "the UI interface's port is the daemon's own (neoaprs/mercury.py)"
    assert subprocess.run([sys.executable, str(ROOT / "packaging" / "windows" / "smoke_mercury.py"), "nothing-here.exe"], check=False, capture_output=True, text=True, timeout=60).returncode == 1
