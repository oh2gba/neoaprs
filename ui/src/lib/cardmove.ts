// Moving a station card over the map (components/StationCards.vue): where a card may stand. A card that was dragged by its head, or moved with Alt and the arrow keys, has a place in the pixels of the row of cards (`.cardstack`, the origin its top left corner),
// and the place is kept inside the map. Pure geometry; the component measures and asks.

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
/** However many cards the user has moved out of the row, no more than this many are open in all: the oldest closes. */
export const MOST_OPEN = 8;

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
