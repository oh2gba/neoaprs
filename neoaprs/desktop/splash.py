"""A small window with the app's name, shown on Windows from the first moment of `neoaprs-app.exe`.

It needs only user32 and gdi32 through ctypes, so it shows before anything heavy is imported.
It goes when the real window shows (`done`) or after LIMIT_SEC; elsewhere nothing is shown."""

import os
import sys
import threading

from .loading import BACKGROUND, TEXT

NAME = "NeoAPRS"
WINDOW_CLASS = "NeoAPRSSplash"  # tells it from the real window, whose title is the name too
SIZE = (360, 120)  # at 96 dpi; scaled by the system's DPI
NAME_PX = 30  # height of the name's letters at 96 dpi
FONT = "Segoe UI"  # the UI font of Windows
LIMIT_SEC = 15.0  # it never stays longer than this, whatever the app does

# The app's options (a copy of cmd.parser's, kept equal by tests/test_desktop_splash.py): whether
# each takes a value. NO_WINDOW lists those that mean no window now.
OPTIONS = {
    "--data": True,
    "--tray": False,
    "--quit": False,
    "--timeout": True,
    "--debug": False,
    "--encryption": False,
    "--owns-daemon": False,
    "--help": False,
    "-h": False,
}
NO_WINDOW = ("--tray", "--quit", "--help", "-h")
# The files of the app that holds a data folder (single.py).
PORT_NAME, PID_NAME = "neoaprs-app.port", "neoaprs-app.pid"


def option(arg: str) -> str | None:
    """Return the option an argument names as argparse reads it, else None."""
    if arg in OPTIONS:
        return arg
    found = [
        name
        for name in OPTIONS
        if name.startswith("--") and arg.startswith("--") and len(arg) > 2 and name.startswith(arg)
    ]
    return found[0] if len(found) == 1 else None


def window_now(argv: list[str]) -> str | None:
    """Return the data folder if the arguments make a window now (not --tray, --quit, help or a bad option)."""
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
    """Return neoaprs.paths.default_data_dir without pathlib (a test keeps them equal)."""
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
    """Return True if an app holds the data folder (port file and a live pid file); nothing is locked."""
    try:
        if not os.path.isfile(os.path.join(data, PORT_NAME)):
            return False
        with open(os.path.join(data, PID_NAME), encoding="ascii") as file:
            pid = int(file.read().strip())
    except (OSError, ValueError):
        return False
    return alive(pid)


def alive(pid: int) -> bool:
    """Return single.process_alive's answer without its imports."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            return False
        try:
            # 0x102 is WAIT_TIMEOUT: the process has not ended.
            return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)
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
    """Return left, top, width and height: SIZE at the DPI, centred in the work area."""
    width, height = (scaled(n, dpi) for n in SIZE)
    left, top, right, bottom = work
    return left + (right - left - width) // 2, top + (bottom - top - height) // 2, width, height


def scaled(pixels: int, dpi: int) -> int:
    return pixels * dpi // 96


def colorref(colour: str) -> int:
    """Convert #rrggbb to the Windows COLORREF (0x00bbggrr)."""
    red, green, blue = int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)
    return blue << 16 | green << 8 | red


