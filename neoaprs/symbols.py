"""The APRS symbol tables: table and code to the symbol name, and the alternate-table overlays.

The table is "/" (primary), "\\" (alternate) or an overlay 0-9 or A-Z on the alternate table.
Compressed positions write the overlays 0-9 as a-j; `table_of` turns those back.
"""

# the 94 names of the codes "!" to "~", in order (APRS Protocol Reference 1.0.1 and 1.2)
_PRIMARY = (
    "Police|reserved|Digipeater|Phone|DX cluster|HF gateway|Small aircraft|Mobile satellite station|Wheelchair|Snowmobile|Red Cross|Boy Scouts|House|X|Red dot|"
    + "Circle|" * 10
    + "Fire|Campground|Motorcycle|Railroad engine|Car|File server|Hurricane|Aid station|BBS|Canoe|reserved|Eyeball|Farm vehicle|Grid square|Hotel|TCP/IP|reserved|School|PC user"
    "|Mac|NTS station|Balloon|Police car|reserved|Recreational vehicle|Space shuttle|SSTV|Bus|ATV|National weather service site|Helicopter|Yacht|Windows|Jogger|Triangle (DF)"
    "|PBBS|Large aircraft|Weather station|Satellite dish|Ambulance|Bicycle|Incident command post|Fire department|Horse|Fire truck|Glider|Hospital|IOTA|Jeep|Truck|Laptop"
    "|Mic-E repeater|Node|Emergency operations center|Rover|Grid square|Antenna|Power boat|Truck stop|Truck (18 wheeler)|Van|Water station|X-APRS|Yagi at QTH|Shelter"
    "|reserved|TNC stream switch|reserved|TNC stream switch"
).split("|")
_ALTERNATE = (
    "Emergency|reserved|Digipeater|Bank or ATM|Power plant|Gateway|Crash site|Cloudy|Firenet MEO|Snow|Church|Girl Scouts|House (HF)|Ambiguous|Waypoint destination"
    "|Circle (IRLP, Echolink, WIRES)|"
    + "reserved|"
    * 7
    + "Network node|Gas station|Hail|Park or picnic area|Advisory (gale flag)|APRStt (DTMF)|Car|Information kiosk|Hurricane|Numbered box|Blowing snow|Coast Guard|Drizzle"
    "|Smoke|Freezing rain|Snow shower|Haze|Rain shower|Lightning|Kenwood|Lighthouse|MARS|Navigation buoy|Rocket|Parking|Earthquake|Restaurant|Satellite|Thunderstorm|Sunny"
    "|VORTAC|NWS site|Pharmacy|Radios and devices|reserved|Wall cloud|GPS|reserved|Large aircraft|Weather station (green)|Rain|ARRL, ARES, WinLink, D-Star|Blowing dust or sand"
    "|Civil Defense|DX spot|Sleet|Funnel cloud|Gale flags|Ham store|Point of interest|Work zone|Special vehicle|Area|Value sign|Triangle|Small circle|Partly cloudy|reserved"
    "|Restrooms|Ship or boat|Tornado|Truck|Van|Flood|Wreck or obstruction|Skywarn|Shelter|Fog|TNC stream switch|reserved|TNC stream switch"
).split("|")

_OVERLAYS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

SYMBOL_NAMES = {"primary": tuple(_PRIMARY), "alternate": tuple(_ALTERNATE)}


def table_of(table: str) -> str | None:
    """Return the canonical table character ("/", "\\", overlay 0-9 / A-Z; a-j become 0-9)."""
    if len(table) != 1:
        return None
    if table in "/\\" or table in _OVERLAYS:
        return table
    if "a" <= table <= "j":
        return chr(ord(table) - ord("a") + ord("0"))
    return None


