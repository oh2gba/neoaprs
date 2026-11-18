// Made-up things of the map's layers of traffic for the tests, round the demo's Espoo (60.2231 N 24.7152 E): every field present, the ones a test cares about given.
import type { LayerThing, LayerThingsMessage, MapLayer } from "@/protocol/protocol";
import { AIRCRAFT_SOURCES, SHIP_SOURCES } from "@/protocol/lists";

const AT = "2026-10-21T12:00:00Z";

/** One layer of the topic `map`: no source chosen, and every source offered (Fintraffic reaches Espoo). */
export function mapLayer(layer: MapLayer["layer"], extra: Partial<MapLayer> = {}): MapLayer {
  return { layer, source: "none", offered: [...(layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES)], receiver: null, ...extra };
}

/** An aircraft north-east of Espoo, flying south-west. */
export function aircraft(extra: Partial<LayerThing> = {}): LayerThing {
  return {
    id: "461f2a",
    lat: 60.3172,
    lon: 24.9633,
    at: AT,
    heading_deg: 225,
    speed_kmh: 420.5,
    name: "FIN7AB",
    emergency: false,
    altitude_m: 2438,
    registration: "OH-LZA",
    type: "AIRBUS A-321",
    category: "A3",
    designator: "A321",
    ship_type: null,
    course_deg: null,
    destination: "",
    ...extra,
  };
}

/** A ship off Helsinki, under way to the south. */
export function ship(extra: Partial<LayerThing> = {}): LayerThing {
  return {
    id: "230123456",
    lat: 60.1512,
    lon: 24.9601,
    at: AT,
    heading_deg: 182,
    speed_kmh: 22.2,
    name: "MADE UP STAR",
    emergency: false,
    altitude_m: null,
    registration: "",
    type: "",
    category: "",
    designator: "",
    ship_type: 60,
    course_deg: 182,
    destination: "TALLINN",
    ...extra,
  };
}

/** The message `layer_things` with a layer's whole table, from the own receiver unless the test says another source. */
export function layerThings(layer: MapLayer["layer"], things: LayerThing[], extra: Partial<LayerThingsMessage> = {}): LayerThingsMessage {
  return { type: "layer_things", layer, source: "receiver", away: false, things, ...extra };
}
