"""The refusals of the daemon that carry a code, found in its source: for each code the values (`params`) it passes and the English sentence it writes, as a template of the page's message syntax (`{name}` is a value, `{{` a
literal brace, `{*}` a part of the sentence that is not one of the values). scripts/gen-protocol.py writes this as ui/src/protocol/errors.json; the page's catalogue (ui/src/i18n/en.ts) is held to it by a test, so that a code
the daemon gains has a sentence on the page, and the sentence is the daemon's.

A refusal is a call that has a code in its second argument (`CodedError(text, "setting.range", value=...)`, `SettingError(key, code, {...}, text)`, `UserError(text, code, params={...})`) or in `code=` (`conn.error(text, code=...)`).
The sentence is its f-string with the `<command>: ` and `<setting>: ` in front taken off (the page puts the reason where it belongs); an expression that is one of the values becomes `{name}`, `{x!r}` becomes `'{name}'`."""
import ast
import re
from pathlib import Path
from typing import Any

CODE = re.compile(r"[a-z_]+(\.[a-z_]+)*")
PREFIX = re.compile(r"^(?:[a-z_/]+|\{\*\}): ")


def _same(a: ast.expr) -> str:
    """An expression for comparison: `round(x)` and `int(x)` are x (the value passed is the rounded one)."""
    if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id in ("round", "int") and len(a.args) == 1:
        return _same(a.args[0])
    return ast.unparse(a)


def _escape(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")


def template(node: ast.expr, params: dict[str, str]) -> str | None:
    """The sentence of an f-string or a string, or None for any other expression (a sum of strings, a call)."""
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
    """The values a refusal passes, by name, as the expressions that make them."""
    found: dict[str, str] = {}
    dicts = [kw.value for kw in call.keywords if kw.arg == "params"] + [a for a in call.args if isinstance(a, ast.Dict)]
    for d in dicts:
        if isinstance(d, ast.Dict):
            found.update({k.value: _same(v) for k, v in zip(d.keys, d.values, strict=True) if isinstance(k, ast.Constant)})
    found.update({kw.arg: _same(kw.value) for kw in call.keywords if kw.arg and kw.arg not in ("code", "params", "key")})
    return found


def _codes(node: ast.expr | None) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and CODE.fullmatch(node.value) and node.value != "other":
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _codes(node.body) + _codes(node.orelse)
    return []


def _refusal(call: ast.Call) -> tuple[list[str], ast.expr | None] | None:
    """The codes and the sentence of a call that is a refusal with a code, else None."""
    name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""
    keyword = next((kw.value for kw in call.keywords if kw.arg == "code"), None)
    if keyword is not None:
        return _codes(keyword), call.args[0] if call.args else None
    if name == "SettingError" and len(call.args) == 4:
        return _codes(call.args[1]), call.args[3]
    if len(call.args) >= 2 and name.endswith("Error"):
        return _codes(call.args[1]), call.args[0]
    return None


def _sentences(text: ast.expr | None, count: int, params: dict[str, str]) -> list[str | None]:
    """One sentence for each code: a choice between two strings goes with a choice between two codes."""
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
            out.setdefault(code, []).append({"params": sorted(params), "text": None if sentence is None else PREFIX.sub("", sentence)})
    return out


def error_codes(package: Path) -> dict[str, dict[str, Any]]:
    """Every code under `package`: the names of its values (all the calls that use the code, together) and the sentences it is written with."""
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
