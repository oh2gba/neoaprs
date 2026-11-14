"""The build of the bundled Mercury for Linux (scripts/build-mercury and packaging/mercury/pulse_stub.c) as far as it can be held without a compiler or the network: the script takes its pins from neoaprs/mercury.py and has
none of its own, the stub is a whole `ffpulse` with designated initialisers, the tarball is named for the version and the machine, and the usage prints. The build itself is tried by hand and by the mercury job of the
release workflow, which checks the program it makes."""
import importlib.machinery
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from neoaprs import mercury
from tests.conftest import ROOT

SCRIPT = ROOT / "scripts" / "build-mercury"
STUB = ROOT / "packaging" / "mercury" / "pulse_stub.c"
MEMBERS = ("init", "uninit", "dev_alloc", "dev_free", "dev_error", "dev_next", "dev_info", "alloc", "free", "error", "open", "start", "stop", "clear", "write", "drain", "read", "signal")       # ffaudio_interface, audio.h


@pytest.fixture(scope="module")
def build() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("build_mercury", str(SCRIPT))
    spec = importlib.util.spec_from_loader("build_mercury", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_script_has_the_pins_of_the_program_and_none_of_its_own() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"neoaprs" / "mercury.py"' in text, "the pins are read out of the daemon's module as text (the container's Python 3.10 cannot import it)"
    assert "SOURCE_URL" in text and "SOURCE_SHA256" in text and "SOURCE_COMMIT" in text and "VERSION" in text
    assert "https://" not in text.replace("https://github.com/oh2gba/neoaprs", "")
    assert not re.search(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{64}\b", text)
    assert not re.search(r"\b\d+\.\d+\.\d+\b", text.replace("127.0.0.1", "").replace("0.0.0", ""))           # no version of Mercury either (the loopback address the ports are checked on is not one)


def test_the_script_takes_the_values_it_builds_from_the_pins(build: ModuleType) -> None:
    assert build.VERSION == mercury.VERSION
    assert build.SOURCE_URL == mercury.SOURCE_URL
    assert build.SOURCE_SHA256 == mercury.SOURCE_SHA256
    assert build.SOURCE_COMMIT == mercury.SOURCE_COMMIT


def test_the_stub_is_a_whole_ffpulse_with_designated_initialisers() -> None:
    text = STUB.read_text(encoding="utf-8")
    assert re.search(r"const\s+ffaudio_interface\s+ffpulse\s*=\s*\{", text)
    body = text[text.index("ffpulse"):]
    for member in MEMBERS:
        assert re.search(rf"^\s*\.{member}\s*=", body, re.MULTILINE), member
    assert not re.search(r"ffpulse\s*=\s*\{\s*[a-z_]", text)            # no positional initialiser
    init = re.search(r"static int stub_init\(.*?\n\}", text, re.DOTALL)
    assert init is not None
    assert "PulseAudio is not in this build of Mercury (NeoAPRS uses ALSA)" in text
    assert "conf->error" in init.group(0) and "FFAUDIO_ERROR" in init.group(0)


def test_the_tarball_is_named_for_the_version_and_the_machine(build: ModuleType) -> None:
    assert build.tarball_name("x86_64", "linux") == "mercury-1.9.24-linux-x86_64.tar.gz"
    assert build.tarball_name("aarch64", "linux") == "mercury-1.9.24-linux-aarch64.tar.gz"
    assert build.tarball_name("amd64", "linux") == "mercury-1.9.24-linux-x86_64.tar.gz"
    assert build.tarball_name("arm64", "linux") == "mercury-1.9.24-linux-aarch64.tar.gz"


def test_the_usage_prints() -> None:
    done = subprocess.run([sys.executable, str(SCRIPT), "--help"], check=False, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0
    assert "usage: build-mercury" in done.stdout
    for option in ("--out", "--tar", "--install", "--source"):
        assert option in done.stdout


def test_the_link_check_refuses_what_the_bundle_does_not_carry(build: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ldd = "\tlinux-vdso.so.1 (0x1)\n\tlibasound.so.2 => {lib} (0x2)\n\tlibm.so.6 => /lib/libm.so.6 (0x3)\n\tlibc.so.6 => /lib/libc.so.6 (0x4)\n\t/lib64/ld-linux-x86-64.so.2 (0x5)\n"
    lib = tmp_path / "lib" / "libasound.so.2"
    lib.parent.mkdir()
    lib.write_bytes(b"")
    folder = tmp_path
    monkeypatch.setattr(build, "run", lambda command: ldd.format(lib=lib))
    assert "libasound.so.2" in build.check_links(folder / "mercury", folder)
    for extra in ("libpulse.so.0 => /usr/lib/libpulse.so.0 (0x6)", "libhamlib.so.4 => /usr/lib/libhamlib.so.4 (0x6)", "libssl.so.3 => /usr/lib/libssl.so.3 (0x6)", "libfoo.so.1 => not found"):
        monkeypatch.setattr(build, "run", lambda command, extra=extra: ldd.format(lib=lib) + f"\t{extra}\n")
        with pytest.raises(build.BuildError):
            build.check_links(folder / "mercury", folder)
    monkeypatch.setattr(build, "run", lambda command: ldd.format(lib="/usr/lib/libasound.so.2"))            # the system's copy, not the folder's
    with pytest.raises(build.BuildError):
        build.check_links(folder / "mercury", folder)
