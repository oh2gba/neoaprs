"""The repository keeps house: every script says what it is for, every document is in the index, the systemd folder, the scripts and the documents are listed where a reader looks for them,
the changelog has its section for what is not released yet.

These tests read files and run `--help` of the scripts; nothing here touches a database, a service or the network."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (the repository's scripts, units and documents: a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent


def tracked(prefix: str = "") -> list[str]:
    if shutil.which("git") is None:
        pytest.skip("needs git")
    done = subprocess.run(["git", "ls-files", "-z", "--", prefix or "."], cwd=ROOT, capture_output=True, text=True, check=True)
    return [p for p in done.stdout.split("\0") if p and (ROOT / p).is_file()]


# ---- the scripts: a header that says what a script is for, and --help ----

def script_files() -> list[Path]:
    return [ROOT / p for p in tracked("scripts") if p.count("/") == 1 and not p.endswith(".json")]


def runnable_scripts() -> list[Path]:
    """The tools: files that start with a shebang."""
    return [p for p in script_files() if p.read_text(encoding="utf-8").startswith("#!")]


def header_of(path: Path) -> str:
    """The comment (or docstring) that follows the shebang, as text; empty when the file goes on with code."""
    lines = path.read_text(encoding="utf-8").splitlines()[1:]
    if lines and lines[0].startswith('"""'):
        return "\n".join(lines).split('"""')[1].strip()
    out = []
    for line in lines:
        if not line.startswith("#"):
            break
        out.append(line.lstrip("#").strip())
    return " ".join(out).strip()


def test_there_are_tools_to_look_at() -> None:
    assert len(runnable_scripts()) >= 3


@pytest.mark.parametrize("path", runnable_scripts(), ids=lambda p: p.name)
def test_every_script_starts_with_a_comment_that_says_what_it_is_for(path: Path) -> None:
    assert len(header_of(path)) >= 40, f"{path.name}: no header comment after the shebang that says what the script is for"


def test_every_library_of_the_scripts_has_a_docstring() -> None:
    libraries = [p for p in script_files() if p not in runnable_scripts() and p.suffix == ".py"]
    assert [p.name for p in libraries if not p.read_text(encoding="utf-8").startswith('"""')] == [], "a module docstring on the first line says what a library of the scripts holds"


