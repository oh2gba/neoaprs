// Moving the station cards over the map (components/StationCards.vue). On a tablet and a desktop a card is dragged by its head (the symbol and the call: not its buttons and links) with a mouse, a finger or a pen, or moved with Alt and the arrow keys while it has the focus,
// and it stays where it was put while it is open. Where the cards stand, and that moving one never moves another, is composables/useCardPlaces.ts.
import { onBeforeUnmount, type Ref } from "vue";
import { useCardPlaces, type Places } from "@/composables/useCardPlaces";
import { DRAG_MIN, keyStep, type Place } from "@/lib/cardmove";

export type { Places };

/** What on a card's head is not the head: a click on these is the button's or the link's. */
const NOT_HEAD = "button, a, input, select, textarea, summary, [role='button']";
const DRAGGING = "card-dragging";

interface Drag {
  call: string;
  pointer: number;
  from: Place;
  origin: Place;
  started: boolean;
  head: HTMLElement;
}

/** The call of the card whose head was pressed (not on a button or a link of it), with the head. */
function headPressed(row: HTMLElement | null, event: Event): { call: string; head: HTMLElement } | null {
  const target = event.target instanceof Element ? event.target : null;
  const head = target?.closest<HTMLElement>(".card-head");
  const call = head?.closest<HTMLElement>(".card")?.dataset.call;
  return head && call !== undefined && row?.contains(head) && !target?.closest(NOT_HEAD) ? { call, head } : null;
}

export function useCardDrag(stack: Readonly<Ref<HTMLElement | null>>, places: Ref<Places>, enabled: () => boolean) {
  const { current, put, pinHere, pinAfter, placeNew, keepInside } = useCardPlaces(stack, places, enabled);
  let drag: Drag | null = null;

  function stop(): void {
    drag = null;
    document.body.classList.remove(DRAGGING);
  }

  function down(event: PointerEvent): void {
    const pressed = enabled() && event.button <= 0 && !drag ? headPressed(stack.value, event) : null;
    const origin = pressed ? current(pressed.call) : null;
    if (!pressed || !origin) return;
    drag = { call: pressed.call, pointer: event.pointerId, from: { x: event.clientX, y: event.clientY }, origin, started: false, head: pressed.head };
    try {
      pressed.head.setPointerCapture?.(event.pointerId);
    } catch {
      // (a pointer that is gone already: the drag goes on with the events that reach the row)
    }
  }

  function move(event: PointerEvent): void {
    if (!drag || event.pointerId !== drag.pointer) return;
    const dx = event.clientX - drag.from.x;
    const dy = event.clientY - drag.from.y;
    if (!drag.started) {
      if (Math.hypot(dx, dy) < DRAG_MIN) return;
      drag.started = true;
      document.body.classList.add(DRAGGING);
    }
    event.preventDefault();
    put(drag.call, { x: drag.origin.x + dx, y: drag.origin.y + dy });
  }

  function up(event: PointerEvent): void {
    if (!drag || event.pointerId !== drag.pointer) return;
    try {
      drag.head.releasePointerCapture?.(event.pointerId);
    } catch {
      // (it is let go of already)
    }
    stop();
  }

  /** Alt with an arrow moves the card that has the focus (a step; Shift for a big one); the first move pins every card where it stands. */
  function key(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || event.ctrlKey || event.metaKey) return;
    const step = keyStep(event.key, event.shiftKey);
    const call = event.target instanceof Element ? event.target.closest<HTMLElement>(".card")?.dataset.call : undefined;
    const at = step && call !== undefined ? current(call) : null;
    if (!step || call === undefined || !at) return;
    event.preventDefault();
    put(call, { x: at.x + step.x, y: at.y + step.y });
  }

  onBeforeUnmount(stop);
  return { down, move, up, key, keepInside, pinHere, pinAfter, placeNew };
}
