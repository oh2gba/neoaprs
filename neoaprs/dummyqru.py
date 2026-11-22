"""The Dummy radio's QRU server (dummyscene.py): the made-up club Q1CLB answers QRU requests.

It serves two groups round the station, RP70 (a repeater) and FOOD (a cafe), so asking for local
info can be tried without a radio. A request is a broadcast and gets no ack.
"""

import re
from collections.abc import Callable
from datetime import datetime

from neoaprs import ax25

from .dummyframes import air, message, object_report

SERVER = "Q1CLB"
RANGE_KM = 50
# each group: its objects (name, symbol, comment, km east, km north of the centre)
GROUPS: dict[str, list[tuple[str, str, str, float, float]]] = {
    "RP70": [("Q1RPT", "/r", "438.925MHz T088 -760", 3.2, 6.1)],
    "FOOD": [("CAFE", "/h", "Cafe, open 8-16 on weekdays", -0.6, 0.9), ("KIOSK", "/h", "Kiosk by the lake", 4.9, -3.0)],
}
# the first frame of an answer comes this long after the request, the others this long after the
# previous
FIRST_SEC, STEP_SEC = 2.5, 1.2
_REQUEST = re.compile(r"\??([A-Z0-9]{1,8})(?: \d{1,5})?")


def answer(
    text: str,
    us: str,
    now: datetime,
    where: Callable[[float, float], tuple[float, float]],
    named: Callable[[str], str] = str,
) -> list[tuple[float, ax25.Frame]]:
    """Return the frames answering the request `text` of the station `us`, each with its delay.

    None for text that is no request or a group not served.
    """
    found = _REQUEST.fullmatch(" ".join(text.upper().split()))
    if found is None:
        return []
    word = found[1]
    if word == "INFO":
        listing = " ".join(f"{group}({len(objects)})" for group, objects in sorted(GROUPS.items()))
        return [(FIRST_SEC, air(SERVER, message(us, f"de {SERVER}:{listing} Max 5@{RANGE_KM}km")))]
    objects = GROUPS.get(word, [])
    frames = [
        air(SERVER, object_report(named(name), now, *where(east, north), symbol, comment))
        for name, symbol, comment, east, north in objects
    ]
    frames.append(air(SERVER, message(us, f"Sent {len(objects)} {word} Objects Max 5@{RANGE_KM}km de {SERVER}")))
    return [(FIRST_SEC + STEP_SEC * n, frame) for n, frame in enumerate(frames)] if objects else []
