#!/usr/bin/env python3
"""Ask every outside link that the page, the manual, the site and the README offer (the stage links).

scripts/linkcheck.py             collect the links, ask each, print the ones that did not answer well
scripts/linkcheck.py --list      print the links it would ask, and where each was found
A link that is not found (404, 410) or whose host does not exist fails the run; one that refuses
robots, is slow, redirects in a loop, cannot be asked or answers otherwise is reported only. scripts/links-allowed.txt lists links known to
refuse robots, each with its reason: never a failure. With no network it says so and passes."""

import argparse
import concurrent.futures
import ipaddress
import re
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
LINKS_MODULE = ROOT / "ui" / "src" / "lib" / "links.ts"
ALLOWED = ROOT / "scripts" / "links-allowed.txt"
# A browser's name, and nothing of the person who runs it.
AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0 (link check)"
TIMEOUT_SEC = 15.0
AT_ONCE = 4
# A host the network is tried on before any link: no answer, no network.
PROBE_HOST = "github.com"
NOT_FOUND = frozenset({404, 410})
REFUSES_ROBOTS = frozenset({401, 403, 429, 999})
# The lookup's answers that say the name does not exist (not that the network is away).
_NO_HOST = {getattr(socket, name) for name in ("EAI_NONAME", "EAI_NODATA") if hasattr(socket, name)}

_ADDRESS = re.compile(r"https?://[^\s\"'`<>()\[\]{}\\|^]+")
# Not outside links: examples, the loopback, a station's own name, a filled-in template.
_SKIP = re.compile(
    r"^https?://([^/]*\.)?(localhost|127\.0\.0\.1|\[::1\]|example\.(com|org|net)|[^/]*\.local|[^/]*\.invalid)([:/]|$)"
)


@dataclass(frozen=True)
class Outcome:
    url: str
    word: str  # "ok", "not found", "no such host", or what it answered instead
    fails: bool
    reported: bool


def _clean(url: str) -> str:
    return url.rstrip(".,;:!?*_'\"")


_CODE_SPAN = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# What HTML and XML name without offering it: code, preformatted text, comments, namespaces.
_HTML_NAMED = re.compile(
    r"<(code|pre|samp|kbd)\b.*?</\1\s*>|<!--.*?-->|\bxmlns(:\w+)?\s*=\s*[\"'][^\"']*[\"']", re.S | re.I
)
# The site's files read whole: every address in them is offered (a sitemap, a script, a style sheet).
SITE_SUFFIXES = (".html", ".md", ".txt", ".xml", ".json", ".js", ".css")


