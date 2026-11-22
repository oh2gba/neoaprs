// The base map: the two files the daemon serves (the world map to zoom 4 or 5, and
// data/basemap.pmtiles, the detailed OpenStreetMap extract round the station) and the MapLibre
// style that draws them in a light and a dark scheme. Layer names and kinds are those of the
// Protomaps basemap tiles (docs.protomaps.com/basemaps/layers); a layer a tile lacks draws nothing.
// The world layers are drawn first and the detailed map on top, so the world shows where the
// detailed map has no tile. With no file at all the style is a blank background.
import { locale } from "@/i18n";
import type {
  ExpressionSpecification,
  LayerSpecification,
  StyleSpecification,
  VectorSourceSpecification,
} from "maplibre-gl";

/** The files the daemon serves, relative to the page. */
export const BASEMAP_FILE = "basemap.pmtiles";
export const WORLD_FILE = "basemap-world.pmtiles";
export const MAX_ZOOM = 18;
/** The map opens at this zoom, centred on our own station. */
export const OPEN_ZOOM = 9;
/**
 * The ODbL requires this credit on every map made from OpenStreetMap data; the wording is the same
 * in every language.
 */
export const ATTRIBUTION = "© OpenStreetMap contributors, Protomaps";

export const FONT_REGULAR = "NotoSans-Regular";
export const FONT_MEDIUM = "NotoSans-Medium";

interface Palette {
  sea: string;
  land: string;
  forest: string;
  grass: string;
  park: string;
  residential: string;
  industrial: string;
  wetland: string;
  sand: string;
  building: string;
  buildingLine: string;
  highway: string;
  highwayCasing: string;
  major: string;
  majorCasing: string;
  minor: string;
  minorCasing: string;
  path: string;
  rail: string;
  border: string;
  region: string;
  text: string;
  halo: string;
}

export const LIGHT: Palette = {
  sea: "#a9cde3",
  land: "#f1eee6",
  forest: "#cfe3c0",
  grass: "#e3ebd4",
  park: "#d5e8c6",
  residential: "#e9e3d7",
  industrial: "#ddd9e2",
  wetland: "#d9e7de",
  sand: "#efe6c8",
  building: "#dcd3c3",
  buildingLine: "#c4b9a6",
  highway: "#f7b267",
  highwayCasing: "#c27a2c",
  major: "#fde7a0",
  majorCasing: "#c8b160",
  minor: "#ffffff",
  minorCasing: "#c9c4b8",
  path: "#a08c6a",
  rail: "#8b8b8b",
  border: "#8c7f70",
  region: "#b8ad9f",
  text: "#2b2b2b",
  halo: "#ffffff",
};

export const DARK: Palette = {
  sea: "#14202a",
  land: "#22262a",
  forest: "#243127",
  grass: "#283025",
  park: "#2b3a2c",
  residential: "#2a2d31",
  industrial: "#2d2c33",
  wetland: "#25332f",
  sand: "#3a3a30",
  building: "#353a40",
  buildingLine: "#464c53",
  highway: "#b36d2e",
  highwayCasing: "#5c3a18",
  major: "#8a7b45",
  majorCasing: "#433c22",
  minor: "#4a4f55",
  minorCasing: "#1b1e21",
  path: "#6b655a",
  rail: "#666a70",
  border: "#9a9a9a",
  region: "#5d6166",
  text: "#d8d8d8",
  halo: "#1b1e21",
};

/** The ids of the two sources of the style (the engine names them in its events). */
export const BASE_SOURCE = "base";
export const WORLD_SOURCE = "world";
const SOURCE = BASE_SOURCE;
const WORLD_PREFIX = "world-";

function kindIn(kinds: string[]): ExpressionSpecification {
  return ["in", ["get", "kind"], ["literal", kinds]];
}

/** A number that grows exponentially with the zoom: `[zoom, value, zoom, value, ...]`. */
function byZoom(stops: number[], base = 1.5): ExpressionSpecification {
  return ["interpolate", ["exponential", base], ["zoom"], ...stops];
}

/** The name of a place in the page language if the tiles carry one, else the local name. */
function names(): ExpressionSpecification {
  const language = locale.value.split("-")[0] ?? "en";
  return ["coalesce", ["get", `name:${language}`], ["get", "name"]];
}

function fill(
  id: string,
  layer: string,
  filter: ExpressionSpecification | null,
  color: string,
  extra: Partial<LayerSpecification> = {},
): LayerSpecification {
  return {
    id,
    type: "fill",
    source: SOURCE,
    "source-layer": layer,
    ...(filter ? { filter } : {}),
    paint: { "fill-color": color },
    ...extra,
  } as LayerSpecification;
}

