// The aircraft and ships the map draws, from the daemon's `layer_things` tables: which things are
// young enough (older than the layer's age, LIMITS.layers, are dropped as the daemon drops them),
// how faded each is (lib/aging.ts steps over the layer's age), its mark (aircraft shape by kind,
// lib/layers/aircraftkinds.ts, turned to its heading; a hull for a ship; a diamond for a thing
// without direction, except a balloon; emergencies in the bad colour; lib/layers/trafficlayers.ts
// makes the images), its name, and how many each layer has drawn (a dash while the source is away).
import { MARKER_STEPS, fadeFraction } from "@/lib/aging";
import { aircraftShape } from "@/lib/layers/aircraftkinds";
import { AIRCRAFT_SHAPES, type AircraftShape } from "@/lib/layers/aircraftshapes";
import { MARK_SIZE } from "@/lib/layers/marks";
import { ageSeconds } from "@/lib/format";
import { clockShift, shiftedTime } from "@/lib/pageclock";
import { glidePosition, nextGlide, type Glide, type Report } from "@/lib/layers/glide";
import { isOwn, type LayerName, type SourceName } from "@/lib/layers/sources";
import { LIMITS } from "@/protocol/lists";
import type { LayerThing, LayerThingsMessage } from "@/protocol/protocol";

/** The tables the page holds, by layer. */
export type LayerTables = ReadonlyMap<LayerName, LayerThingsMessage>;

/** The age in seconds at which a thing of that layer and source is dropped. */
export function maxAgeSec(layer: LayerName, source: SourceName): number {
  if (layer === "ships") return LIMITS.layers.shipsAgeSec;
  return isOwn(source) ? LIMITS.layers.aircraftReceiverAgeSec : LIMITS.layers.aircraftServiceAgeSec;
}

/** The things of a table that are young enough to draw. */
export function liveThings(table: LayerThingsMessage, nowMs: number): LayerThing[] {
  const max = maxAgeSec(table.layer, table.source);
  return table.things.filter((thing) => ageSeconds(thing.at, nowMs) < max);
}

/** The opacities of the four steps of a station's marker (styles/map.css, `.stn--fade-*`). */
export const FADE_OPACITY: readonly number[] = [1, 0.8, 0.6, 0.4];

/** The opacity of a thing of this age, for things dropped at `maxSec`. */
export function fadeOpacity(ageSec: number, maxSec: number): number {
  const step = Math.min(MARKER_STEPS - 1, Math.floor(fadeFraction(ageSec, maxSec / 60) * MARKER_STEPS));
  return FADE_OPACITY[step] ?? FADE_OPACITY[FADE_OPACITY.length - 1] ?? 1;
}

/** The shapes the map draws things with (lib/layers/marks.ts). */
export type ThingShape = AircraftShape | "hull" | "diamond";

/** Every shape the map draws things with. */
export const THING_SHAPES: readonly ThingShape[] = [
  ...(Object.keys(AIRCRAFT_SHAPES) as AircraftShape[]),
  "hull",
  "diamond",
];

/** The side of a shape's image in pixels: an aircraft's own size, else a mark's. */
export const sideOf = (shape: ThingShape): number =>
  shape === "hull" || shape === "diamond" ? MARK_SIZE : AIRCRAFT_SHAPES[shape].size;

/** Whether a shape is turned to where the thing heads. */
const turns = (shape: ThingShape): boolean => shape === "hull" || (shape !== "diamond" && AIRCRAFT_SHAPES[shape].turns);

/** The thing's kind as a shape pointing north: an aircraft's kind or a ship's hull. */
export const kindShape = (layer: LayerName, thing: LayerThing): AircraftShape | "hull" =>
  layer === "aircraft" ? aircraftShape(thing.category, thing.designator) : "hull";

/** The shape on the map: the kind, or a diamond if it turns but has no heading. */
export function thingShape(layer: LayerName, thing: LayerThing): ThingShape {
  const kind = kindShape(layer, thing);
  return thing.heading_deg === null && turns(kind) ? "diamond" : kind;
}

/** The shapes each layer draws with: an aircraft's kinds or a ship's hull, and the diamond. */
export const LAYER_SHAPES: Readonly<Record<LayerName, readonly ThingShape[]>> = {
  aircraft: [...(Object.keys(AIRCRAFT_SHAPES) as AircraftShape[]), "diamond"],
  ships: ["hull", "diamond"],
};

/** The map image name of a layer's shape, in the layer's colour or the bad colour for an emergency. */
export const imageName = (layer: LayerName, shape: ThingShape, emergency: boolean): string =>
  `traffic-${layer}-${shape}${emergency ? "-bad" : ""}`;

/** The key of a thing: its layer and id. */
export const thingKey = (layer: LayerName, id: string): string => `${layer}:${id}`;

interface ThingProperties {
  key: string;
  layer: LayerName;
  id: string;
  icon: string;
  /** the mark's side in pixels, which sets how far below it the name stands */
  side: number;
  rotate: number;
  opacity: number;
  name: string;
  /** drawn over the others: an emergency 1, else 0 */
  rank: number;
}

interface ThingFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: ThingProperties;
}

export interface TrafficCollection {
  type: "FeatureCollection";
  features: ThingFeature[];
}

export const NO_TRAFFIC: TrafficCollection = { type: "FeatureCollection", features: [] };

