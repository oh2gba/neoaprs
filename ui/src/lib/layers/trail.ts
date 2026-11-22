// The way an aircraft or ship has gone, as this page has seen it: the positions the layer tables
// bring (composables/useLayerThings.ts), a point added when a thing's place changed, none older
// than 30 minutes and at most 400 per thing. The daemon keeps nothing; a trail begins when the page
// began to look at the layer. The map draws the trail of the thing whose card is open
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
/** Two points further apart in time than this, in seconds, have no line between them. */
export const TRAIL_GAP_SEC = 5 * 60;

/** A place a thing was seen at: [lon, lat, time in ms]. */
export type TrailPoint = readonly [number, number, number];

/** The trails by the key of the thing (its layer and its id). */
export type Trails = Map<string, TrailPoint[]>;

/** The key of a thing's trail. */
export const trailKey = (layer: LayerName, id: string): string => `${layer}:${id}`;

/** Takes what the tables say into the trails: a point for every thing whose place changed, points
 * too old or beyond the last 400 dropped, and things no longer in their table (or whose layer has
 * none) forgotten. */
export function growTrails(trails: Trails, tables: Iterable<LayerThingsMessage>, nowMs: number): void {
  const present = new Set<string>();
  for (const table of tables) {
    for (const thing of table.things) {
      const key = trailKey(table.layer, thing.id);
      present.add(key);
      const at = Date.parse(thing.at);
      const points = trails.get(key) ?? [];
      const last = points.at(-1);
      if (!last || last[0] !== thing.lon || last[1] !== thing.lat) points.push([thing.lon, thing.lat, Number.isNaN(at) ? nowMs : at]);
      // Pruned in place from the old end, and only when something is too old or too many.
      let drop = 0;
      while (drop < points.length && (nowMs - points[drop][2]) / 1000 > TRAIL_MAX_AGE_SEC) drop++;
      drop = Math.max(drop, points.length - TRAIL_MAX_POINTS);
      if (drop > 0) points.splice(0, drop);
      if (points.length > 0) trails.set(key, points);
      else trails.delete(key);
    }
  }
  for (const key of [...trails.keys()]) if (!present.has(key)) trails.delete(key);
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
