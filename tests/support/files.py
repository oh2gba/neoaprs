"""The files under tests/fixtures (captured frames and streams of the radio, and the parser's cases)."""
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
