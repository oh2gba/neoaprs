// The copy menu of a component: a right-click, the menu key or a long press opens it at the
// pointer with the items `itemsAt` finds for the element (from its data attributes); nothing
// opens when there are none. `on` are the element's listeners, `menu` is what the component gives
// CopyMenu, and `key` makes a reopened menu a new one. `unlessHeld` runs the element's click only
// if it is not the lifting of a finger after a long press.
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

  function onContextMenu(event: MouseEvent): void {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const { x, y } = menuPoint(event, target);
    open(target, x, y);
  }
  const press = useLongPress((x, y, target) => open(target, x, y));

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
