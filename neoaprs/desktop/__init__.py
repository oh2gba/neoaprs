"""The desktop app: `neoaprs app` and `neoaprs-app`. The page of the daemon in a window of the system's own web engine, a tray icon, and the daemon started (and stopped at Quit) by the app when none runs.

    cmd.py        the command line and the run: what is attached to or started (without waiting for it), which shell, the log
    session.py    the daemon of the data folder: attach to the one that runs, else start one detached (as `neoaprs open` does) and remember that the app owns it; in a thread of its own while the window is made
    links.py      which addresses stay in the window and which go to the system's browser
    splash.py     Windows only: the app's name in a small window of user32 and gdi32 from the first moment, until the real window (which needs .NET and WebView2 first) is shown
    loading.py    what the window shows until the daemon's page answers: the mark and the name on the page's background
    menu.py       the tray menu as data, and what its items do (the same for both shells)
    autostart.py  start at sign-in: the Run key on Windows, an XDG autostart file elsewhere
    single.py     one app to a data folder: a second one brings the first one's window up
    appstate.py   what the app remembers in the data folder: the window's size, the web engine's storage
    shell.py      which shell this computer can run, and the fallback when none can show a window
    qtshell.py    the shell of Linux and macOS: Qt (QWebEngineView and QSystemTrayIcon), one event loop
    winshell.py   the shell of Windows: pywebview (WebView2) for the window, pystray for the tray icon
    winplace.py   the window's placement on Windows (GetWindowPlacement, SetWindowPlacement): saved and given back

Only qtshell.py and winshell.py import a toolkit (PySide6, pywebview, pystray, Pillow); they are the app's optional dependencies (`pip install neoaprs[app]`) and nothing else imports them.
"""
