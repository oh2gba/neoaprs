"""Hypothesis strategies that damage real inputs: bytes and text flipped, cut, repeated and filled in,
and JSON whose values change type, vanish or grow, for the property tests of the parsers."""

import json
from typing import Any

from hypothesis import strategies as st

# numbers a JSON parser gives that a float or an int() of a reader may choke on
ODD_NUMBERS = st.sampled_from(
    [
        0,
        -1,
        1,
        2**31,
        2**63,
        2**64,
        -(2**63),
        10**400,
        -(10**400),
        1e308,
        -1e308,
        5e-324,
        -0.0,
        float("nan"),
        float("inf"),
    ]
)
JSON_LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(),
    ODD_NUMBERS,
    st.text(max_size=12),
    st.sampled_from(["", " ", "ground", "nan", "inf", "-1", "1e999", "0x10", "true", "\x00", "@@@@"]),
)
JSON_VALUES = st.recursive(
    JSON_LEAVES,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4),
    max_leaves=8,
)


def _paths(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    found = [path]
    if isinstance(value, dict):
        for key, inner in value.items():
            found += _paths(inner, (*path, key))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found += _paths(inner, (*path, index))
    return found


def _replaced(value: Any, path: tuple[Any, ...], new: Any, drop: bool) -> Any:
    if not path:
        return new
    head, rest = path[0], path[1:]
    if isinstance(value, dict):
        copy = dict(value)
        if drop and not rest:
            del copy[head]
        else:
            copy[head] = _replaced(value[head], rest, new, drop)
        return copy
    copy_list = list(value)
    if drop and not rest:
        del copy_list[head]
    else:
        copy_list[head] = _replaced(value[head], rest, new, drop)
    return copy_list


@st.composite
def mutated_json(draw: st.DrawFn, seed: Any, changes: int = 3) -> Any:
    """The seed with up to `changes` values replaced by any JSON value, removed, or doubled into a list."""
    value = seed
    for _ in range(draw(st.integers(0, changes))):
        path = draw(st.sampled_from(_paths(value)))
        how = draw(st.sampled_from(["replace", "drop", "wrap"]))
        if how == "drop" and path:
            value = _replaced(value, path, None, drop=True)
        elif how == "wrap":
            inner = value
            for key in path:
                inner = inner[key]
            value = _replaced(value, path, [inner, inner], drop=False)
        else:
            value = _replaced(value, path, draw(JSON_VALUES), drop=False)
    return value


def json_bytes(value: Any) -> bytes:
    return json.dumps(value).encode()


@st.composite
def mutated_bytes(draw: st.DrawFn, seed: bytes, changes: int = 4) -> bytes:
    """The seed with up to `changes` bytes flipped, ranges cut, repeated or filled with other bytes."""
    data = bytearray(seed)
    for _ in range(draw(st.integers(0, changes))):
        how = draw(st.sampled_from(["flip", "cut", "insert", "repeat", "truncate"]))
        at = draw(st.integers(0, len(data)))
        if how == "flip" and at < len(data):
            data[at] ^= 1 << draw(st.integers(0, 7))
        elif how == "cut":
            del data[at : at + draw(st.integers(1, 8))]
        elif how == "insert":
            data[at:at] = draw(st.binary(min_size=1, max_size=8))
        elif how == "repeat":
            data[at:at] = data[at : at + draw(st.integers(1, 16))] * draw(st.integers(1, 3))
        else:
            del data[at:]
    return bytes(data)


def mutated_text(seed: str, changes: int = 4) -> st.SearchStrategy[str]:
    """The seed's text damaged as `mutated_bytes` damages bytes, read back as Latin-1."""
    return mutated_bytes(seed.encode("latin-1"), changes).map(lambda b: b.decode("latin-1"))
