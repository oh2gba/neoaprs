"""The clean installs in Docker (scripts/check-installs and scripts/install-probe.py) as far as they can be held without docker and without a release: the builds, the containers and what each is given, from a stand-in
for docker (and for uv, git and the build scripts) that writes down what it was asked; the old release's pin and its checksum; the upgrade from a .deb file or from a commit built here (--update-from); that the
.deb check holds what the release workflow's job `deb` holds; and the probe of the upgrade run for real against this tree's daemon (seed, then verify, then a version that is not the daemon's), with the check
of the database the upgrade ends with. The images and the real builds are tried by hand (docs/development.md)."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from neoaprs.migrations import SCHEMA_VERSION
from tests.conftest import ROOT
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (scripts of the repository that run docker and shell: a development check, not the product)

SCRIPT = ROOT / "scripts" / "check-installs"
PATIENCE_SEC = 120.0
DAEMON_PATIENCE_SEC = 300.0
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
OLD_DEB = b"the old release as a file"
OLD_SHA = hashlib.sha256(OLD_DEB).hexdigest()


def installs_module() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("check_installs", str(SCRIPT))
    spec = importlib.util.spec_from_loader("check_installs", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_installs"] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def installs() -> ModuleType:
    return installs_module()


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
    ubuntu = re.fullmatch(r"ubuntu:(\d\d\.\d\d)@sha256:[0-9a-f]{64}", installs.UBUNTU)
    assert ubuntu is not None and ubuntu.group(1) == "24.04", "the older LTS, pinned by its digest"
    assert re.search(r"^ +runner: ubuntu-24\.04-arm$", deb_job(), re.M), "as the release workflow's job `deb` installs on its arm64 runner"
    series = json.loads((ROOT / "packaging" / "ci" / "runner.json").read_text(encoding="utf-8"))["facts"]["os"]
    assert re.search(rf"^FROM ubuntu:{re.escape(series)}@sha256:", (ROOT / "packaging" / "ci" / "Dockerfile").read_text(encoding="utf-8"), re.M), "the wheel and the AppImage: the runner's series"


def test_the_probe_names_what_the_scripts_it_starts_have(installs: ModuleType) -> None:
    for name in installs.PROBE_FILES:
        assert (ROOT / name).is_file(), name
    assert "scripts/smoke-appimage" in installs.APPIMAGE and "/work/probe/scripts/smoke.py" in installs.WHEEL and "install-probe.py seed" in installs.UPGRADE and "install-probe.py verify" in installs.UPGRADE


def test_the_upgrade_proves_this_build_by_its_files_and_its_database_not_by_its_version_number(installs: ModuleType, tmp_path: Path) -> None:
    """The build before the round and this one have the same version number: apt would leave the old files where they are, and a check of the version would pass on the old program."""
    upgrade = installs.UPGRADE
    assert "grep -v '  usr/share/doc/' /tmp/upgrade/control/md5sums | md5sum --quiet -c -" in upgrade and installs.DATABASE_CHECK in upgrade and '"$before" "$NEW_SCHEMA"' in upgrade
    assert installs.tree_schema() == SCHEMA_VERSION, "NEW_SCHEMA, read from the text of this tree's migrations, is the version its daemon brings a file to"
    assert upgrade.index("install-probe.py seed") < upgrade.index("before=") < upgrade.index("/work/dist-deb/neoaprs_${VERSION}_amd64.deb") < upgrade.index("md5sum") < upgrade.index("install-probe.py verify") < upgrade.index("<<'PY'")
    lines = [line for line in upgrade.splitlines() if line.startswith(("again=", '[ "$OLD_VERSION" != "$VERSION" ]'))]
    for old, new, flag in (("0.18.2", "0.18.2", "--reinstall"), ("0.18.1", "0.18.2", "")):
        said = subprocess.run(["sh", "-c", "\n".join([*lines, 'echo "[$again]"'])], env={"OLD_VERSION": old, "VERSION": new, "PATH": os.environ["PATH"]}, capture_output=True, text=True, check=True)
        assert said.stdout == f"[{flag}]\n", (old, new, said.stdout)


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
FAKE_GIT = f"""#!{sys.executable}
import io, os, sys, tarfile
state = os.environ["FAKE_DOCKER"]
args = sys.argv[3:] if sys.argv[1] == "-C" else sys.argv[1:]
with open(state + "/builds", "a") as builds:
    builds.write("git " + " ".join(args) + "\\n")
