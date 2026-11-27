// The way an aircraft or ship has gone, as this page has seen it: the positions the layer tables
// bring (composables/useLayerThings.ts) and those the daemon kept for the first table of a look, a
// point added when a thing's place changed, none older than 30 minutes and at most 400 per thing.
// A trail outlives a table that is empty for a while (the tab hidden): only its age, or the layer
// switched off, forgets it. The map draws the trail of the thing whose card is open
// (`trailLines`): a thin line that fades toward its old end, broken where two points are more than
// a few minutes apart, so no line crosses the map for a stretch nobody saw.
import { trailOpacity } from "@/lib/aging";
import { fadingLines, type TrackCollection } from "@/lib/tracks";
import type { LayerName } from "@/lib/layers/sources";
import type { LayerThingsMessage } from "@/protocol/protocol";

/** How long a point is kept, in seconds. */
export const TRAIL_MAX_AGE_SEC = 30 * 60;
/** How many points a thing keeps. */
export const TRAIL_MAX_POINTS = 400;
/** How many things keep a trail; past this the ones seen longest ago go. */
export const TRAIL_MAX_THINGS = 2000;
/** Two points further apart in time than this, in seconds, have no line between them. */
export const TRAIL_GAP_SEC = 5 * 60;

/** A place a thing was seen at: [lon, lat, time in ms]. */
export type TrailPoint = readonly [number, number, number];

/** The trails by the key of the thing (its layer and its id). */
export type Trails = Map<string, TrailPoint[]>;

/** The key of a thing's trail. */
export const trailKey = (layer: LayerName, id: string): string => `${layer}:${id}`;

/** Adds a point where the thing's place changed, unless it is not newer than the last one. */
function add(points: TrailPoint[], lon: number, lat: number, at: number): void {
  const last = points.at(-1);
  if (last && (at < last[2] || (last[0] === lon && last[1] === lat))) return;
  points.push([lon, lat, at]);
}

/** Drops in place, from the old end, the points too old or beyond the last 400. */
function prune(points: TrailPoint[], nowMs: number): void {
  let drop = 0;
  while (drop < points.length && (nowMs - points[drop][2]) / 1000 > TRAIL_MAX_AGE_SEC) drop++;
  drop = Math.max(drop, points.length - TRAIL_MAX_POINTS);
  if (drop > 0) points.splice(0, drop);
}

/** Takes what the tables say into the trails: a point for every thing whose place changed, first
 * the points the daemon kept (the first table of a look); every trail is pruned by age, and one
 * left with no point is forgotten. A thing not in its table keeps its trail. */
export function growTrails(trails: Trails, tables: Iterable<LayerThingsMessage>, nowMs: number): void {
  for (const table of tables) {
    for (const kept of table.trails) {
      const key = trailKey(table.layer, kept.id);
      const points = trails.get(key) ?? [];
      for (const [lon, lat, at] of kept.points) add(points, lon, lat, Date.parse(at));
      trails.set(key, points);
    }
    for (const thing of table.things) {
      const key = trailKey(table.layer, thing.id);
      const at = Date.parse(thing.at);
      const points = trails.get(key) ?? [];
      add(points, thing.lon, thing.lat, Number.isNaN(at) ? nowMs : at);
      trails.set(key, points);
    }
  }
  for (const [key, points] of trails) {
    prune(points, nowMs);
    if (points.length === 0) trails.delete(key);
  }
  if (trails.size > TRAIL_MAX_THINGS) {
    const newest = [...trails].sort((a, b) => (b[1].at(-1)?.[2] ?? 0) - (a[1].at(-1)?.[2] ?? 0));
    for (const [key] of newest.slice(TRAIL_MAX_THINGS)) trails.delete(key);
  }
}

/** Forgets every trail of a layer (switched off by the operator). */
export function forgetTrails(trails: Trails, layer: LayerName): void {
  for (const key of [...trails.keys()]) if (key.startsWith(`${layer}:`)) trails.delete(key);
}

/** The lines of a trail for the map, oldest first: runs of stretches of one opacity (the age of a
 * stretch's older point against the 30 minutes), none across a gap. */
export function trailLines(key: string, points: readonly TrailPoint[], nowMs: number): TrackCollection {
  const runs: TrailPoint[][] = [];
  for (const point of points) {
    const run = runs.at(-1);
    const last = run?.at(-1);
    if (run && last && (point[2] - last[2]) / 1000 <= TRAIL_GAP_SEC) run.push(point);
    else runs.push([point]);
  }
  const features = runs.flatMap((run) =>
    fadingLines(key, run, false, (point) => ({
      at: [point[0], point[1]],
      opacity: trailOpacity((nowMs - point[2]) / 1000, TRAIL_MAX_AGE_SEC / 60),
    })),
  );
  return { type: "FeatureCollection", features };
}

/** Nothing to draw. */
export const NO_TRAIL: TrackCollection = { type: "FeatureCollection", features: [] };
