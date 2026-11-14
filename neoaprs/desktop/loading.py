"""What the app's window shows from the moment it is made until the daemon's page answers: the mark and the name on the page's own background, in the light scheme and in the dark one, with the colours of
the page's tokens (ui/src/styles/tokens.css: --bg and --text). Nothing on it moves and there is nothing on it to read but the name; the page takes its place in the same window as soon as it answers, and when
no page comes the window closes and the app says why, as it did before there was a window to wait in. One page for both shells: qtwindow.py gives it to the web view, winshell.py to pywebview."""

BACKGROUND = {False: "#f4f5f3", True: "#14171a"}         # --bg of the page, light and dark
TEXT = {False: "#1d2125", True: "#e3e6e8"}               # --text
MARK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64"><rect width="64" height="64" rx="12.8" fill="#18345c"/><polygon points="22,31.24 42,31.24 32,51.2" fill="#fff"/>'
        '<circle cx="32" cy="26.88" r="10.88" fill="#fff"/><circle cx="32" cy="26.88" r="4.57" fill="#18345c"/><g fill="none" stroke-width="3.2"><path d="M46.22 14.95A18.56 18.56 0 0 1 46.22 38.81M17.78 38.81A18.56 18.56 0 0 1 17.78 14.95" stroke="#fff"/>'
        '<path d="M51.61 10.42A25.6 25.6 0 0 1 51.61 43.34M12.39 43.34A25.6 25.6 0 0 1 12.39 10.42" stroke="#60a5eb"/></g></svg>')       # the page's icon, ui/public/icons/icon.svg (tests/test_desktop_startup.py holds them equal)

HTML = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="color-scheme" content="light dark"><title>NeoAPRS</title><style>
:root {{ color-scheme: light dark; background: {BACKGROUND[False]}; color: {TEXT[False]}; }}
@media (prefers-color-scheme: dark) {{ :root {{ background: {BACKGROUND[True]}; color: {TEXT[True]}; }} }}
html, body {{ margin: 0; height: 100%; overflow: hidden; }}
body {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; font: 600 22px system-ui, sans-serif; cursor: default; user-select: none; }}
svg {{ width: 96px; height: 96px; }}
</style></head><body>{MARK}<div>NeoAPRS</div></body></html>"""


def background(dark: bool) -> str:
    """The colour the window's engine paints before the page has painted: the page's background in the scheme the system has."""
    return BACKGROUND[dark]
