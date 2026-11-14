// The layers of the ships and the aircraft (lib/traffic.ts): an icon for each, drawn here on a canvas once for every kind and colour and turned on the map the way the bow or the track points (a still ship whose heading is
// not known is round), its full name beside it from zoom LABELS_FROM_ZOOM, and a ring round the one whose card is open. A ship is a hull in the colour of its group (cargo green, tanker red, passenger blue, the fast craft
// yellow, fishing orange, the pleasure craft violet, the tugs, pilots, rescue and the like teal, the rest grey: the colours of the maps of the sea); an aircraft is a silhouette of its kind, an emergency in the colour of an
// alert. The colours are the map tokens of styles/tokens.css, read when the layers are made, which is again whenever the style is set (the literals are what is used where a page has no style sheet).
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import type { TrafficCollection } from "@/lib/traffic";

const SHIPS_SOURCE = "traffic-ships";
const AIRCRAFT_SOURCE = "traffic-aircraft";
export const SHIPS_LAYER = "traffic-ships";
export const AIRCRAFT_LAYER = "traffic-aircraft";
const LABELS_FROM_ZOOM = 8;
const PX = 64; // the canvas of an icon; it is drawn at half that (pixelRatio 2)
const EMPTY = { type: "FeatureCollection", features: [] } as const;

const SHIP_COLOURS: Record<string, [string, string]> = {
  cargo: ["--map-ship-cargo", "#2e9d3a"],
  tanker: ["--map-ship-tanker", "#d32f2f"],
  passenger: ["--map-ship-passenger", "#1e5fd9"],
  highspeed: ["--map-ship-highspeed", "#e0b000"],
  fishing: ["--map-ship-fishing", "#ec7a1c"],
  pleasure: ["--map-ship-pleasure", "#a347c9"],
  special: ["--map-ship-special", "#0b9aa8"],
  other: ["--map-ship-other", "#7d8790"],
};

type Draw = (c: CanvasRenderingContext2D) => void;
const polygon =
  (points: readonly number[], scale = 1): Draw =>
  (c) => {
    c.beginPath();
    for (let i = 0; i < points.length; i += 2) {
      const x = PX / 2 + ((points[i] ?? 0) - PX / 2) * scale;
      const y = PX / 2 + ((points[i + 1] ?? 0) - PX / 2) * scale;
      if (i === 0) c.moveTo(x, y);
      else c.lineTo(x, y);
    }
    c.closePath();
  };
const circle =
  (x: number, y: number, r: number): Draw =>
  (c) => {
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
  };

const HULL = [32, 6, 42, 20, 42, 56, 22, 56, 22, 20];
const JET = [32, 4, 35, 10, 35, 24, 58, 37, 58, 41, 35, 35, 35, 50, 43, 56, 43, 59, 32, 56, 21, 59, 21, 56, 29, 50, 29, 35, 6, 41, 6, 37, 29, 24, 29, 10];
const PROP = [32, 8, 35, 12, 35, 24, 58, 26, 58, 31, 35, 32, 34, 48, 42, 52, 42, 55, 32, 54, 22, 55, 22, 52, 30, 48, 29, 32, 6, 31, 6, 26, 29, 24, 29, 12];
const GLIDER = [32, 14, 34, 18, 34, 26, 62, 28, 62, 31, 34, 31, 33, 50, 40, 53, 40, 55, 32, 54, 24, 55, 24, 53, 31, 50, 30, 31, 2, 31, 2, 28, 30, 26, 30, 18];
const ROTOR = [29, 20, 35, 20, 38, 30, 34, 38, 33, 56, 38, 58, 38, 60, 26, 60, 26, 58, 31, 56, 30, 38, 26, 30];
const BALLOON: Draw = (c) => {
  circle(32, 26, 16)(c);
  c.rect(28, 46, 8, 8);
};
const DRONE: Draw = (c) => {
  c.beginPath();
  for (const [x, y] of [
    [16, 16],
    [48, 16],
    [16, 48],
    [48, 48],
  ] as const) {
    c.moveTo(x + 7, y);
    c.arc(x, y, 7, 0, Math.PI * 2);
  }
  c.rect(26, 26, 12, 12);
};

const HELICOPTER: Draw = (c) => {
  polygon(ROTOR)(c);
  c.rect(6, 27, 52, 3);
  c.rect(30.5, 6, 3, 44);
};

