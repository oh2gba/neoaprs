"""The page is built: neoaprs/page/ (kept in git, served as it is, no node needed to run NeoAPRS) is what ui/ builds. The first tests look at page/ alone and always run; the last builds ui/
into a temporary folder and compares every file with page/, and is skipped, and says so, when there is no node or no `npm ci` in ui/. When it fails: scripts/build-page, commit page/."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
PAGE = ROOT / "neoaprs" / "page"
VITE = UI / "node_modules" / ".bin" / "vite"
HINT = "run scripts/build-page and commit neoaprs/page/"

SHIPPED = (
    "symbols/primary.png", "symbols/alternate.png", "symbols/overlay.png", "symbols/SOURCE.txt", "symbols/COPYRIGHT.txt",
    "fonts/NotoSans-Regular/0-255.pbf", "fonts/NotoSans-Medium/0-255.pbf", "fonts/OFL.txt",
)


def tree(folder: Path) -> dict[str, str]:
    """Every file under `folder` (relative path) with the hash of its content."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


NODE_NEEDED = (22, 12)                                   # what the page's build tools need (as scripts/check)


def node_version(node: str) -> tuple[int, ...]:
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    return tuple(int(n) for n in re.findall(r"\d+", out)[:3])


def node_dir() -> str | None:
    """The folder of a node new enough: the one on the PATH, else the newest of the operator's ~/.nvm (the tests run with an empty HOME, so the real one is looked up)."""
    found = shutil.which("node")
    if found and node_version(found) >= NODE_NEEDED:
        return str(Path(found).parent)
    if sys.platform == "win32":
        return None                                      # (no nvm there, and no pwd)
    import pwd
    versions = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".nvm" / "versions" / "node"
    newest = sorted(versions.glob("v*/bin/node"), key=lambda p: [int(n) for n in re.findall(r"\d+", p.parent.parent.name)]) if versions.is_dir() else []
    return str(newest[-1].parent) if newest and node_version(str(newest[-1])) >= NODE_NEEDED else None


def test_the_built_page_is_there_and_works_from_any_path() -> None:
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    assert '<div id="app">' in html and '<script type="module"' in html
    files = tree(PAGE)
    refs = [r for r in re.findall(r'(?:src|href)="([^"]+)"', html) if not r.startswith("data:")]
    assert refs, "index.html names no script and no style sheet"
    for ref in refs:
        assert ref.startswith("./assets/"), f"{ref}: a path from the root of the site would break the page behind a prefix; the build must use base './'"
        assert ref[2:] in files, f"{ref} is named in index.html but is not in page/: {HINT}"
    assert all(re.search(r"-[\w-]{8}\.(m?js|css)$", name) for name in files if name.startswith("assets/")), "the files in assets/ carry the hash of their content"


def test_the_page_lives_under_the_content_security_policy_of_the_daemon() -> None:
    """neoaprs/web/headers.py allows the page's own scripts, styles and workers and nothing else: no inline script or handler, no blob or eval, and the map's worker is a file the page ships."""
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "an inline script is not allowed by script-src 'self'"
    assert not re.search(r"\son\w+=", html), "an inline event handler is not allowed"
    assert not re.search(r"https?://", html.replace("http://www.w3.org/2000/svg", "")), "the shell names an address that is not the page's own"
    files = tree(PAGE)
    assert any(re.fullmatch(r"assets/maplibre-gl-worker-[\w-]{8}\.mjs", n) for n in files), "the map's worker file is not in page/assets: MapLibre would make one from a blob, which the policy forbids"
    assert not any(n.endswith(".map") or any(part.startswith(".") for part in n.split("/")) for n in files), "the daemon serves no source map and nothing whose name begins with a dot"


def test_the_files_the_page_reads_at_run_time_are_shipped() -> None:
    files = tree(PAGE)
    for name in SHIPPED:
        assert name in files, f"{name} is read by the page at run time (ui/public/): {HINT}"
    for gone in ("js", "vendor", "style.css", "package.json"):
        assert not (PAGE / gone).exists(), f"page/{gone} is of the page before the build: {HINT}"


@pytest.mark.skipif(node_dir() is None, reason="no node 22.12 or newer (on the PATH or in ~/.nvm): the page is not rebuilt to compare")
@pytest.mark.skipif(not VITE.exists(), reason="ui/node_modules is not installed (cd ui && npm ci): the page is not rebuilt to compare")
def test_the_page_is_what_the_source_builds(tmp_path: Path) -> None:
    fresh_dir = tmp_path / "fresh"
    env = {**os.environ, "PATH": f"{node_dir()}{os.pathsep}{os.environ['PATH']}", "NEOAPRS_OUT": str(fresh_dir)}
    r = subprocess.run([str(VITE), "build", "--logLevel", "error"], cwd=UI, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    fresh, kept = tree(fresh_dir), tree(PAGE)
    assert sorted(fresh) == sorted(kept), f"page/ and a fresh build have different files: only built {sorted(set(fresh) - set(kept))}, only in page/ {sorted(set(kept) - set(fresh))}; {HINT}"
    stale = [name for name in fresh if fresh[name] != kept[name]]
    assert not stale, f"page/ is out of date ({', '.join(stale)}): {HINT}"
