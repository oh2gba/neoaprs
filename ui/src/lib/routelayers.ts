// The layers of the route of the selected station (lib/routeline.ts): a pale casing under the line so that it shows on any ground, the latest route solid, the best one dashed and fainter, a dot on
// each digipeater with its call beside it. The colours are the page's own (style.css), read when the layers are made, which is again whenever the style is set (the colour scheme changed).
import type { ExpressionSpecification, Map as MapLibreMap } from "maplibre-gl";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import type { RouteCollection } from "@/lib/routeline";

export const ROUTE_SOURCE = "route";

const LINES: ExpressionSpecification = ["==", ["geometry-type"], "LineString"];
const DOTS: ExpressionSpecification = ["==", ["geometry-type"], "Point"];
const BEST: ExpressionSpecification = ["==", ["get", "best"], 1];
const LATEST: ExpressionSpecification = ["==", ["get", "best"], 0];

/** A colour of the page's palette (`--accent`), else the one given where the style sheet is not there. */
function paletteColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function addRouteLayers(map: MapLibreMap, data: RouteCollection): void {
  if (map.getSource(ROUTE_SOURCE)) return;
  const accent = paletteColor("--accent", "#1565c0");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  const text = paletteColor("--map-label", "#1d2125");
  map.addSource(ROUTE_SOURCE, { type: "geojson", data });
  const line = { "line-cap": "round", "line-join": "round" } as const;
  map.addLayer({ id: "route-casing", type: "line", source: ROUTE_SOURCE, filter: LINES, layout: line, paint: { "line-color": halo, "line-width": 6 } });
  map.addLayer({
    id: "route-latest",
    type: "line",
    source: ROUTE_SOURCE,
    filter: ["all", LINES, LATEST],
    layout: line,
    paint: { "line-color": accent, "line-width": 3 },
  });
  map.addLayer({
    id: "route-best",
    type: "line",
    source: ROUTE_SOURCE,
    filter: ["all", LINES, BEST],
    layout: { "line-join": "round" },
    paint: { "line-color": accent, "line-width": 3, "line-opacity": 0.6, "line-dasharray": [2, 2] },
  });
  map.addLayer({
    id: "route-hops",
    type: "circle",
    source: ROUTE_SOURCE,
    filter: DOTS,
    paint: { "circle-radius": 5, "circle-color": accent, "circle-stroke-color": halo, "circle-stroke-width": 2 },
  });
  map.addLayer({
    id: "route-names",
    type: "symbol",
    source: ROUTE_SOURCE,
    filter: DOTS,
    layout: { "text-field": ["get", "call"], "text-font": [FONT_REGULAR], "text-size": 11, "text-offset": [0, 0.9], "text-anchor": "top" },
    paint: { "text-color": text, "text-halo-color": halo, "text-halo-width": 1.5 },
  });
}
