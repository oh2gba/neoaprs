// The marker of the place the first-run guide holds, kept on the map: made when there is a place, moved when it changes, taken away when there is none; it can be dragged, and where it is
// dropped is given to `dropped`, as a click there would be. Returns the marker the map has now.
import type { Map as MapLibreMap, Marker } from "maplibre-gl";

interface Engine {
  Marker: new (options: { element: HTMLElement; anchor: "center" }) => Marker;
}

export function placePin(
  engine: Engine,
  map: MapLibreMap,
  current: Marker | null,
  at: { lat: number; lon: number } | null | undefined,
  dropped: (lat: number, lon: number) => void = () => {},
): Marker | null {
  if (!at) {
    current?.remove();
    return null;
  }
  let marker = current;
  if (!marker) {
    const element = document.createElement("div");
    element.className = "setuppin";
    element.setAttribute("aria-hidden", "true");
    const made = new engine.Marker({ element, anchor: "center" }).setLngLat([at.lon, at.lat]).setDraggable(true).addTo(map);
    made.on("dragend", () => {
      const to = made.getLngLat();
      dropped(to.lat, to.lng);
    });
    marker = made;
  }
  return marker.setLngLat([at.lon, at.lat]);
}
