// What a dialog over a dimmed page does with the keyboard (the update dialog, the path builder): the focus goes into it when it opens (to `first`, else to the dialog itself) and, when it closes, to `back` (the button that opened it;
// a press does not focus a button in every browser) or else back to where it was, Tab and Shift+Tab go round inside it, and Escape closes it. `onKey` is the handler of those keys: the update dialog hears them on the whole page, the path builder on itself. An Escape it takes is marked as handled and goes no further, so that it
// does not also close what the dialog was opened from (the Route box, a conversation, the Objects form); one that something handled already is left alone.
import { nextTick, onBeforeUnmount, onMounted, type Ref } from "vue";

const FOCUSABLE = "a[href], button:not([disabled]), input:not([disabled]), summary, [tabindex]:not([tabindex='-1'])";

export interface DialogFocus {
  first?: () => HTMLElement | null;
  back?: () => HTMLElement | null;
}

export function useDialogFocus(dialog: Readonly<Ref<HTMLElement | null>>, close: () => void, { first = () => null, back = () => null }: DialogFocus = {}) {
  let before: Element | null = null;

  function focusables(): HTMLElement[] {
    return [...(dialog.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
  }

  /** Tab and Shift+Tab go round inside the dialog. */
  function keepFocus(event: KeyboardEvent): void {
    const items = focusables();
    const head = items[0];
    const last = items[items.length - 1];
    if (!head || !last) return;
    const inside = dialog.value?.contains(document.activeElement) ?? false;
    if (event.shiftKey && (document.activeElement === head || !inside)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
      event.preventDefault();
      head.focus();
    }
  }

  function onKey(event: KeyboardEvent): void {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === "Tab") keepFocus(event);
  }

  onMounted(async () => {
    before = document.activeElement;
    await nextTick();
    (first() ?? dialog.value)?.focus();
  });
  onBeforeUnmount(() => {
    const target = back() ?? before;
    if (target instanceof HTMLElement && target.isConnected) target.focus();
  });
  return { onKey };
}
