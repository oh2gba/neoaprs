// What a menu that opens where the pointer is has in common (the menu of a row of the Stations table, StationMenu; the copy menu of a call or a text, CopyMenu): it is a list of items at `x`, `y`, kept inside the window (moved left and up as far as it needs), it takes
// the focus on its first item when it is shown, Up, Down, Home and End move in it, Esc closes it (the focus goes back to `trigger`), and so do a press outside it and Tab. The component owns its items and what choosing one does, and says `close` when it is done.
import { computed, nextTick, onMounted, ref, type Ref } from "vue";
import { usePopup } from "@/composables/usePopup";

const MARGIN = 8;

export interface ContextMenuOptions {
  x: () => number;
  y: () => number;
  trigger: () => HTMLElement | null;
  /** the `ul` of the menu */
  list: Readonly<Ref<HTMLElement | null>>;
  /** the items, in their order */
  buttons: Readonly<Ref<HTMLElement[]>>;
  close: () => void;
}

export function useContextMenu({ x, y, trigger, list, buttons, close }: ContextMenuOptions) {
  const open = ref(false);
  /** Where the menu stands: where it was asked for, kept inside the window. */
  const at = ref({ left: x(), top: y() });

  function closeMenu(): void {
    open.value = false;
    close();
  }
  const popup = usePopup({ open, root: list, trigger: computed(trigger), close: closeMenu, focusAway: false, stopEscape: true });

  function focusItem(index: number): void {
    const count = buttons.value.length;
    if (count > 0) buttons.value[((index % count) + count) % count]?.focus();
  }
  function onKey(event: KeyboardEvent): void {
    const now = buttons.value.findIndex((b) => b === document.activeElement);
    const step: Record<string, () => void> = {
      ArrowDown: () => focusItem(now + 1),
      ArrowUp: () => focusItem(now < 0 ? -1 : now - 1),
      Home: () => focusItem(0),
      End: () => focusItem(-1),
    };
    if (event.key === "Escape") {
      event.preventDefault();
      popup.onEscape(event);
    } else if (event.key === "Tab") {
      closeMenu();
    } else if (step[event.key]) {
      event.preventDefault();
      step[event.key]?.();
    }
  }

  /** Keeps the menu inside the window: where it was asked for, moved left and up as far as it needs. */
  function clamp(): void {
    const box = list.value?.getBoundingClientRect();
    if (!box) return;
    const left = Math.max(MARGIN, Math.min(x(), window.innerWidth - box.width - MARGIN));
    const top = Math.max(MARGIN, Math.min(y(), window.innerHeight - box.height - MARGIN));
    at.value = { left, top };
  }

  onMounted(async () => {
    open.value = true;
    await nextTick();
    clamp();
    focusItem(0);
  });

  /** The menu is done (an item was chosen): it closes without the focus going back. */
  function done(): void {
    open.value = false;
    close();
  }

  return { at, onKey, done };
}
