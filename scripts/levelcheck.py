#!/usr/bin/env python3
"""Ask the registries whether each direct dependency and pinned tool is at its newest release (the stage level).

scripts/levelcheck.py            ask PyPI, npm, nodejs.org and GitHub; print what is behind
scripts/levelcheck.py --list     print every pin and where it is written, ask nothing
One that has been behind for longer than 14 days (counted from the first release after ours) fails the run;
a younger one is listed and passes. Pre-releases, yanked and deprecated versions are not counted.
scripts/level-allowed.txt lists versions we cannot take yet, each with a date and its reason. With no
network, or a registry that does not answer, it says so and passes."""

import argparse
import concurrent.futures
import gzip
import http.client
import json
import os
import re
import socket
import sys
import tomllib
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = ROOT / "scripts" / "level-allowed.txt"
AGENT = "neoaprs-levelcheck"  # a generic client name, nothing of the person who runs it
TIMEOUT_SEC = 20.0
AT_ONCE = 4
LIMIT = timedelta(days=14)
PYPI = "https://pypi.org"
NPM = "https://registry.npmjs.org"
GITHUB = "https://api.github.com"
NODEJS = "https://nodejs.org"
PROBE_HOST = "pypi.org"
GITHUB_PAGE = 30  # the recent releases asked for when ours is not the latest