if args[0] == "rev-parse":
    if args[-1] != "before-the-round^{{commit}}":
        sys.exit(1)
    print("{'ab' * 20}")
elif args[0] == "archive":
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for name, text, mode in (("neoaprs/__init__.py", 'VERSION = "0.0.0"\\n', 0o644), ("scripts/build-deb", open(os.environ["FAKE_BUILD_SCRIPT"]).read(), 0o755)):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(text.encode()), mode
            tar.addfile(info, io.BytesIO(text.encode()))
    sys.stdout.buffer.write(out.getvalue())
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
    build-gi) echo gi > "$out/gi-3.50.2-linux-x86_64.tar.gz" ;;
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
        for name in ("Dockerfile", "runner.json"):
            shutil.copy(ROOT / "packaging" / "ci" / name, self.repo / "packaging" / "ci" / name)
        (self.repo / "neoaprs" / "__init__.py").write_text('VERSION = "0.0.1"\n', encoding="utf-8")
        (self.repo / "neoaprs" / "mercury.py").write_text('VERSION = "1.2.3"\n', encoding="utf-8")
        (self.repo / "neoaprs" / "migrations.py").write_text("MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_v1, _v2, _v3]\nSCHEMA_VERSION = len(MIGRATIONS)\n", encoding="utf-8")
        for name in ("smoke.py", "install-probe.py", "smoke-appimage"):
            (scripts / name).write_text("# a stand-in\n", encoding="utf-8")
        (self.repo / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin").write_bytes(b"\xc0")
        for name in ("build-mercury", "build-deb", "build-appimage", "build-gi"):
            (scripts / name).write_text(FAKE_BUILD, encoding="utf-8")
            (scripts / name).chmod(0o755)
        self.bin = tmp_path / "bin"
        for name, text in (("docker", FAKE_DOCKER), ("uv", FAKE_UV), ("git", FAKE_GIT)):
            (self.bin / name).write_text(text, encoding="utf-8")
            (self.bin / name).chmod(0o755)
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "FAKE_DOCKER": str(self.state), "NEOAPRS_BUILD_CACHE": str(self.cache), "LC_ALL": "C.UTF-8",
                    "XDG_RUNTIME_DIR": str(tmp_path / "home"), "TMPDIR": str(tmp_path), "FAKE_BUILD_SCRIPT": str(scripts / "build-deb")}
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


def test_every_check_builds_what_it_needs_and_runs_in_a_container_of_its_own(rig: Rig, installs: ModuleType) -> None:
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
    assert images[1:3] == ["debian:bookworm-slim", installs.UBUNTU] and images[4] == installs.UBUNTU and images[0] == images[3] and images[0].startswith("neoaprs-ci:")
    for line in runs:
        assert option(line, "--volume")[0] == f"{rig.work}:/work:ro" and "--rm" in line and "--init" in line and "NEOAPRS_NO_DEVICES=1" in option(line, "--env") and "NEOAPRS_UPDATE_CHECK=0" in option(line, "--env")
        assert not {"--publish", "-p", "--device", "--privileged", "--network", "--cap-add"} & set(line), "no port, no device, nothing of this machine's"
        assert all(volume.endswith(":ro") for volume in option(line, "--volume")), "every mount is read-only"
    assert "VERSION=0.0.1" in option(runs[1], "--env") and "MERCURY_VERSION=1.2.3" in option(runs[1], "--env")
    assert "--shm-size" in runs[3] and "SMOKE_APPIMAGE_ARGS=--no-direwolf" in option(runs[3], "--env"), "the AppImage is built without Direwolf here: its smoke test is told so"
    upgrade = runs[4]
    assert f"{rig.cache}/old-releases:/old:ro" in option(upgrade, "--volume") and "OLD_FILE=neoaprs_0.0.0_amd64.deb" in option(upgrade, "--env") and "OLD_VERSION=0.0.0" in option(upgrade, "--env")
    assert "NEW_SCHEMA=3" in option(upgrade, "--env"), "the version of the database this tree's daemon makes: its number of migrations"
    assert (rig.work / "probe" / "scripts" / "smoke.py").is_file() and (rig.work / "probe" / "tests" / "fixtures" / "kiss" / "thd7-2026-10-21.bin").is_file() and (rig.work / "probe" / "neoaprs" / "mercury.py").is_file()


