"""The Debian package (scripts/build-deb, packaging/deb/): the pieces of it are read as files, and the maintainer scripts and the command are run with a fake systemctl. The package itself is built, installed with apt and
run against a fake TNC by the release workflow's job `deb`."""
import os
import re
import subprocess
from pathlib import Path

import pytest

from neoaprs.cli.installkind import DEB_PREFIX
from tests.conftest import ROOT
from tests.support.ptyline import posix_only

pytestmark = posix_only
DEB = ROOT / "packaging" / "deb"
SCRIPT = (ROOT / "scripts" / "build-deb").read_text(encoding="utf-8")


def test_each_architecture_has_a_python_pinned_by_version_and_digest() -> None:
    pins = {m[0]: (m[1], m[2]) for m in re.findall(r'^PYTHON_(amd64|arm64)="(\S+) ([0-9a-f]{64}) \S+"', SCRIPT, re.M)}
    assert set(pins) == {"amd64", "arm64"} and pins["amd64"][1] != pins["arm64"][1]
    assert "x86_64-unknown-linux-gnu" in pins["amd64"][0] and "aarch64-unknown-linux-gnu" in pins["arm64"][0]
    assert re.search(r'^PYTHON_RELEASE="https://github\.com/[^"]*/download/\d+"$', SCRIPT, re.M), "a fixed release of python-build-standalone"
    appimage = (ROOT / "scripts" / "build-appimage").read_text(encoding="utf-8")
    assert pins["amd64"][0] in appimage and pins["amd64"][1] in appimage, "the CPython of the amd64 package is the AppImage's"


def test_the_package_goes_where_the_install_kind_looks() -> None:
    assert re.search(rf'^PREFIX={re.escape(DEB_PREFIX)}$', SCRIPT, re.M)
    assert 'ln -s "$PREFIX/bin/neoaprs" "$pkg/usr/bin/neoaprs"' in SCRIPT


def test_the_name_of_the_file_is_the_one_the_update_panel_links() -> None:
    assert 'target="$out/neoaprs_${deb_version}_$arch.deb"' in SCRIPT
    assert "`neoaprs_${version}_${arch}.deb`" in (ROOT / "ui" / "src" / "lib" / "update.ts").read_text(encoding="utf-8")


def test_the_control_file_has_every_field_the_build_fills_in() -> None:
    control = (DEB / "control.in").read_text(encoding="utf-8")
    fields = dict(re.findall(r"^([A-Z][\w-]+): (.*)$", control, re.M))
    assert {"Package", "Version", "Architecture", "Maintainer", "Installed-Size", "Depends", "Section", "Priority", "Homepage", "Description"} <= set(fields)
    assert fields["Package"] == "neoaprs" and fields["Depends"].startswith("libc6 (>= @GLIBC@)")
    for placeholder in set(re.findall(r"@([A-Z_]+)@", control)):
        assert f's|@{placeholder}@|' in SCRIPT, f"the build does not fill in @{placeholder}@"
    assert control.endswith("\n") and not any(line.rstrip() != line for line in control.splitlines())


@pytest.mark.parametrize("name", ["postinst", "postrm", "neoaprs"])
def test_the_scripts_are_posix_sh_that_parses_and_the_files_are_executable(name: str) -> None:
    path = DEB / name
    assert os.access(path, os.X_OK) and path.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    subprocess.run(["sh", "-n", str(path)], check=True)


def test_the_copyright_file_names_the_licence() -> None:
    text = (DEB / "copyright").read_text(encoding="utf-8")
    assert "License: GPL-3.0-or-later" in text and "/usr/share/common-licenses/GPL-3" in text
    assert text.startswith("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/")


def test_the_command_runs_the_python_beside_it_isolated(tmp_path: Path) -> None:
    folder = tmp_path / "opt" / "bin"
    folder.mkdir(parents=True)
    (folder / "neoaprs").write_bytes((DEB / "neoaprs").read_bytes())
    (folder / "neoaprs").chmod(0o755)
    fake = folder / "python3"
    fake.write_text('#!/bin/sh\nprintf "%s|" "$@"\n', encoding="utf-8")
    fake.chmod(0o755)
    link = tmp_path / "usr-bin-neoaprs"
    link.symlink_to(folder / "neoaprs")
    out = subprocess.run([str(link), "service", "install", "--data", "a b"], capture_output=True, text=True, check=True).stdout
    assert out == "-I|-m|neoaprs|service|install|--data|a b|", "the link finds the Python beside the command, not beside the link"


def run_postinst(tmp_path: Path, *args: str) -> str:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir(exist_ok=True)
    (fakebin / "systemctl").write_text(f'#!/bin/sh\necho "systemctl $*" >> {tmp_path}/calls\n', encoding="utf-8")
    (fakebin / "systemctl").chmod(0o755)
    env = {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"}
    return subprocess.run(["sh", str(DEB / "postinst"), *args], capture_output=True, text=True, check=True, env=env).stdout


def test_a_fresh_install_says_what_comes_next_and_restarts_nothing(tmp_path: Path) -> None:
    out = run_postinst(tmp_path, "configure")
    assert "neoaprs service install --linger" in out and "dialout" in out and "neoaprs doctor" in out
    assert not (tmp_path / "calls").exists()


def test_an_upgrade_by_an_ordinary_user_or_on_another_root_asks_no_systemd_and_says_how_to_restart(tmp_path: Path) -> None:
    out = run_postinst(tmp_path, "configure", "0.3.0")
    assert "systemctl --user restart neoaprs" in out and "dialout" not in out
    assert not (tmp_path / "calls").exists(), "only root, on the machine's own root, asks the user managers"


def test_the_other_steps_of_dpkg_do_nothing(tmp_path: Path) -> None:
    for step in ("abort-upgrade", "abort-remove", "triggered"):
        assert run_postinst(tmp_path, step, "0.3.0") == ""


def test_removal_takes_the_folder_and_leaves_the_data_and_says_so(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "opt" / "neoaprs" / "lib" / "__pycache__").mkdir(parents=True)
    (root / "opt" / "neoaprs" / "lib" / "__pycache__" / "x.pyc").write_bytes(b"")
    env = {**os.environ, "DPKG_ROOT": str(root)}
    kept = subprocess.run(["sh", str(DEB / "postrm"), "upgrade", "0.4.0"], capture_output=True, text=True, check=True, env=env)
    assert kept.stdout == "" and (root / "opt" / "neoaprs").exists(), "an upgrade removes nothing"
    gone = subprocess.run(["sh", str(DEB / "postrm"), "remove"], capture_output=True, text=True, check=True, env=env).stdout
    assert not (root / "opt" / "neoaprs").exists()
    assert "~/.local/share/neoaprs is left" in gone and "systemctl --user disable --now neoaprs" in gone