# symbols of a station that moves, by name, per table; they decide the recommended path
# (route.recommended_path): mobile WIDE1-1,WIDE2-1, fixed WIDE2-2
MOBILE_NAMES = {
    "primary": (
        "Small aircraft",
        "Mobile satellite station",
        "Wheelchair",
        "Snowmobile",
        "Motorcycle",
        "Railroad engine",
        "Car",
        "Canoe",
        "Farm vehicle",
        "Balloon",
        "Police car",
        "Recreational vehicle",
        "Space shuttle",
        "Bus",
        "ATV",
        "Helicopter",
        "Yacht",
        "Jogger",
        "Large aircraft",
        "Ambulance",
        "Bicycle",
        "Horse",
        "Fire truck",
        "Glider",
        "Jeep",
        "Truck",
        "Rover",
        "Power boat",
        "Truck (18 wheeler)",
        "Van",
    ),
    "alternate": ("Car", "Large aircraft", "Special vehicle", "Ship or boat", "Truck", "Van"),
}
MOBILE_CODES = {
    table: "".join(chr(33 + i) for i, name in enumerate(SYMBOL_NAMES[table]) if name in names)
    for table, names in MOBILE_NAMES.items()
}

# overlays of the gateway symbol `&` that mark an iGate: generic, receive-only, one-hop and
# two-hop transmit, LoRa
IGATE_OVERLAYS = ("I", "R", "T", "2", "L")


def is_mobile(table: str, code: str) -> bool:
    t = table_of(table)
    return t is not None and len(code) == 1 and code in MOBILE_CODES["primary" if t == "/" else "alternate"]


def overlay(table: str) -> str | None:
    t = table_of(table)
    return t if t is not None and t in _OVERLAYS else None


def symbol_name(table: str, code: str) -> str:
    """Return the name of the symbol, "unknown" for an invalid table or code."""
    t = table_of(table)
    if t is None or len(code) != 1 or not 33 <= ord(code) <= 126:
        return "unknown"
    return (_PRIMARY if t == "/" else _ALTERNATE)[ord(code) - 33]


# icon a tracker gets from the SSID of its source call (APRS101 ch. 4): primary table code
_SSID_ICONS = {
    1: "a",
    2: "U",
    3: "f",
    4: "b",
    5: "Y",
    6: "X",
    7: "'",
    8: "s",
    9: ">",
    10: "<",
    11: "O",
    12: "j",
    13: "R",
    14: "k",
    15: "v",
}
_UNKNOWN = ("\\", ".")  # unknown / indeterminate position
# (first code, the x of GPSxyz, the y of that code)
_GPS_PRIMARY = (
    (33, "B", 66),
    (48, "P", 48),
    (58, "M", 82),
    (65, "P", 65),
    (91, "H", 83),
    (97, "L", 65),
    (123, "J", 49),
)
_GPS_ALTERNATE = (
    (33, "O", 66),
    (48, "A", 48),
    (58, "N", 82),
    (65, "A", 65),
    (91, "D", 83),
    (97, "S", 65),
    (123, "Q", 49),
)


def _gps_code(table: str, code: int) -> str:
    """Return the two characters xy of a destination GPSxyz naming a symbol (BB for "/!")."""
    first, x, y = [row for row in (_GPS_PRIMARY if table == "/" else _GPS_ALTERNATE) if row[0] <= code][-1]
    y_char = chr(y + code - first)
    return x + (y_char.upper() if "a" <= chr(code) <= "z" else y_char)


_GPS_SYMBOLS = {_gps_code(t, c): (t, chr(c)) for t in "/\\" for c in range(33, 127)}


def tracker_symbol(source: str, destination: str) -> tuple[str, str]:
    """Return the table and code of a tracker from its destination `GPSxyz`, `GPSCnn` or SSID."""
    dest = destination.split("-")[0].upper()
    # the specification's own example is GPSPR
    dest = dest.ljust(6, "V") if len(dest) == 5 else dest
    if dest[:3] in ("GPS", "SPC") and len(dest) == 6:
        if dest[3] in "CE" and dest[4:].isdigit() and 1 <= int(dest[4:]) <= 94:
            return ("/" if dest[3] == "C" else "\\"), chr(32 + int(dest[4:]))
        found = _GPS_SYMBOLS.get(dest[3:5])
        if found:
            table, code = found
            overlay_char = dest[5]
            return (overlay_char if table == "\\" and overlay_char.isalnum() and overlay_char != "V" else table), code
    ssid = source.partition("-")[2]
    if ssid.isdigit() and int(ssid) in _SSID_ICONS:
        return "/", _SSID_ICONS[int(ssid)]
    return _UNKNOWN