def test_without_mercury_nothing_of_it_is_built_or_asked(rig: Rig) -> None:
    done = rig.run("--no-mercury", "--only", "deb-debian", "--only", "appimage")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not any(line.startswith("build-mercury") for line in rig.builds()) and all("--no-mercury" in line for line in rig.builds() if line.startswith(("build-deb", "build-appimage")))
    runs = rig.runs()
    assert "MERCURY_VERSION=" in option(runs[0], "--env") and "SMOKE_APPIMAGE_ARGS=--no-mercury --no-direwolf" in option(runs[1], "--env")


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


def test_an_upgrade_from_a_deb_file_runs_alone_from_that_file_and_needs_no_pin(rig: Rig, tmp_path: Path) -> None:
    old = tmp_path / "elsewhere" / "neoaprs_0.0.0_amd64.deb"
    old.parent.mkdir()
    old.write_bytes(b"an old build")
    done = rig.run("--no-mercury", "--update-from", str(old))
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines()[0].startswith("ok    upgrade") and len(done.stdout.splitlines()) == 2, "the upgrade alone"
    assert [line.split()[0] for line in rig.builds()] == ["uv", "build-deb"], "this build's .deb and nothing else"
    (upgrade,) = rig.runs()
    assert f"{old.parent}:/old:ro" in option(upgrade, "--volume") and {"OLD_FILE=neoaprs_0.0.0_amd64.deb", "OLD_VERSION=", "VERSION=0.0.1", "NEW_SCHEMA=3"} <= set(option(upgrade, "--env"))
    gone = rig.run("--no-mercury", "--update-from", str(tmp_path / "nothing.deb"))
    assert gone.returncode == 1 and "--update-from" in gone.stdout and "there is no such file" in gone.stdout
    assert rig.run("--update-from", str(old), "--only", "wheel").returncode == 2, "--update-from is the upgrade's"


def test_an_upgrade_from_a_commit_builds_its_deb_from_its_own_tree_without_mercury_once(rig: Rig) -> None:
    done = rig.run("--update-from", "before-the-round")
    assert done.returncode == 0, done.stdout + done.stderr
    folder = rig.work / "update-from" / ("ab" * 6)
    builds = rig.builds()
    assert [line.split()[0] for line in builds[:3]] == ["uv", "build-mercury", "build-deb"], "this build's .deb first, with Mercury"
    assert builds[3:6] == ["git rev-parse --verify --quiet before-the-round^{commit}", f"git archive --format=tar {'ab' * 20}", f"uv build --wheel --out-dir {folder}/dist"]
    assert len(builds) == 7 and builds[6].startswith("build-deb --arch amd64 --wheel ") and f"--no-mercury --out {folder}/dist-deb" in builds[6] and "--mercury" not in builds[6].split()
    assert (folder / "tree" / "neoaprs" / "__init__.py").read_text() == 'VERSION = "0.0.0"\n', "the commit's own tree, its own scripts/build-deb"
    (upgrade,) = rig.runs()
    assert f"{folder}/dist-deb:/old:ro" in option(upgrade, "--volume") and "OLD_FILE=neoaprs_0.0.1_amd64.deb" in option(upgrade, "--env")
    assert rig.run("--update-from", "before-the-round").returncode == 0 and len([line for line in rig.builds() if f"{folder}/" in line]) == 2, "the old .deb is built once and used again"
    wrong = rig.run("--no-mercury", "--update-from", "no-such-commit")
    assert wrong.returncode == 1 and "neither a .deb file nor a commit of this repository" in wrong.stdout and len(rig.runs()) == 2


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
    assert kept["stations"] and kept["message"] == "kept over the upgrade" and kept["settings"]["station/call"] == "OH2TST" and kept["hf_radio"] == "dummy-hf" and kept["from_version"] == version
    verified = probe("verify", "--in", str(seen), "--version", version)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert f"the new daemon ({version}) has the {len(kept['stations'])} stations, the message and the settings" in verified.stdout
    wrong = probe("verify", "--in", str(seen), "--version", "99.0.0")
    assert wrong.returncode == 1 and "not '99.0.0': the old program is still the one that runs" in wrong.stderr
    installs = installs_module()
    database = str(data / "neoaprs.sqlite")
    checked = subprocess.run([sys.executable, "-I", "-", database, "30", str(SCHEMA_VERSION)], input=installs.DATABASE_CHECK, capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)
    assert checked.returncode == 0 and f"from version 30 to {SCHEMA_VERSION}, with the radios fm " in checked.stdout and "hf dummy-hf" in checked.stdout, checked.stdout + checked.stderr
    ahead = subprocess.run([sys.executable, "-I", "-", database, "30", str(SCHEMA_VERSION + 1)], input=installs.DATABASE_CHECK, capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)
    assert ahead.returncode == 1 and f"not this build's {SCHEMA_VERSION + 1}: the new daemon did not bring it up to date" in ahead.stderr


