"""The build of the bundled Direwolf (scripts/build-direwolf, packaging/direwolf/, scripts/buildtool.py) as far as it can be held without a compiler or the network: the script takes its pins from neoaprs/direwolf.py
and has none of its own, the tarballs are named for the version and the machine, the configure line leaves out what NeoAPRS does not use, the four patches are there in their order, the link check refuses what the
folder does not carry, the banner check wants the pinned release with cm108-ptt alone, the Windows check reads the import table and the banner's bytes, and the usage prints. With the pinned archive in the build
cache the patches are applied to it and each is held in the source after it. The build itself is the release workflow's direwolf and direwolf-windows jobs', which run the checks on the program they make."""
import importlib.machinery
import importlib.util
import io
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

from neoaprs import direwolf
from tests.conftest import ROOT
from tests.test_mercury_windows import make_pe

SCRIPT = ROOT / "scripts" / "build-direwolf"
PACKAGING = ROOT / "packaging" / "direwolf"


@pytest.fixture(scope="module")
def build() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("build_direwolf", str(SCRIPT))
    spec = importlib.util.spec_from_loader("build_direwolf", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_script_has_the_pins_of_the_program_and_none_of_its_own() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"neoaprs" / "direwolf.py"' in text, "the pins are read out of the daemon's module as text (the container's Python 3.10 cannot import it)"
    assert "https://" not in text and not re.search(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b", text)
    assert not re.search(r"\b\d+\.\d+\.\d+\b", text.replace("127.0.0.1", "")), "no version of Direwolf either"


def test_the_script_takes_the_values_it_builds_from_the_pins_and_builds_nothing_while_the_sha256_is_not_pinned(build: ModuleType, tmp_path: Path) -> None:
    assert (build.VERSION, build.SOURCE_COMMIT, build.SOURCE_URL, build.SOURCE_SHA256, build.BANNER) == (direwolf.VERSION, direwolf.SOURCE_COMMIT, direwolf.SOURCE_URL, direwolf.SOURCE_SHA256, direwolf.BANNER)
    with pytest.raises(build.BuildError, match="not pinned" if not direwolf.SOURCE_SHA256 else "could not be fetched|is not the file"):
        build.buildtool.fetch_source((tmp_path / "none.tar.gz").as_uri(), direwolf.SOURCE_SHA256 or "", "none.tar.gz", "test")     # (a file that is not there: nothing outside this machine is asked)


def source_archive(tmp_path: Path, link: str) -> Path:
    """An archive shaped like Direwolf's: one folder with CMakeLists.txt, CHANGES.md and a symbolic link debian/changelog to LINK."""
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in ("top/CMakeLists.txt", "top/CHANGES.md"):
            info = tarfile.TarInfo(name)
            info.size = 3
            tar.addfile(info, io.BytesIO(b"abc"))
        info = tarfile.TarInfo("top/debian/changelog")
        info.type, info.linkname = tarfile.SYMTYPE, link
        tar.addfile(info)
    return archive


def test_a_relative_link_inside_the_source_is_unpacked_where_an_old_python_refuses_it_and_one_that_leaves_the_tree_is_refused(build: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def old_python(member: tarfile.TarInfo, dest: str) -> tarfile.TarInfo:          # (Python 3.10, the build container's: a link is resolved from the destination, not from its own folder)
        if member.issym():
            raise tarfile.LinkOutsideDestinationError(member, dest)
        return real(member, dest)

    real = tarfile.data_filter
    monkeypatch.setattr(tarfile, "data_filter", old_python)
    tree = build.buildtool.unpack(source_archive(tmp_path, "../CHANGES.md"), tmp_path / "work", "CMakeLists.txt", "Direwolf")       # (Direwolf's own debian/changelog: the build of 15 November 2026 stopped here)
    assert (tree / "CMakeLists.txt").read_bytes() == b"abc"
    if sys.platform != "win32":                                                      # (a symbolic link needs a right on Windows that a test does not have)
        assert (tree / "debian" / "changelog").read_bytes() == b"abc"
    for leaving in ("../../../outside", "/etc/passwd", "../../../etc/passwd"):
        with pytest.raises(tarfile.LinkOutsideDestinationError):
            build.buildtool.unpack(source_archive(tmp_path, leaving), tmp_path / "work", "CMakeLists.txt", "Direwolf")


def test_the_tarballs_are_named_for_the_version_and_the_machine(build: ModuleType) -> None:
    assert build.tarball_name("x86_64", "linux") == f"direwolf-{direwolf.VERSION}-linux-x86_64.tar.gz"
    assert build.tarball_name("arm64", "linux") == f"direwolf-{direwolf.VERSION}-linux-aarch64.tar.gz"
    assert build.tarball_name("aarch64", "win32") == f"direwolf-{direwolf.VERSION}-windows-x86_64.tar.gz"


def test_the_configure_leaves_out_what_neoaprs_does_not_use_and_the_windows_build_is_static_with_the_toolchain_file(build: ModuleType, tmp_path: Path) -> None:
    (configure, make) = build.commands(tmp_path)
    for flag in ("-DOPTIONAL_DNSSD=OFF", "-DUNITTEST=OFF", "-DCMAKE_DISABLE_FIND_PACKAGE_GPSD=ON", "-DCMAKE_DISABLE_FIND_PACKAGE_hamlib=ON", "-DCMAKE_DISABLE_FIND_PACKAGE_gpiod=ON", "-DCMAKE_BUILD_TYPE=Release"):
        assert flag in configure
    assert "-DCMAKE_EXE_LINKER_FLAGS=-Wl,--enable-new-dtags -Wl,-rpath,$ORIGIN/lib" in configure and make[-4:] == ["direwolf", "gen_packets", "atest", "cm108"]
    (configure, make) = build.commands(tmp_path, windows=True)
    assert f"-DCMAKE_TOOLCHAIN_FILE={PACKAGING / 'mingw-w64.cmake'}" in configure and "-DCMAKE_EXE_LINKER_FLAGS=-static -s" in configure and make[-1] == "direwolf"
    toolchain = (PACKAGING / "mingw-w64.cmake").read_text(encoding="utf-8")
    for line in ("set(CMAKE_SYSTEM_NAME Windows)", "set(CMAKE_C_COMPILER x86_64-w64-mingw32-gcc)", "set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++)", "set(CMAKE_RC_COMPILER x86_64-w64-mingw32-windres)",
                 "set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32)"):
        assert line in toolchain


def test_the_four_patches_are_there_in_their_order_and_say_what_they_change(build: ModuleType) -> None:
    assert build.PATCHES == ("loopback.patch", "flush.patch", "quit.patch", "txlevel.patch")
    texts = {name: (PACKAGING / name).read_text(encoding="utf-8") for name in build.PATCHES}
    assert {line[6:] for line in texts["loopback.patch"].splitlines() if line.startswith("+++ b/")} == set(build.LISTENER_FILES)
    added = [line for line in texts["loopback.patch"].splitlines() if line.startswith("+") and not line.startswith("+++")]
    assert len(added) == 6 and all("INADDR_LOOPBACK" in line or 'getaddrinfo("127.0.0.1"' in line for line in added)
    assert "+\tfflush (stdout);" in texts["flush.patch"]
    assert '"hP:B:gjJD:U:c:px:r:b:n:d:q:t:ul:L:Sa:E:T:e:X:AI:i:Q"' in texts["quit.patch"] and "cleanup_linux (0);" in texts["quit.patch"] and "cleanup_win (CTRL_C_EVENT);" in texts["quit.patch"]
    assert '"hP:B:gjJD:U:c:px:r:b:n:d:q:t:ul:L:Sa:E:T:e:X:AI:i:QG:"' in texts["txlevel.patch"] and "+static int audio_amplitude = 100;" in texts["txlevel.patch"]


def test_the_link_check_refuses_what_the_folder_does_not_carry(build: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    for name in build.OWN_LIBS:
        (tmp_path / "lib" / name).write_bytes(b"")
    ldd = ("\tlinux-vdso.so.1 (0x1)\n\tlibasound.so.2 => {asound} (0x2)\n\tlibudev.so.1 => {udev} (0x3)\n\tlibm.so.6 => /lib/libm.so.6 (0x4)\n\tlibc.so.6 => /lib/libc.so.6 (0x5)\n"
           "\t/lib64/ld-linux-x86-64.so.2 (0x6)\n")
    good = ldd.format(asound=tmp_path / "lib" / "libasound.so.2", udev=tmp_path / "lib" / "libudev.so.1")
    check = build.buildtool.check_links
    assert "libudev.so.1" in check(tmp_path / "direwolf", tmp_path, build.NEEDED_OK, build.NEEDED_NEVER, build.OWN_LIBS, lambda command: good)
    mvec = good + "\tlibmvec.so.1 => /lib/x86_64-linux-gnu/libmvec.so.1 (0x8)\n"            # (glibc's own, on x86-64: the first real build linked it)
    assert "libmvec.so.1" in check(tmp_path / "direwolf", tmp_path, build.NEEDED_OK, build.NEEDED_NEVER, build.OWN_LIBS, lambda command: mvec)
    for extra in ("libgps.so.28 => /usr/lib/libgps.so.28 (0x7)", "libhamlib.so.4 => /usr/lib/libhamlib.so.4 (0x7)", "libgpiod.so.2 => /usr/lib/libgpiod.so.2 (0x7)", "libavahi-client.so.3 => /usr/lib/x (0x7)",
                  "libfoo.so.1 => not found"):
        with pytest.raises(build.BuildError):
            check(tmp_path / "direwolf", tmp_path, build.NEEDED_OK, build.NEEDED_NEVER, build.OWN_LIBS, lambda command, extra=extra: good + f"\t{extra}\n")
    with pytest.raises(build.BuildError, match="libudev.so.1 is not taken from"):
        check(tmp_path / "direwolf", tmp_path, build.NEEDED_OK, build.NEEDED_NEVER, build.OWN_LIBS, lambda command: ldd.format(asound=tmp_path / "lib" / "libasound.so.2", udev="/usr/lib/libudev.so.1"))


def test_the_banner_must_say_the_pinned_release_with_cm108_ptt_alone(build: ModuleType) -> None:
    banner = f"Dire Wolf Release {direwolf.VERSION}, November 2025\nIncludes optional support for:  cm108-ptt\n"
    assert build.check_banner(banner) == f"Dire Wolf Release {direwolf.VERSION}, November 2025, optional: cm108-ptt"
    for wrong in (banner.replace(direwolf.VERSION, "1.8.0"), banner.replace(" cm108-ptt", " hamlib cm108-ptt"), banner.replace(" cm108-ptt", " cm108-ptt dns-sd"), banner.replace(" cm108-ptt", " gpsd"),
                  banner.splitlines()[0]):
        with pytest.raises(build.BuildError):
            build.check_banner(wrong)


def test_the_windows_program_names_windows_dlls_alone_and_holds_the_banner_bytes(build: ModuleType, tmp_path: Path) -> None:
    program = tmp_path / "direwolf.exe"
    ok = ["KERNEL32.dll", "msvcrt.dll", "WINMM.dll", "WS2_32.dll", "SETUPAPI.dll", "ADVAPI32.dll", "USER32.dll"]
    program.write_bytes(make_pe(ok, version=False) + direwolf.BANNER.encode("ascii") + b"\0")
    assert build.check_windows(tmp_path) == "imports: " + ", ".join(sorted(ok, key=str.lower))
    for foreign in ("libwinpthread-1.dll", "DSOUND.dll", "libgcc_s_seh-1.dll"):
        program.write_bytes(make_pe([*ok, foreign], version=False) + direwolf.BANNER.encode("ascii"))
        with pytest.raises(build.BuildError):
            build.check_windows(tmp_path)
    program.write_bytes(make_pe(ok, version=False))
    with pytest.raises(build.BuildError, match="banner"):
        build.check_windows(tmp_path)


def test_the_usage_prints() -> None:
    done = subprocess.run([sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "usage: build-direwolf" in done.stdout
    for option in ("--windows", "--out", "--tar", "--install", "--source"):
        assert option in done.stdout


def test_the_patches_apply_to_the_pinned_source_and_each_is_held_in_it_after(build: ModuleType, tmp_path: Path) -> None:
    archive = build.buildtool.cache_dir() / f"direwolf-{direwolf.VERSION}-{direwolf.SOURCE_COMMIT[:8]}.tar.gz"
    if not direwolf.SOURCE_SHA256 or not archive.is_file() or build.sha256(archive) != direwolf.SOURCE_SHA256 or sys.platform == "win32":
        pytest.skip("the pinned source archive is in the build cache after any build of Direwolf")
    tree = build.buildtool.unpack(archive, tmp_path / "work", "CMakeLists.txt", "Direwolf")
    build.apply_patches(tree)
    assert (tree / "data" / "tocalls.yaml").is_file() and (tree / "data" / "symbols-new.txt").is_file() and (tree / "external" / "geotranz" / "readme.txt").is_file()
    assert "Copyright (c) 1998 Todd C. Miller" in build.notices(tree)


@pytest.mark.parametrize(("script", "tools", "arch"), [("build-deb", "$app/tools", ("--arch", "amd64")), ("build-appimage", "$app/usr/tools", ())])
def test_the_linux_packages_carry_direwolf_without_its_utilities_and_a_build_must_say_whether_it_does(script: str, tools: str, arch: tuple[str, ...], tmp_path: Path) -> None:
    text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert f'tar -xzf "$direwolf" -C "{tools}" --exclude=\'direwolf/dev\'' in text, "the folder where neoaprs/bundled.py looks (<sys.prefix>/tools/direwolf), its dev/ left out"
    assert "lib/libasound.so.2 lib/libudev.so.1 share/alsa/alsa.conf data/tocalls.yaml data/symbols-new.txt LICENSE SOURCE.txt" in text
    mercury = tmp_path / "mercury-1.9.24-linux-x86_64.tar.gz"
    mercury.write_bytes(b"")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(ROOT / "scripts" / script), *arch, "--mercury", str(mercury), *args, "--out", str(tmp_path / "out")], capture_output=True, text=True, timeout=30)

    refused = run()
    assert refused.returncode == 2 and "--direwolf TARBALL" in refused.stderr and "--no-direwolf" in refused.stderr, "a release can never silently lack Direwolf"
    arm = tmp_path / "direwolf-1.8.1-linux-aarch64.tar.gz"
    arm.write_bytes(b"")
    assert run("--direwolf", str(arm)).returncode == 2, "a program of another architecture"
    assert run("--direwolf", str(arm), "--no-direwolf").returncode == 2
    x86 = tmp_path / "direwolf-1.8.1-linux-x86_64.tar.gz"
    x86.write_bytes(b"")
    alone = subprocess.run(["bash", str(ROOT / "scripts" / script), *arch, "--no-mercury", "--direwolf", str(x86), "--out", str(tmp_path / "out")], capture_output=True, text=True, timeout=30)
    assert alone.returncode == 2 and "--direwolf needs --mercury" in alone.stderr, "a package with Direwolf and no Mercury would offer the Sound card type with no list of sound cards"


def _load(name: str, path: Path) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _tarball(path: Path, files: dict[str, bytes]) -> Path:
    import io
    import tarfile
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_the_windows_app_takes_direwolf_with_its_data_and_nothing_that_is_not_the_pinned_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _load("bundle_tool", ROOT / "packaging" / "windows" / "bundle_tool.py")
    tool = bundle.TOOLS["direwolf"]
    monkeypatch.setattr(direwolf, "SOURCE_SHA256", "ab" * 32)
    offer = f"Direwolf {direwolf.VERSION}, WB2OSZ's sound-card modem\nCommit: {direwolf.SOURCE_COMMIT}\nSHA-256 of the source archive: {'ab' * 32}\n".encode()
    files = {"direwolf/direwolf.exe": b"MZ program", "direwolf/SOURCE.txt": offer, "direwolf/LICENSE": b"GPL", "direwolf/LICENSE-hidapi.txt": b"BSD", "direwolf/data/tocalls.yaml": b"tocalls", "direwolf/data/symbols-new.txt": b"symbols"}
    archive = _tarball(tmp_path / bundle.tarball_name(tool), files)
    with pytest.raises(SystemExit, match="is bundled after Mercury"):
        bundle.main(["direwolf", str(tmp_path / "NeoAPRS"), str(archive)])              # (an app folder without Mercury: the Sound card type would have no list of sound cards)
    (tmp_path / "NeoAPRS" / "bin" / "mercury").mkdir(parents=True)
    (tmp_path / "NeoAPRS" / "bin" / "mercury" / "mercury.exe").write_bytes(b"MZ")
    assert bundle.main(["direwolf", str(tmp_path / "NeoAPRS"), str(archive)]) == 0
    folder = tmp_path / "NeoAPRS" / "bin" / "direwolf"
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == ["LICENSE", "LICENSE-hidapi.txt", "SOURCE.txt", "data/symbols-new.txt", "data/tocalls.yaml", "direwolf.exe"]
    for number, (override, message) in enumerate(((("direwolf/data/other.txt", b"x"), "not a file the app takes"), (("direwolf/lib/x.dll", b"MZ"), "not a file the app takes"),
                                                  (("direwolf/direwolf.exe", b"\x7fELF"), "not a program for Windows"), (("direwolf/SOURCE.txt", b"Direwolf 0.0.1,"), "not a Direwolf built from the pinned source"))):
        (tmp_path / str(number)).mkdir()
        bad = _tarball(tmp_path / str(number) / bundle.tarball_name(tool), {**files, override[0]: override[1]})
        with pytest.raises(SystemExit, match=message):
            bundle.unpack(tool, bad, tmp_path / f"out-{number}")
        assert not (tmp_path / f"out-{number}").exists()
    missing = {k: v for k, v in files.items() if k != "direwolf/data/tocalls.yaml"}
    (tmp_path / "m").mkdir()
    with pytest.raises(SystemExit, match="or a data file"):
        bundle.unpack(tool, _tarball(tmp_path / "m" / bundle.tarball_name(tool), missing), tmp_path / "out-m")
    monkeypatch.setattr(direwolf, "SOURCE_SHA256", "")
    with pytest.raises(SystemExit, match="a pinned SHA-256"):
        bundle.unpack(tool, archive, tmp_path / "out-unpinned")


def test_the_windows_smoke_check_wants_the_pinned_release_cm108_ptt_alone_and_neoaprss_options() -> None:
    smoke = _load("smoke_direwolf", ROOT / "packaging" / "windows" / "smoke_direwolf.py")
    said = (f"Dire Wolf Release {direwolf.VERSION}, November 2025\nIncludes optional support for:  cm108-ptt\n\nUsage: direwolf [options] [ - | stdin | UDP:nnnn ]\n"
            "    -Q             Exit cleanly at the end of standard input.\n    -G pct         Transmit level, 1 to 100 percent of full scale.\n")
    assert smoke.check(said) == []
    assert len(smoke.check(said.replace(" cm108-ptt", " hamlib cm108-ptt").replace("-G pct", ""))) == 2
    assert smoke.check(said.replace(direwolf.VERSION, "1.7.0"))
