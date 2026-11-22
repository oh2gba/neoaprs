"""What the architecture and size ratchets measure: imports, Signal.connect sites and sizes.

Everything works on a tree: a dict from a repository-relative path to the text of the file.
`load_tree()` reads the real one; the tests of the checks build small trees.

    python -m tests.support.codemap             print the offenders of the size limits
    python -m tests.support.codemap --tighten   lower the ceilings in tests/size_baseline.json
"""
import ast
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("neoaprs",)
BASELINE = ROOT / "tests" / "size_baseline.json"

# The limits (docs/ARCHITECTURE.md). Lines are lines of code: blank lines, comment lines and
# docstrings do not count.
MODULE_LINES = 400
CLASS_LINES = 300
FUNCTION_LINES = 60
COMPLEXITY = 12
LIMITS = {"modules": MODULE_LINES, "classes": CLASS_LINES, "functions": FUNCTION_LINES, "complexity": COMPLEXITY}

Tree = dict[str, str]


def load_tree(root: Path = ROOT) -> Tree:
    out: Tree = {}
    for package in PACKAGES:
        for path in sorted((root / package).rglob("*.py")):
            if "__pycache__" not in path.parts:
                out[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
    return out


def module_name(rel: str) -> str:
    """'neoaprs/clock.py' -> 'neoaprs.clock'; 'neoaprs/__init__.py' -> 'neoaprs';
    'neoaprs/services/x.py' -> 'neoaprs.services.x'."""
    parts = rel.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


# ---- imports -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Import:
    importer: str        # module name of the file
    # A module of the tree ("neoaprs.clock") or a library name ("sqlite3").
    target: str
    internal: bool       # target is in neoaprs/
    line: int

    @property
    def top(self) -> str:
        return self.target.split(".")[0]


def _resolve(importer: str, is_package: bool, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    parts = importer.split(".")
    package = parts if is_package else parts[:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, *([node.module] if node.module else [])])


def imports_of(rel: str, source: str, modules: frozenset[str]) -> list[Import]:
    """Every import in the file at any depth, resolved to the module it names."""
    me = module_name(rel)
    is_package = rel.endswith("/__init__.py")
    found: list[Import] = []

    def add(target: str, line: int) -> None:
        found.append(Import(me, target, target.split(".")[0] in PACKAGES, line))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(me, is_package, node)
            for alias in node.names:
                # `from neoaprs import signal` names the module neoaprs.signal.
                sub = f"{base}.{alias.name}"
                add(sub if sub in modules else base, node.lineno)
    return found


def import_graph(tree: Tree) -> dict[str, list[Import]]:
    modules = frozenset(module_name(rel) for rel in tree)
    return {module_name(rel): imports_of(rel, source, modules) for rel, source in tree.items()}


def find_cycle(graph: dict[str, list[Import]]) -> list[str]:
    """One import cycle as a list of modules (first == last), or []."""
    edges = {m: sorted({i.target for i in imps if i.internal and i.target != m}) for m, imps in graph.items()}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(m: str) -> list[str]:
        state[m] = 1
        stack.append(m)
        for n in edges.get(m, []):
            if state.get(n) == 1:
                return [*stack[stack.index(n):], n]
            if state.get(n) is None:
                cycle = visit(n)
                if cycle:
                    return cycle
        stack.pop()
        state[m] = 2
        return []

    for m in sorted(edges):
        if state.get(m) is None:
            cycle = visit(m)
            if cycle:
                return cycle
    return []


# ---- Signal wiring -------------------------------------------------------------------------------

def connect_sites(tree: Tree) -> dict[str, int]:
    """Per file, the number of `x.connect(...)` calls that are Signal connects (not sockets, sqlite3
    or awaited)."""
    counts: dict[str, int] = {}
    for rel, source in tree.items():
        parsed = ast.parse(source)
        awaited = {id(node.value) for node in ast.walk(parsed) if isinstance(node, ast.Await)}
        n = sum(
            1 for node in ast.walk(parsed)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connect" and id(node) not in awaited
            and not (isinstance(node.func.value, ast.Name) and node.func.value.id in ("sqlite3", "sock"))
        )
        if n:
            counts[rel] = n
    return counts


# ---- SQL -----------------------------------------------------------------------------------------

SQL_CALLS = frozenset({"execute", "executemany", "executescript"})
# The ways of reaching the file that the database thread (neoaprs/db.py) replaced.
FORBIDDEN_NAMES = frozenset({"_flush", "before_write"})


def sql_sites(tree: Tree) -> dict[str, tuple[bool, int]]:
    """Per file with SQL: whether it imports sqlite3 and how many execute calls it makes."""
    found: dict[str, tuple[bool, int]] = {}
    for rel, source in tree.items():
        imports, calls = False, 0
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports = imports or any(a.name == "sqlite3" or a.name.startswith("sqlite3.") for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports = imports or (node.level == 0 and (node.module or "").split(".")[0] == "sqlite3")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in SQL_CALLS:
                calls += 1
        if imports or calls:
            found[rel] = (imports, calls)
    return found


SQL_STATEMENT = re.compile(r"(UPDATE|INSERT|SELECT|DELETE) ")


def sql_strings(tree: Tree) -> dict[str, list[int]]:
    """The lines, per file, of a string literal that begins like an upper-case SQL statement.

    A docstring, a lone string statement and a comment are not counted; the start of an f-string and
    a piece of a concatenation are.
    """
    found: dict[str, list[int]] = {}
    for rel, source in tree.items():
        module = ast.parse(source)
        prose = {id(node.value) for node in ast.walk(module) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
        lines = sorted({node.lineno for node in ast.walk(module)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose and SQL_STATEMENT.match(node.value)})
        if lines:
            found[rel] = lines
    return found


def forbidden_names(tree: Tree) -> dict[str, list[int]]:
    """The lines, per file, that define or use a name of FORBIDDEN_NAMES."""
    found: dict[str, list[int]] = {}
    for rel, source in tree.items():
        lines = sorted({
            node.lineno for node in ast.walk(ast.parse(source))
            if (isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES) or (isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES)
            or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FORBIDDEN_NAMES)
        })
        if lines:
            found[rel] = lines
    return found


# ---- sizes ---------------------------------------------------------------------------------------

def complexity_of(node: ast.AST) -> int:
    """McCabe's number as ruff's C901 counts it: 1 plus each if/elif, loop, except, case and
    comprehension clause.

    Boolean operators and conditional expressions do not count; a nested function counts into its
    parent.
    """
    n = 1
    for sub in ast.walk(node):
        if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.comprehension)):
            n += 1
            if isinstance(sub, (ast.For, ast.AsyncFor, ast.While)) and sub.orelse:
                n += 1
        elif isinstance(sub, ast.match_case):
            n += 1
    return n