def run_help(path: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """`--help` in an empty folder with a HOME of its own: a script that does not know the flag must not be able to reach the user's files or services."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "NEOAPRS_PYTHON": sys.executable, "NEOAPRS_DATA_DIR": str(tmp_path / "data"), "LC_ALL": "C.UTF-8", "PYTHONPATH": str(ROOT), "NEOAPRS_SERIAL_PATTERN": os.environ["NEOAPRS_SERIAL_PATTERN"]}
    command = [sys.executable, str(path), "--help"] if path.suffix == ".py" else [str(path), "--help"]
    return subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def tree_state() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--", "scripts", "systemd", "neoaprs/page", "docs"], cwd=ROOT, capture_output=True, text=True).stdout


@pytest.mark.parametrize("path", runnable_scripts(), ids=lambda p: p.name)
def test_every_script_answers_help_and_changes_nothing(path: Path, tmp_path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert re.search(r"--help|argparse", source), f"{path.name} does not handle --help (it would be run with it, so it is not tried)"
    before = tree_state()
    done = run_help(path, tmp_path)
    assert done.returncode == 0, f"{path.name} --help: exit {done.returncode}: {(done.stdout + done.stderr)[-400:]}"
    assert len(done.stdout.strip()) >= 40, f"{path.name} --help printed nothing useful: {done.stdout!r}"
    assert tree_state() == before, f"{path.name} --help changed the tree"
    assert not list((tmp_path / "home").iterdir()) and not (tmp_path / "data").exists(), f"{path.name} --help wrote files"


# ---- the documents: one index of them all ----

def documents() -> list[str]:
    return [p for p in tracked() if p.endswith(".md")]


def index_rows() -> list[str]:
    """docs/README.md: the table rows `| `path` | what it is |`, the paths."""
    return re.findall(r"^\| `([^`]+)` \|", (ROOT / "docs" / "README.md").read_text(encoding="utf-8"), re.M)


def test_there_are_documents_to_look_at() -> None:
    assert len(documents()) >= 8


def test_the_index_lists_every_document() -> None:
    missing = sorted(set(documents()) - set(index_rows()))
    assert not missing, f"docs/README.md does not list: {missing}"


def test_the_index_lists_nothing_that_is_gone() -> None:
    gone = sorted(p for p in index_rows() if not (ROOT / p).is_file())
    assert not gone, f"docs/README.md lists files that are not there: {gone}"


def test_every_document_a_document_names_is_there() -> None:
    gone = []
    for path in documents():
        text = (ROOT / path).read_text(encoding="utf-8")
        for name in set(re.findall(r"`((?:[\w.-]+/)*[\w.-]+\.md)`", text)) | set(re.findall(r"\]\(((?:[\w.-]+/)*[\w.-]+\.md)[)#]", text)):
            if not any((base / name).is_file() for base in (ROOT, ROOT / Path(path).parent, ROOT / "docs")) and not name.startswith(".."):
                gone.append(f"{path}: {name}")
    assert not gone, f"documents name files that are not there: {gone}"


# ---- the scripts and the units: one line for each, in the manual and the README of the systemd folder ----

def table_rows(text: str, heading: str) -> list[str]:
    """The table rows (`| ... |`) between a heading line that starts with `heading` and the next heading."""
    section = re.split(r"^#+ ", text.split(f"\n{heading}", 1)[1], maxsplit=1, flags=re.M)[0] if f"\n{heading}" in text else ""
    return [line for line in section.splitlines() if line.startswith("| `")]


def test_every_script_has_a_line_in_the_table_of_scripts_in_the_manual_and_the_table_names_no_script_that_is_gone() -> None:
    rows = table_rows((ROOT / "docs" / "MANUAL.md").read_text(encoding="utf-8"), "### Scripts")
    assert len(rows) >= 3
    named = {n: row for row in rows for n in re.findall(r"`scripts/([\w.-]+)`", row.split("|")[1])}
    files = {p.name for p in script_files()}
    assert not files - set(named), f"scripts without a line in docs/MANUAL.md, 'Scripts': {sorted(files - set(named))}"
    assert not set(named) - files, f"docs/MANUAL.md, 'Scripts' names scripts that are gone: {sorted(set(named) - files)}"
    thin = [n for n, row in named.items() if len(row.split("|")[2].strip()) < 25]
    assert not thin, f"a line that does not say what the script is for: {thin}"


def test_every_unit_has_a_line_in_the_readme_of_the_systemd_folder() -> None:
    units = {p for p in tracked() if p.endswith(".service")}
    assert units
    rows = [line for line in (ROOT / "systemd" / "README.md").read_text(encoding="utf-8").splitlines() if line.startswith("| `")]       # the one table of that file
    named = {re.match(r"\| `([^`]+)`", row).group(1): row for row in rows}  # type: ignore[union-attr]
    assert not units - set(named), f"systemd/README.md has no line for: {sorted(units - set(named))}"
    assert not set(named) - units, f"systemd/README.md names units that are gone: {sorted(set(named) - units)}"
    assert all(len(row.split("|")[2].strip()) >= 40 for row in named.values()), "a unit line must say what the unit does"


def test_the_unit_is_a_template_that_names_the_interpreter_the_data_folder_and_the_clone_by_placeholders_and_the_port_of_the_page() -> None:
    unit = (ROOT / "neoaprs" / "cli" / "neoaprs.service").read_text(encoding="utf-8")
    assert "WorkingDirectory=@WORKING_DIRECTORY@\n" in unit and "ExecStart=@COMMAND@ --data @DATA@\n" in unit and "Documentation=@DOCUMENTATION@\n" in unit
    assert "/home/" not in unit, "no path of a machine in the tracked file"
    assert "7303" in unit.split("[Service]")[0]
    for key in ("Restart=always", "RestartPreventExitStatus=2", "StartLimitBurst=5", "KillSignal=SIGTERM", "WantedBy=default.target"):
        assert key in unit, key


# ---- the changelog ----

def test_the_changelog_has_its_unreleased_section_first_and_no_commit_hashes() -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, re.M)
    assert headings and headings[0] == "Unreleased", headings                 # newest first
    assert not re.search(r"\b[0-9a-f]{7,40}\b", re.sub(r"`[^`]*`", "", text)), "no commit hashes in the changelog"


# ---- .gitignore ----

def ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=ROOT).returncode == 0


@pytest.mark.parametrize("path", [
    "data/neoaprs.sqlite", "data/backup/premigrate-v1-to-v2.sqlite", "neoaprs.sqlite", "copy.sqlite-wal", "key.pem", "tls.key", ".env",                                # the data, and anything that holds a secret
    "data/basemap.pmtiles", "basemap.pmtiles.part",                                                                                                        # the base map
    ".venv/bin/python", ".venv-20261011T124153820Z-orig/bin/python", "ui/node_modules/vue/index.js", "ui/dist/index.html", "ui/dist.prev-1/index.html",     # environments and builds
    "neoaprs/__pycache__/x.pyc", "scripts/__pycache__/x.pyc", ".pytest_cache/x", ".mypy_cache/x", ".ruff_cache/x", ".hypothesis/x", ".coverage", "test-results/x",
])
def test_gitignore_keeps_out_the_data_the_environments_and_the_caches(path: str) -> None:
    assert ignored(path), f"{path} would be committed by `git add .`"


@pytest.mark.parametrize("path", ["neoaprs/page/index.html", "neoaprs/page/assets/index-x.js", "neoaprs/data/x.py", "tests/fixtures/capture.kiss", "docs/README.md", "neoaprs/cli/neoaprs.service", "ui/src/main.ts", "uv.lock"])
def test_gitignore_does_not_hide_what_belongs_in_the_repository(path: str) -> None:
    assert not ignored(path), f"{path} is ignored"


def test_nothing_that_is_tracked_is_also_ignored() -> None:
    done = subprocess.run(["git", "ls-files", "-ci", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
    assert not done.stdout.split(), f"tracked and ignored at once: {done.stdout.split()}"
