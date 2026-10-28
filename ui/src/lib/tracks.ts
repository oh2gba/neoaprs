// The tracks of the stations as one GeoJSON collection of lines for the map. A track fades with age along its length: each stretch between two points has the opacity of its older point's age against
// the timeout of the station (lib/aging.ts), the newest stretch full and the oldest faint. Neighbouring stretches of the same opacity are one line, so that the joins are not drawn twice over each other;
// the line of a selected station (of every open card) is marked so that it is drawn heavier, solid and above the others, and its positions are given as points too (`trackPoints`): a dot where each packet was heard,
// which fades with the age of the position as the stretches do, so that the trail of the station picked is read at a glance, each beacon on it.
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

interface PointFeature {
  type: "Feature";
  properties: { call: string; opacity: number };
  geometry: { type: "Point"; coordinates: [number, number] };
}

export interface PointCollection {
  type: "FeatureCollection";
  features: PointFeature[];
}

const picked = (selected: string | null | readonly string[]): readonly string[] => (typeof selected === "string" ? [selected] : (selected ?? []));

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

/** `selected` is the call of the selected station, or the calls of all the stations whose cards are open. */
export function trackLines(rows: Iterable<StationRow>, selected: string | null | readonly string[], nowMs: number, aging: Aging): TrackCollection {
  const calls = picked(selected);
  const features: TrackFeature[] = [];
  for (const row of rows) features.push(...stationLines(row, calls.includes(row.call), nowMs, aging));
  return { type: "FeatureCollection", features };
}

/** The positions of the selected stations' tracks (those that have a line: more than one point), each with the opacity of its age, the oldest first. */
export function trackPoints(rows: Iterable<StationRow>, selected: string | null | readonly string[], nowMs: number, aging: Aging): PointCollection {
  const calls = picked(selected);
  const features: PointFeature[] = [];
  for (const row of rows) {
    if (!calls.includes(row.call) || row.track.length < 2) continue;
    const minutes = timeoutMin(aging, row);
    for (const [at, lat, lon] of row.track) {
      features.push({
        type: "Feature",
        properties: { call: row.call, opacity: trailOpacity(ageSeconds(at, nowMs), minutes) },
        geometry: { type: "Point", coordinates: [lon, lat] },
      });
    }
  }
  return { type: "FeatureCollection", features };
}
