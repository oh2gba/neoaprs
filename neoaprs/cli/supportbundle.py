"""The support bundle as a file: what a zip of the bundle is made of and how it is written, with no knowledge of where the contents come from (neoaprs/cli/supportgather.py gathers them, neoaprs/cli/supportmake.py
puts the two together).

A bundle is one zip, deflate-compressed, `neoaprs-support-<CALL or nocall>-<YYYYmmdd-HHMMSS>Z.zip`, of members that are text. It is written under a temporary name and renamed, so a half-written file is never taken for a bundle. The values of
the secrets (the access key) are taken out of every member as the zip is written, whatever put them there: the settings are redacted by name, this is the net under them.

The logs are cut to a budget: the newest lines are kept, from a line start, and the first line of a cut file says how much of it was left out."""
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOG_BUDGET_BYTES = 12 * 1024 * 1024
MIN_SECRET_CHARS = 6                         # a shorter value would be taken out of words that merely contain it
ROTATED = re.compile(r"\.(\d+)$")


@dataclass(frozen=True)
class Member:
    """One file of the bundle: its path in the zip and its text."""
    name: str
    text: str


def bundle_name(call: str, when: datetime) -> str:
    """`neoaprs-support-OH2GBA-20261026-120000Z.zip`; `nocall` while no call is set. Only letters, digits and dashes of the call are used: the name goes into a path and a header."""
    safe = "".join(c for c in call.upper() if c.isalnum() or c == "-").strip("-")
    return f"neoaprs-support-{safe or 'nocall'}-{when:%Y%m%d-%H%M%S}Z.zip"


def secret_pattern(values: Iterable[str]) -> re.Pattern[str] | None:
    """A pattern for every secret value and for it typed the way a person types an access key (capitals, the dashes and blanks left out); None when there is none worth looking for."""
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
    """Writes the members, in the order given, to `path` (the folder must exist); the size of the file. README.txt and summary.txt should come first: they are what is opened first."""
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
    """The log `name` of the folder and its rotated files, the newest first (`neoaprs.log`, `neoaprs.log.1`, `neoaprs.log.2` ...); those that exist."""
    found: list[tuple[int, Path]] = []
    for path in folder.glob(name + "*"):
        suffix = path.name[len(name):]
        if suffix == "":
            found.append((0, path))
        elif (match := ROTATED.fullmatch(suffix)) is not None and path.is_file():
            found.append((int(match.group(1)), path))
    return [path for _, path in sorted(found)]


def tail_text(path: Path, budget: int) -> tuple[str, int]:
    """(the end of the file as text: whole when it fits in `budget` bytes, else cut at a line start, and how many bytes were left out)."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size <= budget:
            f.seek(0)
            return f.read().decode("utf-8", errors="replace"), 0
        f.seek(size - budget)
        data = f.read()
    cut = data.find(b"\n")
    data = b"" if cut < 0 else data[cut + 1:]                  # (the first line of a cut is the end of one)
    return data.decode("utf-8", errors="replace"), size - len(data)


def log_members(files: list[Path], budget: int | None = None) -> list[Member]:
    """The files as members `logs/<name>`, in the order given, the newest lines of them within `budget` bytes in all. A file that is cut starts with a line that says how much was left out; one that does not fit at all is a
    member of that one line; one that cannot be read says why."""
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
