"""scripts/runner-facts and packaging/ci/runner.json without the network or the clock: the file's
shape, each fact at its own precision, this machine read from stand-ins, and GitHub's image readme
read from excerpts.
"""
import datetime
import importlib.machinery
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "runner-facts"
RUNNER = json.loads((ROOT / "packaging" / "ci" / "runner.json").read_text(encoding="utf-8"))
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the stand-ins for gcc, ldd and php are shell scripts")

# A made-up runner.json of its own, so that a move of the real one changes no test here;
# ubuntu-22.04 is in it to have an announcement read until a day.
MADE_UP = {"labels": ["ubuntu-26.04", "ubuntu-24.04-arm", "ubuntu-22.04", "windows-2025", "macos-26"], "latest": {"ubuntu-latest": "26.04", "windows-latest": "10.0.26100", "macos-latest": "26"},
           "image_version": "20261111.196.1", "facts": {"os": "26.04", "gcc": "15", "march": "x86-64-v3", "glibc": "2.43", "php": "8.5"},
           "announcements": {"14254": "2027-02-21", "14748": None}}

# A few lines in the form of GitHub's readme of an image (images/ubuntu/Ubuntu2604-Readme.md), not a
# copy of it.
README = """# Ubuntu 26.04
- OS Version: 26.04.1 LTS
- Kernel Version: 7.0.0-1019-azure
- Image Version: 20261111.196.1
### PHP Tools
- PHP: 8.5.4
- Composer 2.9.1
### Installed apt packages
| Name    | Version            |
| ------- | ------------------ |
| gcc     | 4:15.2.0-5ubuntu1  |
| git     | 1:2.56.1-0ppa1     |
| locales | 2.43-2ubuntu2.4    |
"""

# The open issues of a made-up day in the form of GitHub's API: ours read for good, ours read until
# a day, ours not read, one that names nothing of ours, and a pull request.
ISSUES: list[dict[str, Any]] = [
    {"number": 14748, "title": "ubuntu-latest moves to Ubuntu 26.04", "body": "The rollout ends on 19 November."},
    {"number": 14254, "title": "The Ubuntu 22.04 image will be retired", "body": "Jobs on ubuntu-22.04 will fail from 17 April 2027."},
    {"number": 15315, "title": "D: becomes ReFS on Windows images", "body": "This affects windows-2025 and windows-latest."},
    {"number": 15400, "title": "macOS 15 images are retired", "body": "Move from macos-15 to macos-15-arm64, released 2026.04."},
    {"number": 15401, "title": "Bump ubuntu-26.04 readme", "body": "", "pull_request": {"url": "x"}},
]


