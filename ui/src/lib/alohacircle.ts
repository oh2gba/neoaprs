// The ALOHA circles of the map: for each radio the daemon worked one out for (`aloha` of the topic `map`: a radio that is on and shares a 1200 baud channel), the ring of points at its radius round our own position, as
// the line the layer draws (lib/alohalayers.ts), with the words its hover says.
import type { Home } from "@/lib/mapview";

const EARTH_RADIUS_KM = 6371.0088; // the daemon's sphere (neoaprs/geo.py)
const POINTS = 120;

export type LonLat = [number, number];

export interface AlohaCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; properties: { km: number; title: string }; geometry: { type: "LineString"; coordinates: LonLat[] } }[];
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

/** One circle to draw: its radius, and what its hover says. */
export interface AlohaRing {
  km: number;
  title: string;
}

/** The closed ring of each circle, or no feature at all without a position; a circle of no radius is left out. */
export function alohaFeatures(home: Home | null, circles: readonly AlohaRing[]): AlohaCollection {
  if (home === null) return { type: "FeatureCollection", features: [] };
  return {
    type: "FeatureCollection",
    features: circles
      .filter((one) => one.km > 0)
      .map(({ km, title }) => ({
        type: "Feature" as const,
        properties: { km, title },
        geometry: { type: "LineString" as const, coordinates: ringAround(home, km) },
      })),
  };
}
