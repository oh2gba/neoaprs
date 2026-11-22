// What a finger does to the bottom sheet of a station card on a phone
// (components/StationCards.vue): a tap on the grip opens or folds it, a swipe up opens it, a
// swipe down folds it, and a swipe down on a folded one closes the card.

export type SheetMove = "expand" | "collapse" | "close" | "toggle";

/** A finger move shorter than this is a tap, longer is a swipe (pixels, down is positive). */
export const SWIPE_MIN = 24;

/**
 * What a finger that went down and came up `dy` pixels lower than it started does to a sheet
 * that is `expanded` or not.
 */
export function sheetMove(dy: number, expanded: boolean): SheetMove {
  if (Math.abs(dy) < SWIPE_MIN) return "toggle";
  if (dy < 0) return "expand";
  return expanded ? "collapse" : "close";
}
