#!/usr/bin/env python3
"""Check that every class in ui/src/styles/*.css appears in the page's source.

    scripts/css-unused.py              exit 1 and list classes no .vue, .ts or .html file mentions
    scripts/css-unused.py ROOT         the same for another tree

Classes built at run time are listed in PREFIXES with the file that builds them."""

import re
import sys
from pathlib import Path

# Start of a class name that code completes (`hop-${chip.kind}`) -> the file that does it.
PREFIXES = {
    "gps-": "lib/beaconstatus.ts",
    "hop-": "components/ChainChips.vue",
    "mark-": "components/MessageMark.vue",
    "size-": "composables/useLayout.ts",
    "state-": "components/ConversationThread.vue",
    "stn--fade-": "lib/markerdom.ts",
    "tnc-": "lib/tncstatus.ts",
    "tone-": "components/TrendChart.vue",
    "view-": "composables/useLayout.ts",
}
LIBRARY_PREFIXES = ("maplibregl-",)


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def selector_text(css: str) -> str:
    """Return the style sheet reduced to its selectors and at-rules."""
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
    """Return the files that write class names (not tests or style sheets), by path under ui/src."""
    src = root / "ui" / "src"
    files = [
        p
        for p in [*src.rglob("*.vue"), *src.rglob("*.ts")]
        if not p.name.endswith(".test.ts") and "test" not in p.relative_to(src).parts
    ]
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
            out.append(
                f"the prefix {prefix!r} of PREFIXES has no rule in the style sheets: take it out of scripts/css-unused.py"
            )
        elif f"{prefix}${{" not in sources.get(where, ""):
            out.append(
                f"the prefix {prefix!r} is not built in {where} any more (`{prefix}${{...}}`): its rules are dead, or the code moved (scripts/css-unused.py)"
            )
    for name in sorted(classes):
        if name.startswith(tuple(PREFIXES) + LIBRARY_PREFIXES):
            continue
        if not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", everything):
            out.append(
                f"the class .{name} has a rule but no .vue, .ts or .html file of ui/ mentions it: delete the rule"
            )
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