def _private(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def links_in(text: str, kind: str = "") -> list[str]:
    """Return the outside addresses a text offers, in order, without trailing punctuation.

    Markdown (`kind` "md") offers none inside code, which names an address; HTML none inside code,
    preformatted text or a comment, and every other one (links, meta tags, structured data)."""
    if kind == "md":
        text = _CODE_SPAN.sub(" ", text)
    elif kind in ("html", "xml"):
        text = _HTML_NAMED.sub(" ", text)
    found = []
    for match in _ADDRESS.finditer(text):
        url = _clean(match.group(0))
        host = urlsplit(url).hostname
        if "${" in url or "{" in url or _SKIP.match(url) or not host or _private(host):
            continue
        found.append(url)
    return found


def sources(root: Path = ROOT) -> list[Path]:
    """The files whose links are offered: the page's link module, the manual, the site, the README."""
    site = [p for p in sorted((root / "site").rglob("*")) if p.is_file() and p.suffix in SITE_SUFFIXES]
    return [
        root / "ui" / "src" / "lib" / "links.ts",
        *sorted((root / "docs" / "manual").glob("*.md")),
        *site,
        root / "README.md",
    ]


def collect(root: Path = ROOT) -> dict[str, list[str]]:
    """Return each link with the files it was found in (relative to `root`)."""
    seen: dict[str, list[str]] = {}
    for path in sources(root):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        for url in links_in(path.read_text(encoding="utf-8", errors="replace"), path.suffix.lstrip(".")):
            where = seen.setdefault(url, [])
            if name not in where:
                where.append(name)
    return seen


def allowed(path: Path = ALLOWED) -> dict[str, str]:
    """Return the allow-list: a link and its reason on each line, `#` lines and blank ones skipped."""
    if not path.is_file():
        return {}
    listed = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        url, _, reason = line.strip().partition(" ")
        if not reason.strip():
            raise SystemExit(f"linkcheck: {path.name}: {url} has no reason")
        listed[url] = reason.strip()
    return listed


def asked_form(url: str) -> str:
    """Return the link as it is asked: the host in IDNA, the rest percent-encoded (an IRI as a URI)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").encode("idna").decode("ascii")
    netloc = host + (f":{parts.port}" if parts.port else "")
    keep = "/%:@!$&'()*+,;=-._~"
    return urlunsplit(
        (parts.scheme, netloc, quote(parts.path, keep), quote(parts.query, keep + "?"), quote(parts.fragment, keep))
    )


def _ask(url: str, method: str, timeout: float) -> int:
    request = urllib.request.Request(asked_form(url), method=method, headers={"User-Agent": AGENT, "Accept": "*/*"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 (http and https only)
            if method == "GET":
                answer.read(1024)
            return int(answer.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def check(url: str, timeout: float = TIMEOUT_SEC) -> Outcome:
    """Ask one link: HEAD, then GET where HEAD is refused or not found."""
    try:
        status = _ask(url, "HEAD", timeout)
        if status >= 400:
            status = _ask(url, "GET", timeout)
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.gaierror) and e.reason.errno in _NO_HOST:
            return Outcome(url, "no such host", True, True)
        if isinstance(e.reason, TimeoutError | socket.timeout):
            return Outcome(url, f"no answer in {timeout:.0f} s", False, True)
        return Outcome(url, f"not reached ({e.reason})", False, True)
    except (TimeoutError, socket.timeout):
        return Outcome(url, f"no answer in {timeout:.0f} s", False, True)
    except OSError as e:
        return Outcome(url, f"not reached ({e})", False, True)
    except Exception as e:  # a link that cannot be asked (a bad address, a broken answer) is reported, not a crash
        return Outcome(url, f"not reached ({type(e).__name__}: {e})", False, True)
    if status in NOT_FOUND:
        return Outcome(url, f"not found ({status})", True, True)
    if 300 <= status < 400:
        return Outcome(url, f"redirects in a loop ({status})", False, True)
    if status >= 400:
        return Outcome(
            url, f"answered {status}" + (" (refuses robots)" if status in REFUSES_ROBOTS else ""), False, True
        )
    return Outcome(url, "ok", False, False)


def online(lookup: Callable[[str], object] = socket.gethostbyname) -> bool:
    try:
        lookup(PROBE_HOST)
    except OSError:
        return False
    return True


def run(
    links: dict[str, list[str]],
    allow: dict[str, str],
    ask: Callable[[str], Outcome] = check,
    is_online: Callable[[], bool] = online,
    out: Callable[[str], None] = print,
) -> int:
    """Ask the links a few at a time and print what did not answer well; return the exit code."""
    if not is_online():
        out(f"linkcheck: no network ({PROBE_HOST} cannot be looked up): {len(links)} links not asked")
        return 0
    with concurrent.futures.ThreadPoolExecutor(AT_ONCE) as pool:
        outcomes = list(pool.map(ask, sorted(links)))
    failed = 0
    for outcome in outcomes:
        if not outcome.reported:
            continue
        where = ", ".join(links[outcome.url])
        if outcome.url in allow:
            out(f"allowed  {outcome.url}: {outcome.word}; {allow[outcome.url]}")
        elif outcome.fails:
            failed += 1
            out(f"FAIL     {outcome.url}: {outcome.word} (in {where})")
        else:
            out(f"reported {outcome.url}: {outcome.word} (in {where})")
    good = sum(1 for outcome in outcomes if not outcome.reported)
    out(f"linkcheck: {len(outcomes)} links, {good} ok, {failed} failed")
    return 1 if failed else 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ask every outside link the page, manual, site and README offer")
    parser.add_argument("--list", action="store_true", help="print the links and where each is, ask nothing")
    args = parser.parse_args(None if argv is None else list(argv))
    links = collect()
    if args.list:
        for url, where in sorted(links.items()):
            print(f"{url}  {', '.join(where)}")
        return 0
    return run(links, allowed())


if __name__ == "__main__":
    sys.exit(main())
