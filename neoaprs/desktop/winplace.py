"""The window's placement on Windows: its size, its place and whether it is maximized, as Windows itself keeps them (WINDOWPLACEMENT), read with GetWindowPlacement and given back with SetWindowPlacement
through ctypes and user32, and the app's file of them (appstate.py). The Windows shell (winshell.py) hands it pywebview's window and its events; this file imports no toolkit, only `ctypes`, whose `windll`
is Windows' alone: where it is not there, nothing is asked of Windows and nothing is saved. Every save and every restore is a line of the app's log that starts with "window:"."""
import ctypes
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import appstate

log = logging.getLogger("neoaprs.desktop")

SAVE_SIZE_SEC = 0.5
SW_HIDE, SW_SHOWNORMAL, SW_SHOWMINIMIZED, SW_SHOWMAXIMIZED = 0, 1, 2, 3     # (Win32's show states, as WINDOWPLACEMENT has them)
WPF_RESTORETOMAXIMIZED = 0x2                    # (in its flags: a minimised window that goes back maximized)
MONITOR_DEFAULTTONEAREST = 2
Rect = tuple[int, int, int, int]                # left, top, right, bottom


class _Point(ctypes.Structure):
    _fields_ = (("x", ctypes.c_int32), ("y", ctypes.c_int32))


class _Rect(ctypes.Structure):
    _fields_ = (("left", ctypes.c_int32), ("top", ctypes.c_int32), ("right", ctypes.c_int32), ("bottom", ctypes.c_int32))

    def corners(self) -> Rect:
        return self.left, self.top, self.right, self.bottom


