// The monitor card's own menu (components/MonitorMenu.vue) as the card opens it, the way a copy menu is opened (composables/useCopyMenu.ts): a right-click anywhere on the card (`on`, the card's listeners) opens it where the
// pointer is, and so does a finger held on the card's body (`pressOn`: its head is where a finger drags the card); the menu key on the picture, which takes the focus (`picture`), opens it under the picture's left edge. The browser's
// own menu is not shown, and the focus goes back to the picture when the menu is closed by Esc. `menu` is what the card gives the menu while it is open, `key` makes a menu opened again a new one in its new place.
import { ref } from "vue";
import { useLongPress } from "@/composables/useLongPress";
import { menuPoint } from "@/lib/copy";

export interface MonitorMenuState {
  x: number;
  y: number;
  trigger: HTMLElement | null;
}

export function useMonitorMenu(picture: () => HTMLElement | null) {
  const menu = ref<MonitorMenuState | null>(null);
  const key = ref(0);

  function open(x: number, y: number): void {
    menu.value = { x, y, trigger: picture() };
    key.value++;
  }
  function close(): void {
    menu.value = null;
  }

  /** The right button (or the menu key): the menu is where the pointer is, the browser's own is not shown, and nothing above the card hears the click. */
  function onContextMenu(event: MouseEvent): void {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const { x, y } = menuPoint(event, picture() ?? target);
    open(x, y);
  }
  const press = useLongPress((x, y) => open(x, y));

  /** The card's listener (`v-on="on"`, beside the drag's). */
  const on = { contextmenu: onContextMenu };
  /** The listeners of the card's body (`v-on="pressOn"`): the finger held on the picture or the level. */
  const pressOn = { pointerdown: press.down, pointermove: press.move, pointerup: press.up, pointercancel: press.cancel };

  return { menu, key, on, pressOn, close };
}
