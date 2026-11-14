"""The small window of the app's name that Windows shows from the first moment of `neoaprs-app.exe` until the real window is there: the real one needs .NET, WinForms and WebView2 first (half a second, three
the first time after an install), and this one needs nothing but user32 and gdi32, through ctypes. It is the name in the system's UI font on the page's dark background (loading.py; the page's own scheme
is not known before anything is read, so it is always the dark one), with no border, no title bar and no taskbar entry, and nothing on it to translate, to animate or to ship.
It is made on a thread of its own, whose message loop it is, and it goes when the real window is shown, when the app ends without one (`done`, from any thread, any number of times), after LIMIT_SEC by
itself, and with the process. The packaging's entry (packaging/windows/neoaprs_entry.py) shows it before anything heavy is imported: this module imports os, sys, threading and, on Windows, ctypes.
A splash that cannot be made is no splash: every failure gives up, with a line in the log and nothing on the screen. On every other system nothing is shown and the functions do nothing."""
import os
import sys
import threading

from .loading import BACKGROUND, TEXT

NAME = "NeoAPRS"
WINDOW_CLASS = "NeoAPRSSplash"            # what tells it from the real window, whose title is the name too
SIZE = (360, 120)                         # at 96 dpi; scaled by the system's DPI
NAME_PX = 30                              # the height of the name's letters at 96 dpi
FONT = "Segoe UI"                         # the UI font of Windows
LIMIT_SEC = 15.0                          # it never stays longer than this, whatever the app does

# The app's arguments as the quick look knows them (cmd.parser has them all; tests/test_desktop_splash.py holds the two equal): whether each takes a value, and which of them mean no window now.
OPTIONS = {"--data": True, "--tray": False, "--quit": False, "--timeout": True, "--debug": False, "--encryption": False, "--help": False, "-h": False}
NO_WINDOW = ("--tray", "--quit", "--help", "-h")
PORT_NAME, PID_NAME = "neoaprs-app.port", "neoaprs-app.pid"     # the files of the app that holds a data folder (single.py)


def option(arg: str) -> str | None:
    """The option an argument names as argparse reads it: the whole name, or a long one shortened to a part that is the start of no other; None for anything else."""
    if arg in OPTIONS:
        return arg
    found = [name for name in OPTIONS if name.startswith("--") and arg.startswith("--") and len(arg) > 2 and name.startswith(arg)]
    return found[0] if len(found) == 1 else None


def window_now(argv: list[str]) -> str | None:
    """The data folder when the app's arguments make a window now, None when they do not: --tray, --quit, the help, or anything the app's parser refuses (it says so, and no window comes)."""
    data: str | None = None
    args = iter(argv)
    for arg in args:
        name, equals, value = arg.partition("=") if arg.startswith("--") else (arg, "", "")
        known = option(name)
        if known is None or known in NO_WINDOW:
            return None
        if not OPTIONS[known]:
            if equals:
                return None
            continue
        if not equals:
            given = next(args, None)
            if given is None:
                return None
            value = given
        if known == "--data":
            data = value
    return os.path.abspath(os.path.expanduser(data if data is not None else default_data()))


def default_data() -> str:
    """neoaprs.paths.default_data_dir without pathlib, which this module does not import (the test holds them equal)."""
    env = os.environ.get("NEOAPRS_DATA_DIR")
    if env:
        return env
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"), "NeoAPRS")
    elif sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "NeoAPRS")
    else:
        return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "neoaprs")


def running(data: str) -> bool:
    """Whether an app holds the data folder, by the files it keeps there: its port file, and its pid file naming a process that is still there. Nothing is locked to find out, so an app starting beside this
    one is not disturbed. A port file that a crash left behind with a pid that is used again leaves the splash out of one start; an app that is only starting is not seen, and this start shows the splash
    until it finds the lock taken (cmd.run)."""
    try:
        if not os.path.isfile(os.path.join(data, PORT_NAME)):
            return False
        with open(os.path.join(data, PID_NAME), encoding="ascii") as file:
            pid = int(file.read().strip())
    except (OSError, ValueError):
        return False
    return alive(pid)


