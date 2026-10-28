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

export interface TrackCollection {
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

/** A point of a trail as the lines are made of it: its place, [lon, lat], and the opacity of the stretch that begins at it (the age of the point against the time the trail fades over). */
type TrailPoint<P> = (point: P) => { at: [number, number]; opacity: number };

/** The lines of one trail, the points the oldest first: a run of stretches of one opacity each, the oldest first. The live tracks are made with it, and so are the trails of the map's replay (lib/replay.ts). */
export function fadingLines<P>(call: string, points: readonly P[], selected: boolean, of: TrailPoint<P>): TrackFeature[] {
  const features: TrackFeature[] = [];
  for (let i = 0; i + 1 < points.length; i++) {
    const [from, to] = [points[i], points[i + 1]];
    if (from === undefined || to === undefined) continue;
    const { at: start, opacity } = of(from);
    const end = of(to).at;
    const open = features.at(-1);
    if (open?.properties.opacity === opacity) {
      open.geometry.coordinates.push(end);
      continue;
    }
    features.push({
      type: "Feature",
      properties: { call, selected: selected ? 1 : 0, opacity },
      geometry: { type: "LineString", coordinates: [start, end] },
    });
  }
  return features;
}

/** The lines of one station's track. */
function stationLines(row: StationRow, selected: boolean, nowMs: number, aging: Aging): TrackFeature[] {
  const minutes = timeoutMin(aging, row);
  return fadingLines(row.call, row.track, selected, ([at, lat, lon]) => ({ at: [lon, lat], opacity: trailOpacity(ageSeconds(at, nowMs), minutes) }));
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
