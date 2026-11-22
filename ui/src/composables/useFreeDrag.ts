// A card standing alone over the map (the statistics card). On a tablet and a desktop it is
// dragged by its head with a mouse, finger or pen, or moved with Alt and the arrows (Shift: a big
// step); it stays inside the map and its place is remembered under `key` in the pixels of its
// parent. The station cards have their own (useCardDrag).
import { computed, onBeforeUnmount, ref, type Ref } from "vue";
import { useResized } from "@/composables/useResized";
import { clampPlace, DRAG_MIN, DRAGGING, keyStep, NOT_HEAD, type Place } from "@/lib/cardmove";
import { readStored, writeStored } from "@/lib/storage";

interface Drag {
  pointer: number;
  from: Place;
  origin: Place;
  started: boolean;
  head: HTMLElement;
}

function readPlace(key: string): Place | null {
  const found = /^(-?\d+),(-?\d+)$/.exec(readStored(key) ?? "");
  return found ? { x: Number(found[1]), y: Number(found[2]) } : null;
}

export function useFreeDrag(card: Readonly<Ref<HTMLElement | null>>, key: string, enabled: () => boolean) {
  const place = ref<Place | null>(readPlace(key));
  let drag: Drag | null = null;

  function current(): Place | null {
    const el = card.value;
    const parent = el?.parentElement;
    if (!el || !parent) return null;
    if (place.value) return place.value;
    const [box, room] = [el.getBoundingClientRect(), parent.getBoundingClientRect()];
    return { x: box.left - room.left, y: box.top - room.top };
  }

  /** Put the card at the place as it is, not kept inside; remembered unless `keep` is off. */
  const setPlace = (next: Place, keep = true): void => {
    if (keep) writeStored(key, `${next.x},${next.y}`);
    place.value = next;
  };
  function put(next: Place): void {
    const el = card.value;
    const parent = el?.parentElement;
    if (!el || !parent) return;
    const box = el.getBoundingClientRect();
    setPlace(clampPlace(next, { width: box.width, height: box.height }, { left: 0, top: 0, right: parent.clientWidth, bottom: parent.clientHeight }));
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
    put({ x: drag.origin.x + dx, y: drag.origin.y + dy });
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

  function keydown(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || event.ctrlKey || event.metaKey) return;
    const step = keyStep(event.key, event.shiftKey);
    const at = step ? current() : null;
    if (!step || !at) return;
    event.preventDefault();
    put({ x: at.x + step.x, y: at.y + step.y });
  }

  const keepInside = (): void => {
    if (enabled() && place.value) put(place.value);
  };
  useResized(
    computed(() => card.value?.parentElement ?? null),
    keepInside,
  );
  useResized(card, keepInside);
  onBeforeUnmount(stop);

  const style = computed(() => (enabled() && place.value ? { left: `${place.value.x}px`, top: `${place.value.y}px` } : undefined));
  const moved = computed(() => enabled() && place.value !== null);
  const on = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: up, keydown };

  return { place, moved, style, on, current, setPlace };
}
