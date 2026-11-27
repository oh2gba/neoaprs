"""Find the daemon's coded refusals in its source: each code with `params` and sentence template.

scripts/gen-protocol.py writes the result as ui/src/protocol/errors.json, which the page's
catalogue must cover. In a template `{name}` is a value, `{{` a brace, `{*}` other text."""

import ast
import re
from pathlib import Path
from typing import Any

CODE = re.compile(r"[a-z_]+(\.[a-z_]+)*")
PREFIX = re.compile(r"^(?:[a-z_/]+|\{\*\}): ")


def _same(a: ast.expr) -> str:
    """Return an expression for comparison, with `round(x)` and `int(x)` reduced to x."""
    if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id in ("round", "int") and len(a.args) == 1:
        return _same(a.args[0])
    return ast.unparse(a)


def _escape(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def template(node: ast.expr, params: dict[str, str]) -> str | None:
    """Return the sentence of a string or f-string, or None for any other expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _escape(node.value)
    if not isinstance(node, ast.JoinedStr):
        return None
    out = ""
    for part in node.values:
        if isinstance(part, ast.Constant):
            out += _escape(str(part.value))
            continue
        assert isinstance(part, ast.FormattedValue)
        name = next((k for k, v in params.items() if v == _same(part.value)), None)
        out += "{*}" if name is None else ("'{%s}'" % name if part.conversion == ord("r") else "{%s}" % name)
    return out


def _params(call: ast.Call) -> dict[str, str]:
    """Return the values a refusal passes, by name, as their expressions."""
    found: dict[str, str] = {}
    dicts = [kw.value for kw in call.keywords if kw.arg == "params"] + [a for a in call.args if isinstance(a, ast.Dict)]
    for d in dicts:
        if isinstance(d, ast.Dict):
            found.update(
                {k.value: _same(v) for k, v in zip(d.keys, d.values, strict=True) if isinstance(k, ast.Constant)}
            )
    found.update(
        {kw.arg: _same(kw.value) for kw in call.keywords if kw.arg and kw.arg not in ("code", "params", "key", "id")}
    )
    return found


def _codes(node: ast.expr | None) -> list[str]:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and CODE.fullmatch(node.value)
        and node.value != "other"
    ):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _codes(node.body) + _codes(node.orelse)
    return []


def _refusal(call: ast.Call) -> tuple[list[str], ast.expr | None] | None:
    """Return the codes and sentence of a call that is a refusal with a code, else None."""
    name = (
        call.func.id
        if isinstance(call.func, ast.Name)
        else call.func.attr
        if isinstance(call.func, ast.Attribute)
        else ""
    )
    keyword = next((kw.value for kw in call.keywords if kw.arg == "code"), None)
    if keyword is not None:
        return _codes(keyword), call.args[0] if call.args else None
    if name == "SettingError" and len(call.args) == 4:
        return _codes(call.args[1]), call.args[3]
    if len(call.args) >= 2 and (name.endswith("Error") or name == "Reason"):
        return _codes(call.args[1]), call.args[0]
    return None


def _sentences(text: ast.expr | None, count: int, params: dict[str, str]) -> list[str | None]:
    """Return one sentence for each code; a choice of two strings goes with a choice of two
    codes."""
    if isinstance(text, ast.IfExp) and count == 2:
        return [template(text.body, params), template(text.orelse, params)]
    return [template(text, params)] * count if text is not None else [None] * count


def found_in(source: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for call in (n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)):
        refusal = _refusal(call)
        if refusal is None or not refusal[0]:
            continue
        codes, text = refusal
        params = _params(call)
        for code, sentence in zip(codes, _sentences(text, len(codes), params), strict=True):
            out.setdefault(code, []).append(
                {"params": sorted(params), "text": None if sentence is None else PREFIX.sub("", sentence)}
            )
    return out


def error_codes(package: Path) -> dict[str, dict[str, Any]]:
    """Return every code under `package` with the value names and sentences of all its uses."""
    merged: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(package.rglob("*.py")):
        for code, uses in found_in(path.read_text(encoding="utf-8")).items():
            merged.setdefault(code, []).extend(uses)
    result: dict[str, dict[str, Any]] = {}
    for code in sorted(merged):
        uses = merged[code]
        texts = sorted({u["text"] for u in uses if u["text"] is not None})
        result[code] = {"params": sorted({p for u in uses for p in u["params"]}), "text": texts}
    return result
