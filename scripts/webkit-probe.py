#!/usr/bin/env python3
"""How the map moves in a window of a web engine, counted (aprs-reference/window-plan.md, 9.1 and 9.3): one window on the daemon's page, then for SECONDS the map is zoomed with the wheel and dragged with the
mouse (events dispatched on the map's canvas: nothing is added to the page for it), and the frames are counted with requestAnimationFrame. It prints one line of JSON: the frames and frames per second, whether
WebGL2 can be had, the engine's user agent, the time from the start of this script to the window's first paint of the page, and the engine.

  webkit-probe.py --url URL [--seconds 20] [--engine web|qt]

--engine web (default): pywebview on WebKitGTK as the trial's window has it (neoaprs/desktop/gtkenv.py first); run it with the trial AppImage's own Python (scripts/smoke-appimage-web does) or a Python that
has pywebview and gi. --engine qt: the same in today's Qt window (QWebEngineView), with a Python that has PySide6-WebEngine (the checkout's .venv). Needs a display; nothing leaves the loopback but what the page
itself asks for (its tiles come from the daemon)."""
import argparse
import importlib
import json
import sys
import threading
import time
from typing import Any

STARTED = time.monotonic()
SETTLE_SEC = 3.0                     # the page and its first tiles, before the map is moved

# Starts the counting and the moving; READ gives what was counted, as JSON text.
START = """(function () {
  var p = window.__probe = {frames: 0, start: performance.now(), done: false};
  (function tick() { p.frames++; if (!p.done) requestAnimationFrame(tick); })();
  var canvas = document.querySelector('.maplibregl-canvas');
  p.map = !!canvas;
  if (!canvas) return;
  var r = canvas.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, step = 0;
  p.timer = setInterval(function () {
    step++;
    if (step % 4 < 2) {
      canvas.dispatchEvent(new WheelEvent('wheel', {deltaY: step % 4 ? 240 : -240, deltaMode: 0, clientX: x, clientY: y, bubbles: true, cancelable: true}));
    } else {
      var dx = step % 8 < 4 ? 160 : -160;
      canvas.dispatchEvent(new MouseEvent('mousedown', {clientX: x, clientY: y, button: 0, buttons: 1, bubbles: true}));
      for (var i = 1; i <= 8; i++) window.dispatchEvent(new MouseEvent('mousemove', {clientX: x + dx * i / 8, clientY: y, buttons: 1, bubbles: true}));
      window.dispatchEvent(new MouseEvent('mouseup', {clientX: x + dx, clientY: y, button: 0, bubbles: true}));
    }
  }, 500);
})();"""
READ = """(function () {
  var p = window.__probe; p.done = true; clearInterval(p.timer);
  var seconds = (performance.now() - p.start) / 1000, paint = performance.getEntriesByType('paint').filter(function (e) { return e.name === 'first-contentful-paint'; })[0];
  var gl = null; try { gl = document.createElement('canvas').getContext('webgl2'); } catch (e) {}
  return JSON.stringify({frames: p.frames, seconds: seconds, fps: p.frames / seconds, map: p.map, webgl2: gl !== null, userAgent: navigator.userAgent, firstPaintMs: paint ? paint.startTime : null});
})()"""


def report(engine: str, said: str, loaded_at: float) -> None:
    result: dict[str, Any] = json.loads(said)
    result.update(engine=engine, loadedAfterSec=round(loaded_at - STARTED, 3))
    print(json.dumps(result), flush=True)


def with_webkit(url: str, seconds: float) -> int:
    from neoaprs.desktop import gtkenv, shell
    gtkenv.prepare()
    problem = shell.gtk_window_problem(importlib.import_module)
    if problem is not None:
        print(f"webkit-probe: no web window here: {problem}", file=sys.stderr)
        return 1
    import webview
    window = webview.create_window("NeoAPRS probe", url, width=1280, height=800)
    loaded = threading.Event()
    window.events.loaded += loaded.set

    def measure() -> None:
        try:
            if not loaded.wait(60):
                print("webkit-probe: the page did not load within 60 s", file=sys.stderr)
                return
            loaded_at = time.monotonic()
            time.sleep(SETTLE_SEC)
            window.evaluate_js(START)
            time.sleep(seconds)
            report("webkitgtk", str(window.evaluate_js(READ)), loaded_at)
        finally:
            window.destroy()

    webview.start(measure, gui="gtk", private_mode=True)
    return 0


def with_qt(url: str, seconds: float) -> int:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.resize(1280, 800)
    loaded_at: list[float] = []

    def read() -> None:
        view.page().runJavaScript(READ, 0, lambda said: (report("qtwebengine", str(said), loaded_at[0]), app.quit()))

    def on_loaded(ok: bool) -> None:
        if loaded_at:
            return
        loaded_at.append(time.monotonic())
        QTimer.singleShot(int(SETTLE_SEC * 1000), lambda: view.page().runJavaScript(START))
        QTimer.singleShot(int((SETTLE_SEC + seconds) * 1000), read)

    view.loadFinished.connect(on_loaded)
    view.setUrl(QUrl(url))
    view.show()
    return int(app.exec())


def main() -> int:
    parser = argparse.ArgumentParser(prog="webkit-probe.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="the daemon's page")
    parser.add_argument("--seconds", type=float, default=20.0, help="how long the map is moved and counted; default %(default)s")
    parser.add_argument("--engine", choices=("web", "qt"), default="web")
    args = parser.parse_args()
    return with_qt(args.url, args.seconds) if args.engine == "qt" else with_webkit(args.url, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
