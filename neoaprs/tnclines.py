"""A Source that also keeps when each log line was written.

`Source.lines` shows only the UTC time of day; the page's terminal shows the line in the viewer's
time and day.
"""

from collections import deque
from datetime import datetime

from .clock import Clock, utcnow
from .source import Source

# what Source prefixes to every kept line: the time of day and two blanks
LINE_TIME_WIDTH = len("12:00:00  ")


class TimedSource(Source):
    def __init__(self, name: str, clock: Clock = utcnow) -> None:
        super().__init__(name, clock)
        # when each of `lines` was written, same length and order
        self.line_times: deque[datetime] = deque(maxlen=self.MAX_LINES)

    def _add_line(self, text: str) -> None:
        self.line_times.append(self.clock())
        super()._add_line(text)

    def recent_lines(self, count: int) -> list[tuple[datetime, str]]:
        """Return the latest `count` lines, oldest first, each with its time and its text without
        the time of day.
        """
        return [(at, line[LINE_TIME_WIDTH:]) for at, line in zip(list(self.line_times)[-count:], list(self.lines)[-count:], strict=False)]
