"""What ruff reads. ruff knows a Python file by the ending of its name, so a tool that is Python and is called `scripts/release` is passed by, with every rule, unless pyproject.toml names it
(`extend-include` of `[tool.ruff]`). That list is held exact here: a file of the folders below that begins with a python line and has no `.py` in its name is in it, and every entry is such a file.
The second half shows the rule failing on a made-up folder."""
import tomllib
from pathlib import Path

from tests.conftest import ROOT

FOLDERS = ("scripts", "packaging", "server", "systemd")           # where the tools of the repository are; neoaprs/ and tests/ hold modules, which have their ending
PASSED_BY = {"node_modules", "__pycache__", "logs", "support"}      # folders that are not the repository's own text: what a tool installed or cached, and what the fetch scripts of server/ brought (server/logs, server/support)
NO_FIRST_LINE = {"packaging/windows/neoaprs.spec": "PyInstaller's spec: Python that PyInstaller runs, with no line naming an interpreter"}      # Python with no `.py` and no `#!`, which only a name can find


def listed() -> list[str]:
    """The files pyproject.toml tells ruff to read beside the *.py it finds itself."""
    found = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"]["extend-include"]
    assert isinstance(found, list) and all(isinstance(entry, str) for entry in found)
    return found


def begins_with_python(path: Path) -> bool:
    """Is the file's first line the line that names its interpreter (`#!`), and is that python?"""
    with path.open("rb") as handle:
        first = handle.readline(200)
    return first.startswith(b"#!") and b"python" in first


def python_without_the_ending(root: Path) -> list[str]:
    """Every file under the folders of tools whose first line names python and whose name does not end in .py, as a path from the root."""
    found: list[str] = []
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*")):
            inside = path.relative_to(root)
            if path.is_file() and path.suffix != ".py" and not PASSED_BY & set(inside.parts[:-1]) and not any(part.startswith(".") for part in inside.parts) and begins_with_python(path):
                found.append(inside.as_posix())
    return found + [name for name in NO_FIRST_LINE if (root / name).is_file()]


def not_as_listed(root: Path, entries: list[str]) -> list[str]:
    """What is wrong between the list and the tree: [] when ruff reads every Python tool and the list names nothing else."""
    there = python_without_the_ending(root)
    wrong = [f"{rel} is Python and ruff does not read it: add it to extend-include of [tool.ruff] in pyproject.toml" for rel in there if rel not in entries]
    wrong += [f"{entry} is in extend-include and is not a file that begins with a python line and has no .py in its name: delete the entry" for entry in entries if entry not in there]
    wrong += [f"{entry} is in extend-include twice" for entry in sorted(set(entries)) if entries.count(entry) > 1]
    return wrong


def test_ruff_reads_every_python_tool_that_has_no_py_in_its_name_and_the_list_names_nothing_else() -> None:
    assert "scripts/release" in python_without_the_ending(ROOT), "the tools were not found as they are: the release script is one of them"
    assert not_as_listed(ROOT, listed()) == []


# ---- the rule fails on a made-up folder ---------------------------------------------------------------------------------------------------------------------

def test_a_python_tool_that_is_not_listed_and_an_entry_that_is_no_such_file_are_found(tmp_path: Path) -> None:
    files = {"scripts/release": "#!/usr/bin/env python3\nprint(1)\n", "scripts/logs": "#!/usr/bin/env python3\n", "scripts/new-tool": "#!/usr/bin/python3 -I\nprint(2)\n", "scripts/check": "#!/usr/bin/env bash\npython -m ruff check .\n",
             "scripts/smoke.py": "#!/usr/bin/env python3\n", "scripts/notes": "python is named here, but not as the interpreter\n", "scripts/dup-baseline.json": "{}\n",
             "packaging/deb/build": "#!/usr/bin/env python3\n", "packaging/node_modules/tool": "#!/usr/bin/env python3\n", "server/.cache/tool": "#!/usr/bin/env python3\n", "systemd/README.md": "# units\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    assert python_without_the_ending(tmp_path) == ["scripts/logs", "scripts/new-tool", "scripts/release", "packaging/deb/build"]
    assert not_as_listed(tmp_path, ["scripts/release", "scripts/logs", "scripts/new-tool", "packaging/deb/build"]) == []
    assert not_as_listed(tmp_path, ["scripts/release", "scripts/logs", "scripts/check", "scripts/smoke.py", "scripts/gone", "scripts/release"]) == [
        "scripts/new-tool is Python and ruff does not read it: add it to extend-include of [tool.ruff] in pyproject.toml",
        "packaging/deb/build is Python and ruff does not read it: add it to extend-include of [tool.ruff] in pyproject.toml",
        "scripts/check is in extend-include and is not a file that begins with a python line and has no .py in its name: delete the entry",
        "scripts/smoke.py is in extend-include and is not a file that begins with a python line and has no .py in its name: delete the entry",
        "scripts/gone is in extend-include and is not a file that begins with a python line and has no .py in its name: delete the entry",
        "scripts/release is in extend-include twice",
    ]