# Where the pins are written, besides pyproject.toml and ui/package.json.
RELEASE_FILES = (
    "scripts/security-tools",
    "scripts/build-appimage",
    "scripts/build-deb",
    "scripts/build-macos-app",
    "scripts/check-windows",
)
MODEM_FILES = {"Rhizomatica/mercury": "neoaprs/mercury.py", "wb2osz/direwolf": "neoaprs/direwolf.py"}
UV_REPO = "astral-sh/uv"
INNO_REPO = "jrsoftware/issrc"  # its tags are is-6_7_1
_NODE_PIN = re.compile(r"^ARG NODE_VERSION=(\d+\.\d+\.\d+)$", re.M)
_INNO_PIN = re.compile(r"choco install innosetup --version=(\d+(?:\.\d+)+)")
# What is pinned by an exact version or hash and not followed here, with the text that shows it in its file.
NOT_FOLLOWED = (
    ("the action SHAs of the workflows", ".github/workflows/ci.yml", "persist-credentials: false", "Dependabot's"),
    ("the lock files", "uv.lock", "[[package]]", "Dependabot's (uv and npm), and the stage lock checks them"),
    (
        "the CI container's base image and Ubuntu snapshot",
        "packaging/ci/Dockerfile",
        "FROM ubuntu:",
        "a digest and a date, not a release; scripts/runner-facts (the stage audit) compares them with GitHub's runner",
    ),
    (
        "the Ubuntu image of the install check",
        "scripts/check-installs",
        "ubuntu:24.04@sha256:",
        "a digest of a tag that is rebuilt, not a release",
    ),
    (
        "com0com's signed release for the proof of virtual COM ports",
        "scripts/check-windows-virtualports",
        "ZIP_SHA256=",
        "3.0.0.0 of 2017 is com0com's last release; the zip is fetched by hand for a proof on the Windows machine",
    ),
    (
        "the Ubuntu image the site's sounds are made in",
        "scripts/site-sounds",
        "FROM ubuntu:26.04@sha256:",
        "a digest of a tag that is rebuilt, not a release",
    ),
    (
        "the PHP image Psalm runs in",
        "scripts/security-tools",
        "PHP_IMAGES",
        "a digest of a tag that is rebuilt, not a release",
    ),
    (
        "Pillow of the AppImage's web window",
        "packaging/appimage/weblock.py",
        "PILLOW_SHA256",
        "the version of pyproject.toml, which is followed there",
    ),
    (
        "the CPython series of the workflows (3.13)",
        ".github/workflows/ci.yml",
        'python-version: "3.13"',
        "a series, not an exact version: uv takes its newest patch release",
    ),
    (
        "Node of the workflows (26)",
        ".github/workflows/ci.yml",
        "node-version: 26",
        "a major line that setup-node resolves to its newest; the exact Node of the container is followed",
    ),
    (
        "the release the .deb check starts from",
        "packaging/ci/old-release.json",
        '"sha256"',
        "the previous NeoAPRS release, which scripts/release rewrites; it is history, not a tool",
    ),
)
_PYTHONHOSTED = re.compile(
    r"https://files\.pythonhosted\.org/packages/[^\"'\s]*/([A-Za-z0-9_.]+?)-(\d+(?:\.\d+)*)(?:\.tar\.gz|-py)"
)
_INNO_TAG = re.compile(r"^is-(\d+(?:_\d+)+)$")
_RELEASE_URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/releases/download/([^/\"'\s]+)[/\"]")
_EXACT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*([^;\s]+)")
_STABLE = re.compile(r"^v?(\d+!)?\d+(\.\d+)*(\.post\d+)?$")
_UV_PINS = (
    re.compile(r"astral\.sh/uv/([\d.]+)/install\.sh"),
    re.compile(r"^ARG UV_VERSION=([\d.]+)$", re.M),
)
_UV_STEP_VERSION = re.compile(r"^[ \t]+version:\s*\"([\d.]+)\"\s*$")


def uv_step_versions(text: str) -> list[str]:
    """The `version:` of every setup-uv step of a workflow: the first one after the step's
    `uses:` line and before the next step."""
    found: list[str] = []
    inside = False
    for line in text.splitlines():
        if "uses:" in line:
            inside = "setup-uv@" in line
        elif inside and (version := _UV_STEP_VERSION.match(line)):
            found.append(version.group(1))
            inside = False
    return found


@dataclass(frozen=True)
class Pin:
    kind: str  # "pypi", "npm", "node" (a line of Node.js) or "github"
    name: str  # the package, or owner/repository
    version: str
    where: tuple[str, ...]


@dataclass(frozen=True)
class Release:
    version: str
    at: datetime | None  # None: the registry gave no date


@dataclass(frozen=True)
class Allowance:
    version: str  # the first version not taken: it and every later one ("7" is 7.0.2 and 8.1)
    until: date
    reason: str


@dataclass(frozen=True)
class Verdict:
    pin: Pin
    word: str  # "level", "behind", "young", "allowed", "not asked"
    fails: bool
    newest: str = ""
    newest_days: int | None = None
    behind_days: int | None = None
    note: str = ""


def version_key(version: str) -> tuple[int, ...]:
    """Order of two stable versions: the epoch, the numbers, then a post-release."""
    text = version.removeprefix("v")
    epoch, _, text = text.rpartition("!") if "!" in text else ("0", "", text)
    text, _, post = text.partition(".post")
    return (int(epoch or 0), *(int(part) for part in text.split(".")), -1 if not post else int(post))


def stable(version: str) -> bool:
    return bool(_STABLE.match(version))


# --- the pins -----------------------------------------------------------------------------------------


def _merge(pins: Iterable[Pin]) -> list[Pin]:
    merged: dict[tuple[str, str, str], Pin] = {}
    for pin in pins:
        key = (pin.kind, pin.name.lower(), pin.version)
        old = merged.get(key)
        where = pin.where if old is None else tuple(dict.fromkeys((*old.where, *pin.where)))
        merged[key] = Pin(pin.kind, pin.name if old is None else old.name, pin.version, where)
    return sorted(merged.values(), key=lambda p: (p.kind, p.name.lower(), p.version))


def python_pins(root: Path) -> list[Pin]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lines = list(project.get("build-system", {}).get("requires", []))
    lines += project.get("project", {}).get("dependencies", [])
    for group in (*project.get("project", {}).get("optional-dependencies", {}).values(),):
        lines += group
    for group in project.get("dependency-groups", {}).values():
        lines += [line for line in group if isinstance(line, str)]
    found = [m for m in (_EXACT.match(line) for line in lines) if m]
    return [Pin("pypi", m.group(1), m.group(3), ("pyproject.toml",)) for m in found]


def page_pins(root: Path) -> list[Pin]:
    path = root / "ui" / "package.json"
    if not path.is_file():
        return []
    package = json.loads(path.read_text(encoding="utf-8"))
    names = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    return [Pin("npm", name, version, ("ui/package.json",)) for name, version in names.items()]


def build_pins(root: Path) -> list[Pin]:
    """Node.js of the CI container, Inno Setup of the Windows release, PyGObject and Meson of the GTK build."""
    pins = []
    docker = root / "packaging" / "ci" / "Dockerfile"
    if docker.is_file():
        pins += [
            Pin("node", "node", v, ("packaging/ci/Dockerfile",)) for v in _NODE_PIN.findall(docker.read_text("utf-8"))
        ]
    release = root / ".github" / "workflows" / "release.yml"
    if release.is_file():
        found = _INNO_PIN.findall(release.read_text("utf-8"))
        pins += [Pin("github", INNO_REPO, v, (".github/workflows/release.yml",)) for v in found]
    gi = root / "scripts" / "build-gi"
    if gi.is_file():
        found = _PYTHONHOSTED.findall(gi.read_text("utf-8"))
        pins += [Pin("pypi", name, v, ("scripts/build-gi",)) for name, v in found]
    return pins


def tool_pins(root: Path) -> list[Pin]:
    pins = []
    for name in RELEASE_FILES:
        path = root / name
        if path.is_file():
            for repo, tag in _RELEASE_URL.findall(path.read_text(encoding="utf-8")):
                pins.append(Pin("github", repo, tag, (name,)))
    uv_files = sorted((root / ".github" / "workflows").glob("*.yml"))
    uv_files += [root / "packaging" / "install.sh.in", root / "packaging" / "ci" / "Dockerfile"]
    for path in uv_files:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for version in [*uv_step_versions(text), *(v for pattern in _UV_PINS for v in pattern.findall(text))]:
                pins.append(Pin("github", UV_REPO, version, (path.relative_to(root).as_posix(),)))
    for repo, name in MODEM_FILES.items():
        path = root / name
        found = re.search(r'^VERSION = "([^"]+)"', path.read_text(encoding="utf-8"), re.M) if path.is_file() else None
        if found:
            pins.append(Pin("github", repo, found.group(1), (name,)))
    return pins


def collect(root: Path = ROOT) -> list[Pin]:
    """Every direct dependency and pinned tool, one entry for each name and version."""
    return _merge([*python_pins(root), *page_pins(root), *tool_pins(root), *build_pins(root)])


def allowed(path: Path = ALLOWED) -> dict[tuple[str, str], Allowance]:
    """The allow file: `KIND:NAME VERSION UNTIL REASON` on each line, `#` lines and blank ones skipped."""
    if not path.is_file():
        return {}
    listed = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split(None, 3)
        try:
            kind, _, name = parts[0].partition(":")
            until = date.fromisoformat(parts[2])
            reason = parts[3].strip()
        except (IndexError, ValueError):
            raise SystemExit(
                f"levelcheck: {path.name} line {number}: not KIND:NAME VERSION YYYY-MM-DD REASON"
            ) from None
        listed[(kind, name.lower())] = Allowance(parts[1], until, reason)
    return listed


# --- the registries -----------------------------------------------------------------------------------


@dataclass
class Registries:
    """Asks PyPI, npm and GitHub, each address once for the run."""

    pypi: str = PYPI
    npm: str = NPM
    github: str = GITHUB
    nodejs: str = NODEJS
    token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", ""))
    timeout: float = TIMEOUT_SEC
    _cache: dict[str, Any] = field(default_factory=dict)

    def _get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        if url not in self._cache:
            asked = {"User-Agent": AGENT, "Accept-Encoding": "gzip", **(headers or {})}
            request = urllib.request.Request(url, headers=asked)  # noqa: S310 (https, or a test's loopback)
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:  # noqa: S310
                body = answer.read()
                if answer.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            self._cache[url] = json.loads(body)
        return self._cache[url]

    def releases(self, pin: Pin) -> list[Release]:
        if pin.kind == "pypi":
            return self._pypi(pin.name)
        if pin.kind == "npm":
            return self._npm(pin.name)
        if pin.kind == "node":
            return self._node(pin.version)
        return self._github(pin.name, pin.version)

    def _pypi(self, name: str) -> list[Release]:
        doc = self._get(f"{self.pypi}/pypi/{quote(name)}/json")
        out = []
        for version, files in doc.get("releases", {}).items():
            kept = [f for f in files if not f.get("yanked")]
            if kept and stable(version):
                out.append(Release(version, min(_when(f.get("upload_time_iso_8601")) or _NEVER for f in kept)))
        return out

    def _npm(self, name: str) -> list[Release]:
        doc = self._get(f"{self.npm}/{quote(name, safe='@')}")
        times = doc.get("time", {})
        return [
            Release(version, _when(times.get(version)))
            for version, meta in doc.get("versions", {}).items()
            if stable(version) and not meta.get("deprecated")
        ]

    def _node(self, ours: str) -> list[Release]:
        """The releases of the line (22.x) we are on: a newer line is a choice, not a fall behind."""
        line = ours.split(".")[0]
        return [
            Release(item["version"].removeprefix("v"), _when(item.get("date")))
            for item in self._get(f"{self.nodejs}/dist/index.json")
            if stable(item["version"]) and item["version"].removeprefix("v").split(".")[0] == line
        ]

    def _github(self, repo: str, ours: str) -> list[Release]:
        """The latest release alone where it is ours; else the recent ones, to see when we fell behind.

        A repository with thousands of files in each release (python-build-standalone) may time out
        on the list: the latest release is then the only one known."""
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        latest = _github_releases([self._get(f"{self.github}/repos/{repo}/releases/latest", headers)])
        if latest and stable(ours) and version_key(latest[0].version) <= version_key(ours):
            return latest
        try:
            return _github_releases(self._get(f"{self.github}/repos/{repo}/releases?per_page={GITHUB_PAGE}", headers))
        except (OSError, ValueError, EOFError, zlib.error, http.client.HTTPException):
            if latest:
                return latest
            raise


_NEVER = datetime.max.replace(tzinfo=UTC)


def _github_releases(doc: list[dict[str, Any]]) -> list[Release]:
    return [
        Release(tag_version(r["tag_name"]), _when(r.get("published_at")))
        for r in doc
        if not r.get("draft") and not r.get("prerelease") and stable(tag_version(r.get("tag_name", "")))
    ]


def tag_version(tag: str) -> str:
    """The version a tag names: v1.2 is 1.2, Inno Setup's is-6_7_1 is 6.7.1."""
    inno = _INNO_TAG.match(tag)
    return inno.group(1).replace("_", ".") if inno else tag.removeprefix("v")


def _when(text: object) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        at = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            at = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


# --- the verdict --------------------------------------------------------------------------------------


def _covers(allowance: Allowance, version: str) -> bool:
    return version_key(version) >= version_key(allowance.version)


def judge(pin: Pin, releases: list[Release], allowance: Allowance | None, now: datetime) -> Verdict:
    """Level, behind and young, behind for longer than the limit, or allowed."""
    if not stable(pin.version):
        return Verdict(pin, "not asked", False, note="ours is no plain version")
    ours = version_key(pin.version)
    newer = [r for r in releases if version_key(r.version) > ours]
    live = allowance if allowance and allowance.until >= now.date() else None
    held = [r for r in newer if live and _covers(live, r.version)]
    counted = [r for r in newer if r not in held]
    note = f"allowed until {allowance.until}: {allowance.reason}" if live and allowance else ""
    if allowance and not live:
        note = f"the allowance for {allowance.version} ended on {allowance.until}"
    if not counted:
        if held:
            newest = max(held, key=lambda r: version_key(r.version))
            return Verdict(pin, "allowed", False, newest.version, _days(newest.at, now), note=note)
        return Verdict(pin, "level", False, note=note)
    newest = max(counted, key=lambda r: version_key(r.version))
    dated = [r.at for r in counted if r.at]
    since = min(dated) if dated else None
    if since is not None and now - since > LIMIT:
        word, fails = "behind", True
    else:
        word, fails = "young", False
        note = note or ("" if since else "the registry gave no date")
    return Verdict(pin, word, fails, newest.version, _days(newest.at, now), _days(since, now), note)


def _days(at: datetime | None, now: datetime) -> int | None:
    return None if at is None else max(0, (now - at).days)


def ask(pin: Pin, registries: Registries, allow: dict[tuple[str, str], Allowance], now: datetime) -> Verdict:
    try:
        releases = registries.releases(pin)
    except urllib.error.HTTPError as e:
        return Verdict(pin, "not asked", False, note=f"the registry answered {e.code}")
    except (OSError, ValueError, EOFError, zlib.error, http.client.HTTPException) as e:
        return Verdict(pin, "not asked", False, note=f"the registry did not answer ({e})")
    except (AttributeError, KeyError, TypeError) as e:
        return Verdict(pin, "not asked", False, note=f"the registry's answer is not one this reads ({e!r})")
    return judge(pin, releases, allow.get((pin.kind, pin.name.lower())), now)


# --- the run ------------------------------------------------------------------------------------------


def online(lookup: Callable[[str], object] = socket.gethostbyname) -> bool:
    try:
        lookup(PROBE_HOST)
    except OSError:
        return False
    return True


def _cell(days: int | None) -> str:
    return "?" if days is None else f"{days}d"


def table(verdicts: list[Verdict]) -> list[str]:
    """The pins that are not level: name, ours, newest, days it has been out, days we have been behind."""
    shown = [v for v in verdicts if v.word != "level"]
    if not shown:
        return []
    rows = [("", "pin", "ours", "newest", "out", "behind", "")]
    for v in shown:
        word = "FAIL" if v.fails else v.word
        cells = (word, f"{v.pin.kind}:{v.pin.name}", v.pin.version, v.newest or "-")
        rows.append((*cells, _cell(v.newest_days), _cell(v.behind_days), v.note or ", ".join(v.pin.where)))
    widths = [max(len(row[i]) for row in rows) for i in range(6)]
    return ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:6])) + "  " + row[6] for row in rows]


