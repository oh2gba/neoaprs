// What a note or a menu that opens from a button has in common (the (i) InfoTip, the Route box RouteMenu, the tabs' menu TabMenu): while it is open a press or tap outside it closes it, so does the focus moving outside it (`focusAway`), and Esc closes it and puts the
// focus back on the button. The component owns `open` and how it closes (`close`: the one note open at a time of the (i) is the page's); this is the listening, which goes with the popup being open and with the component being unmounted.
// `onEscape` is for the element that takes the key: the whole popup, or only its list; `stopEscape` keeps the Esc from being passed on to what holds the popup (a conversation, which Esc would leave); `escapeAnywhere` hears Esc on the page, not only in the popup.
import { onBeforeUnmount, watch, type Ref } from "vue";

export interface PopupOptions {
  open: Readonly<Ref<boolean>>;
  /** what a press outside of is "away" */
  root: Readonly<Ref<HTMLElement | null>>;
  /** gets the focus back on Esc */
  trigger: Readonly<Ref<HTMLElement | null>>;
  close: () => void;
  focusAway?: boolean;
  stopEscape?: boolean;
  escapeAnywhere?: boolean;
}

export function usePopup({ open, root, trigger, close, focusAway = true, stopEscape = false, escapeAnywhere = false }: PopupOptions) {
  function away(event: Event): void {
    if (!(event.target instanceof Node) || !root.value?.contains(event.target)) close();
  }

  /** Esc, while the popup is open. */
  function onEscape(event: KeyboardEvent): void {
    if (event.key !== "Escape" || !open.value) return;
    if (stopEscape) event.stopPropagation();
    close();
    trigger.value?.focus();
  }

  function listen(on: boolean): void {
    const act = (type: string, handler: EventListener): void => (on ? document.addEventListener(type, handler) : document.removeEventListener(type, handler));
    act("pointerdown", away);
    if (focusAway) act("focusin", away);
    if (escapeAnywhere) act("keydown", onEscape as EventListener);
  }

  watch(open, listen);
  onBeforeUnmount(() => listen(false));
  return { onEscape };
}
