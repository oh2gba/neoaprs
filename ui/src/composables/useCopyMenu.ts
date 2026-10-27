// The copy menu of a component (CopyMenu): a right-click on an element (the menu key, a long press on a touch screen) opens it where the pointer is with the items `itemsAt` finds for that element (by its data attributes: the call of a row, the id of a message),
// and nothing opens when there are none. `on` are the listeners the element takes (`v-on="copy.on"`); `menu` is what the component gives the CopyMenu while it is open, `key` makes a menu opened again a new one in its new place. A click on the element after a long press
// is the finger being lifted, not a choice: `unlessHeld` runs the element's click only when it was none.
import { computed, ref } from "vue";
import { useLongPress } from "@/composables/useLongPress";
import { menuPoint, type CopyItem } from "@/lib/copy";

export interface CopyMenuState {
  items: readonly CopyItem[];
  x: number;
  y: number;
  trigger: HTMLElement;
}

export function useCopyMenu(itemsAt: (target: HTMLElement) => readonly CopyItem[]) {
  const menu = ref<CopyMenuState | null>(null);
  const key = ref(0);

  function open(target: HTMLElement, x: number, y: number): void {
    const items = itemsAt(target);
    if (items.length === 0) return;
    menu.value = { items, x, y, trigger: target };
    key.value++;
  }
  function close(): void {
    menu.value = null;
  }

  /** The right button (or the menu key): the menu is where the pointer is, the browser's own is not shown, and nothing above the element hears the click. */
  function onContextMenu(event: MouseEvent): void {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const { x, y } = menuPoint(event, target);
    open(target, x, y);
  }
  const press = useLongPress((x, y, target) => open(target, x, y));

  /** Runs the element's own click, unless it is the finger being lifted after a long press. */
  function unlessHeld(act: () => void): void {
    if (!press.swallowClick()) act();
  }

  const on = computed(() => ({
    contextmenu: onContextMenu,
    pointerdown: press.down,
    pointermove: press.move,
    pointerup: press.up,
    pointercancel: press.cancel,
  }));

  return { menu, key, on, close, unlessHeld };
}
