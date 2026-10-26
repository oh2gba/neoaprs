"""The Dummy radio's QRU server (dummyscene.py): the made-up club station Q1CLB answers a request to QRU, so that asking for local info can be tried without a radio. It serves two groups round the station, RP70
(a repeater) and FOOD (a cafe), as a QRU server does (neoaprs/services/qru.py): `INFO` is answered with the list of the groups, a group with its objects one after the other and the line that says how many went. It has
no ack for a request, which is a broadcast, and its messages carry no id. Everything is made up and goes nowhere: the traffic of the Dummy radio is never gated."""
import re
from collections.abc import Callable
from datetime import datetime

from neoaprs import ax25

from .dummyframes import air, message, object_report

SERVER = "Q1CLB"
RANGE_KM = 50
GROUPS: dict[str, list[tuple[str, str, str, float, float]]] = {         # each group: its objects (name, symbol, comment, km east, km north of the centre)
    "RP70": [("Q1RPT", "/r", "438.925MHz T088 -760", 3.2, 6.1)],
    "FOOD": [("CAFE", "/h", "Cafe, open 8-16 on weekdays", -0.6, 0.9), ("KIOSK", "/h", "Kiosk by the lake", 4.9, -3.0)],
}
FIRST_SEC, STEP_SEC = 2.5, 1.2                 # the first frame of an answer comes this long after the request, the others each this long after the one before
_REQUEST = re.compile(r"\??([A-Z0-9]{1,8})(?: \d{1,5})?")


def answer(text: str, us: str, now: datetime, where: Callable[[float, float], tuple[float, float]]) -> list[tuple[float, ax25.Frame]]:
    """The frames the server answers the request `text` of the station `us` with, each with the seconds after the request it comes; none for a text that is no request or a group it does not serve."""
    found = _REQUEST.fullmatch(" ".join(text.upper().split()))
    if found is None:
        return []
    word = found[1]
    if word == "INFO":
        listing = " ".join(f"{group}({len(objects)})" for group, objects in sorted(GROUPS.items()))
        return [(FIRST_SEC, air(SERVER, message(us, f"de {SERVER}:{listing} Max 5@{RANGE_KM}km")))]
    objects = GROUPS.get(word, [])
    frames = [air(SERVER, object_report(name, now, *where(east, north), symbol, comment)) for name, symbol, comment, east, north in objects]
    frames.append(air(SERVER, message(us, f"Sent {len(objects)} {word} Objects Max 5@{RANGE_KM}km de {SERVER}")))
    return [(FIRST_SEC + STEP_SEC * n, frame) for n, frame in enumerate(frames)] if objects else []
