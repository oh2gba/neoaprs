// The map's own menu (components/MapMenu.vue) as the map opens it: where it was asked for and the place under the pointer there. A right-click is MapLibre's `contextmenu` event, with the place in it (the browser's own menu is
// not shown); a finger held on the map (`on`, the listeners of the map's root: useLongPress) is the same for the place under it, which the map is asked for (`unproject`; the browser gives no right-click there, and where it
// does, the second asking replaces the first). `key` makes a menu asked for again a new one, in its new place. The map's hover card is hidden as the menu opens.
import { ref, type Ref } from "vue";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useLongPress } from "@/composables/useLongPress";

export interface MapMenuState {
  lat: number;
  lon: number;
  /** where the menu stands, in the window's pixels */
  x: number;
  y: number;
}

/** What MapLibre's `contextmenu` event carries, as far as the menu needs it. */
export interface MapMenuEvent {
  lngLat?: { lat: number; lng: number };
  point?: { x: number; y: number };
  originalEvent?: MouseEvent;
  preventDefault?: () => void;
}

/** What the map lends the menu: the map itself (for the place under a finger), and its hover card, hidden as the menu opens. */
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

  /** A pixel of the map in the window's coordinates. */
  function pageXY(point?: { x: number; y: number }): { x: number; y: number } {
    const box = host.value?.getBoundingClientRect();
    return { x: (box?.left ?? 0) + (point?.x ?? 0), y: (box?.top ?? 0) + (point?.y ?? 0) };
  }

  /** The right button on the map: the menu for the place, and no browser menu. Nothing without a place. */
  function onContextMenu(event?: MapMenuEvent): void {
    if (!event?.lngLat) return;
    event.preventDefault?.();
    event.originalEvent?.preventDefault();
    const at = event.originalEvent ? { x: event.originalEvent.clientX, y: event.originalEvent.clientY } : pageXY(event.point);
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

  /** The listeners of the map's root (`v-on="on"`): the finger held on the map. */
  const on = { pointerdown: press.down, pointermove: press.move, pointerup: press.up, pointercancel: press.cancel };

  return { menu, key, onContextMenu, on, close };
}
