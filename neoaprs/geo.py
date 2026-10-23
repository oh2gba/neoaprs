"""Distance and bearing between two positions on the earth.

Positions are degrees, north and east positive. The earth is a sphere of the mean radius."""
import math

EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """The initial bearing from the first position to the second, 0 up to 360 (north is 0); 0 for two equal positions."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    bearing = math.degrees(math.atan2(y, x)) % 360.0
    return 0.0 if bearing >= 360.0 else bearing


KM_PER_DEGREE = 111.195                       # a degree of latitude on the sphere of EARTH_RADIUS_KM
MAX_MERCATOR_LAT = 85.0511                    # the map's tiles end here


def box_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """The box west, south, east, north (degrees) that holds the circle of `radius_km` round the position: a square on the ground, wider in degrees of longitude the nearer the pole. It stops at the
    edges of the world map (the date line, the latitude the tiles end at) and is not wrapped over them."""
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat))
    dlat = radius_km / KM_PER_DEGREE
    south, north = max(-MAX_MERCATOR_LAT, lat - dlat), min(MAX_MERCATOR_LAT, lat + dlat)
    widest = max(abs(south), abs(north))
    scale = math.cos(math.radians(widest))
    dlon = 180.0 if scale < 1e-6 else min(180.0, radius_km / (KM_PER_DEGREE * scale))
    return max(-180.0, lon - dlon), south, min(180.0, lon + dlon), north
