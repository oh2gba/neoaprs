// The layers of the locator grid (lib/layers/grid.ts): thin lines in the map's label colour at a low strength (the subsquares' lines without names fainter still), and one name in each cell in the regular face, muted,
// with the halo of the map's text. The names never push a name of the base map away and are never pushed away themselves: one cell's name never meets another's. The colours are the page's own (styles/tokens.css),
// read when the layers are made, which is again whenever the style is set (the colour scheme changed).
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import type { GridCollection } from "@/lib/layers/grid";

export const GRID_SOURCE = "grid";
export const GRID_LAYERS: readonly string[] = ["grid-lines", "grid-names"];

export function addGridLayers(map: MapLibreMap, data: GridCollection): void {
  if (map.getSource(GRID_SOURCE)) return;
  const ink = paletteColor("--map-label", "#1d2125");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  map.addSource(GRID_SOURCE, { type: "geojson", data });
  map.addLayer({
    id: "grid-lines",
    type: "line",
    source: GRID_SOURCE,
    filter: ["==", ["geometry-type"], "LineString"],
    paint: { "line-color": ink, "line-width": 1, "line-opacity": ["case", ["==", ["get", "rank"], 0], 0.3, 0.14] },
  });
  map.addLayer({
    id: "grid-names",
    type: "symbol",
    source: GRID_SOURCE,
    filter: ["==", ["geometry-type"], "Point"],
    layout: {
      "text-field": ["get", "name"],
      "text-font": [FONT_REGULAR],
      "text-size": 12,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: { "text-color": ink, "text-opacity": 0.6, "text-halo-color": halo, "text-halo-width": 1.2 },
  });
}

/** What the grid's layers draw. */
export function setGridData(map: MapLibreMap, data: GridCollection): void {
  void map.getSource<GeoJSONSource>(GRID_SOURCE)?.setData(data);
}
