// The layers of the map's replay (lib/replay.ts, composables/useMapReplay.ts): the trails of the stations up to the time of the replay, a line in the colour of the live tracks that fades behind each station, over the
// live layers; and the live tracks and the route of the selected station, which give way while the replay plays and come back as they were when it closes (their data goes on being set meanwhile). The colour is
// read when the layer is made, which is again whenever the style is set (the colour scheme changed).
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { ROUTE_LAYERS } from "@/lib/routelayers";
import { TRACK_LAYERS } from "@/lib/tracklayers";
import type { TrackCollection } from "@/lib/tracks";

const REPLAY_SOURCE = "replay-trails";
const NONE: TrackCollection = { type: "FeatureCollection", features: [] };

export function addReplayLayers(map: MapLibreMap): void {
  if (map.getSource(REPLAY_SOURCE)) return;
  map.addSource(REPLAY_SOURCE, { type: "geojson", data: NONE });
  map.addLayer({
    id: "replay-trails",
    type: "line",
    source: REPLAY_SOURCE,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": paletteColor("--map-track", "#2f80ed"), "line-width": 2.5, "line-opacity": ["get", "opacity"] },
  });
}

/** What the trails layer draws; none when the replay is closed. */
export function setReplayTrails(map: MapLibreMap, data: TrackCollection = NONE): void {
  void map.getSource<GeoJSONSource>(REPLAY_SOURCE)?.setData(data);
}

/** The live tracks and route in sight (`on`), or given way to the replay. */
export function showLive(map: MapLibreMap, on: boolean): void {
  for (const id of [...TRACK_LAYERS, ...ROUTE_LAYERS]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
}
