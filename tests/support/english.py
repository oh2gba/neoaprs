"""The page's English sentence of a coded refusal (ui/src/i18n/en/errors.ts), for tests that hold the
daemon's own English, which the log keeps, to what the page shows."""

import functools
import json
import re
from pathlib import Path

from neoaprs.coded import CodedError

CATALOGUE = Path(__file__).resolve().parents[2] / "ui" / "src" / "i18n" / "en" / "errors.ts"
_ENTRY = re.compile(r'"error\.([\w.]+)":\s*("(?:[^"\\]|\\.)*")')


@functools.cache
def sentences() -> dict[str, str]:
    """Every code of the catalogue and its English sentence with its {names}."""
    return {code: json.loads(text) for code, text in _ENTRY.findall(CATALOGUE.read_text(encoding="utf-8"))}


def page_english(error: CodedError) -> str:
    """The sentence the page shows for `error`, its {names} filled from the params."""
    return re.sub(r"\{(\w+)\}", lambda m: str(error.params[m.group(1)]), sentences()[error.code])
