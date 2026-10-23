"""The unused-class check of the page's style sheets (scripts/css-unused.py, the stage ui-lint of scripts/check): a class a rule names that no source file writes is reported; a class the page builds at run
time (a prefix of PREFIXES, with the code that builds it) and a class of the map library are not; a prefix whose code or rules are gone is reported too; and the style sheets of this tree are clean."""
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from tests.support.ptyline import posix_only

pytestmark = posix_only      # (a development check of the repository, not the product)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "css-unused.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("css_unused", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


css_unused = load()


@pytest.fixture(autouse=True)
def no_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A small page has none of the prefixes of the real one (the last test runs the script as a process, with its own)."""
    monkeypatch.setattr(css_unused, "PREFIXES", {})


def tree(tmp_path: Path, css: str, vue: str = "", **files: str) -> Path:
    """A small page: one style sheet, one component, and more files by path under ui/src (`__` for a folder separator)."""
    (tmp_path / "ui" / "src" / "styles").mkdir(parents=True)
    (tmp_path / "ui" / "src" / "styles" / "a.css").write_text(css, encoding="utf-8")
    (tmp_path / "ui" / "src" / "A.vue").write_text(vue, encoding="utf-8")
    for name, text in files.items():
        path = tmp_path / "ui" / "src" / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def named(root: Path) -> list[str]:
    """What the check complains about: the class or the prefix of each line."""
    return [line.split()[2] for line in css_unused.problems(root)]


def test_a_class_that_no_source_file_writes_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path, ".used, .dead p { color: red; } .also.dead2 { top: 0; }", '<div class="used also"></div>')
    assert named(root) == [".dead", ".dead2"]


def test_a_class_is_a_whole_word_and_comments_attributes_and_declarations_are_no_classes(tmp_path: Path) -> None:
    css = "/* .in-a-comment */ .real { background: url(x.png); width: 1.5em; } a[href$='.pdf'] { top: 0 } .real-big { top: 0 }"
    root = tree(tmp_path, css, '<div class="real"></div>')
    assert named(root) == [".real-big"]


def test_a_class_the_page_builds_at_run_time_is_not_reported_while_its_code_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(css_unused, "PREFIXES", {"tone-": "lib/tone.ts"})
    root = tree(tmp_path, ".tone-temp { color: red; } .maplibregl-popup { top: 0; }", "")
    (root / "ui" / "src" / "lib").mkdir()
    (root / "ui" / "src" / "lib" / "tone.ts").write_text("const c = `tone-${tone}`;", encoding="utf-8")
    assert named(root) == []
    (root / "ui" / "src" / "lib" / "tone.ts").write_text("const c = 'tone-temp';", encoding="utf-8")
    assert named(root) == ["'tone-'"]


def test_a_prefix_with_no_rule_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(css_unused, "PREFIXES", {"tone-": "lib/tone.ts"})
    root = tree(tmp_path, ".other { top: 0; }", '<i class="other"></i>')
    (root / "ui" / "src" / "lib").mkdir()
    (root / "ui" / "src" / "lib" / "tone.ts").write_text("const c = `tone-${tone}`;", encoding="utf-8")
    assert named(root) == ["'tone-'"]


def test_tests_and_the_test_folder_do_not_count_as_a_mention(tmp_path: Path) -> None:
    root = tree(tmp_path, ".only-in-a-test { top: 0; }", "", **{"A.test.ts": "find('.only-in-a-test')", "test__helper.ts": "'only-in-a-test'"})
    assert named(root) == [".only-in-a-test"]


def test_the_style_sheets_of_this_tree_are_clean() -> None:
    if not (ROOT / "ui" / "src" / "styles").is_dir():
        pytest.skip("no ui/ in this tree")
    done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
