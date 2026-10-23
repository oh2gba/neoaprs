"""The manual (docs/MANUAL.md) says what exists: these tests fail when something is added that it does not mention, or it names something that is gone; the README is the front page and its pictures, links and licence are held here too. The documents
name only code that is there, the one table of environment variables holds every variable in use, and the tables of docs/ARCHITECTURE.md are made from the architecture test."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support import archdoc
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (the repository's documents, checked with git and the shell scripts: a development check, not the product)

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
MANUAL = (ROOT / "docs" / "MANUAL.md").read_text(encoding="utf-8")


def tracked() -> list[str]:
    if shutil.which("git") is None:
        pytest.skip("needs git")
    done = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [p for p in done.stdout.split("\0") if p and (ROOT / p).exists()]


def test_every_stage_of_scripts_check_is_in_the_table_of_the_manual() -> None:
    script = (ROOT / "scripts" / "check").read_text(encoding="utf-8")
    stages = re.search(r"^STAGES=\(([^)]*)\)", script, re.M).group(1).split()  # type: ignore[union-attr]
    assert len(stages) >= 5
    missing = [name for name in stages if f"| `{name}` |" not in MANUAL]
    assert not missing, f"scripts/check has stages that docs/MANUAL.md does not describe: {missing}"
    rows = re.findall(r"^\| `([\w-]+)` \| [^|]*\|$", MANUAL.split("### The stages of scripts/check", 1)[1].split("### Scripts", 1)[0], re.M)
    assert rows == stages, "the table of stages is the stages of scripts/check, in order"


def test_every_top_level_folder_and_file_is_in_the_map_of_the_repository() -> None:
    entries = {p.split("/", 1)[0] for p in tracked()}
    missing = []
    for name in sorted(entries - {"README.md", ".gitignore"}):
        is_folder = any(p.startswith(name + "/") for p in tracked())
        if f"`{name}/`" not in MANUAL and f"`{name}`" not in MANUAL and not (is_folder and f"`{name}/" in MANUAL):
            missing.append(name)
    assert not missing, f"not in docs/MANUAL.md ('What is in the folder' or 'Documents'): {missing}"


def test_every_folder_of_tests_and_docs_is_in_the_map_of_the_repository() -> None:
    folders = sorted({"/".join(p.split("/")[:2]) for p in tracked() if p.split("/")[0] in ("tests", "docs") and p.count("/") >= 2})
    missing = [f for f in folders if f"`{f.split('/')[1]}/`" not in MANUAL and f"`{f}/`" not in MANUAL]
    assert not missing, f"not in the map of docs/MANUAL.md: {missing}"


def test_every_script_is_named_in_the_manual() -> None:
    names = [p.name for p in (ROOT / "scripts").iterdir() if p.is_file()]
    missing = [n for n in names if f"scripts/{n}" not in MANUAL]
    assert not missing, f"docs/MANUAL.md does not name: {missing}"


ENVIRONMENT = re.compile(r"(?<![A-Za-z_])NEOAPRS_[A-Z][A-Z_]*[A-Z]")


def used_variables() -> dict[str, str]:
    """Every NEOAPRS_* name in the code, the scripts, the units and the tests (text files only), with a file that uses it."""
    found: dict[str, str] = {}
    for rel in tracked():
        path = ROOT / rel
        if (rel.split("/", 1)[0] in ("neoaprs", "scripts", "tests", "systemd", "packaging") or rel == "ui/vite.config.ts") and rel != "tests/test_docs.py":
            if path.suffix in ("", ".py", ".sh", ".in", ".service", ".timer", ".ts") and path.is_file():
                for name in ENVIRONMENT.findall(path.read_text(errors="ignore")):
                    found.setdefault(name, rel)
    return found


def table_variables() -> set[str]:
    section = (ROOT / "CONVENTIONS.md").read_text(encoding="utf-8").split("## Environment variables\n", 1)[1].split("\n## ", 1)[0]
    return {name for row in section.splitlines() if row.startswith("| `") for name in ENVIRONMENT.findall(row.split("|")[1])}


def test_every_environment_variable_in_use_is_in_the_one_table_of_the_conventions() -> None:
    used = used_variables()
    assert len(used) >= 5
    missing = {name: rel for name, rel in used.items() if name not in table_variables()}
    assert not missing, f"CONVENTIONS.md, 'Environment variables', does not name {missing}"
    unused = sorted(table_variables() - set(used))
    assert not unused, f"the table names variables that nothing uses: {unused}"


def test_the_manual_sends_the_reader_to_the_table_of_environment_variables() -> None:
    assert "table \"Environment variables\" of `CONVENTIONS.md`" in MANUAL


def test_the_commands_of_the_readme_and_the_manual_run_scripts_that_exist() -> None:
    blocks = re.findall(r"```bash\n(.*?)```", README + MANUAL, re.S)
    called = {m for block in blocks for m in re.findall(r"(?:^|[\s(])(scripts/[A-Za-z0-9_.-]+)", block)}
    assert len(called) >= 1
    gone = sorted(c for c in called if not (ROOT / c).exists())
    assert not gone, f"README.md or docs/MANUAL.md runs scripts that are not there: {gone}"


# ---- the front page: its pictures and links are there, and it names the licence the project has ----

def test_the_pictures_and_links_of_the_readme_are_files_that_are_there() -> None:
    targets = re.findall(r"\]\(([^)\s]+)\)", README)
    local = [t.split("#", 1)[0] for t in targets if not t.startswith(("http://", "https://", "#"))]
    assert len([t for t in local if t.endswith(".png")]) >= 4, "the README shows the page in at least four pictures"
    gone = sorted(t for t in local if not (ROOT / t).is_file())
    assert not gone, f"README.md points to files that are not there: {gone}"


def test_the_readme_names_the_licence_the_license_file_and_pyproject_have() -> None:
    licence = re.search(r'^license = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert licence and licence.group(1) in README, "README.md names the licence of pyproject.toml"
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007") and "END OF TERMS AND CONDITIONS" in text
    assert licence.group(1).startswith("GPL-3.0")


# ---- the documents are kept true: what they name is there ----

PATH_IN_BACKTICKS = re.compile(r"`((?:neoaprs|tests|scripts|docs|systemd)/[\w./-]*[\w])/?`")
ROADMAPS = {"ROADMAP.md"}                       # a roadmap names what does not exist yet


def current_docs() -> list[str]:
    return [p for p in tracked() if p.endswith(".md") and p not in ROADMAPS]


def names_that_are_not_there(text: str, files: set[str]) -> list[str]:
    """The lines that put in backticks a path under neoaprs/, tests/, scripts/, docs/ or systemd/ that the tree does not have. A path with a star is a pattern."""
    folders = {"/".join(p.split("/")[:n]) for p in files for n in range(1, p.count("/") + 1)}
    found = []
    for line in archdoc.BLOCK.sub("", text).splitlines():                 # (the generated blocks are held against the architecture test, not against the tree)
        for name in PATH_IN_BACKTICKS.findall(line):
            if "*" not in name and name not in files and name + ".py" not in files and name not in folders:
                found.append(f"{name}: {line.strip()[:100]}")
    return found


def test_every_path_a_current_document_puts_in_backticks_is_in_the_tree() -> None:
    files = set(tracked())
    docs = current_docs()
    assert {"README.md", "docs/MANUAL.md", "docs/ARCHITECTURE.md"} <= set(docs)
    found = [f"{rel}: {line}" for rel in docs for line in names_that_are_not_there((ROOT / rel).read_text(encoding="utf-8"), files)]
    assert not found, "documents name files that are not there (bring the text up to date, or move what is planned to ROADMAP.md):\n" + "\n".join(found)


def test_a_path_that_is_not_there_is_found_and_a_pattern_is_not() -> None:
    files = {"neoaprs/clock.py", "tests/test_x.py"}
    text = "`neoaprs/clock.py` and `tests/` are there; `neoaprs/gone.py` is not.\n`neoaprs/web/*` and `tests/support/*.py` are patterns.\n"
    assert names_that_are_not_there(text, files) == ["neoaprs/gone.py: `neoaprs/clock.py` and `tests/` are there; `neoaprs/gone.py` is not."]


def sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if len(s.strip()) > 40]


def test_no_paragraph_of_a_document_says_a_sentence_twice() -> None:
    """A merge that joined two versions of a paragraph leaves its end twice."""
    twice = []
    for rel in current_docs():
        for paragraph in re.split(r"\n\s*\n", (ROOT / rel).read_text(encoding="utf-8")):
            if paragraph.lstrip().startswith("|"):
                continue
            found = sentences(paragraph)
            twice += [f"{rel}: {s[:80]}" for s in found if found.count(s) > 1]
    assert not twice, twice


ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"


def test_the_tables_of_the_architecture_document_are_the_data_of_the_architecture_test() -> None:
    stale = archdoc.stale_blocks(ARCHITECTURE.read_text(encoding="utf-8"))
    assert stale == [], f"docs/ARCHITECTURE.md: out of date: {stale}; run  .venv/bin/python scripts/doc-arch --write"


def test_the_architecture_document_names_every_part_the_composition_root_makes() -> None:
    attributes = re.findall(r"^        self\.(\w+)\b.*?=", (ROOT / "neoaprs" / "app.py").read_text(encoding="utf-8"), re.M)
    parts = [a for a in attributes if a not in ("running", "debug", "clock", "data_dir")]
    assert len(parts) >= 3
    missing = [a for a in parts if f"`{a}`" not in ARCHITECTURE.read_text(encoding="utf-8") and f"(`{a}`)" not in ARCHITECTURE.read_text(encoding="utf-8")]
    assert not missing, f"docs/ARCHITECTURE.md ('The composition root') does not name {missing}"
