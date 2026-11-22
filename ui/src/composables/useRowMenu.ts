// The menu of a Stations table row: which station, where it stands and what regains the focus on
// close. A right-click or a long press opens it at the pointer; `n` makes a reopened menu a new
// one. A menu whose station is forgotten closes.
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
  /** The right button or menu key on a row: open at the pointer, or at the row for a key. */
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
