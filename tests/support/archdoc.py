"""The tables of docs/ARCHITECTURE.md that are data of tests/test_architecture.py, made from that data.

The layer table and the lists of what is still allowed (SQL outside its homes, wiring outside the root, imports against the layers) go stale in the document each time the test changes.
They are blocks between `<!-- doc-arch:NAME -->` and `<!-- /doc-arch -->` in the document; `scripts/doc-arch --write` makes them, `tests/test_docs.py` fails when one differs.
"""
import re
from collections.abc import Sequence

from tests import test_architecture as arch

BLOCK = re.compile(r"(<!-- doc-arch:(\w+)[^>\n]*-->\n)(.*?)(<!-- /doc-arch -->)", re.S)
SPECIAL = {"services": ", and everything in `neoaprs/services/`", "delivery": ""}


def _row(*cells: object) -> str:
    return "| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |"


def _table(head: tuple[str, ...], rows: Sequence[tuple[object, ...]]) -> str:
    return "\n".join([_row(*head), _row(*["---"] * len(head)), *[_row(*r) for r in rows]]) + "\n"


def _path(module: str) -> str:
    return f"`{module.replace('.', '/')}.py`"


def layers() -> str:
    rows = []
    for layer, names in arch.LAYERS.items():
        listed = " ".join(n for n in names if n != "neoaprs")
        extra = SPECIAL.get(layer, "")
        if layer == "delivery":
            modules = "`neoaprs/web/*`, `neoaprs/cli/*`, `neoaprs/desktop/*`, `neoaprs/daemon`, `neoaprs/__main__`"
        elif listed:
            modules = f"`{listed}`" + extra
        else:
            modules = extra.removeprefix(", and ") or "-"
        may = ", ".join(sorted(arch.MAY_IMPORT[layer], key=list(arch.LAYERS).index))
        not_may = ", ".join(other for other in arch.LAYERS if other not in arch.MAY_IMPORT[layer]) or "-"
        rows.append((layer, modules, may, not_may + (", and any I/O library" if layer in arch.PURE else "")))
    return _table(("layer", "modules", "may import", "may not import"), rows)


def rules() -> str:
    bases = ", ".join(f"`{m}`" for m in sorted(arch.ADAPTER_BASES))
    pairs = ", ".join(f"`{a}` and `{b}`" for a, b in sorted(arch.ADAPTER_SIBLINGS)) or "none yet"
    tornado = ", ".join(f"`{m}`" for m in sorted(arch.TORNADO_HOMES))
    pydantic = ", ".join(_path(m) for m in sorted(arch.PYDANTIC_HOMES)) or "none yet"
    return "\n".join([
        f"* The I/O libraries that foundation and domain may not import (pyserial, `serial`, is one of them): `{' '.join(sorted(arch.IO_LIBRARIES))}`.",
        "* pyserial (`serial`) only in the adapters layer.",
        f"* Among the adapters only the bases every feed shares may be imported: {bases}; and the sibling pairs: {pairs}.",
        f"* bleak (the extra `ble`) only in {', '.join(_path(m) for m in sorted(arch.BLEAK_HOMES))}.",
        f"* Tornado only in {tornado + ' and ' if tornado else ''}`neoaprs/web/`.",
        f"* pydantic only in the wire modules of `neoaprs/web/`: {pydantic}.",
        f"* The desktop app's toolkits (`{' '.join(sorted(arch.TOOLKITS))}`, the extra `app`) only in the shells: {', '.join(_path(m) for m in sorted(arch.TOOLKIT_HOMES))}.",
    ]) + "\n"


def allowed() -> str:
    rows = [(f"`{a}` imports `{b}`", why) for (a, b), why in sorted(arch.ALLOWED.items())] or [("-", "nothing is allowed against the layers")]
    return _table(("import against the layers (`ALLOWED`)", "why it is there"), rows)


def wiring() -> str:
    roots = ", ".join(f"`{r}`" for r in sorted(arch.COMPOSITION_ROOTS)) or "none"
    rows: list[tuple[object, ...]] = [(f"`{rel}`", n, why) for rel, (n, why) in sorted(arch.CONNECTS.items())] or [("-", "-", "nothing connects a signal outside the places above")]
    return f"Places for `Signal.connect` (`COMPOSITION_ROOTS`): {roots}.\n\n" + _table(("connects outside them (`CONNECTS`)", "how many", "why"), rows)


def sql_homes() -> str:
    return _table(("file (`SQL_HOMES`)", "what it is"), [(f"`{rel}`", why) for rel, why in sorted(arch.SQL_HOMES.items())])


def sql_elsewhere() -> str:
    rows: list[tuple[object, ...]] = [(f"`{rel}`", "yes" if imports else "no", calls, why) for rel, (imports, calls, why) in sorted(arch.SQL_ELSEWHERE.items())] or [("-", "-", "-", "no file outside the homes touches SQL")]
    return _table(("file (`SQL_ELSEWHERE`)", "imports `sqlite3`", "calls of `execute`", "why"), rows)


MAKERS = {"layers": layers, "rules": rules, "allowed": allowed, "wiring": wiring, "sql_homes": sql_homes, "sql_elsewhere": sql_elsewhere}


def blocks_of(text: str) -> dict[str, str]:
    return {m.group(2): m.group(3) for m in BLOCK.finditer(text)}


def stale_blocks(text: str) -> list[str]:
    """The blocks of the generated kind that the text lacks or whose content is not what the test's data says now."""
    found = blocks_of(text)
    return [name for name, make in MAKERS.items() if found.get(name) != make()]


def refreshed(text: str) -> str:
    """The text with every block made again from the data."""
    def one(m: re.Match[str]) -> str:
        return m.group(1) + MAKERS[m.group(2)]() + m.group(4)
    return BLOCK.sub(one, text)
