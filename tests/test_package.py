"""The package as a user gets it: `uv build` makes an sdist and, from it, a wheel; the wheel holds the code, the built page with its map glyphs and symbol sheets, the placeholder and the unit template and none
of the repository's other files; installed into a fresh virtual environment it gives the `neoaprs` command, which reports the version and runs `doctor`, and its daemon serves the page that it carries.

It needs `uv` and, the first time, the network for the build backend and the three dependencies (afterwards uv's cache is enough); without either the tests skip and say so."""
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.cli.daemonstate import LOG_NAME, page_url
from neoaprs.updateasset import wheel_version
from tests.conftest import ROOT
from tests.support.proc import NEW_GROUP, stop

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed: the wheel is not built")
WHEEL_VERSION = wheel_version(VERSION)            # the build writes 0.10.0rc1 for 0.10.0-rc1
NEEDS_NETWORK = ("error sending request", "failed to fetch", "dns error", "connection refused", "network", "timed out", "tcp connect error", "unable to connect", "name resolution")


REAL_ENV = dict(os.environ)             # as it was when the tests were collected: before the guards pointed HOME and the caches at an empty folder, so that uv finds the cache of the person who runs the tests


def uv_env() -> dict[str, str]:
    """The environment of a uv run: the person's own, with their uv cache, no other Python fetched, nothing of the venv the tests run in."""
    env = {k: v for k, v in REAL_ENV.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env.update({"UV_PYTHON_DOWNLOADS": "never", "UV_NO_PROGRESS": "1"})
    return env


def uv(*args: str, env: dict[str, str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["uv", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if done.returncode != 0 and any(word in done.stderr.lower() for word in NEEDS_NETWORK):
        pytest.skip(f"uv needs the network once to fetch the build backend and the dependencies: {done.stderr.strip().splitlines()[-1][:200]}")
    assert done.returncode == 0, f"uv {' '.join(args)}: {done.stdout[-1500:]}{done.stderr[-1500:]}"
    return done


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """`uv build`: the sdist and the wheel made from it, in a folder of their own."""
    out = tmp_path_factory.mktemp("dist")
    uv("build", "--out-dir", str(out), env=uv_env())
    wheels, sdists = sorted(out.glob("*.whl")), sorted(out.glob("*.tar.gz"))
    assert len(wheels) == 1 and len(sdists) == 1, list(out.iterdir())
    return {"wheel": wheels[0], "sdist": sdists[0]}


@pytest.fixture(scope="module")
def installed(built: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A fresh virtual environment with the wheel installed (and its three dependencies): the folder of the environment."""
    venv = tmp_path_factory.mktemp("venv") / "env"
    env = uv_env()
    uv("venv", str(venv), "--python", sys.executable, env=env)
    uv("pip", "install", "--python", program(venv, "python"), str(built["wheel"]), env=env)
    return venv


def program(venv: Path, name: str) -> str:
    return str(venv / ("Scripts" if sys.platform == "win32" else "bin") / (name + (".exe" if sys.platform == "win32" else "")))


def clean_env(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG")}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def test_the_wheel_holds_the_package_the_page_and_the_unit_and_nothing_of_the_repository(built: dict[str, Path]) -> None:
    names = zipfile.ZipFile(built["wheel"]).namelist()
    assert built["wheel"].name == f"neoaprs-{WHEEL_VERSION}-py3-none-any.whl"
    for needed in ("neoaprs/__init__.py", "neoaprs/__main__.py", "neoaprs/daemon.py", "neoaprs/cli/__init__.py", "neoaprs/cli/neoaprs.service", "neoaprs/desktop/cmd.py", "neoaprs/desktop/icon.png", "neoaprs/desktop/icon.ico", "neoaprs/samples/thd7.kiss", "neoaprs/web/server.py", "neoaprs/web/placeholder/index.html",
                   "neoaprs/page/index.html", "neoaprs/page/symbols/primary.png", "neoaprs/page/symbols/alternate.png", "neoaprs/page/symbols/overlay.png", "neoaprs/page/symbols/SOURCE.txt", "neoaprs/page/symbols/COPYRIGHT.txt",
                   "neoaprs/maps/basemap-world.pmtiles", "neoaprs/maps/basemap-world.json", "neoaprs/page/fonts/NotoSans-Regular/0-255.pbf", "neoaprs/page/fonts/NotoSans-Medium/0-255.pbf", "neoaprs/page/fonts/OFL.txt", f"neoaprs-{WHEEL_VERSION}.dist-info/licenses/LICENSE"):
        assert needed in names, f"{needed} is not in the wheel"
    assets = [n for n in names if n.startswith("neoaprs/page/assets/")]
    assert any(n.endswith(".js") for n in assets) and any(n.endswith(".css") for n in assets) and any("maplibre-gl-worker" in n for n in assets)
    assert not [n for n in names if n.split("/")[0] not in ("neoaprs", f"neoaprs-{WHEEL_VERSION}.dist-info")], "only the package and its metadata"
    assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".sqlite", ".map")) or (n.endswith(".pmtiles") and n != "neoaprs/maps/basemap-world.pmtiles") or "/tests/" in n or "node_modules" in n]
    html = zipfile.ZipFile(built["wheel"]).read("neoaprs/page/index.html").decode()
    assert "./assets/" in html
    entry = zipfile.ZipFile(built["wheel"]).read(f"neoaprs-{WHEEL_VERSION}.dist-info/entry_points.txt").decode()
    assert "[console_scripts]\nneoaprs = neoaprs.cli:main" in entry and "[gui_scripts]\nneoaprs-app = neoaprs.desktop.cmd:gui_main\nneoaprsw = neoaprs.cli:gui_main" in entry
    metadata = zipfile.ZipFile(built["wheel"]).read(f"neoaprs-{WHEEL_VERSION}.dist-info/METADATA").decode()
    assert f"Version: {VERSION}\n" in metadata and "Requires-Dist: tornado==" in metadata and "Requires-Python: >=3.13" in metadata and "License-Expression: GPL-3.0-or-later" in metadata
    assert "Provides-Extra: app" in metadata and "pywebview==" in metadata and "pyside6-webengine==" in metadata.lower(), "the desktop app is an extra"
    assert not [line for line in metadata.splitlines() if line.startswith("Requires-Dist:") and "extra ==" not in line and any(n in line.lower() for n in ("pywebview", "pyside6", "pystray", "pillow"))], "the daemon's install stays lean: none of the toolkits is a dependency without the extra"


def test_the_sdist_is_named_by_the_version_the_wheel_is_named_by(built: dict[str, Path]) -> None:
    assert built["sdist"].name == f"neoaprs-{WHEEL_VERSION}.tar.gz"


def test_the_sdist_is_the_package_and_the_licence(built: dict[str, Path]) -> None:
    with tarfile.open(built["sdist"]) as sdist:
        names = [n.split("/", 1)[1] for n in sdist.getnames() if "/" in n]
    assert "pyproject.toml" in names and "LICENSE" in names and "neoaprs/page/index.html" in names and "neoaprs/cli/neoaprs.service" in names
    assert not [n for n in names if n.startswith(("tests/", "ui/", "scripts/", "docs/", "data/"))]


def test_the_installed_command_reports_its_version_and_runs_the_doctor(installed: Path, built: dict[str, Path], tmp_path: Path) -> None:
    env = clean_env(tmp_path)
    version = subprocess.run([program(installed, "neoaprs"), "--version"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert version.returncode == 0 and version.stdout.strip() == f"NeoAPRS {VERSION}", version.stderr
    data = tmp_path / "data"
    data.mkdir()
    doctor = subprocess.run([program(installed, "neoaprs"), "doctor", "--data", str(data)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert doctor.stdout.startswith(f"NeoAPRS {VERSION} on ") and "ok    Python 3." in doctor.stdout and f"data folder {data} (writable)" in doctor.stdout
    assert str(installed) in doctor.stdout, "it is the installed Python that reports"
    assert Path(program(installed, "neoaprsw")).exists(), "the script for Windows's start at login is made on every system"
    module = subprocess.run([program(installed, "python"), "-m", "neoaprs", "--version"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert module.stdout.strip() == f"NeoAPRS {VERSION}"


def test_the_installed_replay_plays_the_sample_that_is_in_the_package(installed: Path, tmp_path: Path) -> None:
    proc = subprocess.Popen([program(installed, "neoaprs"), "replay"], cwd=tmp_path, env=clean_env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().startswith("socket://127.0.0.1:"), "it listens: the sample was found in the package"
    finally:
        stop(proc)
        proc.communicate(timeout=30)


def test_the_installed_package_finds_its_page_and_unit_template_and_its_daemon_serves_the_page(installed: Path, tmp_path: Path) -> None:
    env = clean_env(tmp_path)
    where = subprocess.run([program(installed, "python"), "-c", "from neoaprs.web.server import default_page_dir; from importlib import resources; print(default_page_dir()); print(resources.files('neoaprs.cli').joinpath('neoaprs.service').is_file())"],
                           cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    page_dir, unit = where.stdout.split("\n")[:2]
    assert Path(page_dir) == installed / ("Lib" if sys.platform == "win32" else "lib") / ("site-packages" if sys.platform == "win32" else f"python{sys.version_info.major}.{sys.version_info.minor}/site-packages") / "neoaprs" / "page"
    assert (Path(page_dir) / "index.html").is_file() and unit == "True"
    data = tmp_path / "data"
    daemon = subprocess.Popen([program(installed, "neoaprs"), "run", "--data", str(data), "--web-port", "0"], cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NEW_GROUP)
    try:
        url = None
        deadline = time.monotonic() + 60
        while url is None and time.monotonic() < deadline and daemon.poll() is None:
            time.sleep(0.2)
            url = page_url(data)
        assert url, (data / LOG_NAME).read_text(encoding="utf-8") if (data / LOG_NAME).exists() else "no log"
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode()
        assert response.status == 200 and '<div id="app">' in body
        asset = next(part for part in body.split('"') if part.startswith("./assets/") and part.endswith(".js"))
        with urllib.request.urlopen(url + asset[2:], timeout=10) as response:
            assert response.status == 200 and len(response.read()) > 10_000
        with urllib.request.urlopen(url + "symbols/primary.png", timeout=10) as response:
            assert response.status == 200
    finally:
        stop(daemon)
        out, err = daemon.communicate(timeout=30)
    assert daemon.returncode == 0, err