class _Placement(ctypes.Structure):
    """Win32's WINDOWPLACEMENT."""
    _fields_ = (("length", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("showCmd", ctypes.c_uint32), ("ptMinPosition", _Point), ("ptMaxPosition", _Point), ("rcNormalPosition", _Rect))


class _MonitorInfo(ctypes.Structure):
    """Win32's MONITORINFO."""
    _fields_ = (("cbSize", ctypes.c_uint32), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", ctypes.c_uint32))


@dataclass(frozen=True)
class Placement:
    """What GetWindowPlacement says: the show state, the flags and the normal rectangle (the one the window has when it is neither maximized nor minimised, kept by Windows whatever the window is now)."""
    show_cmd: int
    flags: int
    normal: Rect

    @property
    def maximized(self) -> bool:
        """Maximized, or minimised from maximized (a click on the taskbar takes it back maximized): a window is never brought back minimised."""
        return self.show_cmd == SW_SHOWMAXIMIZED or (self.show_cmd == SW_SHOWMINIMIZED and bool(self.flags & WPF_RESTORETOMAXIMIZED))


class Win32Window:
    """The window as Windows itself has it, through user32 and the window's handle (pywebview's `window.native` is the WinForms Form, whose `Handle` is the HWND). Every call is one Windows answers for any thread
    of the process, and one that fails (a handle that is gone, a function an old Windows has not) is None or False, never an error: the window must go on."""

    def __init__(self, user32: Any, hwnd: int) -> None:
        self.user32 = user32
        self.hwnd = hwnd

    @classmethod
    def of(cls, window: Any) -> "Win32Window | None":
        """The window's Win32 side, or None where there is no Win32 (`ctypes.windll` is Windows' alone) or the window has no form yet."""
        windll = getattr(ctypes, "windll", None)
        native = getattr(window, "native", None)
        if windll is None or native is None:
            return None
        try:
            return cls(windll.user32, int(native.Handle.ToInt64()))
        except Exception:
            log.debug("window: the handle of the form could not be had", exc_info=True)
            return None

    def _call(self, name: str, *args: Any) -> Any:
        try:
            return getattr(self.user32, name)(*args)
        except (AttributeError, OSError, ctypes.ArgumentError):
            return None

    def placement(self) -> Placement | None:
        wp = _Placement()
        wp.length = ctypes.sizeof(_Placement)
        if not self._call("GetWindowPlacement", ctypes.c_void_p(self.hwnd), ctypes.byref(wp)):
            return None
        return Placement(wp.showCmd, wp.flags, wp.rcNormalPosition.corners())

    def place(self, normal: Rect, show_cmd: int) -> bool:
        """SetWindowPlacement: the normal rectangle and the show state. Windows moves a rectangle that is on no monitor now onto one itself."""
        wp = _Placement()
        wp.length = ctypes.sizeof(_Placement)
        wp.showCmd = show_cmd
        wp.rcNormalPosition = _Rect(*normal)
        return bool(self._call("SetWindowPlacement", ctypes.c_void_p(self.hwnd), ctypes.byref(wp)))

    def visible(self) -> bool:
        return bool(self._call("IsWindowVisible", ctypes.c_void_p(self.hwnd)))

    def zoomed(self) -> bool:
        return bool(self._call("IsZoomed", ctypes.c_void_p(self.hwnd)))

    def frame(self) -> Rect | None:
        """GetWindowRect: where the frame is on the screen now."""
        rc = _Rect()
        return rc.corners() if self._call("GetWindowRect", ctypes.c_void_p(self.hwnd), ctypes.byref(rc)) else None

    def monitor(self, normal: Rect) -> tuple[Rect, Rect] | None:
        """The whole area and the work area (without the taskbar) of the monitor the rectangle is on, or of the nearest one."""
        handle = self._call("MonitorFromRect", ctypes.byref(_Rect(*normal)), MONITOR_DEFAULTTONEAREST)
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        if not handle or not self._call("GetMonitorInfoW", ctypes.c_void_p(handle), ctypes.byref(info)):
            return None
        return info.rcMonitor.corners(), info.rcWork.corners()

    def dpi(self) -> int | None:
        """The window's DPI (96 is 100 %); GetDpiForWindow is Windows 10 1607 and later."""
        return self._call("GetDpiForWindow", ctypes.c_void_p(self.hwnd)) or None

    def screen(self) -> tuple[int, int] | None:
        """The size of the primary monitor (SM_CXSCREEN, SM_CYSCREEN)."""
        width, height = self._call("GetSystemMetrics", 0), self._call("GetSystemMetrics", 1)
        return (width, height) if width and height else None


class WindowKeeper:
    """Remembers the window the Windows way: what is saved is what GetWindowPlacement says at that moment (the normal rectangle, which Windows keeps whatever the window is now, and whether it is maximized), and
    it is given back with SetWindowPlacement, in the same units, so neither the order of pywebview's events nor display scaling can bend it. pywebview tells each event in a thread of its own, so a `resized`
    with the size of the whole screen can be handled before the `maximized` that came first, and 0.12.0, which put the window together from those events, could save the maximized size as the normal one;
    here an event only starts the timer, and the timer asks Windows. It is saved when the window is hidden (the close button), at Quit, and once the window has stopped changing; it is put back before the
    window is first shown (still hidden, so that the first frame is the right one), again once it is on screen, in case the form undid any of it, and when it is opened from the tray. A window is never brought
    back minimised. Every save and every restore is a line of the app's log that starts with "window:"; the events themselves are DEBUG lines."""

    def __init__(self, data: Path, state: appstate.WindowState, window: Any) -> None:
        self.data = data
        self.state = state                      # the file's, then the latest read from Windows
        self.window = window
        self.maximized = state.maximized
        self._win: Win32Window | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def win32(self) -> Win32Window | None:
        if self._win is None:
            self._win = Win32Window.of(self.window)
        return self._win

    def told(self, name: str) -> Callable[..., None]:
        """A handler for one of pywebview's window events: it is written down (DEBUG) and starts the timer; what it says is not used."""
        def handler(*args: Any) -> None:
            log.debug("window: event %s %s [%s]", name, args, threading.current_thread().name)
            self._later()
        return handler

    def _later(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(SAVE_SIZE_SEC, self.save, ("settled", logging.DEBUG))
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

    def save(self, why: str, level: int = logging.INFO) -> None:
        """Reads the placement from Windows and writes it to the file when it is other than the file has. A hidden window is not read: it was read when it was hidden."""
        win = self.win32()
        if win is None:
            return
        if not win.visible():
            log.log(level, "window: %s: the window is hidden, the placement saved when it was hidden stays", why)
            return
        now = win.placement()
        if now is None:
            log.warning("window: %s: GetWindowPlacement failed, nothing saved", why)
            return
        left, top, right, bottom = now.normal
        state = appstate.WindowState(right - left, bottom - top, None, None, now.maximized, now.normal)
        log.log(level, "window: %s: read showCmd=%d flags=%d normal=%s, saved maximized=%s", why, now.show_cmd, now.flags, now.normal, state.maximized)
        with self._lock:
            self.maximized = state.maximized
            if state != self.state:
                appstate.save_window(self.data, state)
                self.state = state

    def before_show(self) -> None:
        """pywebview's `before_show`, on its GUI thread with the form made and not yet shown: the form goes to the normal rectangle it had, still hidden (SW_HIDE); the form itself shows it maximized, which
        create_window was told."""
        win = self.win32()
        if win is None or self.state.normal is None:
            return
        done = win.place(self.state.normal, SW_HIDE)
        log.info("window: start: before it is shown, normal=%s %s", self.state.normal, "placed" if done else "refused by SetWindowPlacement")

    def shown(self) -> None:
        """pywebview's `shown`: the placement is applied again to the window on screen, and what Windows then says is logged. A window started in the tray is shown and hidden at once: it gets its placement when
        it is opened."""
        log.debug("window: event shown [%s]", threading.current_thread().name)
        win = self.win32()
        if win is None:
            return
        if not win.visible():
            log.info("window: start: in the tray, the placement is applied when the window is opened")
            return
        self.apply("start", self.state)

    def open(self) -> bool:
        """Open from the tray (or a second app's show): the window is shown and given the placement it was hidden with, or its own when it is on screen already (perhaps minimised). False where there is no Win32."""
        win = self.win32()
        if win is None:
            return False
        now = win.placement() if win.visible() else None
        state = self.state if now is None else replace(self.state, maximized=now.maximized, normal=now.normal)
        log.info("window: open: %s placement, maximized=%s normal=%s", "the saved" if now is None else "its own", state.maximized, state.normal)
        self.window.show()
        self.apply("open", state)
        return True

    def apply(self, why: str, state: appstate.WindowState) -> None:
        """SetWindowPlacement with the normal rectangle of `state` (the window's own when the file has none: an earlier version's file) and maximized or normal; then what GetWindowPlacement and GetWindowRect
        say, and a warning when it is not what was asked (Windows moves a rectangle that is on no monitor, and anything else that undoes it is worth knowing)."""
        win = self.win32()
        if win is None:
            return
        normal = state.normal
        if normal is None:
            now = win.placement()
            if now is None:
                log.warning("window: %s: GetWindowPlacement failed, nothing applied", why)
                return
            normal = now.normal
        show_cmd = SW_SHOWMAXIMIZED if state.maximized else SW_SHOWNORMAL
        areas, screen = win.monitor(normal), win.screen()
        log.info("window: %s: apply showCmd=%d normal=%s monitor=%s work=%s dpi=%s screen=%s", why, show_cmd, normal, areas[0] if areas else "?", areas[1] if areas else "?", win.dpi() or "?",
                 f"{screen[0]}x{screen[1]}" if screen else "?")
        done = win.place(normal, show_cmd)
        after = win.placement()
        log.info("window: %s: after showCmd=%s normal=%s frame=%s zoomed=%s", why, after.show_cmd if after else "?", after.normal if after else "?", win.frame(), win.zoomed())
        if not done or after is None or after.show_cmd != show_cmd or after.normal != normal:
            log.warning("window: %s: the window is not as applied (showCmd=%d normal=%s)%s", why, show_cmd, normal, "" if done else ": SetWindowPlacement failed")
        self.maximized = state.maximized
