// What a popup opened from a button has in common (InfoTip, RouteMenu, TabMenu): a press outside
// or focus moving outside (`focusAway`) closes it, and Esc closes it and puts the focus back on
// the button. The component owns `open` and `close`; this is the listening. `onEscape` is for the
// element that takes the key. An Esc that closed the popup is marked handled (`preventDefault`)
// so that other Esc listeners leave it alone; `stopEscape` also keeps it from the holder of the
// popup; `escapeAnywhere` hears Esc on the whole page in the capture phase and passes it on to
// nothing.
import { onBeforeUnmount, watch, type Ref } from "vue";

export interface PopupOptions {
  open: Readonly<Ref<boolean>>;
  root: Readonly<Ref<HTMLElement | null>>;
  trigger: Readonly<Ref<HTMLElement | null>>;
  close: () => void;
  focusAway?: boolean;
  stopEscape?: boolean;
  escapeAnywhere?: boolean;
}

export function usePopup({
  open,
  root,
  trigger,
  close,
  focusAway = true,
  stopEscape = false,
  escapeAnywhere = false,
}: PopupOptions) {
  function away(event: Event): void {
    if (!(event.target instanceof Node) || !root.value?.contains(event.target)) close();
  }

  function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape" || !open.value) return;
    event.preventDefault();
    if (stopEscape || escapeAnywhere) event.stopPropagation();
    close();
    trigger.value?.focus();
  }

  function listen(on: boolean): void {
    const act = (type: string, handler: EventListener, capture = false): void =>
      on ? document.addEventListener(type, handler, capture) : document.removeEventListener(type, handler, capture);
    act("pointerdown", away);
    if (focusAway) act("focusin", away);
    if (escapeAnywhere) act("keydown", onEscape as EventListener, true);
  }

  watch(open, listen);
  onBeforeUnmount(() => listen(false));
  return { onEscape };
}
