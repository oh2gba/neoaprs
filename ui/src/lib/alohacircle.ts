// The ALOHA circle of the map: the ring of points at the radius the daemon worked out (`aloha_km` of the topic `map`) round our own position, as the line the layer draws (lib/alohalayers.ts).
import type { Home } from "@/lib/mapview";

const EARTH_RADIUS_KM = 6371.0088; // the daemon's sphere (neoaprs/geo.py)
const POINTS = 120;

export type LonLat = [number, number];

export interface AlohaCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; properties: { km: number }; geometry: { type: "LineString"; coordinates: LonLat[] } }[];
}

/** The point `km` from `from` on the great circle that leaves it at `bearing` radians (north is 0). */
function destination(from: Home, km: number, bearing: number): LonLat {
  const lat = (from.lat * Math.PI) / 180;
  const lon = (from.lon * Math.PI) / 180;
  const angle = km / EARTH_RADIUS_KM;
  const toLat = Math.asin(Math.sin(lat) * Math.cos(angle) + Math.cos(lat) * Math.sin(angle) * Math.cos(bearing));
  const toLon = lon + Math.atan2(Math.sin(bearing) * Math.sin(angle) * Math.cos(lat), Math.cos(angle) - Math.sin(lat) * Math.sin(toLat));
  return [(toLon * 180) / Math.PI, (toLat * 180) / Math.PI];
}

/** The closed ring of points `km` round `center`, the longitudes running on past the date line instead of wrapping, so that the ring stays one line. */
export function ringAround(center: Home, km: number): LonLat[] {
  const ring = Array.from({ length: POINTS + 1 }, (_, i) => destination(center, km, (2 * Math.PI * i) / POINTS));
  let shift = 0;
  return ring.map(([lon, lat], i): LonLat => {
    const before = ring[i - 1];
    if (before !== undefined && Math.abs(lon - before[0]) > 180) shift += lon < before[0] ? 360 : -360; // (a jump of the longitude across the date line)
    return [lon + shift, lat];
  });
}

/** The closed ring of the circle, or no feature at all without a position or a radius. */
export function alohaFeatures(home: Home | null, km: number | null): AlohaCollection {
  if (home === null || km === null || !(km > 0)) return { type: "FeatureCollection", features: [] };
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: { km }, geometry: { type: "LineString", coordinates: ringAround(home, km) } }],
  };
}
