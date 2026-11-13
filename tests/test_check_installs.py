"""The clean installs in Docker (scripts/check-installs and scripts/install-probe.py) as far as they can be held without docker and without a release: the builds, the containers and what each is given, from a stand-in
for docker (and for uv and the build scripts) that writes down what it was asked; the old release's pin and its checksum; that the .deb check holds what the release workflow's job `deb` holds; and the probe of the
upgrade run for real against this tree's daemon (seed, then verify, then a version that is not the daemon's). The images and the real builds are tried by hand (docs/development.md)."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import ROOT
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (scripts of the repository that run docker and shell: a development check, not the product)

SCRIPT = ROOT / "scripts" / "check-installs"
PATIENCE_SEC = 120.0
DAEMON_PATIENCE_SEC = 300.0
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
OLD_DEB = b"the old release as a file"
OLD_SHA = hashlib.sha256(OLD_DEB).hexdigest()


@pytest.fixture(scope="module")
def installs() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("check_installs", str(SCRIPT))
    spec = importlib.util.spec_from_loader("check_installs", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_installs"] = module
    loader.exec_module(module)
    return module


# ---- what the containers run ----

def deb_job() -> str:
    return RELEASE.split("\n  deb:\n", 1)[1].split("\n  assemble:\n", 1)[0]


SHARED = ('[ "$(readlink -f /usr/bin/neoaprs)" = /opt/neoaprs/bin/neoaprs ]', "[ -f /usr/share/doc/neoaprs/copyright ]", "from neoaprs.cli.installkind import detect_here", 'assert (info.kind, info.arch) == ("deb", sys.argv[1]), info',
          "/opt/neoaprs/bin/python3 -I -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version'", "grep -q 'not found' /tmp/ldd.txt", 'ldd "$bundled/mercury"', 'grep -q "$bundled/lib/libasound.so.2" /tmp/ldd.txt',
          'export ALSA_CONFIG_PATH="$bundled/share/alsa/alsa.conf"', 'echo "$said" | grep -qF', '"$bundled/mercury" -z', '[ "$status" -ge 126 ]', "grep -q 'error while loading' /tmp/z.txt",
          "grep -q 'keeps the old version until it is restarted'", "^ExecStart=/opt/neoaprs/bin/python3 -m neoaprs ")


def test_the_deb_check_holds_what_the_release_workflows_deb_job_holds(installs: ModuleType) -> None:
    job = deb_job()
    for fragment in SHARED:
        assert fragment in installs.DEB, f"the check lacks: {fragment}"
        assert fragment in job, f"the release workflow's job `deb` lacks: {fragment}"


def test_the_two_debian_images_are_the_ones_the_release_workflow_names(installs: ModuleType) -> None:
    assert installs.DEBIAN == "debian:bookworm-slim" and "debian:bookworm-slim" in deb_job()
    assert installs.UBUNTU == "ubuntu:24.04" and "ubuntu-latest" in deb_job() and "FROM ubuntu:24.04" in (ROOT / "packaging" / "ci" / "Dockerfile").read_text(encoding="utf-8")


def test_the_probe_names_what_the_scripts_it_starts_have(installs: ModuleType) -> None:
    for name in installs.PROBE_FILES:
        assert (ROOT / name).is_file(), name
    assert "scripts/smoke-appimage" in installs.APPIMAGE and "/work/probe/scripts/smoke.py" in installs.WHEEL and "install-probe.py seed" in installs.UPGRADE and "install-probe.py verify" in installs.UPGRADE


# ---- the script from end to end, on stand-ins for docker, uv and the builds ----

FAKE_DOCKER = f"""#!{sys.executable}
import json, os, sys
state = os.environ["FAKE_DOCKER"]
args = sys.argv[1:]
if args[0] == "image":
    sys.exit(0)
if args[0] == "run":
    with open(state + "/runs", "a") as runs:
        runs.write(json.dumps(args) + "\\n")
    image = args[args.index("sh") - 1]
    rules = json.load(open(state + "/rules.json"))
    for rule in rules:
        if rule["image"] in image or rule["image"] in args[-1]:
            print(rule["stdout"])
            sys.exit(rule["exit"])
    print("proved")
    sys.exit(0)
