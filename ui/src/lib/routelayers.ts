// The layers of the routes of the selected station (lib/routeline.ts): a pale casing under the line so that it shows on any ground, the latest route solid, the one before it grey, thinner and dashed, a dot on
// each digipeater with its call beside it, and the iGate that ends a route to the internet in the colour of the internet. The colours are the page's own (ui/src/styles/tokens.css), read when the layers are made, which is again whenever the style is set (the colour scheme changed).
import type { ExpressionSpecification, Map as MapLibreMap } from "maplibre-gl";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import type { RouteCollection } from "@/lib/routeline";

export const ROUTE_SOURCE = "route";

const LINES: ExpressionSpecification = ["==", ["geometry-type"], "LineString"];
const DOTS: ExpressionSpecification = ["==", ["geometry-type"], "Point"];
const PREVIOUS: ExpressionSpecification = ["==", ["get", "previous"], 1];
const LATEST: ExpressionSpecification = ["==", ["get", "previous"], 0];
const IGATE: ExpressionSpecification = ["==", ["get", "end"], 1];

/** A colour of the page's palette (`--accent`), else the one given where the style sheet is not there. */
function paletteColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function addRouteLayers(map: MapLibreMap, data: RouteCollection): void {
  if (map.getSource(ROUTE_SOURCE)) return;
  const accent = paletteColor("--accent", "#1565c0");
  const grey = paletteColor("--muted", "#5d6670");
  const internet = paletteColor("--info", "#00697f");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const text = paletteColor("--map-label", "#1d2125");
  map.addSource(ROUTE_SOURCE, { type: "geojson", data });
  const line = { "line-cap": "round", "line-join": "round" } as const;
  map.addLayer({
    id: "route-casing",
    type: "line",
    source: ROUTE_SOURCE,
    filter: LINES,
    layout: line,
    paint: { "line-color": halo, "line-width": ["case", PREVIOUS, 4, 6] },
  });
  map.addLayer({
    id: "route-previous",
    type: "line",
    source: ROUTE_SOURCE,
    filter: ["all", LINES, PREVIOUS],
    layout: { "line-join": "round" },
    paint: { "line-color": grey, "line-width": 2, "line-dasharray": [2, 2] },
  });
  map.addLayer({
    id: "route-latest",
    type: "line",
    source: ROUTE_SOURCE,
    filter: ["all", LINES, LATEST],
    layout: line,
    paint: { "line-color": accent, "line-width": 3 },
  });
  map.addLayer({
    id: "route-hops",
    type: "circle",
    source: ROUTE_SOURCE,
    filter: DOTS,
    paint: {
      "circle-radius": ["case", IGATE, 6, 5],
      "circle-color": ["case", PREVIOUS, grey, IGATE, internet, accent],
      "circle-stroke-color": halo,
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "route-names",
    type: "symbol",
    source: ROUTE_SOURCE,
    filter: DOTS,
    layout: { "text-field": ["get", "label"], "text-font": [FONT_REGULAR], "text-size": 11, "text-offset": [0, 0.9], "text-anchor": "top" },
    paint: { "text-color": text, "text-halo-color": halo, "text-halo-width": 1.5 },
  });
}
