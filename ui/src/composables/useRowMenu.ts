// The menu of a row of the Stations table (StationMenu) and the box that its "Alert me when…" opens (StationAlertBox): which station each is for, where it stands and what gets the focus back when it closes. The menu is opened by a
// right-click on the row, a long press on a touch screen or the "..." button at the row's end, where the pointer is (under the button for that); `n` makes a menu opened again a new one, in its new place. A menu whose station is
// forgotten closes. The alert box opens where the menu was, for its station, and gives the focus back to what the menu was opened from.
import { computed, ref, watch, type Ref } from "vue";
import { useLongPress } from "@/composables/useLongPress";
import { menuPoint } from "@/lib/copy";
import type { StationRow } from "@/protocol/protocol";

interface Place {
  call: string;
  x: number;
  y: number;
  trigger: HTMLElement;
}

export function useRowMenu(stations: Readonly<Ref<ReadonlyMap<string, StationRow>>>) {
  const menu = ref<(Place & { n: number }) | null>(null);
  let menus = 0;
  const menuRow = computed(() => (menu.value === null ? undefined : stations.value.get(menu.value.call)));
  watch(menuRow, (row) => row === undefined && (menu.value = null));
  const alertBox = ref<Place | null>(null);

  function openMenu(call: string, x: number, y: number, trigger: HTMLElement): void {
    menu.value = { call, x, y, trigger, n: ++menus };
  }
  /** "Alert me when…" of the menu: the box opens where the menu was. */
  function openAlertBox(call: string): void {
    if (menu.value) alertBox.value = { call, x: menu.value.x, y: menu.value.y, trigger: menu.value.trigger };
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
  /** The "..." button: the menu opens under it (and the button gets the focus back when it closes); the button again closes it. The press outside the menu closes it before the click comes, so the press says whether this button's menu was open. */
  let closing = false;
  const isOpenFrom = (call: string, button: HTMLElement): boolean => menu.value?.call === call && menu.value.trigger === button;
  function pressFrom(event: PointerEvent, call: string): void {
    closing = isOpenFrom(call, event.currentTarget as HTMLElement);
  }
  function openFrom(event: MouseEvent, call: string): void {
    const button = event.currentTarget as HTMLElement;
    const wasOpen = closing || isOpenFrom(call, button);
    closing = false;
    if (wasOpen) {
      menu.value = null;
      return;
    }
    const box = button.getBoundingClientRect();
    openMenu(call, box.left, box.bottom + 2, button);
  }

  return {
    menu,
    menuRow,
    alertBox,
    press,
    onContextMenu,
    pressFrom,
    openFrom,
    openAlertBox,
    closeMenu: () => (menu.value = null),
    closeAlertBox: () => (alertBox.value = null),
  };
}
