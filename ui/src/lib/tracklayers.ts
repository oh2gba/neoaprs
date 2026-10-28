// The layers of the tracks of the stations (lib/tracks.ts): a line that fades with age for every station that moved, and for the selected station (every open card) its trail drawn to be read: above the others, orange,
// heavier and solid whatever its age, on a pale casing so that it shows on any ground, with a dot at each position the station was heard at, which fades with the age of the position as the stretches of the other tracks do.
// `setTrackData` gives both sources what to draw; the colours are the map tokens of styles/tokens.css, read when the layers are made (the literals are what is used where a page has no style sheet).
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Aging } from "@/lib/aging";
import { paletteColor } from "@/lib/alohalayers";
import { trackLines, trackPoints } from "@/lib/tracks";
import type { StationRow } from "@/protocol/protocol";

const TRACKS_SOURCE = "tracks";
const TRACK_POINTS_SOURCE = "track-points";
const OTHERS: ExpressionSpecification = ["==", ["get", "selected"], 0];
const SELECTED: ExpressionSpecification = ["==", ["get", "selected"], 1];
const EMPTY = { type: "FeatureCollection", features: [] } as const;
/** The layers made here, which give way while the map's replay plays (lib/replaylayers.ts). */
export const TRACK_LAYERS: readonly string[] = ["tracks-line", "tracks-selected-casing", "tracks-selected", "tracks-points"];

export function addTrackLayers(map: MapLibreMap): void {
  if (map.getSource(TRACKS_SOURCE)) return;
  const trackColor = paletteColor("--map-track", "#2f80ed");
  const selectedColor = paletteColor("--map-select", "#ff6d00");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  map.addSource(TRACKS_SOURCE, { type: "geojson", data: EMPTY });
  map.addSource(TRACK_POINTS_SOURCE, { type: "geojson", data: EMPTY });
  const round = { "line-cap": "round", "line-join": "round" } as const;
  map.addLayer({
    id: "tracks-line",
    type: "line",
    source: TRACKS_SOURCE,
    filter: OTHERS,
    layout: { "line-cap": "butt", "line-join": "round" },
    paint: { "line-color": trackColor, "line-width": 2, "line-opacity": ["get", "opacity"] },
  });
  map.addLayer({
    id: "tracks-selected-casing",
    type: "line",
    source: TRACKS_SOURCE,
    filter: SELECTED,
    layout: round,
    paint: { "line-color": halo, "line-width": 8 },
  });
  map.addLayer({
    id: "tracks-selected",
    type: "line",
    source: TRACKS_SOURCE,
    filter: SELECTED,
    layout: round,
    paint: { "line-color": selectedColor, "line-width": 4 },
  });
  map.addLayer({
    id: "tracks-points",
    type: "circle",
    source: TRACK_POINTS_SOURCE,
    paint: {
      "circle-radius": 4,
      "circle-color": selectedColor,
      "circle-opacity": ["get", "opacity"],
      "circle-stroke-color": halo,
      "circle-stroke-width": 1.5,
      "circle-stroke-opacity": ["get", "opacity"],
    },
  });
}

/** What the layers draw: the lines of the stations' tracks, `selected` among them marked, and the points of the selected ones. */
export function setTrackData(map: MapLibreMap, rows: readonly StationRow[], selected: string | null | readonly string[], nowMs: number, aging: Aging): void {
  void map.getSource<GeoJSONSource>(TRACKS_SOURCE)?.setData(trackLines(rows, selected, nowMs, aging));
  void map.getSource<GeoJSONSource>(TRACK_POINTS_SOURCE)?.setData(trackPoints(rows, selected, nowMs, aging));
}
