// The menu of a row of the Stations table (StationMenu): which station it is for, where it stands and what gets the focus back when it closes. It is opened by a right-click on the row or a long press on a touch screen, where
// the pointer is; `n` makes a menu opened again a new one, in its new place. A menu whose station is forgotten closes.
import { computed, ref, watch, type Ref } from "vue";
import { useLongPress } from "@/composables/useLongPress";
import { menuPoint } from "@/lib/copy";
import type { StationRow } from "@/protocol/protocol";

interface Place {
  call: string;
  x: number;
  y: number;
  trigger: HTMLElement;
  n: number;
}

export function useRowMenu(stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>) {
  const menu = ref<Place | null>(null);
  let menus = 0;
  const menuRow = computed(() => (menu.value === null ? undefined : stations.value.get(menu.value.call)));
  watch(menuRow, (row) => row === undefined && (menu.value = null));

  function openMenu(call: string, x: number, y: number, trigger: HTMLElement): void {
    menu.value = { call, x, y, trigger, n: ++menus };
  }
  /** The right button on a row (or the menu key): the menu is where the pointer is, and the browser's own is not shown. A key has no pointer: the menu is at the row. */
  function onContextMenu(event: MouseEvent, call: string): void {
    event.preventDefault();
    const row = event.currentTarget as HTMLElement;
    const { x, y } = menuPoint(event, row);
    openMenu(call, x, y, row);
  }
  const press = useLongPress((x, y, target) => {
    const call = target.dataset.call;
    if (call !== undefined) openMenu(call, x, y, target);
  });

  return { menu, menuRow, press, onContextMenu, closeMenu: () => (menu.value = null) };
}
