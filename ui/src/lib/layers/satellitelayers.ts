// The map's layers of the satellites (lib/layers/satellite.ts), in their own colour
// (`--map-satellite`): the footprint of each open card as a faint wash with a thin edge, its track
// ahead as a dashed line, and over them every satellite's mark with its name beside it. The mark is
// an image given to the map like the aircraft's (lib/layers/trafficlayers.ts) and given again with
// the layers when the style is set; the colours are read then.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { paletteColor } from "@/lib/alohalayers";
import { FONT_REGULAR } from "@/lib/basemapstyle";
import { MARK_SIZE } from "@/lib/layers/marks";
import { NO_SATELLITES, type SatelliteFeatures } from "@/lib/layers/satellite";
import { drawMark, pixelRatio } from "@/lib/layers/trafficlayers";

export const SATELLITE_LAYER = "satellites";
const MARKS_SOURCE = "satellites";
const TRACKS_SOURCE = "satellite-tracks";
const FOOTPRINTS_SOURCE = "satellite-footprints";
const IMAGE = "satellite-mark";
const SIDE = MARK_SIZE + 4;

function addImage(map: MapLibreMap): void {
  const ratio = pixelRatio();
  const image = drawMark(
    "satellite",
    SIDE,
    paletteColor("--map-satellite", "#00796b"),
    paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)"),
    ratio,
  );
  if (!image) return;
  if (map.hasImage(IMAGE)) map.removeImage(IMAGE);
  map.addImage(IMAGE, image, { pixelRatio: ratio });
}

export function addSatelliteLayers(map: MapLibreMap, data: SatelliteFeatures = NO_SATELLITES): void {
  addImage(map);
  if (map.getSource(MARKS_SOURCE)) return;
  const ink = paletteColor("--map-satellite", "#00796b");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  map.addSource(FOOTPRINTS_SOURCE, { type: "geojson", data: data.footprints });
  map.addSource(TRACKS_SOURCE, { type: "geojson", data: data.tracks });
  map.addSource(MARKS_SOURCE, { type: "geojson", data: data.marks });
  map.addLayer({
    id: "satellite-footprints",
    type: "fill",
    source: FOOTPRINTS_SOURCE,
    paint: { "fill-color": ink, "fill-opacity": 0.07, "fill-antialias": false },
  });
  map.addLayer({
    id: "satellite-footprint-edges",
    type: "line",
    source: FOOTPRINTS_SOURCE,
    paint: { "line-color": ink, "line-width": 1, "line-opacity": 0.6 },
  });
  map.addLayer({
    id: "satellite-tracks",
    type: "line",
    source: TRACKS_SOURCE,
    layout: { "line-join": "round", "line-cap": "butt" },
    paint: { "line-color": ink, "line-width": 1.5, "line-dasharray": [3, 2] },
  });
  map.addLayer({
    id: SATELLITE_LAYER,
    type: "symbol",
    source: MARKS_SOURCE,
    layout: {
      "icon-image": IMAGE,
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "text-field": ["get", "name"],
      "text-font": [FONT_REGULAR],
      "text-size": 11,
      "text-anchor": "left",
      "text-offset": [1.1, 0],
      "text-optional": true,
    },
    paint: { "text-color": ink, "text-halo-color": halo, "text-halo-width": 1.2 },
  });
}

export function setSatelliteData(map: MapLibreMap, data: SatelliteFeatures): void {
  void map.getSource<GeoJSONSource>(FOOTPRINTS_SOURCE)?.setData(data.footprints);
  void map.getSource<GeoJSONSource>(TRACKS_SOURCE)?.setData(data.tracks);
  void map.getSource<GeoJSONSource>(MARKS_SOURCE)?.setData(data.marks);
}
