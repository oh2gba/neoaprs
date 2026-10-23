"""What the commands print for a person to read: on stderr, so that what a command prints on stdout (a port to give the daemon, a table) can be taken by a script."""
import signal
import sys

SETTLE_SEC = 0.5                    # after a client has opened the line: a port that opens may clear its input buffer as it does


def ctrl_break_is_ctrl_c() -> None:
    """Windows: Ctrl+Break is the signal a program in a process group of its own can be sent (a script that runs a command, a test), and by default it ends the program at once; here it is Ctrl+C."""
    number = getattr(signal, "SIGBREAK", None)
    if number is not None:
        signal.signal(number, signal.default_int_handler)


def say(text: str) -> None:
    print(text, file=sys.stderr, flush=True)
