"""No main radio is left (the owner, 16 November 2026: "all radio's are equal"): not one `main_radio`, `mainRadio`, `MainRadio` or "main radio" (any case, the words apart by a space, a line break, a dash
or an underscore) in the daemon (neoaprs/), the page's source (ui/src/), the manual (docs/manual/) or the site (site/). Excepted by file name: the frozen migration steps, which name the setting they delete
(`neoaprs/migrationsteps*.py`), and the page as it is built (neoaprs/page/), which is ui/src/ built and is held to it by tests/test_page_build.py. The changelog's released sections and aprs-reference/ are
history and are not read."""
import re
from pathlib import Path

from tests.conftest import ROOT

WHERE = ("neoaprs", "ui/src", "docs/manual", "site")
WORDS = re.compile(r"(?<![a-z])main(?:[\s_-]|//|#|\*)*radio", re.IGNORECASE)    # "main radio", "Main radio", "main_radio", "main-radio", "mainradio", a comment's line break between
CODE = re.compile(r"MainRadio|mainRadio")                            # inside a longer name: useMainRadio, isMainRadio
FROZEN = re.compile(r"migrationsteps\w*\.py")


def excepted(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return (rel.parts[0] == "neoaprs" and (FROZEN.fullmatch(path.name) is not None or rel.parts[1:2] == ("page",))) or "node_modules" in rel.parts


def texts() -> list[tuple[Path, str]]:
    """Every file under the places read that is text (a picture, a font, a database is not), but those excepted."""
    found = []
    for top in WHERE:
        for path in sorted((ROOT / top).rglob("*")):
            if not path.is_file() or excepted(path):
                continue
            try:
                found.append((path, path.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                continue
    return found


def said(text: str) -> list[str]:
    return [m.group(0) for m in (*WORDS.finditer(text), *CODE.finditer(text))]


def test_the_words_are_found_however_they_are_written() -> None:
    for text in ("the main radio", "Main radio", "station/main_radio", "mainRadio()", "MainRadio.vue", "useMainRadio", "the main\n// radio", "MAIN-RADIO"):
        assert said(text), text
    for text in ("the domain radio", "remain radios", "main(radios)", "the main tab", "radio main"):
        assert not said(text), text


def test_no_main_radio_is_left_in_the_daemon_the_page_the_manual_or_the_site() -> None:
    files = texts()
    assert len(files) > 500 and any(path.suffix == ".vue" for path, _ in files) and any(path.parent.name == "manual" for path, _ in files), "the places are read"
    left = [f"{path.relative_to(ROOT)}: {', '.join(sorted(set(said(text))))}" for path, text in files if said(text)]
    assert left == [], "all radios are equal: " + "; ".join(left)


def test_only_the_frozen_steps_are_excepted_and_one_of_them_names_the_setting() -> None:
    steps = sorted(p for p in (ROOT / "neoaprs").glob("migrationsteps*.py"))
    assert any("station/main_radio" in p.read_text(encoding="utf-8") for p in steps), "step 34 deletes the setting by its name"
    assert not excepted(ROOT / "neoaprs" / "migrations.py") and not excepted(ROOT / "neoaprs" / "radiospec.py") and not excepted(ROOT / "ui" / "src" / "App.vue")
