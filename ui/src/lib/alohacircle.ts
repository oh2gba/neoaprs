// The map's ALOHA circles: for each radio the daemon computed one for (`aloha` of the topic `map`:
// a radio that is on and shares a 1200 baud channel), the ring of points at its radius round our
// position, as the line the layer draws (lib/alohalayers.ts).
import { unwrapLine } from "@/lib/dateline";
import type { Home } from "@/lib/mapview";

// the daemon's sphere (neoaprs/geo.py)
const EARTH_RADIUS_KM = 6371.0088;
const POINTS = 120;

export type LonLat = [number, number];

export interface AlohaCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; properties: { km: number }; geometry: { type: "LineString"; coordinates: LonLat[] } }[];
}

/** The point `km` from `from` on the great circle leaving it at `bearing` radians (north is 0). */
function destination(from: Home, km: number, bearing: number): LonLat {
  const lat = (from.lat * Math.PI) / 180;
  const lon = (from.lon * Math.PI) / 180;
  const angle = km / EARTH_RADIUS_KM;
  const toLat = Math.asin(Math.sin(lat) * Math.cos(angle) + Math.cos(lat) * Math.sin(angle) * Math.cos(bearing));
  const toLon = lon + Math.atan2(Math.sin(bearing) * Math.sin(angle) * Math.cos(lat), Math.cos(angle) - Math.sin(lat) * Math.sin(toLat));
  return [(toLon * 180) / Math.PI, (toLat * 180) / Math.PI];
}

/**
 * The closed ring of points `km` round `center`; longitudes run on past the date line so it stays
 * one line.
 */
export function ringAround(center: Home, km: number): LonLat[] {
  const ring = Array.from({ length: POINTS + 1 }, (_, i) => destination(center, km, (2 * Math.PI * i) / POINTS));
  return unwrapLine(ring);
}

/**
 * The ring of each circle by radius in km; no features without a position; zero radii are left out.
 */
export function alohaFeatures(home: Home | null, radii: readonly number[]): AlohaCollection {
  if (home === null) return { type: "FeatureCollection", features: [] };
  return {
    type: "FeatureCollection",
    features: radii
      .filter((km) => km > 0)
      .map((km) => ({
        type: "Feature" as const,
        properties: { km },
        geometry: { type: "LineString" as const, coordinates: ringAround(home, km) },
      })),
  };
}
