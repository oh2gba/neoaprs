// Moving the station cards over the map. On a tablet and a desktop a card is dragged by its head
// with a mouse, finger or pen, or moved with Alt and the arrow keys while focused.
import { onBeforeUnmount, watch, type Ref } from "vue";
import { useCardPlaces, type Places } from "@/composables/useCardPlaces";
import { DRAG_MIN, DRAGGING, keyStep, NOT_HEAD, type Place } from "@/lib/cardmove";

export type { Places };

interface Drag {
  call: string;
  pointer: number;
  from: Place;
  origin: Place;
  started: boolean;
  head: HTMLElement;
}

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
    if (drag && !drag.head.isConnected) stop();
    const pressed = enabled() && event.button <= 0 && !drag ? headPressed(stack.value, event) : null;
    const origin = pressed ? current(pressed.call) : null;
    if (!pressed || !origin) return;
    drag = { call: pressed.call, pointer: event.pointerId, from: { x: event.clientX, y: event.clientY }, origin, started: false, head: pressed.head };
    try {
      pressed.head.setPointerCapture?.(event.pointerId);
    } catch {
      // The pointer is gone already.
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
      // It is released already.
    }
    stop();
  }

  /** Alt with an arrow moves the focused card (Shift: a big step). */
  function key(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || event.ctrlKey || event.metaKey) return;
    const step = keyStep(event.key, event.shiftKey);
    const call = event.target instanceof Element ? event.target.closest<HTMLElement>(".card")?.dataset.call : undefined;
    const at = step && call !== undefined ? current(call) : null;
    if (!step || call === undefined || !at) return;
    event.preventDefault();
    put(call, { x: at.x + step.x, y: at.y + step.y });
  }

  watch(stack, (row) => row === null && stop());
  onBeforeUnmount(stop);
  return { down, move, up, key, keepInside, pinHere, pinAfter, placeNew };
}
