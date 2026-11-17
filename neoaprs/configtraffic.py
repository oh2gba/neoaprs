"""The settings of the map's ships and aircraft (services/ais.py, services/adsb.py): their switches, which ships are shown, how far round us and how long a track each draws: their rows for the SETTINGS of
config.py (attribute, key, the parse of the text), whose fields (the defaults) are in `Config` in the same order. None of these can make anything be sent: the feeds only read and draw."""
from collections.abc import Callable
from typing import Any

from .ais import CATEGORIES
from .coded import CodedError
from .configtypes import boolean, int_among, int_in

TRAFFIC_RADIUS_KM = (50, 450)                      # ais/radius_km and adsb/radius_km: how far round our position the ships and the aircraft are read, in whole km (450 km: the farthest adsb.fi answers for, 250 NM, rounded down)
TRACK_MINUTES = (0, 15, 30, 60, 180, 720)          # ais/track_min and adsb/track_min: how long a track each draws (0: none); the feeds keep at most the last 12 hours
ALL_SHIP_TYPES = ",".join(CATEGORIES)               # ais/types: every colour group of ships (ais.CATEGORIES), the default


def ship_types(text: str) -> str:
    """ais/types: the colour groups of the ships drawn, separated by commas, in the order of ais.CATEGORIES and each once; empty draws none."""
    named = {part.strip().lower() for part in text.split(",") if part.strip()}
    if unknown := sorted(named - set(CATEGORIES)):
        raise CodedError(f"{unknown[0]!r} is not one of {', '.join(CATEGORIES)}", "setting.not_among", value=unknown[0], choices=", ".join(CATEGORIES))
    return ",".join(category for category in CATEGORIES if category in named)


TRAFFIC_ROWS: tuple[tuple[str, str, Callable[[str], Any]], ...] = (
    ("ais_enabled", "ais/enabled", boolean),                       # true: the ships round us (Digitraffic's AIS, over the internet) are drawn on the map; received only, never sent on the air or to APRS-IS
    ("ais_types", "ais/types", ship_types),                         # which ships, by their colour groups (cargo, tanker, passenger, highspeed, fishing, pleasure, special, other), separated by commas
    ("ais_hide_still", "ais/hide_still", boolean),                  # true: a ship moored, at anchor or still is not drawn
    ("ais_radius_km", "ais/radius_km", int_in(*TRAFFIC_RADIUS_KM)),     # how far round our position the ships are read
    ("ais_track_min", "ais/track_min", int_among(TRACK_MINUTES)),       # the minutes of a ship's track that the map draws; 0: none
    ("adsb_enabled", "adsb/enabled", boolean),                     # true: the aircraft round us (adsb.fi's ADS-B, over the internet) are drawn on the map; received only, never sent on the air or to APRS-IS
    ("adsb_radius_km", "adsb/radius_km", int_in(*TRAFFIC_RADIUS_KM)),   # how far round our position the aircraft are read
    ("adsb_track_min", "adsb/track_min", int_among(TRACK_MINUTES)),     # the minutes of an aircraft's track that the map draws; 0: none
)
