// The layer of the tracks of the stations (lib/tracks.ts): a line that fades with age, heavier and orange for the selected station.
import type { Map as MapLibreMap } from "maplibre-gl";
import type { trackLines } from "@/lib/tracks";

const TRACK_COLOR = "#2f80ed";
const TRACK_SELECTED_COLOR = "#ff6d00";

export function addTrackLayers(map: MapLibreMap, data: ReturnType<typeof trackLines>): void {
  if (map.getSource("tracks")) return;
  map.addSource("tracks", { type: "geojson", data });
  map.addLayer({
    id: "tracks-line",
    type: "line",
    source: "tracks",
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: {
      "line-color": ["case", ["==", ["get", "selected"], 1], TRACK_SELECTED_COLOR, TRACK_COLOR],
      "line-width": ["case", ["==", ["get", "selected"], 1], 4, 2],
      "line-opacity": ["get", "opacity"],
    },
  });
}