const AIRCRAFT_SHAPES: Record<string, Draw> = {
  light: polygon(PROP, 0.8),
  small: polygon(PROP),
  jet: polygon(JET, 0.9),
  heavy: polygon(JET, 1.05),
  rotor: HELICOPTER,
  glider: polygon(GLIDER),
  balloon: BALLOON,
  drone: DRONE,
  other: polygon(JET, 0.8),
};

/** One icon on a canvas of its own, filled and outlined; null where the browser draws no canvas (a test's). */
function paint(shape: Draw, fill: string, ink: string): ImageData | null {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = PX;
  const c = canvas.getContext("2d");
  if (!c) return null;
  shape(c);
  c.fillStyle = fill;
  c.strokeStyle = ink;
  c.lineWidth = 3;
  c.lineJoin = "round";
  c.fill();
  c.stroke();
  return c.getImageData(0, 0, PX, PX);
}

/** Every icon the layers ask for, by its name (lib/traffic.ts shipIcon and aircraftIcon). */
function icons(): [string, Draw, string][] {
  const out: [string, Draw, string][] = [];
  for (const [category, [token, fallback]] of Object.entries(SHIP_COLOURS)) {
    const colour = paletteColor(token, fallback);
    out.push([`ship-${category}`, polygon(HULL), colour], [`ship-${category}-still`, circle(32, 32, 11), colour]);
  }
  const plane = paletteColor("--map-aircraft", "#3949ab");
  const alert = paletteColor("--map-aircraft-alert", "#d50000");
  for (const [kind, shape] of Object.entries(AIRCRAFT_SHAPES)) out.push([`aircraft-${kind}`, shape, plane], [`aircraft-${kind}-alert`, shape, alert]);
  return out;
}

function addIcons(map: MapLibreMap): void {
  const images = map as Partial<Pick<MapLibreMap, "addImage" | "hasImage" | "removeImage">>;
  if (!images.addImage || !images.hasImage) return; // (the test's stand-in for the map draws nothing)
  const ink = paletteColor("--map-label", "#1d2125");
  for (const [name, shape, fill] of icons()) {
    const image = paint(shape, fill, ink);
    if (image === null) return;
    if (images.hasImage.call(map, name)) images.removeImage?.call(map, name); // (the colour scheme changed: the icons are drawn again in its colours)
    images.addImage.call(map, name, image, { pixelRatio: 2 });
  }
}

const SIZE: ExpressionSpecification = ["interpolate", ["linear"], ["zoom"], 4, 0.55, 9, 0.8, 13, 1];
const LABEL: ExpressionSpecification = ["step", ["zoom"], "", LABELS_FROM_ZOOM, ["get", "label"]];
const PICKED: ExpressionSpecification = ["==", ["get", "picked"], 1];

function addLayer(map: MapLibreMap, source: string, id: string, labelColour: string, halo: string, ring: string): void {
  map.addSource(source, { type: "geojson", data: EMPTY });
  map.addLayer({
    id: `${id}-picked`,
    type: "circle",
    source,
    filter: PICKED,
    paint: { "circle-radius": 15, "circle-color": "rgba(0, 0, 0, 0)", "circle-stroke-color": ring, "circle-stroke-width": 3 },
  });
  map.addLayer({
    id,
    type: "symbol",
    source,
    layout: {
      "icon-image": ["get", "icon"],
      "icon-rotate": ["get", "rotate"],
      "icon-rotation-alignment": "map",
      "icon-size": SIZE,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "text-field": LABEL,
      "text-font": [FONT_REGULAR],
      "text-size": 11,
      "text-offset": [0, 1.3],
      "text-anchor": "top",
      "text-optional": true,
    },
    paint: { "text-color": labelColour, "text-halo-color": halo, "text-halo-width": 1.5 },
  });
}

/** The sources, the icons and the layers, ships under aircraft; again after every change of the style, which takes them away. */
export function addTrafficLayers(map: MapLibreMap): void {
  addIcons(map);
  if (map.getSource(SHIPS_SOURCE)) return;
  const label = paletteColor("--map-label", "#1d2125");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const ring = paletteColor("--map-select", "#ff6d00");
  addLayer(map, SHIPS_SOURCE, SHIPS_LAYER, label, halo, ring);
  addLayer(map, AIRCRAFT_SOURCE, AIRCRAFT_LAYER, label, halo, ring);
}

/** What the layers draw now. */
export function setTrafficData(map: MapLibreMap, ships: TrafficCollection, aircraft: TrafficCollection): void {
  void map.getSource<GeoJSONSource>(SHIPS_SOURCE)?.setData(ships);
  void map.getSource<GeoJSONSource>(AIRCRAFT_SOURCE)?.setData(aircraft);
}
