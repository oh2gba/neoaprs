#!/usr/bin/env python3
"""The unused-class check of the page's style sheets (ui/src/styles/*.css, the stage ui-lint of scripts/check): every class a rule names must be written somewhere in the page's source.

    scripts/css-unused.py              exit 1 and list the classes of the style sheets that no .vue, .ts or .html file of ui/ mentions
    scripts/css-unused.py ROOT         the same for another tree (the tests give it a small one)

A class is mentioned when its name stands as a whole word anywhere in ui/src (the tests and the style sheets themselves left out) or in ui/index.html. Classes the page makes up at run time are not
written whole in the source: PREFIXES says, for each, which code builds them (the check also fails when that code is gone, or when no rule has the prefix any more, so the list cannot go stale);
LIBRARY_PREFIXES are the classes of the map library, which the page styles but does not write."""
import re
import sys
from pathlib import Path

# the start of a class name that code adds a value to (`hop-${chip.kind}`): the file that does it
PREFIXES = {
    "hop-": "components/ChainChips.vue",
    "link-": "components/PanelFooter.vue",
    "mark-": "components/MessageMark.vue",
    "size-": "composables/useLayout.ts",
    "state-": "components/ConversationThread.vue",
    "stn--fade-": "lib/markerdom.ts",
    "tnc-": "components/RadioStatus.vue",
    "tone-": "components/TrendChart.vue",
    "view-": "composables/useLayout.ts",
}
LIBRARY_PREFIXES = ("maplibregl-",)


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def selector_text(css: str) -> str:
    """The style sheet without the declarations (what is left is the selectors and the at-rules), and without attribute selectors."""
    css = strip_comments(css)
    while True:
        smaller = re.sub(r"\{[^{}]*\}", ";", css)
        if smaller == css:
            break
        css = smaller
    return re.sub(r"\[[^\]]*\]", "", css)


def defined_classes(css: str) -> set[str]:
    return set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", selector_text(css)))


def page_sources(root: Path) -> dict[str, str]:
    """The files that write class names: the .vue and .ts files of ui/src (not the tests, not the style sheets) and ui/index.html, by path under ui/src."""
    src = root / "ui" / "src"
    files = [p for p in [*src.rglob("*.vue"), *src.rglob("*.ts")] if not p.name.endswith(".test.ts") and "test" not in p.relative_to(src).parts]
    found = {p.relative_to(src).as_posix(): p.read_text(encoding="utf-8") for p in files}
    index = root / "ui" / "index.html"
    if index.is_file():
        found["../index.html"] = index.read_text(encoding="utf-8")
    return found


def problems(root: Path) -> list[str]:
    sheets = sorted((root / "ui" / "src" / "styles").glob("*.css"))
    classes = set().union(*(defined_classes(p.read_text(encoding="utf-8")) for p in sheets)) if sheets else set()
    sources = page_sources(root)
    everything = "\n".join(sources.values())
    out: list[str] = []
    for prefix, where in PREFIXES.items():
        if not any(name.startswith(prefix) for name in classes):
            out.append(f"the prefix {prefix!r} of PREFIXES has no rule in the style sheets: take it out of scripts/css-unused.py")
        elif f"{prefix}${{" not in sources.get(where, ""):
            out.append(f"the prefix {prefix!r} is not built in {where} any more (`{prefix}${{...}}`): its rules are dead, or the code moved (scripts/css-unused.py)")
    for name in sorted(classes):
        if name.startswith(tuple(PREFIXES) + LIBRARY_PREFIXES):
            continue
        if not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", everything):
            out.append(f"the class .{name} has a rule but no .vue, .ts or .html file of ui/ mentions it: delete the rule")
    return out


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    found = problems(root)
    if found:
        print("\n".join(found))
        return 1
    print("every class of the style sheets is used")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
