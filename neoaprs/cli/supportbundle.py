"""The support bundle as a file: how a zip of text members is written.

The zip is renamed into place when complete. Secret values are removed from every member as it is
written (a safety net behind the redaction by name). Logs are cut to a budget."""
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOG_BUDGET_BYTES = 12 * 1024 * 1024
# A shorter secret would match inside ordinary words.
MIN_SECRET_CHARS = 6
ROTATED = re.compile(r"\.(\d+)$")


@dataclass(frozen=True)
class Member:
    name: str
    text: str


def bundle_name(call: str, when: datetime) -> str:
    """Return `neoaprs-support-CALL-20261026-120000Z.zip` (`nocall` if unset)."""
    safe = "".join(c for c in call.upper() if c.isalnum() or c == "-").strip("-")
    return f"neoaprs-support-{safe or 'nocall'}-{when:%Y%m%d-%H%M%S}Z.zip"


def secret_pattern(values: Iterable[str]) -> re.Pattern[str] | None:
    """Return a pattern for each secret, also as typed by hand (no dashes, blanks); None if none."""
    parts: set[str] = set()
    for value in values:
        if len(value) >= MIN_SECRET_CHARS:
            parts.add(re.escape(value))
            plain = "".join(c for c in value if c not in " -")
            if len(plain) >= MIN_SECRET_CHARS and plain != value:
                parts.add(re.escape(plain))
    return re.compile("|".join(sorted(parts, key=len, reverse=True)), re.IGNORECASE) if parts else None


def scrubbed(text: str, secrets: re.Pattern[str] | None) -> str:
    return text if secrets is None else secrets.sub("(secret removed)", text)


def write_zip(path: Path, members: list[Member], when: datetime, secrets: Iterable[str] = ()) -> int:
    """Write the members in order to `path` (its folder must exist); return the file size."""
    pattern = secret_pattern(secrets)
    part = path.with_name(path.name + ".part")
    stamp = (when.year, when.month, when.day, when.hour, when.minute, when.second)
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for member in members:
                info = zipfile.ZipInfo(member.name, stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, scrubbed(member.text, pattern).encode("utf-8"))
        part.replace(path)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return path.stat().st_size


# ---- the logs, within a budget

def rotated_logs(folder: Path, name: str) -> list[Path]:
    """Return the log `name` and its rotated files, newest first."""
    found: list[tuple[int, Path]] = []
    for path in folder.glob(name + "*"):
        suffix = path.name[len(name):]
        if suffix == "":
            found.append((0, path))
        elif (match := ROTATED.fullmatch(suffix)) is not None and path.is_file():
            found.append((int(match.group(1)), path))
    return [path for _, path in sorted(found)]


def tail_text(path: Path, budget: int) -> tuple[str, int]:
    """Return the end of the file (cut at a line start over `budget`) and the bytes left out."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size <= budget:
            f.seek(0)
            return f.read().decode("utf-8", errors="replace"), 0
        f.seek(size - budget)
        data = f.read()
    cut = data.find(b"\n")
    # Drop the partial first line.
    data = b"" if cut < 0 else data[cut + 1:]
    return data.decode("utf-8", errors="replace"), size - len(data)


def log_members(files: list[Path], budget: int | None = None) -> list[Member]:
    """Return the files as members `logs/<name>`, keeping the newest lines within `budget` bytes."""
    members: list[Member] = []
    left = LOG_BUDGET_BYTES if budget is None else budget
    for path in files:
        name = f"logs/{path.name}"
        try:
            text, dropped = tail_text(path, max(0, left))
        except OSError as e:
            members.append(Member(name, f"[{path.name} could not be read: {e}]\n"))
            continue
        left -= len(text.encode("utf-8"))
        if dropped:
            what = "the whole file" if text == "" else f"the first {dropped:,} bytes"
            text = f"[{what} of {path.name} left out here to keep the bundle small: the newest lines are kept]\n{text}"
        members.append(Member(name, text))
    return members
