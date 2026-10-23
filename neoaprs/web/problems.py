"""The words a page is told when a command does not fit neoaprs/web/protocol.py: pydantic's errors for the frame, as one short line naming the field and the problem."""
from collections.abc import Callable
from typing import Any

_PROBLEMS = {
    "missing": "is missing",
    "extra_forbidden": "is not a field of this command",
    "int_type": "must be a whole number", "int_parsing": "must be a whole number", "int_from_float": "must be a whole number",
    "int_parsing_size": "is too big", "float_type": "must be a number", "float_parsing": "must be a number",
    "finite_number": "must be a finite number", "bool_type": "must be true or false", "bool_parsing": "must be true or false",
    "string_type": "must be text", "dict_type": "must be an object", "list_type": "must be a list", "tuple_type": "must be a list",
    "model_type": "must be an object", "model_attributes_type": "must be an object",
}


# the problems whose words carry a number or a name out of the error's context: kind -> words from (context, error)
_FROM_CONTEXT: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "greater_than_equal": lambda ctx, err: f"must be at least {ctx.get('ge')}",
    "greater_than": lambda ctx, err: f"must be more than {ctx.get('gt')}",
    "less_than_equal": lambda ctx, err: f"must be at most {ctx.get('le')}",
    "less_than": lambda ctx, err: f"must be less than {ctx.get('lt')}",
    "string_too_long": lambda ctx, err: f"is too long (at most {ctx.get('max_length')} characters)",
    "too_long": lambda ctx, err: f"has too many items (at most {ctx.get('max_length')})",
    "literal_error": lambda ctx, err: f"must be one of {ctx.get('expected')}",
    "string_pattern_mismatch": lambda ctx, err: "is not in the expected form",
    "value_error": lambda ctx, err: str(ctx.get("error") or err["msg"]),
}


def _problem(err: dict[str, Any]) -> str:
    kind, ctx = str(err["type"]), err.get("ctx") or {}
    if kind in _PROBLEMS:
        return _PROBLEMS[kind]
    if kind in _FROM_CONTEXT:
        return _FROM_CONTEXT[kind](ctx, err)
    return str(err["msg"])


def describe_errors(name: str, errors: list[Any]) -> str:
    """One short line for the page: 'qso_delete: id: must be a whole number'. At most three problems; the first ones are the ones to fix."""
    parts = []
    for err in errors[:3]:
        loc = [str(x) for x in err["loc"][1:]] if err["loc"] and err["loc"][0] == name else [str(x) for x in err["loc"]]     # the tag of the union is not a field
        text = _problem(err)
        parts.append(f"{'.'.join(loc)}: {text}" if loc else text)
    more = f" (and {len(errors) - 3} more)" if len(errors) > 3 else ""
    return f"{name}: " + "; ".join(parts) + more

