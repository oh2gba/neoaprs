"""What a test reads of the log it captured."""

import logging

import pytest

# The database's note of an operation that ran long (neoaprs/dbthread.py) says how fast the
# machine's disk was, not what the code under test did
SLOW_DISK = ("neoaprs.db", "of the database ran for")


def warnings_in(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The records at WARNING and above, the database's note of a slow disk left out."""
    return [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING and not (r.name == SLOW_DISK[0] and SLOW_DISK[1] in r.getMessage())
    ]
