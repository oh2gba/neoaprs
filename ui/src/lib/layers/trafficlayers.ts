// The map's layer of aircraft and ships (lib/layers/traffic.ts): each thing a flat mark of 16 px in the layers' own colour (`--map-layer`; an emergency in `--bad`) with a thin halo so that it shows on any ground, turned to
// where it heads, faded by its age; from zoom 10 its name under it, in the regular face and the muted colour of the map's text, giving way to the base map's names and to each other. The marks are images the map is given, drawn from the shapes
// of the Layers box (lib/layers/marks.ts) and given again with the layers, which are made again whenever the style is set (the colour scheme changed: the colours are read from styles/tokens.css then).
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import { MARKS, MARK_SIZE } from "@/lib/layers/marks";
import { NO_TRAFFIC, imageName, type ThingShape, type TrafficCollection } from "@/lib/layers/traffic";

const TRAFFIC_SOURCE = "traffic";
export const TRAFFIC_LAYER = "traffic";
/** The things' names. */
const TRAFFIC_NAMES_LAYER = "traffic-names";
/** A thing's name shows from this zoom on. */
const NAMES_FROM_ZOOM = 10;
const RATIO = 2; // (the images are drawn at twice their size, sharp on a screen of high density)
const SHAPES: readonly ThingShape[] = ["dart", "hull", "diamond"];

/** A shape drawn in a colour with its halo, as the map takes an image; null where the browser draws nothing (no canvas). */
function drawShape(shape: ThingShape, fill: string, halo: string): ImageData | null {
  if (typeof Path2D === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = MARK_SIZE * RATIO;
  canvas.height = MARK_SIZE * RATIO;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.scale(RATIO, RATIO);
  const path = new Path2D(MARKS[shape].d);
  context.lineJoin = "round";
  context.lineWidth = 2;
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
  for (const shape of SHAPES) {
    for (const emergency of [false, true]) {
      const image = drawShape(shape, emergency ? colours.bad : colours.plain, halo);
      if (!image) return;
      const name = imageName(shape, emergency);
      if (map.hasImage(name)) map.updateImage(name, image);
      else map.addImage(name, image, { pixelRatio: RATIO });
    }
  }
}

/** The first of the base map's names (the names of the roads, the places), before which the things' names are drawn: none on a blank map. */
function firstBaseName(map: MapLibreMap): string | undefined {
  return map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
}

export function addTrafficLayers(map: MapLibreMap, data: TrafficCollection = NO_TRAFFIC): void {
  addTrafficImages(map);
  if (map.getSource(TRAFFIC_SOURCE)) return;
  const ink = paletteColor("--map-label", "#1d2125");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const before = firstBaseName(map); // (asked before the marks are added: the page's own layers come after the base map's)
  map.addSource(TRAFFIC_SOURCE, { type: "geojson", data });
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
        "text-size": 11,
        "text-anchor": "top",
        "text-offset": [0, 0.9],
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
