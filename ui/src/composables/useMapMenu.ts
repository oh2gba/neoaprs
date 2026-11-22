// The map's own menu: where it was asked for and the place under the pointer. A right-click is
// MapLibre's `contextmenu` event; a finger held on the map (`on`, the listeners of the map's root)
// asks the map for the place (`unproject`). `key` makes a menu asked for again a new one.
import { ref, type Ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useLongPress } from "@/composables/useLongPress";

export type MapCard = "stats" | "packets" | "monitor";

export interface MapMenuState {
  lat: number;
  lon: number;
  /** Where the menu stands, in window pixels. */
  x: number;
  y: number;
}

export interface MapMenuEvent {
  lngLat?: { lat: number; lng: number };
  point?: { x: number; y: number };
  originalEvent?: MouseEvent;
  preventDefault?: () => void;
}

export interface MapParts {
  map: MapLibreMap | null;
  hover: { hide(): void } | null;
}

export function useMapMenu(host: Readonly<Ref<HTMLElement | null>>, parts: () => MapParts) {
  const menu = ref<MapMenuState | null>(null);
  const key = ref(0);

  function open(lat: number, lon: number, x: number, y: number): void {
    parts().hover?.hide();
    menu.value = { lat, lon, x, y };
    key.value++;
  }

  function pageXY(point?: { x: number; y: number }): { x: number; y: number } {
    const box = host.value?.getBoundingClientRect();
    return { x: (box?.left ?? 0) + (point?.x ?? 0), y: (box?.top ?? 0) + (point?.y ?? 0) };
  }

  /** The right button on the map: open the menu for the place, with no browser menu. */
  function onContextMenu(event?: MapMenuEvent): void {
    if (!event?.lngLat) return;
    event.preventDefault?.();
    event.originalEvent?.preventDefault();
    const at = event.originalEvent
      ? { x: event.originalEvent.clientX, y: event.originalEvent.clientY }
      : pageXY(event.point);
    open(event.lngLat.lat, event.lngLat.lng, at.x, at.y);
  }

  const press = useLongPress((x, y) => {
    const { map } = parts();
    const box = host.value?.getBoundingClientRect();
    if (!map || !box) return;
    const at = map.unproject([x - box.left, y - box.top]);
    open(at.lat, at.lng, x, y);
  });

  function close(): void {
    menu.value = null;
  }

  const on = { pointerdown: press.down, pointermove: press.move, pointerup: press.up, pointercancel: press.cancel };

  return { menu, key, onContextMenu, on, close };
}
