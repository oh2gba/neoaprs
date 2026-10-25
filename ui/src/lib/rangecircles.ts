// The range circles of the digipeaters on the map: for each one that gave a range (lib/nearby.ts, `rangeCircles`) the ring of points at that range round its position, as a polygon for the pale fill and its outline (the layers are in lib/rangelayers.ts).
import { ringAround, type LonLat } from "@/lib/alohacircle";

export interface RangeCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; properties: { call: string; km: number }; geometry: { type: "Polygon"; coordinates: LonLat[][] } }[];
}

/** One polygon for each circle (`km` round `lat`, `lon`); no feature for a circle with no radius. */
export function rangeFeatures(circles: readonly { call: string; lat: number; lon: number; km: number }[]): RangeCollection {
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
