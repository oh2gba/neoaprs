// Moving a station card over the map (components/StationCards.vue): where a card may stand. A card that was dragged by its head, or moved with Alt and the arrow keys, has a place in the pixels of the row of cards (`.cardstack`, the origin its top left corner),
// and the place is kept inside the map. Moving one card never moves another: the first time a card is moved the others are pinned where they stand (they get a place too), and a card that is opened later is put in the first free slot (`freeSlot`).
// Pure geometry; the component measures and asks.

/** Where a card's top left corner is, in the pixels of the row of cards. */
export interface Place {
  x: number;
  y: number;
}

/** The map as the row of cards sees it: the room a card may stand in (the origin is the row's top left corner, so the numbers can be negative). */
export interface Area {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface CardSize {
  width: number;
  height: number;
}

/** A move of the pointer shorter than this (pixels) is a click on the head, not a drag. */
export const DRAG_MIN = 4;
/** How far Alt+arrow moves a card, and with Shift held. */
export const KEY_STEP = 24;
export const KEY_STEP_BIG = 96;
/** The gap between two cards that stand side by side (the row's, in pixels). */
const SLOT_GAP = 8;

/** The place nearest to `place` where a card of this size is wholly inside the area (a card larger than the area is put at its top left). Whole pixels. */
export function clampPlace(place: Place, size: CardSize, area: Area): Place {
  const x = Math.max(area.left, Math.min(area.right - size.width, place.x));
  const y = Math.max(area.top, Math.min(area.bottom - size.height, place.y));
  return { x: Math.round(Math.max(area.left, x)), y: Math.round(Math.max(area.top, y)) };
}

/** The step of an Alt+arrow key in the pixels of the screen, or null when the key is not an arrow. */
export function keyStep(key: string, big: boolean): Place | null {
  const n = big ? KEY_STEP_BIG : KEY_STEP;
  switch (key) {
    case "ArrowLeft":
      return { x: -n, y: 0 };
    case "ArrowRight":
      return { x: n, y: 0 };
    case "ArrowUp":
      return { x: 0, y: -n };
    case "ArrowDown":
      return { x: 0, y: n };
    default:
      return null;
  }
}

/** A card as it stands: its top left corner in the pixels of the row, and its size. */
export interface Placed extends Place, CardSize {}

const overlaps = (a: Placed, b: Placed): boolean =>
  a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

/**
 * Where a card that is opened now stands, when the cards that are open stay where they are: the first slot of the row where it overlaps no card, the bottom of the row first (the cards' bottom edge on the row's) and from the left (the slot a card
 * was moved out of is free again, and so is any space between cards), then the rows above. The places tried are the row's edges and the sides of the cards, a gap from them. Never on top of a card; a map so full that there is no room anywhere
 * puts it to the right of the rightmost card (the caller keeps it inside the map). `row` is the size of the row of cards: its top left corner is the origin.
 */
export function freeSlot(size: CardSize, others: readonly Placed[], row: CardSize, gap: number = SLOT_GAP): Place {
  const inside = (at: number, room: number, wide: number): boolean => at >= 0 && at + wide <= room + 0.5;
  const bottom = Math.max(0, Math.round(row.height - size.height));
  const xs = [0, row.width - size.width, ...others.flatMap((card) => [card.x + card.width + gap, card.x - gap - size.width])]
    .map(Math.round)
    .filter((x) => inside(x, row.width, size.width));
  const ys = [bottom, ...others.map((card) => card.y - gap - size.height)].map(Math.round).filter((y) => inside(y, row.height, size.height));
  for (const y of [...new Set(ys)].sort((a, b) => b - a)) {
    const at = [...new Set(xs)].sort((a, b) => a - b).find((x) => !others.some((card) => overlaps({ x, y, ...size }, card)));
    if (at !== undefined) return { x: at, y };
  }
  return { x: others.length > 0 ? Math.round(Math.max(...others.map((card) => card.x + card.width)) + gap) : 0, y: bottom };
}
