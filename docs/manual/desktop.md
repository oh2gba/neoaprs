# The desktop app

`neoaprs app` (or `neoaprs-app`, the same without a console window) is NeoAPRS for people who do not want to run a daemon. It is the page in a window of its own and an icon in the tray.

The window is not a second program. It is the same page that the daemon serves, in the system's own web engine, so anything the page does in a browser it does here.

It needs the extra `app`: `uv tool install "neoaprs[app]"` or `pip install "neoaprs[app]"`. The Windows installer and the AppImage have it inside.

## Attach or start

- With a daemon holding the data folder (a service, `neoaprs run` in a terminal, `neoaprs open`), the app **attaches**. It finds the page's address in the log, as `neoaprs open` does, and shows it. **Quit leaves that daemon running**, and a systemd user service keeps running.
- With none, the app **starts** one, detached, and owns it. **Stop and quit** stops it (the same end as `neoaprs stop`). While it runs, the app notices when something else stops it (`neoaprs stop`, the uninstaller, the Start menu's Stop NeoAPRS) and ends too.
- The daemon outlives a crash of the window, and a crashed app leaves a daemon that the next `neoaprs app` attaches to.

## The window

- It is titled NeoAPRS, 1280x800 the first time, then the size it was closed with.
- What the page keeps in the browser (the panel's width and tab, the map's view, the messages and bulletins seen) is kept in the folder `webview/` of the data folder, so it survives a restart. It belongs to the page's address, `127.0.0.1` and the port. A page that moves to another port (7303 was taken) starts with a clean slate there.
- Closing the window **hides** it. NeoAPRS goes on listening in the tray.
- A link to another site (the QRZ page of a call, the credits of the map) and a link that asks for a new tab open in the system's browser and never in the window. `file:` and `javascript:` addresses are dropped.

## The tray menu

- *Open NeoAPRS* (also a click on the icon) shows the window.
- *Open in browser* shows the page in the browser.
- *Start at sign-in* is a checkbox.
- *Stop and quit* stops the daemon if the app started it and ends the app. For an attached daemon the last item reads *Quit (NeoAPRS keeps running as a service)* and only ends the app.

**Start at sign-in** makes the app start in the tray, with the window hidden, when you sign in: `neoaprs-app --tray`.

- On Windows it is the value `NeoAPRS` of the same login list that the installer's task and `neoaprs service install` write to, so there is one start at sign-in. The checkbox replaces a daemon entry from `neoaprs service install` with the app's.
- On Linux it is an autostart file, `~/.config/autostart/neoaprs.desktop` (`$XDG_CONFIG_HOME`), which KDE, GNOME and the others read.
- macOS has none and the item is not there.
- The daemon is not a second thing to start: the app starts it.

## One app

A second `neoaprs-app` on the same data folder raises the first one's window and ends (with `--tray` it only ends). `neoaprs app --quit` ends the app that is running and waits until it has ended; the Windows uninstaller and an update use it.

## Alerts

The tray shows no toast of its own. The alert command of the daemon ([notifications.md](notifications.md)) runs whether the app is open, hidden in the tray or not installed at all, and is configured and tried in one place, the Settings tab. The only tray notice is the one that says why *Start at sign-in* could not be changed.

## When there is no window

The app chooses what the computer can run and says what it chose, and why, in `neoaprs-app.log`.

- **The window and the tray** when the computer has the web engine. On Windows that is the WebView2 runtime, which Windows 11 and every current Windows 10 have.
- **The tray and the page in the browser** without the web engine (*Open NeoAPRS* is the browser then).
- **The page in the browser and nothing else** without any toolkit, with the daemon left running and the way to end it (`neoaprs stop`) printed.
- A window that cannot start at all (no display) is the same fallback, with exit code 1.
- A desktop with no system tray (GNOME without its extension) gets the window, and closing it quits, there being nothing to bring it back from. At sign-in the tray is waited for for a minute, since the panel may start after the app.

## Which toolkit

- **Linux and macOS:** Qt (`PySide6-Essentials`, `PySide6-Addons` and `PySide6-WebEngine`, which is its own wheel and needs the other two), with the web engine of Qt, a Chromium: about 260 MB to download and 670 MB installed on Linux.
- **Windows:** pywebview, which uses the Edge engine that is already on the computer, and pystray with Pillow for the tray icon: about 9 MB of wheels. The frozen app carries no browser.

## Files in the data folder

`neoaprs-app.log` (the app's log, rotating, 1 MB), `neoaprs-app.json` (the window's size), `neoaprs-app.lock` and `neoaprs-app.port` (the one-app rule), and `webview/` (the web engine's storage). The daemon's own lock, `neoaprs.lock`, is separate.

On Windows, the app is `neoaprs-app.exe`, not `NeoAPRS.exe`, because Windows file names ignore case and that would be the console program `neoaprs.exe`.
