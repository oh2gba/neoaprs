"""The page as an installable app: the manifest and the service worker are served with the headers a browser needs of them (and the checks of every other file of the page), and the built page carries them, with the icons the
manifest names, the version of the package in the worker, and the links in the shell."""
import json
import re
import struct
from pathlib import Path

import pytest

from neoaprs import VERSION
from neoaprs.web import server as web_server
from tests.support.env import Env

PAGE = Path(__file__).resolve().parent.parent / "neoaprs" / "page"
SECURITY = ("Content-Security-Policy", "X-Frame-Options", "Referrer-Policy", "X-Content-Type-Options", "Cross-Origin-Resource-Policy")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


async def test_the_manifest_and_the_worker_are_served_for_the_browser_to_check_at_every_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = tmp_path / "page"
    (page / "assets").mkdir(parents=True)
    (page / "icons").mkdir()
    (page / "index.html").write_text('<div id="app"></div>')
    (page / "sw.js").write_text("self.addEventListener('fetch', () => {})")
    (page / "manifest.webmanifest").write_text('{"name": "NeoAPRS"}')
    (page / "icons" / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (page / "assets" / "index-abc12345.js").write_text("1")
    monkeypatch.setattr(web_server, "PAGE_DIR", page)
    e = Env(tmp_path / "data", web=True)
    await e.start()
    worker = await e.fetch("/sw.js")
    assert worker.code == 200 and worker.headers["Content-Type"].startswith("text/javascript")
    assert worker.headers["Cache-Control"] == "no-cache", "a new worker is found at the browser's next check, not a day later"
    assert "Service-Worker-Allowed" not in worker.headers, "the worker is at the root of the page: its scope is the page"
    manifest = await e.fetch("/manifest.webmanifest")
    assert manifest.code == 200 and manifest.headers["Content-Type"].split(";")[0] == "application/manifest+json"
    assert manifest.headers["Cache-Control"] == "no-cache" and json.loads(manifest.body)["name"] == "NeoAPRS"
    icon = await e.fetch("/icons/icon-192.png")
    assert icon.code == 200 and icon.headers["Content-Type"] == "image/png" and icon.headers["Cache-Control"] == "no-cache"
    assert (await e.fetch("/assets/index-abc12345.js")).headers["Cache-Control"] == "public, max-age=31536000, immutable"
    for path in ("/sw.js", "/manifest.webmanifest", "/icons/icon-192.png"):
        answer = await e.fetch(path)
        for key in SECURITY:
            assert answer.headers.get(key), (path, key)


async def test_the_manifest_and_the_worker_answer_only_to_a_host_name_of_ours(tmp_path: Path) -> None:
    e = Env(tmp_path, web=True)
    await e.start()
    for path in ("/sw.js", "/manifest.webmanifest", "/icons/icon-512.png"):
        assert (await e.fetch(path)).code == 200, path
        assert (await e.fetch(path, headers={"Host": "evil.example"})).code == 403, path


def test_the_built_page_is_an_installable_app() -> None:
    manifest = json.loads((PAGE / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "NeoAPRS" and manifest["short_name"] == "NeoAPRS" and manifest["display"] == "standalone"
    assert manifest["start_url"] == "./" and manifest["scope"] == "./", "the page may be opened at any host and port, and behind a prefix"
    assert re.fullmatch(r"#[0-9a-f]{6}", manifest["theme_color"]) and re.fullmatch(r"#[0-9a-f]{6}", manifest["background_color"])
    sizes = {(icon["sizes"], icon["purpose"]) for icon in manifest["icons"]}
    assert sizes == {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
    for icon in manifest["icons"]:
        side = int(icon["sizes"].split("x")[0])
        assert png_size(PAGE / icon["src"]) == (side, side), icon["src"]
    assert png_size(PAGE / "icons" / "apple-touch-icon.png") == (180, 180)
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    assert '<link rel="manifest" href="./manifest.webmanifest"' in html and '<link rel="apple-touch-icon" href="./icons/apple-touch-icon.png"' in html
    assert html.count('name="theme-color"') == 2 and 'media="(prefers-color-scheme: dark)"' in html
    for meta in ("apple-mobile-web-app-capable", "apple-mobile-web-app-status-bar-style", "apple-mobile-web-app-title"):
        assert f'name="{meta}"' in html, meta


def test_the_built_worker_is_of_this_version_and_keeps_to_what_it_may_cache() -> None:
    worker = (PAGE / "sw.js").read_text(encoding="utf-8")
    assert f'const VERSION = "{VERSION}"' in worker and "__PAGE_VERSION__" not in worker
    for forbidden in ("/ws", "pmtiles", "/access"):
        assert forbidden not in re.sub(r"//.*", "", worker), f"the worker names {forbidden}: it handles a short list of the page's own files and nothing else"