def alive(pid: int) -> bool:
    """single.process_alive, without its imports."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)             # SYNCHRONIZE and PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)           # WAIT_TIMEOUT: the process has not ended
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def place(work: tuple[int, int, int, int], dpi: int) -> tuple[int, int, int, int]:
    """Left, top, width and height of the splash: SIZE at the DPI, in the middle of the work area (left, top, right, bottom)."""
    width, height = (scaled(n, dpi) for n in SIZE)
    left, top, right, bottom = work
    return left + (right - left - width) // 2, top + (bottom - top - height) // 2, width, height


def scaled(pixels: int, dpi: int) -> int:
    return pixels * dpi // 96


def colorref(colour: str) -> int:
    """A colour of the page (#rrggbb) as Windows takes it (0x00bbggrr)."""
    red, green, blue = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    return blue << 16 | green << 8 | red


class Splash:
    """The handle: `close` takes the window away from any thread, before it is made (the thread then destroys it at once), while it shows, and after its thread has ended, any number of times."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hwnd = 0
        self._closed = False
        self.procedure: object = None         # the window's procedure (a ctypes callback): kept here, never freed while Windows may still call it

    def made(self, hwnd: int) -> bool:
        """The window's thread has made the window; False when it was closed before that."""
        with self._lock:
            if self._closed:
                return False
            self._hwnd = hwnd
            return True

    def gone(self) -> None:
        """The window is destroyed, or its thread has ended: there is nothing left to close."""
        with self._lock:
            self._closed, self._hwnd = True, 0

    def close(self) -> None:
        with self._lock:
            self._closed = True
            hwnd, self._hwnd = self._hwnd, 0
        if hwnd:
            post_close(hwnd)


_current: Splash | None = None


def show(argv: list[str]) -> None:
    """The splash, on Windows, when the app's arguments make a window now and no app holds the data folder already (this start would only raise that one's window); once in a process."""
    global _current
    if sys.platform == "win32":
        try:
            data = window_now(argv)
            if _current is None and data is not None and not running(data):
                _current = Splash()
                threading.Thread(target=run, args=(_current,), name="neoaprs-splash", daemon=True).start()
        except Exception:                                             # (the app starts as it would without a splash)
            _gave_up()


def done() -> None:
    """Takes the splash away, if there is one: safe anywhere, on any system, any number of times."""
    if _current is not None:
        _current.close()


def _gave_up() -> None:
    """A line that says why there is no splash, in the app's log once it is set up and on the standard error before that (logging is imported only then)."""
    import logging
    logging.getLogger("neoaprs.desktop").warning("splash: it could not be made", exc_info=True)


def post_close(hwnd: int) -> None:
    if sys.platform == "win32":
        _user32().PostMessageW(hwnd, WM_CLOSE, 0, 0)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    WS_POPUP, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x80000000, 0x00000080, 0x00000008
    WM_DESTROY, WM_PAINT, WM_CLOSE, WM_TIMER = 0x0002, 0x000F, 0x0010, 0x0113
    SW_SHOWNOACTIVATE, SPI_GETWORKAREA, IDC_ARROW, TRANSPARENT = 4, 0x0030, 32512, 1
    DT_CENTER, DT_VCENTER, DT_SINGLELINE = 0x01, 0x04, 0x20
    FW_SEMIBOLD, CLEARTYPE_QUALITY = 600, 5
    PER_MONITOR_AWARE_V2 = -4                 # a DPI_AWARENESS_CONTEXT: for this thread only, so that the process's own (pywebview's) is not touched
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    P = ctypes.c_void_p

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", P), ("hIcon", P), ("hCursor", P), ("hbrBackground", P),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", P), ("fErase", wintypes.BOOL), ("rcPaint", wintypes.RECT), ("fRestore", wintypes.BOOL), ("fIncUpdate", wintypes.BOOL), ("rgbReserved", ctypes.c_byte * 32)]

    # Every call with its result and its arguments, on libraries of this module's own (ctypes.windll's functions are shared with pywebview and pystray, which give some of them other argument types).
    USER32: dict[str, tuple[object, ...]] = {"SetThreadDpiAwarenessContext": (P, P), "GetDpiForSystem": (wintypes.UINT,), "SystemParametersInfoW": (wintypes.BOOL, wintypes.UINT, wintypes.UINT, P, wintypes.UINT),
              "LoadCursorW": (P, P, P), "RegisterClassW": (wintypes.ATOM, P), "UnregisterClassW": (wintypes.BOOL, wintypes.LPCWSTR, P),
              "CreateWindowExW": (P, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, P, P, P, P),
              "ShowWindow": (wintypes.BOOL, P, ctypes.c_int), "UpdateWindow": (wintypes.BOOL, P), "DestroyWindow": (wintypes.BOOL, P), "SetTimer": (ctypes.c_size_t, P, ctypes.c_size_t, wintypes.UINT, P),
              "GetMessageW": (wintypes.BOOL, P, P, wintypes.UINT, wintypes.UINT), "TranslateMessage": (wintypes.BOOL, P), "DispatchMessageW": (LRESULT, P),
              "DefWindowProcW": (LRESULT, P, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM), "PostMessageW": (wintypes.BOOL, P, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM),
              "PostQuitMessage": (None, ctypes.c_int), "BeginPaint": (P, P, P), "EndPaint": (wintypes.BOOL, P, P), "GetClientRect": (wintypes.BOOL, P, P),
              "DrawTextW": (ctypes.c_int, P, wintypes.LPCWSTR, ctypes.c_int, P, wintypes.UINT)}
    GDI32: dict[str, tuple[object, ...]] = {"CreateSolidBrush": (P, wintypes.DWORD), "CreateFontW": (P, *(ctypes.c_int,) * 5, *(wintypes.DWORD,) * 8, wintypes.LPCWSTR), "SelectObject": (P, P, P),
             "SetBkMode": (ctypes.c_int, P, ctypes.c_int), "SetTextColor": (wintypes.DWORD, P, wintypes.DWORD), "DeleteObject": (wintypes.BOOL, P)}
    KERNEL32: dict[str, tuple[object, ...]] = {"GetModuleHandleW": (P, wintypes.LPCWSTR)}

    _libraries: dict[str, ctypes.WinDLL] = {}

    def _library(name: str, calls: dict[str, tuple[object, ...]]) -> ctypes.WinDLL:
        if name not in _libraries:
            dll = ctypes.WinDLL(name)
            for call, (result, *arguments) in calls.items():
                function = getattr(dll, call, None)                   # (the two DPI calls are Windows 10 1607 and later)
                if function is not None:
                    function.restype, function.argtypes = result, arguments
            _libraries[name] = dll
        return _libraries[name]

    def _user32() -> ctypes.WinDLL:
        return _library("user32", USER32)

    def run(handle: Splash) -> None:
        """The splash's thread: the window, its message loop until it is destroyed, and what it used given back."""
        try:
            user32, gdi32 = _user32(), _library("gdi32", GDI32)
            instance = _library("kernel32", KERNEL32).GetModuleHandleW(None)
            if hasattr(user32, "SetThreadDpiAwarenessContext"):
                user32.SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)
            dpi = (user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 0) or 96
            brush = gdi32.CreateSolidBrush(colorref(BACKGROUND[True]))
            font = gdi32.CreateFontW(-scaled(NAME_PX, dpi), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, 1, 0, 0, CLEARTYPE_QUALITY, 0, FONT)
            try:
                handle.procedure = WNDPROC(lambda hwnd, message, wparam, lparam: _message(handle, hwnd, message, wparam, lparam, font))     # (kept by the handle, which lives as long as the process)
                kind = WNDCLASSW(lpfnWndProc=handle.procedure, hInstance=instance, hCursor=user32.LoadCursorW(None, IDC_ARROW), hbrBackground=brush, lpszClassName=WINDOW_CLASS)
                if user32.RegisterClassW(ctypes.byref(kind)):
                    try:
                        _window(handle, user32, instance, dpi)
                    finally:
                        user32.UnregisterClassW(WINDOW_CLASS, instance)
            finally:
                gdi32.DeleteObject(font)
                gdi32.DeleteObject(brush)
        except Exception:                                             # (no splash, and the app goes on as it would without one)
            _gave_up()
        finally:
            handle.gone()

    def _window(handle: Splash, user32: ctypes.WinDLL, instance: int, dpi: int) -> None:
        work = wintypes.RECT()
        if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
            return
        left, top, width, height = place((work.left, work.top, work.right, work.bottom), dpi)
        hwnd = user32.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST, WINDOW_CLASS, NAME, WS_POPUP, left, top, width, height, None, None, instance, None)
        if not hwnd:
            return
        if not handle.made(hwnd):
            user32.DestroyWindow(hwnd)
            return
        try:
            user32.SetTimer(hwnd, 1, int(LIMIT_SEC * 1000), None)
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)                # (not activated: the real window takes the focus when it comes, and nothing is given back to another program when this one goes)
            user32.UpdateWindow(hwnd)
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:     # (-1 is a failure: the loop ends, and so does the window)
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            handle.gone()
            user32.DestroyWindow(hwnd)                                # (nothing when it is destroyed already; a window the loop left behind is not left to the end of the thread)

    def _message(handle: Splash, hwnd: int, message: int, wparam: int, lparam: int, font: int) -> int:
        """The window's procedure: the background is the class's brush; WM_CLOSE (from `close`) destroys the window by default, and so does the limit's timer. Once it is destroyed nothing is posted to it."""
        user32 = _user32()
        if message == WM_PAINT:
            _paint(user32, hwnd, font)
            return 0
        if message == WM_TIMER:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            handle.gone()
            user32.PostQuitMessage(0)
            return 0
        return int(user32.DefWindowProcW(hwnd, message, wparam, lparam))

    def _paint(user32: ctypes.WinDLL, hwnd: int, font: int) -> None:
        gdi32 = _library("gdi32", GDI32)
        paint = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(paint))
        try:
            if hdc:
                area = wintypes.RECT()
                user32.GetClientRect(hwnd, ctypes.byref(area))
                before = gdi32.SelectObject(hdc, font)
                gdi32.SetBkMode(hdc, TRANSPARENT)
                gdi32.SetTextColor(hdc, colorref(TEXT[True]))
                user32.DrawTextW(hdc, NAME, -1, ctypes.byref(area), DT_CENTER | DT_VCENTER | DT_SINGLELINE)
                gdi32.SelectObject(hdc, before)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(paint))               # (always: a WM_PAINT left unvalidated comes again at once, without end)
else:
    def run(handle: Splash) -> None:
        """Only Windows has a splash."""
