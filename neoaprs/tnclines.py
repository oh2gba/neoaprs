"""A source that also keeps when each line of its log was written: `Source.lines` shows only the time of day (UTC), and the page's terminal shows the line in the viewer's time and on its own day."""
from collections import deque
from datetime import datetime

from .clock import Clock, utcnow
from .source import Source

LINE_TIME_WIDTH = len("12:00:00  ")             # what Source puts in front of every line it keeps: the time of day and two blanks


class TimedSource(Source):
    def __init__(self, name: str, clock: Clock = utcnow) -> None:
        super().__init__(name, clock)
        self.line_times: deque[datetime] = deque(maxlen=self.MAX_LINES)   # when each of `lines` was written, the same length and order

    def _add_line(self, text: str) -> None:
        self.line_times.append(self.clock())
        super()._add_line(text)

    def recent_lines(self, count: int) -> list[tuple[datetime, str]]:
        """The latest `count` lines, oldest first, each with the time it was written and its text without the time of day that `lines` shows in front of it."""
        return [(at, line[LINE_TIME_WIDTH:]) for at, line in zip(list(self.line_times)[-count:], list(self.lines)[-count:], strict=False)]
