// The map's layer of aircraft and ships (lib/layers/traffic.ts): each thing a flat mark in the layers' own colour (`--map-layer`; an emergency in `--bad`) with a thin halo so that it shows on any ground, an aircraft
// the shape of its kind at its own size (lib/layers/aircraftshapes.ts, 17 to 30 px), a ship's hull and the diamond 16 px, turned to where it heads, faded by its age; from zoom 10 its name under it, as far under as its mark is large, in the regular face
// and the muted colour of the map's text, giving way to the base map's names and to each other. The marks are images the map is given, one for each shape and colour, drawn from the shapes of the Layers box
// (lib/layers/marks.ts) at the density of the screen the page opened on (twice at least, three times at most) and given again with the layers, which are made again whenever the style is set (the
// colour scheme changed: the colours are read from styles/tokens.css then).
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import { MARKS, markBox } from "@/lib/layers/marks";
import { NO_TRAIL } from "@/lib/layers/trail";
import type { TrackCollection } from "@/lib/tracks";
import { NO_TRAFFIC, THING_SHAPES, imageName, sideOf, type ThingShape, type TrafficCollection } from "@/lib/layers/traffic";

const TRAFFIC_SOURCE = "traffic";
const TRAIL_SOURCE = "traffic-trail";
const TRAIL_LAYER = "traffic-trail";
export const TRAFFIC_LAYER = "traffic";
/** The things' names. */
const TRAFFIC_NAMES_LAYER = "traffic-names";
/** A thing's name shows from this zoom on. */
const NAMES_FROM_ZOOM = 10;
/** The halo's width in pixels, half of it outside the shape. */
const HALO = 2;

/** How many image pixels a pixel of the page has: the screen's density, twice at least and three times at most, read when the marks are made. */
const pixelRatio = (): number => Math.min(3, Math.max(2, Math.ceil(globalThis.devicePixelRatio || 1)));

/** The name's size in pixels, and the room between the foot of a mark and the top of its name. */
const NAME_SIZE = 11;
const NAME_GAP = 1.9;

/** How far under its place a name stands, for each size of mark a thing has: the mark's half and the gap, in the name's ems (0.9 under a mark of 16). */
const NAME_OFFSET: ExpressionSpecification = [
  "match",
  ["get", "side"],
  ...[...new Set(THING_SHAPES.map(sideOf))].flatMap((side) => [side, ["literal", [0, Math.round(((side / 2 + NAME_GAP) / NAME_SIZE) * 100) / 100]]]),
  ["literal", [0, 0.9]],
] as unknown as ExpressionSpecification;

/** A shape drawn in a colour with its halo, its box fitted to the middle of a square of its side, as the map takes an image; null where the browser draws nothing (no canvas). */
function drawShape(shape: ThingShape, fill: string, halo: string, ratio: number): ImageData | null {
  if (typeof Path2D === "undefined") return null;
  const canvas = document.createElement("canvas");
  const side = sideOf(shape);
  canvas.width = Math.round(side * ratio);
  canvas.height = canvas.width;
  const context = canvas.getContext("2d");
  if (!context) return null;
  const [x, y, width, height] = markBox(MARKS[shape]).split(" ").map(Number) as [number, number, number, number];
  const scale = side / Math.max(width, height);
  context.scale(ratio * scale, ratio * scale);
  context.translate((Math.max(width, height) - width) / 2 - x, (Math.max(width, height) - height) / 2 - y);
  const path = new Path2D(MARKS[shape].d);
  context.lineJoin = "round";
  context.lineWidth = HALO / scale;
  context.strokeStyle = halo;
  context.stroke(path); // (the outer half stays round the fill: the halo)
  context.fillStyle = fill;
  context.fill(path);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

/** Gives the map the marks in the colours of the scheme that is on (an image it has already is drawn anew). */
function addTrafficImages(map: MapLibreMap): void {
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const colours = { plain: paletteColor("--map-layer", "#8e24aa"), bad: paletteColor("--bad", "#b9401d") };
  const ratio = pixelRatio();
  for (const shape of THING_SHAPES) {
    for (const emergency of [false, true]) {
      const image = drawShape(shape, emergency ? colours.bad : colours.plain, halo, ratio);
      if (!image) return;
      const name = imageName(shape, emergency);
      if (map.hasImage(name)) map.removeImage(name); // (an image keeps the ratio it was added with)
      map.addImage(name, image, { pixelRatio: ratio });
    }
  }
}

/** The first of the base map's names (the names of the roads, the places), before which the things' names are drawn: none on a blank map. */
function firstBaseName(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
}

export function addTrafficLayers(map: MapLibreMap, data: TrafficCollection = NO_TRAFFIC, trail: TrackCollection = NO_TRAIL): void {
  addTrafficImages(map);
  if (map.getSource(TRAFFIC_SOURCE)) return;
  const ink = paletteColor("--map-label", "#1d2125");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const before = firstBaseName(map); // (asked before the marks are added: the page's own layers come after the base map's)
  map.addSource(TRAFFIC_SOURCE, { type: "geojson", data });
  // the way the thing whose card is open has gone: under the marks (and over the grid and the circles, which were made first)
  map.addSource(TRAIL_SOURCE, { type: "geojson", data: trail });
  map.addLayer({
    id: TRAIL_LAYER,
    type: "line",
    source: TRAIL_SOURCE,
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: { "line-color": paletteColor("--map-layer", "#8e24aa"), "line-width": 2, "line-opacity": ["get", "opacity"] },
  });
  map.addLayer({
    id: TRAFFIC_LAYER,
    type: "symbol",
    source: TRAFFIC_SOURCE,
    layout: {
      "icon-image": ["get", "icon"],
      "icon-rotate": ["get", "rotate"],
      "icon-rotation-alignment": "map",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "symbol-sort-key": ["get", "rank"],
    },
    paint: { "icon-opacity": ["get", "opacity"] },
  });
  // The names: a layer of their own under the base map's names, so that the map places those first and a thing's name gives way to them and to the other things' names.
  map.addLayer(
    {
      id: TRAFFIC_NAMES_LAYER,
      type: "symbol",
      source: TRAFFIC_SOURCE,
      minzoom: NAMES_FROM_ZOOM,
      layout: {
        "text-field": ["get", "name"],
        "text-font": [FONT_REGULAR],
        "text-size": NAME_SIZE,
        "text-anchor": "top",
        "text-offset": NAME_OFFSET,
        "symbol-sort-key": ["-", ["get", "rank"]],
      },
      paint: {
        "text-color": ink,
        "text-opacity": ["*", 0.7, ["get", "opacity"]],
        "text-halo-color": halo,
        "text-halo-width": 1.2,
      },
    },
    before,
  );
}

/** What the layer draws. */
export function setTrafficData(map: MapLibreMap, data: TrafficCollection): void {
  void map.getSource<GeoJSONSource>(TRAFFIC_SOURCE)?.setData(data);
}

/** What the trail layer draws: the lines of the open card's thing, or nothing. */
export function setTrailData(map: MapLibreMap, data: TrackCollection): void {
  void map.getSource<GeoJSONSource>(TRAIL_SOURCE)?.setData(data);
}