function landLayers(p: Palette): LayerSpecification[] {
  return [
    fill("earth", "earth", null, p.land),
    fill("landcover-forest", "landcover", ["==", ["get", "kind"], "forest"], p.forest, { maxzoom: 8 }),
    fill(
      "landuse-grass",
      "landuse",
      kindIn([
        "grassland",
        "meadow",
        "grass",
        "farmland",
        "allotments",
        "recreation_ground",
        "golf_course",
        "garden",
        "scrub",
      ]),
      p.grass,
    ),
    fill("landuse-wetland", "landuse", kindIn(["wetland"]), p.wetland),
    fill("landuse-sand", "landuse", kindIn(["sand", "beach", "bare_rock"]), p.sand),
    fill(
      "landuse-residential",
      "landuse",
      kindIn(["residential", "commercial", "retail", "hospital", "school", "university", "college", "kindergarten"]),
      p.residential,
    ),
    fill(
      "landuse-industrial",
      "landuse",
      kindIn(["industrial", "railway", "military", "quarry", "aerodrome", "airfield"]),
      p.industrial,
    ),
    fill("landuse-forest", "landuse", kindIn(["forest", "wood"]), p.forest),
    fill(
      "landuse-park",
      "landuse",
      kindIn(["park", "nature_reserve", "dog_park", "playground", "pitch", "zoo", "cemetery"]),
      p.park,
    ),
  ];
}

function waterLayers(p: Palette): LayerSpecification[] {
  return [
    fill("water", "water", ["==", ["geometry-type"], "Polygon"], p.sea),
    {
      id: "waterway",
      type: "line",
      source: SOURCE,
      "source-layer": "water",
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": p.sea, "line-width": byZoom([6, 0.4, 14, 3, 18, 12]) },
    },
  ];
}

interface RoadClass {
  id: string;
  kinds: string[];
  minzoom: number;
  /** the width of the road at zoom 8, 14 and 18 */
  widths: [number, number, number];
  color: (p: Palette) => string;
  casing: (p: Palette) => string;
}

// Bottom to top: a path under a minor road under a major road under a highway.
const ROAD_CLASSES: RoadClass[] = [
  {
    id: "minor",
    kinds: ["minor_road", "medium_road", "other"],
    minzoom: 12,
    widths: [0.3, 3, 12],
    color: (p) => p.minor,
    casing: (p) => p.minorCasing,
  },
  {
    id: "major",
    kinds: ["major_road"],
    minzoom: 7,
    widths: [0.7, 5, 18],
    color: (p) => p.major,
    casing: (p) => p.majorCasing,
  },
  {
    id: "highway",
    kinds: ["highway"],
    minzoom: 4,
    widths: [1.3, 7, 22],
    color: (p) => p.highway,
    casing: (p) => p.highwayCasing,
  },
];

function roadLine(
  id: string,
  kinds: string[],
  minzoom: number,
  color: string,
  widths: [number, number, number],
  extra: object = {},
): LayerSpecification {
  return {
    id,
    type: "line",
    source: SOURCE,
    "source-layer": "roads",
    minzoom,
    filter: kindIn(kinds),
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": color, "line-width": byZoom([8, widths[0], 14, widths[1], 18, widths[2]]), ...extra },
  };
}

function roadLayers(p: Palette): LayerSpecification[] {
  const path = roadLine("road-path", ["path"], 13, p.path, [0.2, 1, 3], { "line-dasharray": [2, 1.5] });
  const casings = ROAD_CLASSES.map((c) =>
    roadLine(`road-${c.id}-casing`, c.kinds, c.minzoom, c.casing(p), [
      c.widths[0] + 0.6,
      c.widths[1] + 1.6,
      c.widths[2] + 3,
    ]),
  );
  const fills = ROAD_CLASSES.map((c) => roadLine(`road-${c.id}`, c.kinds, c.minzoom, c.color(p), c.widths));
  const rail = roadLine("road-rail", ["rail"], 10, p.rail, [0.3, 1, 2], { "line-dasharray": [4, 2] });
  return [rail, path, ...casings, ...fills];
}

function buildingLayer(p: Palette): LayerSpecification {
  return {
    id: "buildings",
    type: "fill",
    source: SOURCE,
    "source-layer": "buildings",
    minzoom: 14,
    filter: ["==", ["get", "kind"], "building"],
    paint: { "fill-color": p.building, "fill-outline-color": p.buildingLine },
  };
}

function boundaryLayers(p: Palette): LayerSpecification[] {
  const line = (id: string, kind: string, color: string, width: number, opacity: number): LayerSpecification => ({
    id,
    type: "line",
    source: SOURCE,
    "source-layer": "boundaries",
    filter: ["==", ["get", "kind"], kind],
    paint: { "line-color": color, "line-width": width, "line-opacity": opacity, "line-dasharray": [3, 2] },
  });
  return [line("boundary-region", "region", p.region, 0.6, 0.7), line("boundary-country", "country", p.border, 1, 0.8)];
}

