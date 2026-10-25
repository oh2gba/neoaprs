// The layers of the ALOHA circle (lib/alohacircle.ts): a thin dashed line in the map label colour with a pale halo under it, and an invisible wider line over it that the pointer can find, because the circle
// has a title. The colours are the page's own (ui/src/styles/tokens.css), read when the layers are made, which is again whenever the style is set (the colour scheme changed).
import type { Map as MapLibreMap } from "maplibre-gl";
import type { AlohaCollection } from "@/lib/alohacircle";

export const ALOHA_SOURCE = "aloha";
export const ALOHA_HIT = "aloha-hit";

/** A colour of the page's palette (`--map-label`), else the one given where the style sheet is not there. */
export function paletteColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export function addAlohaLayers(map: MapLibreMap, data: AlohaCollection): void {
  if (map.getSource(ALOHA_SOURCE)) return;
  const ink = paletteColor("--map-label", "#1d2125");
  const halo = paletteColor("--map-halo", "rgba(255, 255, 255, 0.9)");
  map.addSource(ALOHA_SOURCE, { type: "geojson", data });
  const layout = { "line-join": "round", "line-cap": "butt" } as const;
  map.addLayer({ id: "aloha-halo", type: "line", source: ALOHA_SOURCE, layout, paint: { "line-color": halo, "line-width": 3.5, "line-opacity": 0.7 } });
  map.addLayer({
    id: "aloha-line",
    type: "line",
    source: ALOHA_SOURCE,
    layout,
    paint: { "line-color": ink, "line-width": 1.5, "line-opacity": 0.75, "line-dasharray": [4, 3] },
  });
  map.addLayer({ id: ALOHA_HIT, type: "line", source: ALOHA_SOURCE, paint: { "line-color": ink, "line-width": 14, "line-opacity": 0 } });
}
