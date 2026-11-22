// The size of a card standing alone over the map (the Packets and Monitor cards). Edges and
// corners are dragged, or Ctrl and Alt with arrows size it from the bottom right corner (Shift:
// a big step). The size stays between `least` and the map, is remembered under `key` as
// "width,height", and the first sizing gives the card a place of its own.
import { computed, onBeforeUnmount, ref, type Ref } from "vue";
import { useResized } from "@/composables/useResized";
import { DRAG_MIN, type CardSize, type Place } from "@/lib/cardmove";
import { clampSize, resizeByKey, resizeRect, sizeStep, type Edge, type Rect } from "@/lib/cardsize";
import { readStored, writeStored } from "@/lib/storage";

const SIZING = "card-sizing";
export const SIZE_KEYS = "Control+Alt+ArrowLeft Control+Alt+ArrowRight Control+Alt+ArrowUp Control+Alt+ArrowDown";

export interface Anchor {
  current(): Place | null;
  setPlace(place: Place, keep?: boolean): void;
}

interface Sizing {
  pointer: number;
  edge: Edge;
  from: Place;
  start: Rect;
  handle: HTMLElement;
}

function readSize(key: string): CardSize | null {
  const found = /^(\d{1,5}),(\d{1,5})$/.exec(readStored(key) ?? "");
  return found ? { width: Number(found[1]), height: Number(found[2]) } : null;
}

export function useCardSize(card: Readonly<Ref<HTMLElement | null>>, key: string, least: CardSize, anchor: Anchor, enabled: () => boolean) {
  const size = ref<CardSize | null>(readSize(key));
  let sizing: Sizing | null = null;
  let last: Rect | null = null;

  function room(): CardSize | null {
    const parent = card.value?.parentElement;
    return parent ? { width: parent.clientWidth, height: parent.clientHeight } : null;
  }

  function rect(): Rect | null {
    const at = anchor.current();
    const box = card.value?.getBoundingClientRect();
    return at && box ? { ...at, width: Math.round(box.width), height: Math.round(box.height) } : null;
  }

  /** Put the card at `next`; place and size are kept only when the gesture ends. */
  function apply(next: Rect, keep: boolean): void {
    anchor.setPlace({ x: next.x, y: next.y }, keep);
    size.value = { width: next.width, height: next.height };
    if (keep) writeStored(key, `${next.width},${next.height}`);
  }

  function stop(): void {
    sizing = null;
    document.body.classList.remove(SIZING);
  }

  function down(event: PointerEvent, edge: Edge): void {
    const handle = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    const start = rect();
    if (!enabled() || event.button > 0 || sizing || !handle || !start) return;
    last = null;
    sizing = { pointer: event.pointerId, edge, from: { x: event.clientX, y: event.clientY }, start, handle };
    document.body.classList.add(SIZING);
    event.preventDefault();
    try {
      handle.setPointerCapture?.(event.pointerId);
    } catch {
      // The pointer is gone already.
    }
  }

  function move(event: PointerEvent): void {
    const space = room();
    if (!sizing || event.pointerId !== sizing.pointer || !space) return;
    event.preventDefault();
    const dx = event.clientX - sizing.from.x;
    const dy = event.clientY - sizing.from.y;
    if (Math.hypot(dx, dy) < DRAG_MIN && size.value === null) return;
    last = resizeRect(sizing.start, sizing.edge, dx, dy, least, space);
    apply(last, false);
  }

  function up(event: PointerEvent): void {
    if (!sizing || event.pointerId !== sizing.pointer) return;
    try {
      sizing.handle.releasePointerCapture?.(event.pointerId);
    } catch {
      // It is released already.
    }
    if (last) apply(last, true);
    stop();
  }

  function keydown(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || !event.ctrlKey || event.metaKey) return;
    const step = sizeStep(event.key, event.shiftKey);
    const from = step ? rect() : null;
    const space = room();
    if (!step || !from || !space) return;
    event.preventDefault();
    apply(resizeByKey(from, step, least, space), true);
  }

  /** The shown size is the chosen one within the map; the chosen one stays as it was. */
  const space = ref<CardSize | null>(null);
  useResized(
    computed(() => card.value?.parentElement ?? null),
    () => (space.value = room()),
  );
  onBeforeUnmount(stop);

  /** The card's style size while sizing is on; the map's height limit gives way to it. */
  const shown = computed(() =>
    size.value && space.value && space.value.width > 0 && space.value.height > 0 ? clampSize(size.value, least, space.value) : size.value,
  );
  const style = computed(() =>
    enabled() && shown.value ? { width: `${shown.value.width}px`, height: `${shown.value.height}px`, maxHeight: "none" } : undefined,
  );
  const sized = computed(() => enabled() && size.value !== null);
  /** The listeners of a handle (`v-on="handle"`); the key listener is the card's. */
  const handle = { pointermove: move, pointerup: up, pointercancel: up };

  return { size, sized, style, handle, keydown, down, enabled };
}

export type CardSizing = ReturnType<typeof useCardSize>;
