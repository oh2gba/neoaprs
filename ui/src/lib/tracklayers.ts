// The layer of the tracks of the stations (lib/tracks.ts): a line that fades with age, heavier and orange for the selected station.
import type { Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import type { trackLines } from "@/lib/tracks";

export function addTrackLayers(map: MapLibreMap, data: ReturnType<typeof trackLines>): void {
  if (map.getSource("tracks")) return;
  // the colours of the tracks are the map tokens of styles/tokens.css, read when the layer is made (the literals are what is used where a page has no style sheet)
  const trackColor = paletteColor("--map-track", "#2f80ed");
  const selectedColor = paletteColor("--map-select", "#ff6d00");
  map.addSource("tracks", { type: "geojson", data });
  map.addLayer({
    id: "tracks-line",
    type: "line",
    source: "tracks",
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: {
      "line-color": ["case", ["==", ["get", "selected"], 1], selectedColor, trackColor],
      "line-width": ["case", ["==", ["get", "selected"], 1], 4, 2],
      "line-opacity": ["get", "opacity"],
    },
  });
}