def test_the_probe_is_given_what_it_needs_or_says_so(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "install-probe.py"), "seed", "--command", "x", "--data", str(tmp_path)], capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)
    assert done.returncode == 2 and "seed needs --out" in done.stderr



def test_the_trial_of_the_web_window_runs_only_when_named_and_tries_every_case_of_its_own_in_a_container(rig: Rig, installs: ModuleType) -> None:
    for name in ("smoke-appimage-web", "webkit-probe.py"):
        (rig.repo / "scripts" / name).write_text("# a stand-in\n", encoding="utf-8")
    done = rig.run("--no-mercury", "--only", "appimage-web")
    assert done.returncode == 0, done.stdout + done.stderr
    builds = rig.builds()
    assert [line.split()[0] for line in builds] == ["uv", "build-gi", "build-appimage"]
    web = builds[-1]
    assert "--window web" in web and f"--gi {rig.work}/dist-gi/gi-3.50.2-linux-x86_64.tar.gz" in web and "--no-mercury" in web and f"--out {rig.work}/dist-appimage-web" in web
    assert "--no-direwolf" in web, "the trial carries no Mercury, so no Direwolf either (build-appimage refuses Direwolf without Mercury)"
    assert "build-gi --docker" in builds[1]
    runs = rig.runs()
    assert len(runs) == len(installs.WEB_CASES) and [line[line.index("sh") - 1] for line in runs] == [case[0] for case in installs.WEB_CASES]
    scripts = [line[-1] for line in runs]
    assert all("smoke-appimage-web" in script and "/work/dist-appimage-web/" in script for script in scripts)
    assert sum("--expect window --probe" in script and "libgl1-mesa-dri" in script for script in scripts) == 6 and sum("--expect tray" in script and "webkit2gtk" not in script for script in scripts) == 6
    assert any("libwebkit2gtk-4.0-37 gir1.2-webkit2-4.0" in script and "--expect window" in script for script in scripts), "Ubuntu 22.04's desktop: the 4.0 API"
    for line in runs:
        assert not {"--publish", "-p", "--device", "--privileged", "--network", "--cap-add"} & set(line)
    assert (rig.work / "probe" / "scripts" / "smoke-appimage-web").is_file()
    assert "appimage-web" in done.stdout and done.stdout.splitlines()[-1] == "all green"


def test_the_default_run_leaves_the_trial_out(rig: Rig) -> None:
    rig.pin()
    rig.cached()
    done = rig.run("--no-mercury")
    assert done.returncode == 0 and "appimage-web" not in done.stdout and not any(line.startswith("build-gi") for line in rig.builds())


# ---- a Mercury that this system's glibc is too old for ----

