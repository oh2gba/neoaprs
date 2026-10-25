// The layers of the range circle of the selected digipeater (lib/rangecircles.ts): a pale fill and a thin line in the page's accent colour, under the tracks, the route and the markers. The colour is read when the layers are made, which is again whenever the style is set (the colour scheme changed).
import type { Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import type { RangeCollection } from "@/lib/rangecircles";

export const RANGE_SOURCE = "digipeater-ranges";

export function addRangeLayers(map: MapLibreMap, data: RangeCollection): void {
  if (map.getSource(RANGE_SOURCE)) return;
  const colour = paletteColor("--accent", "#1565c0");
  map.addSource(RANGE_SOURCE, { type: "geojson", data });
  map.addLayer({ id: "digipeater-ranges-fill", type: "fill", source: RANGE_SOURCE, paint: { "fill-color": colour, "fill-opacity": 0.07 } });
  map.addLayer({
    id: "digipeater-ranges-line",
    type: "line",
    source: RANGE_SOURCE,
    layout: { "line-join": "round" },
    paint: { "line-color": colour, "line-width": 1.5, "line-opacity": 0.7 },
  });
}
