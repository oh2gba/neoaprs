// The size of a card that stands alone over the map (the Packets card and the Monitor card, which move with composables/useFreeDrag.ts): its edges and its corners are dragged with a mouse, a finger or a pen (components/CardSizer.vue
// draws the handles), or Ctrl and Alt with the arrow keys size it from its bottom right corner while it has the focus (Shift for a big step; Alt alone moves it). The size is never below `least` (what the card's content can be read at)
// and never beyond the map, a map or a window made smaller brings the card back inside, and the size is remembered in this browser under `key`, "width,height", beside the place. A card that was never sized has the size its style gives it.
// The first time a card is sized it takes a place of its own (the corner that stays is a place in the map's pixels), as a moved card has.
import { computed, onBeforeUnmount, ref, type Ref } from "vue";
import { useResized } from "@/composables/useResized";
import { DRAG_MIN, type CardSize, type Place } from "@/lib/cardmove";
import { clampSize, resizeByKey, resizeRect, sizeStep, type Edge, type Rect } from "@/lib/cardsize";
import { readStored, writeStored } from "@/lib/storage";

const SIZING = "card-sizing";
/** What a screen reader is told the keys of the card are (`aria-keyshortcuts`). */
export const SIZE_KEYS = "Control+Alt+ArrowLeft Control+Alt+ArrowRight Control+Alt+ArrowUp Control+Alt+ArrowDown";

/** What the card's place is: where it stands, and putting it somewhere without keeping it inside (the size does that). */
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

/** The size remembered under the key, "w,h"; null for none or nonsense. */
function readSize(key: string): CardSize | null {
  const found = /^(\d{1,5}),(\d{1,5})$/.exec(readStored(key) ?? "");
  return found ? { width: Number(found[1]), height: Number(found[2]) } : null;
}

export function useCardSize(card: Readonly<Ref<HTMLElement | null>>, key: string, least: CardSize, anchor: Anchor, enabled: () => boolean) {
  const size = ref<CardSize | null>(readSize(key));
  let sizing: Sizing | null = null;
  let last: Rect | null = null; // (the card as the last move put it: the page may not have drawn it yet when the pointer is let go)

  /** The map's size, the room the card is inside; null while the card is not there. */
  function room(): CardSize | null {
    const parent = card.value?.parentElement;
    return parent ? { width: parent.clientWidth, height: parent.clientHeight } : null;
  }

  /** The card as it stands now, in the map's pixels. */
  function rect(): Rect | null {
    const at = anchor.current();
    const box = card.value?.getBoundingClientRect();
    return at && box ? { ...at, width: Math.round(box.width), height: Math.round(box.height) } : null;
  }

  /** Puts the card as `next`; the place and the size are kept (`keep`) when the gesture is done, not at every move. */
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
      // (a pointer that is gone already)
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
      // (it is let go of already)
    }
    if (last) apply(last, true);
    stop();
  }

  /** Ctrl and Alt with an arrow key size the card (a step; Shift for a big one). */
  function keydown(event: KeyboardEvent): void {
    if (!enabled() || !event.altKey || !event.ctrlKey || event.metaKey) return;
    const step = sizeStep(event.key, event.shiftKey);
    const from = step ? rect() : null;
    const space = room();
    if (!step || !from || !space) return;
    event.preventDefault();
    apply(resizeByKey(from, step, least, space), true);
  }

  /** The map's size as last seen: the size that is shown is the chosen one within it, and the chosen one stays as it was (a window made small for a moment loses nothing). */
  const space = ref<CardSize | null>(null);
  useResized(
    computed(() => card.value?.parentElement ?? null),
    () => (space.value = room()),
  );
  onBeforeUnmount(stop);

  /** The size as the card's style, while it was sized and sizing is on; the map's own limit on the height gives way to it, which is the map's room already. */
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