function placeLabel(
  id: string,
  details: string[],
  p: Palette,
  minzoom: number,
  maxzoom: number,
  sizes: number[],
  font: string,
): LayerSpecification {
  return {
    id,
    type: "symbol",
    source: SOURCE,
    "source-layer": "places",
    minzoom,
    maxzoom,
    filter: ["in", ["get", "kind_detail"], ["literal", details]],
    layout: {
      "text-field": names(),
      "text-font": [font],
      "text-size": byZoom(sizes, 1.2),
      "text-max-width": 8,
      "text-padding": 4,
    },
    paint: { "text-color": p.text, "text-halo-color": p.halo, "text-halo-width": 1.4 },
  };
}

/** Country names from zoom 1: small capitals that give way to town names as the map zooms in. */
function countryLabel(p: Palette): LayerSpecification {
  return {
    id: "place-country",
    type: "symbol",
    source: SOURCE,
    "source-layer": "places",
    minzoom: 1,
    maxzoom: 7,
    filter: ["==", ["get", "kind"], "country"],
    layout: {
      "text-field": names(),
      "text-font": [FONT_MEDIUM],
      "text-size": byZoom([1, 9, 4, 12, 6, 15], 1.2),
      "text-max-width": 7,
      "text-transform": "uppercase",
      "text-letter-spacing": 0.08,
      "text-padding": 8,
    },
    paint: { "text-color": p.border, "text-halo-color": p.halo, "text-halo-width": 1.4 },
  };
}

function roadName(p: Palette): LayerSpecification {
  return {
    id: "road-names",
    type: "symbol",
    source: SOURCE,
    "source-layer": "roads",
    minzoom: 13,
    filter: ["all", kindIn(["highway", "major_road", "medium_road", "minor_road"]), ["has", "name"]],
    layout: {
      "symbol-placement": "line",
      "text-field": names(),
      "text-font": [FONT_REGULAR],
      "text-size": byZoom([13, 10, 18, 14], 1.2),
      "symbol-spacing": 280,
      "text-padding": 4,
    },
    paint: { "text-color": p.text, "text-halo-color": p.halo, "text-halo-width": 1.3 },
  };
}

function labelLayers(p: Palette): LayerSpecification[] {
  return [
    roadName(p),
    countryLabel(p),
    placeLabel("place-hamlet", ["hamlet", "suburb", "neighbourhood"], p, 11, 24, [11, 10, 16, 13], FONT_REGULAR),
    placeLabel("place-village", ["village"], p, 8, 24, [8, 10, 14, 14], FONT_REGULAR),
    placeLabel("place-town", ["town"], p, 6, 24, [6, 11, 12, 16], FONT_MEDIUM),
    placeLabel("place-city", ["city"], p, 3, 24, [3, 12, 10, 20], FONT_MEDIUM),
  ];
}

/** The absolute addresses of the two archives (named after `pmtiles://`); null if absent. */
export interface Archives {
  detail: string | null;
  world: string | null;
}

/** The detailed map's layers drawn from the world file instead, with their own ids. */
function fromWorld(layers: LayerSpecification[]): LayerSpecification[] {
  return layers.map((layer) => ({ ...layer, id: WORLD_PREFIX + layer.id, source: WORLD_SOURCE }) as LayerSpecification);
}

function vectorSource(archive: string): VectorSourceSpecification {
  // Zooms and bounds come from the file's header.
  return { type: "vector", url: `pmtiles://${archive}`, attribution: ATTRIBUTION };
}

/** The style over the archives; `glyphs` is a template with {fontstack} and {range}. */
export function basemapStyle(archives: Archives, dark: boolean, glyphs: string): StyleSpecification {
  const p = dark ? DARK : LIGHT;
  const drawn = archives.detail !== null || archives.world !== null;
  const background: LayerSpecification = {
    id: "background",
    type: "background",
    paint: { "background-color": drawn ? p.sea : p.land },
  };
  if (!drawn) return { version: 8, sources: {}, layers: [background] };
  const layers = [
    ...landLayers(p),
    ...waterLayers(p),
    ...boundaryLayers(p),
    ...roadLayers(p),
    buildingLayer(p),
    ...labelLayers(p),
  ];
  const sources: Record<string, VectorSourceSpecification> = {};
  const stacked: LayerSpecification[] = [background];
  if (archives.world !== null) {
    sources[WORLD_SOURCE] = vectorSource(archives.world);
    stacked.push(...fromWorld(layers));
  }
  if (archives.detail !== null) {
    sources[SOURCE] = vectorSource(archives.detail);
    stacked.push(...layers);
  }
  return { version: 8, glyphs, sources, layers: stacked };
}