/** What the map draws: every young-enough thing with mark, turn, fade and name. */
export function trafficFeatures(tables: Iterable<LayerThingsMessage>, nowMs: number): TrafficCollection {
  const features: ThingFeature[] = [];
  for (const table of tables) {
    const max = maxAgeSec(table.layer, table.source);
    for (const thing of liveThings(table, nowMs)) {
      const shape = thingShape(table.layer, thing);
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [thing.lon, thing.lat] },
        properties: {
          key: thingKey(table.layer, thing.id),
          layer: table.layer,
          id: thing.id,
          icon: imageName(table.layer, shape, thing.emergency),
          side: sideOf(shape),
          rotate: turns(shape) ? (thing.heading_deg ?? 0) : 0,
          opacity: fadeOpacity(ageSeconds(thing.at, nowMs), max),
          name: thing.name,
          rank: thing.emergency ? 1 : 0,
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/** How many things each layer with a table draws now; null (a dash) while its source is away. */
export function trafficCounts(tables: LayerTables, nowMs: number): Partial<Record<LayerName, number | null>> {
  const counts: Partial<Record<LayerName, number | null>> = {};
  for (const [layer, table] of tables) counts[layer] = table.away ? null : liveThings(table, nowMs).length;
  return counts;
}

/** How long a thing glides on after its report: a few of its layer's report intervals. */
export const GLIDE_STOP_SEC: Readonly<Record<LayerName, number>> = { aircraft: 20, ships: 120 };

/**
 * The table with its times on the page's clock (lib/pageclock.ts); one whose `at` is no time is
 * left as it is.
 */
export function inPageClock(table: LayerThingsMessage, nowMs: number): LayerThingsMessage {
  const shift = clockShift(table.at, nowMs);
  if (shift === null || shift === 0) return table;
  return {
    ...table,
    at: shiftedTime(table.at, shift),
    things: table.things.map((thing) => ({ ...thing, at: shiftedTime(thing.at, shift) })),
    trails: table.trails.map((trail) => ({
      ...trail,
      points: trail.points.map(([lon, lat, at]): [number, number, string] => [lon, lat, shiftedTime(at, shift)]),
    })),
  };
}

/**
 * A thing's report as it glides, `receivedMs` being when its table came on the motion's clock: an
 * aircraft goes its track, a ship its course over ground. Its age is the table's `at` less its
 * own, at most the stop; one with no time, or a time well after the table's, does not move.
 */
export function reportOf(layer: LayerName, thing: LayerThing, table: LayerThingsMessage, receivedMs: number): Report {
  const stopSec = GLIDE_STOP_SEC[layer];
  const ageSec = (Date.parse(table.at) - Date.parse(thing.at)) / 1000;
  const sane = Number.isFinite(ageSec) && ageSec > -stopSec;
  return {
    lon: thing.lon,
    lat: thing.lat,
    atMs: receivedMs - (sane ? Math.min(stopSec, Math.max(0, ageSec)) : 0) * 1000,
    courseDeg: sane ? thing.course_deg : null,
    speedKmh: thing.speed_kmh,
  };
}

/**
 * The glides by thing key after a table came, at `nowMs` on the motion's clock; `receivedOf` tells
 * when each table came. A thing no longer in the tables is forgotten.
 */
export function nextGlides(
  was: ReadonlyMap<string, Glide>,
  tables: Iterable<LayerThingsMessage>,
  nowMs: number,
  receivedOf: (table: LayerThingsMessage) => number = () => nowMs,
): Map<string, Glide> {
  const next = new Map<string, Glide>();
  for (const table of tables) {
    const received = receivedOf(table);
    for (const thing of table.things) {
      const key = thingKey(table.layer, thing.id);
      const report = reportOf(table.layer, thing, table, received);
      next.set(key, nextGlide(was.get(key), report, nowMs, GLIDE_STOP_SEC[table.layer]));
    }
  }
  return next;
}

/** The things where they are drawn at `nowMs`: each moved along its glide. */
export function glidedFeatures(
  drawn: TrafficCollection,
  glides: ReadonlyMap<string, Glide>,
  nowMs: number,
): TrafficCollection {
  return {
    type: "FeatureCollection",
    features: drawn.features.map((feature) => {
      const glide = glides.get(feature.properties.key);
      if (!glide) return feature;
      const at = glidePosition(glide, nowMs, GLIDE_STOP_SEC[feature.properties.layer]);
      return { ...feature, geometry: { type: "Point", coordinates: at } };
    }),
  };
}

const sameProperties = (a: ThingProperties, b: ThingProperties): boolean =>
  a === b ||
  (a.key === b.key &&
    a.icon === b.icon &&
    a.side === b.side &&
    a.rotate === b.rotate &&
    a.opacity === b.opacity &&
    a.name === b.name &&
    a.rank === b.rank);

/** Whether two drawings have the same things with the same marks in the same places. */
export function samePlaces(a: TrafficCollection, b: TrafficCollection): boolean {
  if (a.features.length !== b.features.length) return false;
  return a.features.every((one, i) => {
    const other = b.features[i];
    return (
      sameProperties(one.properties, other.properties) &&
      one.geometry.coordinates[0] === other.geometry.coordinates[0] &&
      one.geometry.coordinates[1] === other.geometry.coordinates[1]
    );
  });
}