def run(
    pins: list[Pin],
    allow: dict[tuple[str, str], Allowance],
    registries: Registries | None = None,
    now: datetime | None = None,
    is_online: Callable[[], bool] = online,
    out: Callable[[str], None] = print,
) -> int:
    """Ask every pin a few at a time, print what is not level, and return the exit code."""
    if not is_online():
        out(f"levelcheck: no network ({PROBE_HOST} cannot be looked up): {len(pins)} pins not asked")
        return 0
    registries = registries or Registries()
    moment = now or datetime.now(UTC)
    with concurrent.futures.ThreadPoolExecutor(AT_ONCE) as pool:
        verdicts = list(pool.map(lambda pin: ask(pin, registries, allow, moment), pins))
    for line in table(verdicts):
        out(line)
    count = {word: sum(1 for v in verdicts if v.word == word) for word in ("level", "young", "allowed", "not asked")}
    failed = sum(1 for v in verdicts if v.fails)
    out(
        f"levelcheck: {len(verdicts)} pins, {count['level']} level, {count['young']} behind for {LIMIT.days} days"
        f" or less, {count['allowed']} allowed, {count['not asked']} not asked, {failed} failed"
    )
    return 1 if failed else 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask the registries whether every pin is at its newest release")
    parser.add_argument("--list", action="store_true", help="print every pin and where it is written, ask nothing")
    args = parser.parse_args(None if argv is None else list(argv))
    pins = collect()
    if args.list:
        for pin in pins:
            print(f"{pin.kind}:{pin.name} {pin.version}  {', '.join(pin.where)}")
        for what, where, _needle, because in NOT_FOLLOWED:
            print(f"not followed: {what}  {where}: {because}")
        return 0
    return run(pins, allowed())


if __name__ == "__main__":
    sys.exit(main())
