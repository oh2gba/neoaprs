"""The loading window of the Windows app (neoaprs/desktop/splash.py) made for real, with the Win32 calls themselves: it is there and shown, of its size, in the middle of the work area, with no button on the
taskbar and without taking the focus, and it is gone when it is taken away. This needs a Windows desktop that is shown: GitHub's Windows runner has one; a service's or an SSH session's window station is
hidden (a window made there is never visible: tried on the test machine, 14 November 2026), and every other system has no such window, so the test is skipped there."""
import ctypes
import sys
import time
from collections.abc import Callable

import pytest

from neoaprs.desktop import splash

CLASS = "NeoAPRSSplash"
PATIENCE_SEC = 30.0                     # how long the test waits for the window to come or go: the patience of a start on a busy runner, not a measure


def shown_desktop() -> bool:
    """Whether this process is on a window station that is shown."""
    visible = False
    if sys.platform == "win32":
        from ctypes import wintypes

        class Flags(ctypes.Structure):
            _fields_ = [("inherit", wintypes.BOOL), ("reserved", wintypes.BOOL), ("flags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.GetProcessWindowStation.restype = ctypes.c_void_p
        user32.GetUserObjectInformationW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        flags, needed = Flags(), wintypes.DWORD()
        station = user32.GetProcessWindowStation()
        visible = bool(station and user32.GetUserObjectInformationW(station, 1, ctypes.byref(flags), ctypes.sizeof(flags), ctypes.byref(needed)) and flags.flags & 1)       # (UOI_FLAGS, WSF_VISIBLE)
    return visible


def wait_for(done: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + PATIENCE_SEC
    while not done():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


@pytest.mark.skipif(not shown_desktop(), reason="needs a Windows desktop that is shown (not a service's or an SSH session's, and no other system)")
def test_the_loading_window_is_shown_in_the_middle_of_the_work_area_without_the_focus_and_is_gone_when_taken_away() -> None:
    if sys.platform == "win32":                         # (always, where the test is not skipped: said so that both type checks read the calls)
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]

        def window() -> int:
            return user32.FindWindowW(CLASS, None) or 0

        assert not window(), "no loading window before the test"
        splash.show([])
        try:
            assert wait_for(lambda: bool(window()) and bool(user32.IsWindowVisible(window()))), "the window is made and shown"
            rect, area = wintypes.RECT(), wintypes.RECT()
            assert user32.GetWindowRect(window(), ctypes.byref(rect)) and user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0)       # (SPI_GETWORKAREA)
            scale = user32.GetDpiForSystem() / 96
            width, height = rect.right - rect.left, rect.bottom - rect.top
            assert abs(width - 360 * scale) <= 2 and abs(height - 120 * scale) <= 2, f"its size follows the screen's scale: {width} x {height} at {scale:g}"
            assert abs((rect.left + rect.right) - (area.left + area.right)) <= 4 and abs((rect.top + rect.bottom) - (area.top + area.bottom)) <= 4, "in the middle of the work area"
            style = user32.GetWindowLongW(window(), -20)                                        # (GWL_EXSTYLE)
            assert style & 0x80 and not style & 0x40000, "a tool window: no button on the taskbar"      # (WS_EX_TOOLWINDOW, not WS_EX_APPWINDOW)
            assert user32.GetForegroundWindow() != window(), "it does not take the focus"
        finally:
            splash.done()
        assert wait_for(lambda: not window()), "taken away, the window is gone"
        splash.done()                                                                           # (a second time is nothing)
