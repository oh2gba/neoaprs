"""Real examples, damaged: bytes flipped, cut, inserted (awkward Unicode too) and repeated, for property tests."""

import json
from collections.abc import Sequence

from hypothesis import strategies as st

from neoaprs.packet import decode_text
from tests.support.files import FIXTURES

# bytes that have broken parsers: Unicode digits and letters that fold to ASCII, controls, long runs
AWKWARD = (
    b"\x00",
    b"\xff",
    b"\xb2",  # superscript two in Latin-1: isdigit() but no int
    "K".encode(),  # Kelvin sign: folds to k
    "ı".encode(),  # dotless i: upper() is I
    "٣".encode(),  # Arabic-Indic three: a decimal digit
    b"\r\n",
    b"|",
    b"{",
    b"}",
    b":",
    b">",
    b",",
    b"*",
    b"-",
    b".",
    b"9" * 12,
    b"!",
)


@st.composite
def mutated(draw: st.DrawFn, examples: Sequence[bytes], max_edits: int = 4) -> bytes:
    """One of `examples` after up to `max_edits` edits."""
    data = bytearray(draw(st.sampled_from(examples)))
    for _ in range(draw(st.integers(min_value=0, max_value=max_edits))):
        at = draw(st.integers(min_value=0, max_value=len(data)))
        edit = draw(st.sampled_from(("flip", "cut", "insert", "awkward", "repeat")))
        if edit == "flip" and at < len(data):
            data[at] = draw(st.integers(min_value=0, max_value=255))
        elif edit == "cut":
            del data[at : draw(st.integers(min_value=at, max_value=min(len(data), at + 8)))]
        elif edit == "insert":
            data[at:at] = draw(st.binary(min_size=1, max_size=4))
        elif edit == "awkward":
            data[at:at] = draw(st.sampled_from(AWKWARD))
        elif edit == "repeat":
            piece = data[at : draw(st.integers(min_value=at, max_value=min(len(data), at + 8)))]
            data[at:at] = piece * draw(st.integers(min_value=1, max_value=3))
    return bytes(data)


def mutated_text(examples: Sequence[str], max_edits: int = 4) -> st.SearchStrategy[str]:
    """One of `examples` after edits of its UTF-8, read back as a receiver reads it."""
    return mutated([e.encode() for e in examples], max_edits).map(decode_text)


def aprs_cases() -> list[dict[str, str]]:
    """The source, destination and information field of every case of tests/fixtures/aprs/cases.json."""
    cases = json.loads((FIXTURES / "aprs" / "cases.json").read_text(encoding="utf-8"))
    return [{key: case[key] for key in ("source", "destination", "info")} for case in cases]


AFTER_IDENTIFIER = tuple(c["info"][1:] for c in aprs_cases() if c["info"])
