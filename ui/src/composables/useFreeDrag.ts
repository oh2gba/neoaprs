// A card that stands alone over the map (the statistics card, components/StatsCard.vue): on a tablet and a desktop it is dragged by its head (not its buttons) with a mouse, a finger or a pen, or moved with Alt and the arrow keys while it
// has the focus (Shift for a big step), anywhere over the map and never outside it (the geometry is lib/cardmove.ts); where it was left is remembered in this browser under `key`, and it is kept inside the map when the map or the card
// changes size. The station cards have their own (composables/useCardDrag.ts: a row of cards, each one placing the others). The card's own place is in the pixels of its parent, the map's box, from its top left corner.
import { computed, onBeforeUnmount, ref, type Ref } from "vue";
import { useResized } from "@/composables/useResized";
import { clampPlace, DRAG_MIN, keyStep, type Place } from "@/lib/cardmove";
import { readStored, writeStored } from "@/lib/storage";

/** What on the head is not the head: a press on these is the button's or the link's. */
const NOT_HEAD = "button, a, input, select, textarea, summary, [role='button']";
const DRAGGING = "card-dragging";

interface Drag {
  pointer: number;
  from: Place;
  origin: Place;
  started: boolean;
  head: HTMLElement;
}

/** The place remembered under the key, "x,y"; null for none or nonsense. */
function readPlace(key: string): Place | null {
  const found = /^(-?\d+),(-?\d+)$/.exec(readStored(key) ?? "");
  return found ? { x: Number(found[1]), y: Number(found[2]) } : null;
}

export function useFreeDrag(card: Readonly<Ref<HTMLElement | null>>, key: string, enabled: () => boolean) {
  const place = ref<Place | null>(readPlace(key));
  let drag: Drag | null = null;

  /** Where the card stands now: its place, else where the page has put it. */
  function current(): Place | null {
    const el = card.value;
    const parent = el?.parentElement;
    if (!el || !parent) return null;
    if (place.value) return place.value;
    const box = el.getBoundingClientRect();
    const room = parent.getBoundingClientRect();
    return { x: box.left - room.left, y: box.top - room.top };
  }

  /** Puts the card at the place, kept inside its parent, and remembers it. */
  function put(next: Place): void {
    const el = card.value;
    const parent = el?.parentElement;
    if (!el || !parent) return;
    const box = el.getBoundingClientRect();
    const clamped = clampPlace(next, { width: box.width, height: box.height }, { left: 0, top: 0, right: parent.clientWidth, bottom: parent.clientHeight });
    if (place.value?.x === clamped.x && place.value?.y === clamped.y) return;
    place.value = clamped;
    writeStored(key, `${clamped.x},${clamped.y}`);
  }

  function stop(): void {
    drag = null;
    document.body.classList.remove(DRAGGING);
  }

  function down(event: PointerEvent): void {
    const target = event.target instanceof Element ? event.target : null;
    const head = target?.closest<HTMLElement>(".card-head");
    if (!enabled() || event.button > 0 || drag || !head || !card.value?.contains(head) || target?.closest(NOT_HEAD)) return;
    const origin = current();
    if (!origin) return;
    drag = { pointer: event.pointerId, from: { x: event.clientX, y: event.clientY }, origin, started: false, head };
    try {
      head.setPointerCapture?.(event.pointerId);
    } catch {
      // (a pointer that is gone already: the drag goes on with the events that reach the card)
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
    put({ x: drag.origin.x + dx, y: drag.origin.y + dy });
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

  /** Alt with an arrow moves the card (a step; Shift for a big one). */
  function keydown(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || event.ctrlKey || event.metaKey) return;
    const step = keyStep(event.key, event.shiftKey);
    const at = step ? current() : null;
    if (!step || !at) return;
    event.preventDefault();
    put({ x: at.x + step.x, y: at.y + step.y });
  }

  /** The map or the card changed size: a card that was moved is kept inside the map. */
  const keepInside = (): void => {
    if (enabled() && place.value) put(place.value);
  };
  useResized(
    computed(() => card.value?.parentElement ?? null),
    keepInside,
  );
  useResized(card, keepInside);
  onBeforeUnmount(stop);

  /** Where the card stands, as its style, while it was moved and moving is on. */
  const style = computed(() => (enabled() && place.value ? { left: `${place.value.x}px`, top: `${place.value.y}px` } : undefined));
  const moved = computed(() => enabled() && place.value !== null);
  /** The listeners of the card (`v-on="on"`). */
  const on = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: up, keydown };

  return { place, moved, style, on };
}
