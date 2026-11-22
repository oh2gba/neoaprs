"""Short description of a page's browser for the log, from its User-Agent (`Firefox 140 on Linux`).

The header is the client's own claim, so an unrecognised one is logged as plain, shortened text.
"""
import re

from .pageerrors import one_line

MAX_UNKNOWN = 80
BROWSERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("NeoAPRS window (Qt)", re.compile(r"QtWebEngine/(\d+)")),
    ("Edge", re.compile(r"\bEdgA?/(\d+)")),
    ("Opera", re.compile(r"\bOPR/(\d+)")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/(\d+)")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/(\d+)")),
    ("Safari", re.compile(r"\bVersion/(\d+)[\d.]* (?:Mobile/\S+ )?Safari/")),
)
SYSTEMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Android", re.compile(r"Android (\d+)")),
    ("iOS", re.compile(r"\b(?:iPhone|iPad|iPod)\b")),
    ("Windows", re.compile(r"Windows NT")),
    ("macOS", re.compile(r"Mac OS X")),
    ("ChromeOS", re.compile(r"CrOS")),
    ("Linux", re.compile(r"Linux|X11")),
)


def system_of(agent: str) -> str:
    for name, pattern in SYSTEMS:
        found = pattern.search(agent)
        if found:
            return f"{name} {found.group(1)}" if found.groups() else name
    return ""


def browser_of(agent: str) -> str:
    """Return `Firefox 140 on Linux`, `unknown browser (...)` or `no User-Agent`."""
    if not agent.strip():
        return "no User-Agent"
    system = system_of(agent)
    for name, pattern in BROWSERS:
        found = pattern.search(agent)
        if found:
            return f"{name} {found.group(1)}" + (f" on {system}" if system else "")
    return f"unknown browser ({one_line(agent, MAX_UNKNOWN)})"
