"""A program run with administrator rights on Windows: the verb `runas` of ShellExecuteExW, which raises the UAC prompt (or, for a user who is an administrator with UAC switched off, runs at once), and the exit code of
what it ran. The daemon has no such rights and asks for them only for the one thing it cannot do without: the Windows Firewall rule that keeps the network from Mercury (mercuryrule.py).

`run_elevated` blocks, in the Windows API, until the user has answered the prompt and the program has ended; `elevated` runs it in a thread of its own that does not hold the daemon back when it stops (the prompt may
stay unanswered), and hands the answer to the event loop. A declined prompt is `Declined` (ShellExecuteExW fails with ERROR_CANCELLED); any other failure to start is an OSError; a program that does not end in time is
a TimeoutError. Nothing here is run off Windows."""
import asyncio
import ctypes
import sys
import threading
from ctypes import wintypes

ERROR_CANCELLED = 1223                   # the user said no at the prompt
SEE_MASK_NOCLOSEPROCESS = 0x00000040     # keep the process handle, to wait for it and read its exit code
SEE_MASK_NOASYNC = 0x00000100            # do the work in this thread: it is not a thread of a message loop
COINIT_APARTMENTTHREADED = 0x2
COINIT_DISABLE_OLE1DDE = 0x4
SW_HIDE = 0
WAIT_OBJECT_0 = 0


def on_windows() -> bool:
    return sys.platform == "win32"


class Declined(Exception):
    """The user did not allow the prompt."""


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def run_elevated(file: str, parameters: str, timeout_sec: float) -> int:
    """Runs `file` with `parameters` as an administrator and waits for it for `timeout_sec`; its exit code. Declined when the user said no at the prompt, OSError when it could not be started, TimeoutError when it did not end
    (it is left running). For a thread: it waits for the user."""
    if not on_windows():
        raise OSError("administrator rights are asked for on Windows only")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)                        # type: ignore[attr-defined, unused-ignore]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)                      # type: ignore[attr-defined, unused-ignore]
    ole32 = ctypes.WinDLL("ole32")                                                 # type: ignore[attr-defined, unused-ignore]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
    info.lpVerb, info.lpFile, info.lpParameters, info.nShow = "runas", file, parameters, SW_HIDE
    ole_up = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE) >= 0
    try:
        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()                                        # type: ignore[attr-defined, unused-ignore]
            if error == ERROR_CANCELLED:
                raise Declined()
            raise ctypes.WinError(error)                                           # type: ignore[attr-defined, unused-ignore]
        if not info.hProcess:
            raise OSError("Windows started no process to wait for")
        try:
            if kernel32.WaitForSingleObject(info.hProcess, int(timeout_sec * 1000)) != WAIT_OBJECT_0:
                raise TimeoutError(f"the program did not end in {timeout_sec:g} s")
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())                     # type: ignore[attr-defined, unused-ignore]
            return int(code.value)
        finally:
            kernel32.CloseHandle(info.hProcess)
    finally:
        if ole_up:
            ole32.CoUninitialize()


async def elevated(file: str, parameters: str, timeout_sec: float) -> int:
    """`run_elevated` in a thread of its own (a daemon thread: a prompt left unanswered must not hold the daemon back when it stops), awaited."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[int] = loop.create_future()

    def finish(code: int | None, error: BaseException | None) -> None:
        if done.done():
            return
        if error is not None:
            done.set_exception(error)
        else:
            done.set_result(code or 0)

    def work() -> None:
        try:
            code, error = run_elevated(file, parameters, timeout_sec), None
        except BaseException as e:
            code, error = None, e
        try:
            loop.call_soon_threadsafe(finish, code, error)
        except RuntimeError:                                                       # (the loop has closed: nobody waits for the answer)
            pass

    threading.Thread(target=work, name="elevated", daemon=True).start()
    return await done