@pytest.fixture(scope="module")
def facts() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("runner_facts", str(SCRIPT))
    spec = importlib.util.spec_from_loader("runner_facts", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.splitlines()


# ---- runner.json ----

def test_runner_json_holds_the_labels_the_latest_labels_the_facts_and_the_announcements_read(facts: ModuleType) -> None:
    assert set(RUNNER) == {"labels", "latest", "image_version", "facts", "announcements"}
    assert facts.load_runner() == RUNNER
    labels = RUNNER["labels"]
    assert labels and len(set(labels)) == len(labels) and all(re.fullmatch(r"(ubuntu|windows|macos)-[\d.]+(-arm)?", label) for label in labels), "named runners only"
    assert set(RUNNER["latest"]) == {"ubuntu-latest", "windows-latest", "macos-latest"}
    assert tuple(RUNNER["facts"]) == facts.FACTS and all(isinstance(value, str) and value for value in RUNNER["facts"].values())
    assert re.fullmatch(r"\d\d\.\d\d", RUNNER["facts"]["os"]) and re.fullmatch(r"\d+", RUNNER["facts"]["gcc"]), "the series, and gcc by its major: its minor moves inside a series"
    assert re.fullmatch(r"\d+\.\d+", RUNNER["facts"]["glibc"]) and re.fullmatch(r"\d+\.\d+", RUNNER["facts"]["php"]) and RUNNER["facts"]["march"].startswith("x86-64")
    assert re.fullmatch(r"\d{8}\.\d+\.\d+", RUNNER["image_version"])
    for number, until in RUNNER["announcements"].items():
        assert number.isdigit() and (until is None or datetime.date.fromisoformat(until)), number


def test_a_runner_json_without_its_facts_is_refused(facts: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "runner.json").write_text('{"labels": [], "facts": {"os": "26.04"}}')
    with pytest.raises(ValueError, match="has no `facts`"):
        facts.load_runner(tmp_path / "runner.json")


# ---- the comparison ----

@pytest.mark.parametrize(("found", "fact", "same"), [
    ("15.2.0", "15", True), ("15", "15", True), ("14.2.0", "15", False), ("150.1", "15", False),
    ("2.43", "2.43", True), ("2.43.1", "2.43", True), ("2.4", "2.43", False), ("2.39", "2.43", False),
    ("8.5.4", "8.5", True), ("8.4.27", "8.5", False), ("26.04", "26.04", True), ("24.04", "26.04", False),
    ("x86-64-v3", "x86-64-v3", True), ("x86-64", "x86-64-v3", False), (None, "15", False),
])
def test_each_fact_is_compared_at_its_own_precision(facts: ModuleType, found: str | None, fact: str, same: bool) -> None:
    assert facts.agrees(found, fact) is same


# ---- --here ----

STAND_INS = {
    "gcc": '#!/bin/sh\ncase "$1" in\n  -dumpfullversion) echo 15.2.0 ;;\n  -Q) printf "  -m64\\t\\t[enabled]\\n  -march=                     \\t\\tx86-64-v3\\n  -mtune=\\t\\tgeneric\\n" ;;\nesac\n',
    "ldd": '#!/bin/sh\necho "ldd (Ubuntu GLIBC 2.43-2ubuntu2.4) 2.43"\necho "Copyright (C) 2026 Free Software Foundation, Inc."\n',
    "php": "#!/bin/sh\nprintf 8.5.4\n",
}


def stand_ins(folder: Path, **changed: str) -> Path:
    folder.mkdir()
    for name, text in {**STAND_INS, **changed}.items():
        (folder / name).write_text(text)
        (folder / name).chmod(0o755)
    return folder


def os_release(tmp_path: Path, version: str = "26.04") -> Path:
    file = tmp_path / "os-release"
    file.write_text(f'PRETTY_NAME="Ubuntu Resolute"\nNAME="Ubuntu"\nVERSION_ID="{version}"\nID=ubuntu\n')
    return file


@posix_only
def test_here_reads_this_machine_and_says_nothing_wrong_on_the_runner_it_names(facts: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PATH", str(stand_ins(tmp_path / "bin")))
    out = facts.Out(github=True)
    facts.here(out, MADE_UP, {"ImageVersion": "20261118.201.1"}, os_release(tmp_path))
    assert not out.failed
    assert lines(capsys) == ["runner-facts: read here: os 26.04, gcc 15.2.0, march x86-64-v3, glibc 2.43, php 8.5.4",
                             "::notice title=runner-facts::the runner's image is 20261118.201.1; runner.json's facts were last checked against 20261111.196.1"]


@posix_only
def test_here_says_each_fact_that_parts_and_fails(facts: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PATH", str(stand_ins(tmp_path / "bin", gcc=STAND_INS["gcc"].replace("x86-64-v3", "x86-64").replace("15.2.0", "14.2.0"), php="#!/bin/sh\nexit 1\n")))
    out = facts.Out(github=True)
    facts.here(out, MADE_UP, {}, os_release(tmp_path, "24.04"))
    assert out.failed
    assert lines(capsys) == ["runner-facts: read here: os 24.04, gcc 14.2.0, march x86-64, glibc 2.43, php not found",
                             "::error title=runner-facts::os is 24.04 here, packaging/ci/runner.json says 26.04",
                             "::error title=runner-facts::gcc is 14.2.0 here, packaging/ci/runner.json says 15",
                             "::error title=runner-facts::march is x86-64 here, packaging/ci/runner.json says x86-64-v3",
                             "::error title=runner-facts::php is not found here, packaging/ci/runner.json says 8.5"]


def test_here_finds_nothing_where_there_is_no_such_program_or_file(facts: ModuleType, tmp_path: Path) -> None:
    assert facts.read_here(tmp_path / "no-os-release", lambda command: None) == dict.fromkeys(facts.FACTS)
    assert facts.first_line([str(tmp_path / "no-such-program")]) is None


# ---- --latest ----

@pytest.mark.parametrize(("label", "system", "moved"), [
    ("ubuntu-latest", "26.04", False), ("ubuntu-latest", "28.04", True),
    ("windows-latest", "10.0.26100", False), ("windows-latest", "10.0.26200", True), ("windows-latest", "10.0.261000", True),
    ("macos-latest", "26.7.2", False), ("macos-latest", "27.0", True),
])
def test_latest_says_when_a_latest_label_is_no_longer_the_system_we_name(facts: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str], label: str, system: str, moved: bool) -> None:
    out = facts.Out(github=False)
    facts.latest(out, MADE_UP, label, os_release(tmp_path, system), windows_version=system, mac_version=system)
    said = lines(capsys)
    assert out.failed is moved and len(said) == 1 + moved
    assert said[0] == f"runner-facts: {label} is {system.split('.')[0] if label == 'macos-latest' else system} here; runner.json names {MADE_UP['latest'][label]}"


# Stands in for macOS's sw_vers: the true version only with the compatibility number turned off,
# else the number an old SDK's program is shown.
SW_VERS = '#!/bin/sh\n[ "$1" = -productVersion ] || exit 1\nif [ "$SYSTEM_VERSION_COMPAT" = 0 ]; then echo 26.1; else echo 16.0; fi\n'


@posix_only
def test_macos_is_read_from_sw_vers_with_the_compatibility_number_off(facts: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PATH", str(stand_ins(tmp_path / "bin", **{"sw_vers": SW_VERS})))
    # What a Python of an older SDK says
    monkeypatch.setattr(facts.platform, "mac_ver", lambda: ("16.0", ("", "", ""), "arm64"))
    assert facts.macos_version() == "26.1"
    out = facts.Out(github=False)
    facts.latest(out, MADE_UP, "macos-latest")
    assert not out.failed and lines(capsys) == ["runner-facts: macos-latest is 26 here; runner.json names 26"]


def test_macos_falls_back_to_pythons_own_reading_without_sw_vers(facts: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "bin").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(facts.platform, "mac_ver", lambda: ("26.0.1", ("", "", ""), "arm64"))
    assert facts.macos_version() == "26.0.1"
    monkeypatch.setattr(facts.platform, "mac_ver", lambda: ("", ("", "", ""), ""))
    assert facts.macos_version() is None


def test_a_label_runner_json_does_not_follow_is_a_wrong_argument(facts: ModuleType) -> None:
    with pytest.raises(SystemExit) as stopped:
        facts.main(["--latest", "ubuntu-24.04"])
    assert stopped.value.code == 2


def test_nothing_to_compare_is_a_wrong_argument(facts: ModuleType) -> None:
    with pytest.raises(SystemExit) as stopped:
        facts.main([])
    assert stopped.value.code == 2


# ---- --published ----

def test_the_readme_is_read_and_compared_at_the_facts_precision(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    assert facts.read_readme(README) == {"os": "26.04", "gcc": "15.2.0", "glibc": "2.43", "php": "8.5.4"}, "the epoch and Ubuntu's revision taken off"
    asked: list[str] = []
    out = facts.Out(github=False)
    facts.published(out, MADE_UP, lambda url: asked.append(url) or README)
    assert asked == ["https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2604-Readme.md"] and not out.failed
    assert lines(capsys) == ["runner-facts: read in GitHub's readme: os 26.04, gcc 15.2.0, glibc 2.43, php 8.5.4"], "-march is never compared here: no readme lists it"


def test_a_readme_that_parts_fails(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    out = facts.Out(github=False)
    facts.published(out, MADE_UP, lambda url: README.replace("4:15.2.0-5ubuntu1", "4:16.1.0-1ubuntu1"))
    assert out.failed and lines(capsys)[1:] == ["runner-facts: gcc is 16.1.0 in GitHub's readme, packaging/ci/runner.json says 15"]


def test_a_readme_that_cannot_be_fetched_or_read_fails(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    def unreachable(url: str) -> str:
        raise facts.Unreadable(f"{url} could not be fetched (no route)")
    out = facts.Out(github=False)
    facts.published(out, MADE_UP, unreachable)
    assert out.failed and lines(capsys) == ["runner-facts: https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2604-Readme.md could not be fetched (no route)"]
    out = facts.Out(github=False)
    facts.published(out, MADE_UP, lambda url: "\n".join(line for line in README.splitlines() if "locales" not in line and "PHP" not in line))
    assert out.failed and lines(capsys) == ["runner-facts: https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2604-Readme.md could not be read: no glibc, php in it"]


def test_a_page_that_cannot_be_fetched_is_unreadable(facts: ModuleType) -> None:
    with pytest.raises(facts.Unreadable, match=r"^https://127\.0\.0\.1:9/x could not be fetched \("):
        facts.fetch("https://127.0.0.1:9/x")
    with pytest.raises(facts.Unreadable, match=r"^file:///etc/passwd is not fetched: https only$"):
        facts.fetch("file:///etc/passwd", token="made-up")


# ---- --announcements ----

@pytest.mark.parametrize(("today", "unread"), [("2027-02-21", [15315]), ("2027-02-22", [14254, 15315])])
def test_an_announcement_that_names_ours_and_is_not_read_or_read_until_a_day_that_passed_is_said(facts: ModuleType, today: str, unread: list[int]) -> None:
    assert [issue["number"] for issue in facts.unread(ISSUES, MADE_UP, datetime.date.fromisoformat(today))] == unread, "not 15400 (macos-15, 2026.04: none of ours) and not the pull request"


def test_the_announcements_are_said_with_their_number_and_title_and_fail(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    out = facts.Out(github=True)
    facts.announcements(out, MADE_UP, lambda url: json.dumps(ISSUES), datetime.date(2027, 3, 1))
    assert out.failed
    assert lines(capsys) == [
        "runner-facts: 5 open announcements, 2 that name one of our runners and are not read",
        "::error title=runner-facts::#14254 The Ubuntu 22.04 image will be retired (read until 2027-02-21, which has passed): read it, act on it, and add it to `announcements` in packaging/ci/runner.json with the day until which it stays read",
        "::error title=runner-facts::#15315 D: becomes ReFS on Windows images (not read): read it, act on it, and add it to `announcements` in packaging/ci/runner.json with the day until which it stays read",
    ]
    out = facts.Out(github=False)
    facts.announcements(out, {**MADE_UP, "announcements": {"14254": None, "14748": None, "15315": "2027-03-01"}}, lambda url: json.dumps(ISSUES), datetime.date(2027, 3, 1))
    assert not out.failed and lines(capsys) == ["runner-facts: 5 open announcements, 0 that name one of our runners and are not read"]


@pytest.mark.parametrize("answer", ["<html>rate limited</html>", '{"message": "API rate limit exceeded"}', "[1, 2]"])
def test_an_answer_that_is_no_list_of_issues_fails(facts: ModuleType, capsys: pytest.CaptureFixture[str], answer: str) -> None:
    out = facts.Out(github=False)
    facts.announcements(out, MADE_UP, lambda url: answer, datetime.date(2027, 3, 1))
    assert out.failed and len(said := lines(capsys)) == 1 and said[0].startswith(f"runner-facts: {facts.ANNOUNCEMENTS} could not be read")


def test_the_list_that_cannot_be_fetched_fails(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    def unreachable(url: str) -> str:
        raise facts.Unreadable(f"{url} could not be fetched (no route)")
    out = facts.Out(github=False)
    facts.announcements(out, MADE_UP, unreachable, datetime.date(2027, 3, 1))
    assert out.failed and lines(capsys) == [f"runner-facts: {facts.ANNOUNCEMENTS} could not be fetched (no route)"]


def test_a_name_is_found_as_a_word_of_its_own(facts: ModuleType) -> None:
    assert facts.names("Ubuntu 26.04.1 LTS", "26.04") and facts.names("jobs on UBUNTU-22.04 fail", "ubuntu-22.04") and facts.names("ubuntu-24.04-arm", "ubuntu-24.04-arm")
    assert not facts.names("released 2026.04", "26.04") and not facts.names("macos-260", "macos-26")


# ---- where it runs ----

def job(workflow: str, name: str) -> str:
    found = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"), re.S | re.M)
    assert found is not None, f"no job {name} in {workflow}"
    return found.group(1)


def test_the_runners_jobs_check_their_facts_first_and_the_weekly_job_each_latest_label() -> None:
    for name, condition in (("python", "        if: runner.os == 'Linux'\n"), ("sim", "")):
        steps = re.split(r"^      - ", job("ci.yml", name), flags=re.M)[1:]
        assert steps[0].startswith("uses: actions/checkout@") and steps[1].startswith("name: "), f"{name}: the first step after the checkout"
        assert f"\n{condition}        run: python3 scripts/runner-facts --here --github\n" in steps[1], steps[1]
    latest = job("audit.yml", "latest")
    assert re.search(r"^        os: \[([^\]]*)\]$", latest, re.M).group(1).split(", ") == list(RUNNER["latest"])        # type: ignore[union-attr]
    assert 'run: uv run --no-project python scripts/runner-facts --latest "$LABEL" --github\n        env:\n          LABEL: ${{ matrix.os }}' in latest, "the label goes in by the environment, never into the shell line"


def test_a_text_with_a_line_end_stays_one_workflow_command(facts: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    out = facts.Out(True)
    out.error("title\n::warning::x 100%")
    out.notice("a\r\n::add-mask::b")
    out.info("c\n::stop-commands::d")
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["::error title=runner-facts::title%0A::warning::x 100%25", "::notice title=runner-facts::a%0D%0A::add-mask::b", "runner-facts: c ::stop-commands::d"]
