// The monitor card's own menu, opened like a copy menu (useCopyMenu): a right-click anywhere on the
// card (`on`) opens it at the pointer, so does a finger held on the card's body (`pressOn`), and
// the menu key on the picture (`picture`) opens it under the picture's left edge. The browser's
// own menu is not shown, and the focus returns to the picture when Esc closes the menu. `menu` is
// what the card gives the menu while open; `key` makes a reopened menu a new one.
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

  /** The right button or menu key: open at the pointer; the browser menu is not shown. */
  function onContextMenu(event: MouseEvent): void {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const { x, y } = menuPoint(event, picture() ?? target);
    open(x, y);
  }
  const press = useLongPress((x, y) => open(x, y));

  const on = { contextmenu: onContextMenu };
  const pressOn = { pointerdown: press.down, pointermove: press.move, pointerup: press.up, pointercancel: press.cancel };

  return { menu, key, on, pressOn, close };
}
