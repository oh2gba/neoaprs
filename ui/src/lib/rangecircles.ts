// The selected digipeater's range circle on the map (lib/nearby.ts `rangeCircleOf`): the ring of
// points at its range as a polygon for the pale fill and outline (layers in lib/rangelayers.ts),
// and the box the map fits itself to.
import { ringAround, type LonLat } from "@/lib/alohacircle";

export interface RangeCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    properties: { call: string; km: number };
    geometry: { type: "Polygon"; coordinates: LonLat[][] };
  }[];
}

/** One polygon per circle (`km` round `lat`, `lon`); none for a circle with no radius. */
export function rangeFeatures(
  circles: readonly { call: string; lat: number; lon: number; km: number }[],
): RangeCollection {
  return {
    type: "FeatureCollection",
    features: circles
      .filter((circle) => circle.km > 0)
      .map((circle) => ({
        type: "Feature",
        properties: { call: circle.call, km: circle.km },
        geometry: { type: "Polygon", coordinates: [ringAround({ lat: circle.lat, lon: circle.lon }, circle.km)] },
      })),
  };
}

/** The south-west and north-east corners of the box round the circle's ring; null for no radius. */
export function circleBounds(circle: { lat: number; lon: number; km: number }): [LonLat, LonLat] | null {
  if (!(circle.km > 0)) return null;
  const ring = ringAround({ lat: circle.lat, lon: circle.lon }, circle.km);
  const lons = ring.map(([lon]) => lon);
  const lats = ring.map(([, lat]) => lat);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}