def code_lines(source: str) -> set[int]:
    """Line numbers that hold code: not blank, not only a comment, not part of a docstring."""
    lines = {n for n, text in enumerate(source.splitlines(), 1) if text.strip() and not text.lstrip().startswith("#")}
    for node in ast.walk(ast.parse(source)):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                lines -= set(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def _span(node: ast.stmt, code: set[int]) -> int:
    return len(code & set(range(node.lineno, (node.end_lineno or node.lineno) + 1)))


def _units(body: list[ast.stmt], prefix: str) -> Iterator[tuple[str, str, ast.stmt]]:
    """(kind, name, node) of every class and function below `body`, with dotted names; nested ones
    are not listed."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            name = f"{prefix}{node.name}"
            yield "class", name, node
            yield from _units(node.body, f"{name}.")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield "function", f"{prefix}{node.name}", node
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            yield from _units(getattr(node, "body", []), prefix)
            yield from _units(getattr(node, "orelse", []), prefix)


def measure(tree: Tree) -> dict[str, dict[str, int]]:
    """Sizes of every module, class and function (lines and complexity), not only the offenders."""
    out: dict[str, dict[str, int]] = {"modules": {}, "classes": {}, "functions": {}, "complexity": {}}
    for rel, source in tree.items():
        code = code_lines(source)
        out["modules"][rel] = len(code)
        for kind, name, node in _units(ast.parse(source).body, ""):
            key = f"{rel}::{name}"
            if kind == "class":
                out["classes"][key] = _span(node, code)
            else:
                out["functions"][key] = _span(node, code)
                out["complexity"][key] = complexity_of(node)
    return out


def offenders(measured: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {kind: {k: v for k, v in sorted(values.items()) if v > LIMITS[kind]} for kind, values in measured.items()}


def load_baseline() -> dict[str, dict[str, int]]:
    data: dict[str, dict[str, int]] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {kind: dict(data.get(kind, {})) for kind in LIMITS}


def tighten(baseline: dict[str, dict[str, int]], now: dict[str, dict[str, int]]) -> tuple[dict[str, dict[str, int]], list[str]]:
    """The baseline with every ceiling lowered to today's size and within-limit entries dropped.

    It never raises a ceiling or adds an entry. Return the new baseline and what it refused.
    """
    out: dict[str, dict[str, int]] = {kind: {} for kind in LIMITS}
    refused: list[str] = []
    for kind, entries in baseline.items():
        for key, ceiling in entries.items():
            size = now[kind].get(key)
            if size is None or size <= LIMITS[kind]:
                # Gone, or back within the limit: the entry has done its job.
                continue
            if size > ceiling:
                refused.append(f"{kind} {key}: {size} is over its ceiling {ceiling}")
            out[kind][key] = min(size, ceiling)
    for kind, values in offenders(now).items():
        refused.extend(f"{kind} {key}: {size} is over the limit {LIMITS[kind]} and not in the baseline" for key, size in values.items() if key not in out[kind])
    return out, refused


def main(argv: list[str]) -> int:
    now = measure(load_tree())
    if argv[:1] == ["--tighten"]:
        new, refused = tighten(load_baseline(), now)
        BASELINE.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("\n".join(refused) or "baseline tightened")
        return 1 if refused else 0
    print(json.dumps(offenders(now), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