def mercury_part(installs: ModuleType, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """The Mercury part of the .deb check, cut out of the script and pointed at a folder of the test, with an ldd, a dpkg and a mercury of the test's own first on the PATH."""
    text = installs.DEB
    part = text[text.index('if [ -n "${MERCURY_VERSION:-}" ]'):text.index("mkdir -p /tmp/home")]
    part = part.replace("/tmp/", "/@work/").replace("/opt/neoaprs/tools/mercury", str(tmp_path / "mercury")).replace("/@work/", f"{tmp_path}/")
    script = tmp_path / "part.sh"
    script.write_text("set -eu\n" + part, encoding="utf-8")
    (tmp_path / "mercury" / "lib").mkdir(parents=True)
    (tmp_path / "mercury" / "LICENSE").write_text("licence", encoding="utf-8")
    (tmp_path / "mercury" / "mercury").write_text('#!/bin/sh\n[ "$1" != -V ] || echo "Mercury 1.2.3"\n', encoding="utf-8")
    (tmp_path / "mercury" / "mercury").chmod(0o755)
    bin = tmp_path / "bin"
    bin.mkdir()
    (bin / "dpkg").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (bin / "ldd").write_text(f'#!/bin/sh\ncat "{tmp_path}/ldd-says"\n', encoding="utf-8")
    for name in ("dpkg", "ldd"):
        (bin / name).chmod(0o755)
    return script, {"PATH": f"{bin}{os.pathsep}{os.environ['PATH']}", "MERCURY_VERSION": "1.2.3"}


def run_part(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True, timeout=PATIENCE_SEC, check=False)


def test_a_mercury_built_against_a_newer_glibc_than_the_system_has_is_said_to_be_skipped_not_passed_or_failed(installs: ModuleType, tmp_path: Path) -> None:
    script, env = mercury_part(installs, tmp_path)
    (tmp_path / "ldd-says").write_text(
        "./mercury: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.38' not found (required by ./mercury)\n\tlibasound.so.2 => /x/lib/libasound.so.2 (0x1)\n", encoding="utf-8")
    done = run_part(script, env)
    assert done.returncode == 0, done.stdout + done.stderr
    skipped = [line for line in done.stdout.splitlines() if line.startswith(installs.SKIPPED)]
    assert len(skipped) == 1 and "GLIBC_2.38" in skipped[0] and "mercury -V" not in done.stdout


def test_a_library_of_mercury_that_is_missing_still_fails_beside_a_glibc_that_is_too_old(installs: ModuleType, tmp_path: Path) -> None:
    script, env = mercury_part(installs, tmp_path)
    (tmp_path / "ldd-says").write_text("./mercury: /lib/libc.so.6: version `GLIBC_2.38' not found (required by ./mercury)\n\tlibfoo.so.1 => not found\n", encoding="utf-8")
    done = run_part(script, env)
    assert done.returncode == 1 and "a library of mercury is missing" in done.stdout and installs.SKIPPED not in done.stdout


def test_a_mercury_that_fits_the_system_is_still_run_and_not_skipped(installs: ModuleType, tmp_path: Path) -> None:
    script, env = mercury_part(installs, tmp_path)
    (tmp_path / "ldd-says").write_text(f"\tlibasound.so.2 => {tmp_path}/mercury/lib/libasound.so.2 (0x1)\n", encoding="utf-8")
    done = run_part(script, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "mercury -V: Mercury 1.2.3" in done.stdout and installs.SKIPPED not in done.stdout


def test_a_check_that_passed_with_a_part_skipped_says_so_in_one_line_and_the_run_is_not_called_all_green(rig: Rig) -> None:
    rig.rules({"image": "debian:bookworm-slim", "stdout": "SKIPPED: Mercury was not run: it needs GLIBC_2.38", "exit": 0})
    done = rig.run("--only", "deb-debian", "--only", "deb-ubuntu")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[0].startswith("ok    deb-debian") and lines[1] == "      | skipped: Mercury was not run: it needs GLIBC_2.38" and lines[2].startswith("ok    deb-ubuntu")
    assert lines[-1] == "all green, but a part of deb-debian was skipped"