sys.exit(0)
"""
FAKE_UV = """#!/bin/sh
echo "uv $*" >> "$FAKE_DOCKER/builds"
[ "$1" = build ] || exit 0
out=""
while [ $# -gt 0 ]; do [ "$1" = --out-dir ] && out="$2"; shift; done
mkdir -p "$out" && echo wheel > "$out/neoaprs-0.0.1-py3-none-any.whl"
"""
FAKE_BUILD = """#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_DOCKER/builds"
[ ! -e "$FAKE_DOCKER/fails-$(basename "$0")" ] || { echo "it broke"; exit 1; }
out=""; prev=""
for arg in "$@"; do [ "$prev" = --out ] && out="$arg"; prev="$arg"; done
mkdir -p "$out"
case "$(basename "$0")" in
    build-mercury) echo tar > "$out/mercury-1.2.3-linux-x86_64.tar.gz" ;;
    build-deb) echo deb > "$out/neoaprs_0.0.1_amd64.deb" ;;
    build-appimage) echo image > "$out/NeoAPRS-0.0.1-x86_64.AppImage" ;;
esac
"""


class Rig:
    """The script in a made-up repository (it reads its tree's files by their place), with stand-ins for docker and uv first on the PATH and for the build scripts and the scripts the containers run beside it."""

    def __init__(self, tmp_path: Path) -> None:
        self.repo, self.state, self.work, self.cache = tmp_path / "repo", tmp_path / "state", tmp_path / "work", tmp_path / "cache"
        scripts = self.repo / "scripts"
        for folder in (scripts, self.repo / "packaging" / "ci", self.repo / "neoaprs", self.repo / "tests" / "fixtures" / "kiss", self.state, tmp_path / "bin", tmp_path / "home"):
            folder.mkdir(parents=True)
        shutil.copy(SCRIPT, scripts / "check-installs")
        shutil.copy(ROOT / "scripts" / "check-in-container", scripts / "check-in-container")
        shutil.copy(ROOT / "packaging" / "ci" / "Dockerfile", self.repo / "packaging" / "ci" / "Dockerfile")
        (self.repo / "neoaprs" / "__init__.py").write_text('VERSION = "0.0.1"\n', encoding="utf-8")
        (self.repo / "neoaprs" / "mercury.py").write_text('VERSION = "1.2.3"\n', encoding="utf-8")
        for name in ("smoke.py", "install-probe.py", "smoke-appimage"):
            (scripts / name).write_text("# a stand-in\n", encoding="utf-8")
        (self.repo / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin").write_bytes(b"\xc0")
        for name in ("build-mercury", "build-deb", "build-appimage"):
            (scripts / name).write_text(FAKE_BUILD, encoding="utf-8")
            (scripts / name).chmod(0o755)
        self.bin = tmp_path / "bin"
        for name, text in (("docker", FAKE_DOCKER), ("uv", FAKE_UV)):
            (self.bin / name).write_text(text, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "FAKE_DOCKER": str(self.state), "NEOAPRS_BUILD_CACHE": str(self.cache), "LC_ALL": "C.UTF-8",
                    "XDG_RUNTIME_DIR": str(tmp_path / "home"), "TMPDIR": str(tmp_path)}
        self.rules()

    def rules(self, *rules: dict[str, Any]) -> None:
        (self.state / "rules.json").write_text(json.dumps(list(rules)))

    def pin(self, digest: str = OLD_SHA, url: str = "https://127.0.0.1:9/neoaprs_0.0.0_amd64.deb") -> None:
        (self.repo / "packaging" / "ci" / "old-release.json").write_text(json.dumps({"version": "0.0.0", "amd64": {"url": url, "sha256": digest}}), encoding="utf-8")

    def cached(self, content: bytes = OLD_DEB) -> None:
        (self.cache / "old-releases").mkdir(parents=True, exist_ok=True)
        (self.cache / "old-releases" / "neoaprs_0.0.0_amd64.deb").write_bytes(content)

    def run(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.repo / "scripts" / "check-installs"), "--work", str(self.work), *args], cwd=self.repo, env=env or self.env, capture_output=True, text=True, timeout=PATIENCE_SEC)

    def builds(self) -> list[str]:
        file = self.state / "builds"
        return file.read_text().splitlines() if file.exists() else []

    def runs(self) -> list[list[str]]:
        file = self.state / "runs"
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    if not sys.platform.startswith("linux"):
        pytest.skip("the image script reads the cores from /sys, which is Linux's")
    return Rig(tmp_path)


