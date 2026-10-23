// The tracks of the stations as one GeoJSON collection of lines for the map. A track fades with age along its length: each stretch between two points has the opacity of its older point's age against
// the timeout of the station (lib/aging.ts), the newest stretch full and the oldest faint. Neighbouring stretches of the same opacity are one line, so that the joins are not drawn twice over each other;
// the selected station's line is marked so that it is drawn heavier.
import { timeoutMin, trailOpacity, type Aging } from "@/lib/aging";
import { ageSeconds } from "@/lib/format";
import type { StationRow } from "@/protocol/protocol";

interface TrackFeature {
  type: "Feature";
  properties: { call: string; selected: number; opacity: number };
  geometry: { type: "LineString"; coordinates: [number, number][] };
}

interface TrackCollection {
  type: "FeatureCollection";
  features: TrackFeature[];
}

/** The lines of one station: a run of stretches of one opacity each, the oldest first. */
function stationLines(row: StationRow, selected: boolean, nowMs: number, aging: Aging): TrackFeature[] {
  const minutes = timeoutMin(aging, row);
  const features: TrackFeature[] = [];
  for (let i = 0; i + 1 < row.track.length; i++) {
    const [from, to] = [row.track[i], row.track[i + 1]];
    if (!from || !to) continue;
    const opacity = trailOpacity(ageSeconds(from[0], nowMs), minutes);
    const start: [number, number] = [from[2], from[1]];
    const open = features.at(-1);
    if (open?.properties.opacity === opacity) {
      open.geometry.coordinates.push([to[2], to[1]]);
      continue;
    }
    features.push({
      type: "Feature",
      properties: { call: row.call, selected: selected ? 1 : 0, opacity },
      geometry: { type: "LineString", coordinates: [start, [to[2], to[1]]] },
    });
  }
  return features;
}

export function trackLines(rows: Iterable<StationRow>, selected: string | null, nowMs: number, aging: Aging): TrackCollection {
  const features: TrackFeature[] = [];
  for (const row of rows) features.push(...stationLines(row, row.call === selected, nowMs, aging));
  return { type: "FeatureCollection", features };
}