class Splash:
    """The splash handle; `close` is safe from any thread, at any time, any number of times."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hwnd = 0
        self._closed = False
        # The window procedure (a ctypes callback), kept so it is not freed while still in use.
        self.procedure: object = None

    def made(self, hwnd: int) -> bool:
        """Record the new window; return False if the splash was closed before it was made."""
        with self._lock:
            if self._closed:
                return False
            self._hwnd = hwnd
            return True

    def gone(self) -> None:
        """Record that the window is destroyed or its thread has ended."""
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
    """Show the splash on Windows, once per process, unless no window is coming or an app runs already."""
    global _current
    if sys.platform == "win32":
        try:
            data = window_now(argv)
            if _current is None and data is not None and not running(data):
                _current = Splash()
                threading.Thread(target=run, args=(_current,), name="neoaprs-splash", daemon=True).start()
        except Exception:
            # The app starts as it would without a splash.
            _gave_up()


def done() -> None:
    """Close the splash if there is one; safe anywhere, on any system, any number of times."""
    if _current is not None:
        _current.close()


def _gave_up() -> None:
    """Log why there is no splash (logging is imported only now, to keep start-up light)."""
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
    # A DPI_AWARENESS_CONTEXT, set for this thread only so pywebview's process setting is untouched.
    PER_MONITOR_AWARE_V2 = -4
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    P = ctypes.c_void_p

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", P),
            ("hIcon", P),
            ("hCursor", P),
            ("hbrBackground", P),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hdc", P),
            ("fErase", wintypes.BOOL),
            ("rcPaint", wintypes.RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", ctypes.c_byte * 32),
        ]

    # Each call's result and argument types, on this module's own library objects (ctypes.windll is
    # shared with pywebview and pystray, which set other argument types on some of them).
    USER32: dict[str, tuple[object, ...]] = {
        "SetThreadDpiAwarenessContext": (P, P),
        "GetDpiForSystem": (wintypes.UINT,),
        "SystemParametersInfoW": (wintypes.BOOL, wintypes.UINT, wintypes.UINT, P, wintypes.UINT),
        "LoadCursorW": (P, P, P),
        "RegisterClassW": (wintypes.ATOM, P),
        "UnregisterClassW": (wintypes.BOOL, wintypes.LPCWSTR, P),
        "CreateWindowExW": (
            P,
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            P,
            P,
            P,
            P,
        ),
        "ShowWindow": (wintypes.BOOL, P, ctypes.c_int),
        "UpdateWindow": (wintypes.BOOL, P),
        "DestroyWindow": (wintypes.BOOL, P),
        "SetTimer": (ctypes.c_size_t, P, ctypes.c_size_t, wintypes.UINT, P),
        "GetMessageW": (wintypes.BOOL, P, P, wintypes.UINT, wintypes.UINT),
        "TranslateMessage": (wintypes.BOOL, P),
        "DispatchMessageW": (LRESULT, P),
        "DefWindowProcW": (LRESULT, P, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM),
        "PostMessageW": (wintypes.BOOL, P, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM),
        "PostQuitMessage": (None, ctypes.c_int),
        "BeginPaint": (P, P, P),
        "EndPaint": (wintypes.BOOL, P, P),
        "GetClientRect": (wintypes.BOOL, P, P),
        "DrawTextW": (ctypes.c_int, P, wintypes.LPCWSTR, ctypes.c_int, P, wintypes.UINT),
    }
    GDI32: dict[str, tuple[object, ...]] = {
        "CreateSolidBrush": (P, wintypes.DWORD),
        "CreateFontW": (P, *(ctypes.c_int,) * 5, *(wintypes.DWORD,) * 8, wintypes.LPCWSTR),
        "SelectObject": (P, P, P),
        "SetBkMode": (ctypes.c_int, P, ctypes.c_int),
        "SetTextColor": (wintypes.DWORD, P, wintypes.DWORD),
        "DeleteObject": (wintypes.BOOL, P),
    }
    KERNEL32: dict[str, tuple[object, ...]] = {"GetModuleHandleW": (P, wintypes.LPCWSTR)}

    _libraries: dict[str, ctypes.WinDLL] = {}

    def _library(name: str, calls: dict[str, tuple[object, ...]]) -> ctypes.WinDLL:
        if name not in _libraries:
            dll = ctypes.WinDLL(name)
            for call, (result, *arguments) in calls.items():
                # The two DPI calls exist only on Windows 10 1607 and later.
                function = getattr(dll, call, None)
                if function is not None:
                    function.restype, function.argtypes = result, arguments
            _libraries[name] = dll
        return _libraries[name]

    def _user32() -> ctypes.WinDLL:
        return _library("user32", USER32)

    def run(handle: Splash) -> None:
        """Thread body: make the window, run its message loop until destroyed, release resources."""
        try:
            user32, gdi32 = _user32(), _library("gdi32", GDI32)
            instance = _library("kernel32", KERNEL32).GetModuleHandleW(None)
            if hasattr(user32, "SetThreadDpiAwarenessContext"):
                user32.SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)
            dpi = (user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 0) or 96
            brush = gdi32.CreateSolidBrush(colorref(BACKGROUND[True]))
            font = gdi32.CreateFontW(
                -scaled(NAME_PX, dpi), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, 1, 0, 0, CLEARTYPE_QUALITY, 0, FONT
            )
            try:
                # The handle keeps the callback alive for the life of the process.
                handle.procedure = WNDPROC(
                    lambda hwnd, message, wparam, lparam: _message(handle, hwnd, message, wparam, lparam, font)
                )
                kind = WNDCLASSW(
                    lpfnWndProc=handle.procedure,
                    hInstance=instance,
                    hCursor=user32.LoadCursorW(None, IDC_ARROW),
                    hbrBackground=brush,
                    lpszClassName=WINDOW_CLASS,
                )
                if user32.RegisterClassW(ctypes.byref(kind)):
                    try:
                        _window(handle, user32, instance, dpi)
                    finally:
                        user32.UnregisterClassW(WINDOW_CLASS, instance)
            finally:
                gdi32.DeleteObject(font)
                gdi32.DeleteObject(brush)
        except Exception:
            # No splash; the app goes on without one.
            _gave_up()
        finally:
            handle.gone()

    def _window(handle: Splash, user32: ctypes.WinDLL, instance: int, dpi: int) -> None:
        work = wintypes.RECT()
        if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
            return
        left, top, width, height = place((work.left, work.top, work.right, work.bottom), dpi)
        hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
            WINDOW_CLASS,
            NAME,
            WS_POPUP,
            left,
            top,
            width,
            height,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            return
        if not handle.made(hwnd):
            user32.DestroyWindow(hwnd)
            return
        try:
            user32.SetTimer(hwnd, 1, int(LIMIT_SEC * 1000), None)
            # Not activated: the real window takes focus later, and focus is not handed to another
            # program when this one goes.
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            user32.UpdateWindow(hwnd)
            message = wintypes.MSG()
            # GetMessageW returns -1 on failure: the loop ends, and so does the window.
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            handle.gone()
            # Harmless if already destroyed; otherwise do not leave the window behind.
            user32.DestroyWindow(hwnd)

    def _message(handle: Splash, hwnd: int, message: int, wparam: int, lparam: int, font: int) -> int:
        """The window procedure; WM_CLOSE (from `close`) and the limit timer destroy the window."""
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
            # Always end the paint: an unvalidated WM_PAINT is sent again at once, endlessly.
            user32.EndPaint(hwnd, ctypes.byref(paint))
else:

    def run(handle: Splash) -> None:
        """Only Windows has a splash."""