def option(line: list[str], name: str) -> list[str]:
    return [line[index + 1] for index, word in enumerate(line) if word == name and index + 1 < len(line)]


def test_every_check_builds_what_it_needs_and_runs_in_a_container_of_its_own(rig: Rig) -> None:
    rig.pin()
    rig.cached()
    done = rig.run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert [line.split()[1] for line in done.stdout.splitlines()[:5]] == ["wheel", "deb-debian", "deb-ubuntu", "appimage", "upgrade"] and done.stdout.splitlines()[-1] == "all green"
    builds = rig.builds()
    assert [line.split()[0] + " " + line.split()[1] for line in builds] == ["uv build", "build-mercury --tar", "build-deb --arch", "build-appimage --wheel"]
    deb, appimage = next(line for line in builds if line.startswith("build-deb")), next(line for line in builds if line.startswith("build-appimage"))
    assert f"--wheel {rig.work}/dist/neoaprs-0.0.1-py3-none-any.whl --mercury {rig.work}/mercury/mercury-1.2.3-linux-x86_64.tar.gz --out {rig.work}/dist-deb" in deb and "--arch amd64" in deb
    assert "--mercury" in appimage and "--no-mercury" not in appimage
    runs = rig.runs()
    assert len(runs) == 5
    images = [line[line.index("sh") - 1] for line in runs]
    assert images[1:3] == ["debian:bookworm-slim", "ubuntu:24.04"] and images[4] == "ubuntu:24.04" and images[0] == images[3] and images[0].startswith("neoaprs-ci:")
    for line in runs:
        assert option(line, "--volume")[0] == f"{rig.work}:/work:ro" and "--rm" in line and "--init" in line and "NEOAPRS_NO_DEVICES=1" in option(line, "--env") and "NEOAPRS_UPDATE_CHECK=0" in option(line, "--env")
        assert not {"--publish", "-p", "--device", "--privileged", "--network", "--cap-add"} & set(line), "no port, no device, nothing of this machine's"
        assert all(volume.endswith(":ro") for volume in option(line, "--volume")), "every mount is read-only"
    assert "VERSION=0.0.1" in option(runs[1], "--env") and "MERCURY_VERSION=1.2.3" in option(runs[1], "--env")
    assert "--shm-size" in runs[3] and "SMOKE_APPIMAGE_ARGS=" in option(runs[3], "--env")
    upgrade = runs[4]
    assert f"{rig.cache}/old-releases:/old:ro" in option(upgrade, "--volume") and "OLD_FILE=neoaprs_0.0.0_amd64.deb" in option(upgrade, "--env") and "OLD_VERSION=0.0.0" in option(upgrade, "--env")
    assert (rig.work / "probe" / "scripts" / "smoke.py").is_file() and (rig.work / "probe" / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin").is_file() and (rig.work / "probe" / "neoaprs" / "mercury.py").is_file()


def test_without_mercury_nothing_of_it_is_built_or_asked(rig: Rig) -> None:
    done = rig.run("--no-mercury", "--only", "deb-debian", "--only", "appimage")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not any(line.startswith("build-mercury") for line in rig.builds()) and all("--no-mercury" in line for line in rig.builds() if line.startswith(("build-deb", "build-appimage")))
    runs = rig.runs()
    assert "MERCURY_VERSION=" in option(runs[0], "--env") and "SMOKE_APPIMAGE_ARGS=--no-mercury" in option(runs[1], "--env")


def test_one_check_builds_only_what_it_needs(rig: Rig) -> None:
    done = rig.run("--only", "wheel")
    assert done.returncode == 0 and [line.split()[0] + " " + line.split()[1] for line in rig.builds()] == ["uv build"] and len(rig.runs()) == 1
    assert rig.run("--only", "no-such-check").returncode == 2


def test_a_container_that_fails_is_a_failed_check_with_the_end_of_its_log_and_the_others_still_run(rig: Rig) -> None:
    rig.rules({"image": "debian:bookworm-slim", "stdout": "a library of mercury is missing", "exit": 1})
    done = rig.run("--only", "deb-debian", "--only", "deb-ubuntu")
    assert done.returncode == 1
    lines = done.stdout.splitlines()
    assert lines[0].startswith("FAIL  deb-debian") and lines[1] == "      | a library of mercury is missing" and lines[2].startswith("ok    deb-ubuntu") and lines[-1] == "failed: deb-debian"


def test_a_build_that_fails_fails_the_checks_that_need_it_and_not_the_others(rig: Rig) -> None:
    (rig.state / "fails-build-deb").write_text("")
    done = rig.run("--no-mercury", "--only", "wheel", "--only", "deb-ubuntu", "--only", "appimage")
    assert done.returncode == 1
    lines = done.stdout.splitlines()
    assert [line.split()[0] for line in lines[:2]] == ["ok", "FAIL"] and "the build of deb failed (exit 1)" in lines[1 + 1] and lines[3].startswith("ok    appimage")
    assert len(rig.runs()) == 2, "the check whose file is not there is not started"


def test_a_wheel_that_fails_to_build_fails_every_check(rig: Rig) -> None:
    (rig.bin / "uv").write_text("#!/bin/sh\necho no\nexit 1\n")
    done = rig.run("--no-mercury")
    assert done.returncode == 1 and done.stdout.count("FAIL ") == 5 and rig.runs() == []


def test_a_mercury_that_fails_to_build_fails_the_packages_and_not_the_wheel(rig: Rig) -> None:
    (rig.state / "fails-build-mercury").write_text("")
    done = rig.run("--only", "wheel", "--only", "deb-ubuntu")
    assert done.returncode == 1 and done.stdout.splitlines()[0].startswith("ok    wheel") and "the build of mercury failed" in done.stdout and len(rig.runs()) == 1


def test_an_old_release_that_is_not_pinned_is_a_check_that_did_not_run_and_so_a_failure(rig: Rig) -> None:
    done = rig.run("--no-mercury", "--only", "upgrade")
    assert done.returncode == 1 and "FAIL  upgrade" in done.stdout and "scripts/check-installs --pin" in done.stdout and rig.runs() == []
    rig.pin(digest="")
    again = rig.run("--no-mercury", "--only", "upgrade")
    assert again.returncode == 1 and "is not pinned by its SHA-256 yet" in again.stdout and rig.runs() == []


def test_an_old_release_in_the_cache_that_is_not_the_pinned_file_is_never_used(rig: Rig) -> None:
    rig.pin()
    rig.cached(b"another file")
    done = rig.run("--no-mercury", "--only", "upgrade")
    assert done.returncode == 1 and "could not be fetched" in done.stdout and rig.runs() == [], "its digest is not the pin's, so it is fetched again (here the address is nothing)"


def test_a_download_that_is_not_the_pinned_file_is_thrown_away(installs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp_path))

    def other(url: str, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not it")
        return hashlib.sha256(b"not it").hexdigest()

    monkeypatch.setattr(installs, "download", other)
    pin = {"version": "0.0.0", "url": "https://example.test/x.deb", "sha256": OLD_SHA, "file": "x.deb"}
    with pytest.raises(installs.NotPinned, match="not the .* that is pinned: the file was thrown away"):
        installs.old_release(pin)
    assert not (tmp_path / "old-releases" / "x.deb").exists()


def test_a_pin_is_written_only_when_the_deb_is_the_one_the_releases_checksums_name(installs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEOAPRS_BUILD_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(installs, "ROOT", tmp_path)
    monkeypatch.setattr(installs, "PIN", tmp_path / "packaging" / "ci" / "old-release.json")
    (tmp_path / "packaging" / "ci").mkdir(parents=True)
    listed = {"digest": OLD_SHA}

    def fetch(url: str, target: Path) -> str:
        target.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith("/SHA256SUMS"):
            target.write_text(f"{listed['digest']}  neoaprs_1.2.3_amd64.deb\n{'0' * 64}  other-file\n", encoding="utf-8")
            return ""
        target.write_bytes(OLD_DEB)
        return OLD_SHA

    monkeypatch.setattr(installs, "download", fetch)
    listed["digest"] = "1" * 64
    assert installs.write_pin("1.2.3") == 1 and not installs.PIN.exists(), "a file that is not the one the release lists is not pinned"
    listed["digest"] = OLD_SHA
    assert installs.write_pin("1.2.3") == 0
    assert json.loads(installs.PIN.read_text(encoding="utf-8")) == {"version": "1.2.3", "amd64": {"url": "https://github.com/oh2gba/neoaprs/releases/download/v1.2.3/neoaprs_1.2.3_amd64.deb", "sha256": OLD_SHA}}
    assert installs.load_pin(installs.PIN)["file"] == "neoaprs_1.2.3_amd64.deb"


def test_the_pin_of_the_tree_names_the_release_before_this_one_or_none(installs: ModuleType) -> None:
    pin = json.loads((ROOT / "packaging" / "ci" / "old-release.json").read_text(encoding="utf-8"))
    assert set(pin) == {"version", "amd64"} and pin["amd64"]["url"] == f"{installs.RELEASES}/v{pin['version']}/neoaprs_{pin['version']}_amd64.deb"
    assert pin["amd64"]["sha256"] == "" or len(pin["amd64"]["sha256"]) == 64


def test_without_docker_or_uv_the_script_says_so(rig: Rig, tmp_path: Path) -> None:
    empty = tmp_path / "no-tools"
    empty.mkdir()
    done = rig.run(env={**rig.env, "PATH": str(empty)})
    assert done.returncode == 2 and done.stderr == "check-installs: docker is not installed\n"
    shutil.copy(rig.bin / "docker", empty / "docker")
    assert rig.run(env={**rig.env, "PATH": str(empty)}).stderr == "check-installs: uv is not installed\n"


# ---- the probe of the upgrade, against this tree's daemon ----

def test_the_probe_seeds_a_daemon_and_finds_all_of_it_in_the_next_one_and_refuses_a_version_that_is_not_the_daemons(tmp_path: Path) -> None:
    program = tmp_path / "neoaprs"
    program.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m neoaprs "$@"\n', encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "PYTHONPATH": str(ROOT), "NEOAPRS_NO_DEVICES": "1", "NEOAPRS_UPDATE_CHECK": "0"}
    base = [sys.executable, "-I", str(ROOT / "scripts" / "install-probe.py")]
    data, seen = tmp_path / "data", tmp_path / "seen.json"
    version = subprocess.run([str(program), "--version"], env=env, capture_output=True, text=True, timeout=PATIENCE_SEC, check=False).stdout.split()[-1]

    def probe(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*base, *args, "--command", str(program), "--data", str(data)], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=DAEMON_PATIENCE_SEC, check=False)

    seeded = probe("seed", "--out", str(seen))
    assert seeded.returncode == 0, seeded.stdout + seeded.stderr
    kept = json.loads(seen.read_text(encoding="utf-8"))
    assert kept["stations"] and kept["message"] == "kept over the upgrade" and kept["settings"]["hf/profile"] == "dummy-hf" and kept["from_version"] == version
    verified = probe("verify", "--in", str(seen), "--version", version)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert f"the new daemon ({version}) has the {len(kept['stations'])} stations, the message and the settings" in verified.stdout
    wrong = probe("verify", "--in", str(seen), "--version", "99.0.0")
    assert wrong.returncode == 1 and "not '99.0.0': the old program is still the one that runs" in wrong.stderr


def test_the_probe_is_given_what_it_needs_or_says_so(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "install-probe.py"), "seed", "--command", "x", "--data", str(tmp_path)], capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)
    assert done.returncode == 2 and "seed needs --out" in done.stderr

