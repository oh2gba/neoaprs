// The aircraft and ships as the map draws them, from the tables the daemon sends (`layer_things`): what is still young enough to be drawn (a thing older than its layer's age, LIMITS.layers, is dropped between two tables
// as the daemon drops it when it tells one), how faded each is (the four steps of a station's marker, lib/aging.ts, over its layer's age), its mark (an aircraft the shape of its kind, lib/layers/aircraftkinds.ts,
// turned to where it heads; a hull for a ship; a small diamond for a thing that gives no direction, save a balloon, which has none of its own; an emergency in the page's bad colour: lib/layers/trafficlayers.ts
// makes the images) and its name, and how many each layer has drawn now (a dash while its source is away).
import { MARKER_STEPS, fadeFraction } from "@/lib/aging";
import { aircraftShape } from "@/lib/layers/aircraftkinds";
import { AIRCRAFT_SHAPES, type AircraftShape } from "@/lib/layers/aircraftshapes";
import { ageSeconds } from "@/lib/format";
import { isOwn, type LayerName, type SourceName } from "@/lib/layers/sources";
import { LIMITS } from "@/protocol/lists";
import type { LayerThing, LayerThingsMessage } from "@/protocol/protocol";

/** The tables the page holds, by layer. */
export type LayerTables = ReadonlyMap<LayerName, LayerThingsMessage>;

/** How old a thing of that layer and source may be, in seconds, before it is dropped. */
export function maxAgeSec(layer: LayerName, source: SourceName): number {
  if (layer === "ships") return LIMITS.layers.shipsAgeSec;
  return isOwn(source) ? LIMITS.layers.aircraftReceiverAgeSec : LIMITS.layers.aircraftServiceAgeSec;
}

/** The things of a table that are young enough to be drawn now. */
export function liveThings(table: LayerThingsMessage, nowMs: number): LayerThing[] {
  const max = maxAgeSec(table.layer, table.source);
  return table.things.filter((thing) => ageSeconds(thing.at, nowMs) < max);
}

/** The opacities of the four steps, as a station's marker has them (styles/map.css, `.stn--fade-*`). */
export const FADE_OPACITY: readonly number[] = [1, 0.8, 0.6, 0.4];

/** How opaque a thing of that age is, for things that are dropped at `maxSec`. */
export function fadeOpacity(ageSec: number, maxSec: number): number {
  const step = Math.min(MARKER_STEPS - 1, Math.floor(fadeFraction(ageSec, maxSec / 60) * MARKER_STEPS));
  return FADE_OPACITY[step] ?? FADE_OPACITY[FADE_OPACITY.length - 1] ?? 1;
}

/** The shapes the map draws things with (lib/layers/marks.ts). */
export type ThingShape = AircraftShape | "hull" | "diamond";

/** Every shape the map draws things with. */
export const THING_SHAPES: readonly ThingShape[] = [...(Object.keys(AIRCRAFT_SHAPES) as AircraftShape[]), "hull", "diamond"];

/** Whether a shape is turned to where the thing heads. */
export const turns = (shape: ThingShape): boolean => shape === "hull" || (shape !== "diamond" && AIRCRAFT_SHAPES[shape].turns);

/** What kind of thing it is, as a shape pointing north: an aircraft's kind, a ship's hull (the hover box and the card's head show it). */
export const kindShape = (layer: LayerName, thing: LayerThing): AircraftShape | "hull" =>
  layer === "aircraft" ? aircraftShape(thing.category, thing.designator) : "hull";

/** The shape of a thing on the map: its kind, a diamond where it gives no direction and its kind has one. */
export function thingShape(layer: LayerName, thing: LayerThing): ThingShape {
  const kind = kindShape(layer, thing);
  return thing.heading_deg === null && turns(kind) ? "diamond" : kind;
}

/** The name of the map's image of a shape, in the layers' colour or in the bad colour of an emergency. */
export const imageName = (shape: ThingShape, emergency: boolean): string => `traffic-${shape}${emergency ? "-bad" : ""}`;

/** The key of a thing on the map and in the page: its layer and its id. */
const thingKey = (layer: LayerName, id: string): string => `${layer}:${id}`;

interface ThingProperties {
  key: string;
  layer: LayerName;
  id: string;
  icon: string;
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

/** What the map draws for the tables: every thing young enough, with its mark, its turn, how faded it is and its name. */
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
          icon: imageName(shape, thing.emergency),
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

/** How many things each layer that has a table draws now; null (a dash) while its source is away. A layer without a table has none. */
export function trafficCounts(tables: LayerTables, nowMs: number): Partial<Record<LayerName, number | null>> {
  const counts: Partial<Record<LayerName, number | null>> = {};
  for (const [layer, table] of tables) counts[layer] = table.away ? null : liveThings(table, nowMs).length;
  return counts;
}
