// Made-up traffic layer things for the tests, round Espoo (60.2231 N 24.7152 E): every field
// present.
import type { LayerThing, LayerThingsMessage, MapLayer } from "@/protocol/protocol";
import { AIRCRAFT_SOURCES, SHIP_SOURCES } from "@/protocol/lists";

const AT = "2026-10-21T12:00:00Z";

export function mapLayer(layer: MapLayer["layer"], extra: Partial<MapLayer> = {}): MapLayer {
  return {
    layer,
    source: "none",
    offered: [...(layer === "aircraft" ? AIRCRAFT_SOURCES : SHIP_SOURCES)],
    receiver: null,
    problem: "",
    ...extra,
  };
}

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
    vertical_ms: null,
    registration: "OH-LZA",
    type: "AIRBUS A-321",
    category: "A3",
    designator: "A321",
    ship_type: null,
    course_deg: null,
    destination: "",
    origin: "",
    origin_place: "",
    destination_place: "",
    ...extra,
  };
}

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
    vertical_ms: null,
    registration: "",
    type: "",
    category: "",
    designator: "",
    ship_type: 60,
    course_deg: 182,
    destination: "TALLINN",
    origin: "",
    origin_place: "",
    destination_place: "",
    ...extra,
  };
}

export function layerThings(
  layer: MapLayer["layer"],
  things: LayerThing[],
  extra: Partial<LayerThingsMessage> = {},
): LayerThingsMessage {
  return { type: "layer_things", at: AT, layer, source: "receiver", away: false, things, trails: [], ...extra };
}
