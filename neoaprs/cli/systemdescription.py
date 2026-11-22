"""The operating system as a person names it, for the log and the support bundle.

A module of its own, so the daemon need not load the bundle modules to say it."""
import platform


def system_description() -> str:
    """The operating system and its version, as a person names them."""
    system = platform.system()
    if system == "Linux":
        try:
            name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except OSError:
            name = "Linux"
        return f"{name}, kernel {platform.release()}"
    if system == "Windows":
        return f"Windows {platform.release()} ({platform.version()})"
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0] or platform.release()}"
    return platform.platform()
