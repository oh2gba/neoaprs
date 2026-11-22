// Sizing a card over the map (composables/useCardSize.ts: the Packets card and the Monitor
// card): where a card ends up after an edge or corner is dragged, or an arrow key is pressed
// with Ctrl and Alt. The card is a rectangle in the pixels of the map's box; its size is never
// below what its content can be read at and never beyond the map, and the side not dragged
// stays where it is. Pure geometry; the composable measures and asks.
import { keyStep } from "@/lib/cardmove";
import type { CardSize, Place } from "@/lib/cardmove";

/** A card as it stands: its top left corner and its size, in the pixels of the map. */
export interface Rect extends Place, CardSize {}

/** The edge or corner dragged: n, s, e, w for the sides, two letters for a corner. */
export type Edge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

export const EDGES: readonly Edge[] = ["n", "s", "e", "w", "ne", "nw", "se", "sw"];

/**
 * A size within [min, max]; where the map is smaller than the least, the map's room wins (a
 * card is never larger than the map).
 */
export function clampSize(size: CardSize, least: CardSize, room: CardSize): CardSize {
  const fit = (value: number, low: number, high: number): number => Math.round(Math.min(high, Math.max(low, value)));
  return { width: fit(size.width, least.width, room.width), height: fit(size.height, least.height, room.height) };
}

/**
 * One axis: the card from `start` for `length`, a move of `delta` of its low side (`low`) or
 * its high side, the other side kept, within [least, room].
 */
function axis(
  start: number,
  length: number,
  delta: number,
  low: boolean,
  least: number,
  room: number,
): [start: number, length: number] {
  const end = start + length;
  if (low) {
    const longest = Math.min(room, end);
    const next = Math.round(Math.min(longest, Math.max(Math.min(least, longest), length - delta)));
    return [end - next, next];
  }
  const longest = Math.max(0, room - start);
  const next = Math.round(Math.min(longest, Math.max(Math.min(least, longest), length + delta)));
  return [start, next];
}

/**
 * The card after its `edge` was dragged by (dx, dy) pixels: the opposite side stays, the size
 * stays within `least` and the map `room` (its size).
 */
export function resizeRect(from: Rect, edge: Edge, dx: number, dy: number, least: CardSize, room: CardSize): Rect {
  const [x, width] =
    edge.includes("e") || edge.includes("w")
      ? axis(from.x, from.width, dx, edge.includes("w"), least.width, room.width)
      : [from.x, from.width];
  const [y, height] =
    edge.includes("n") || edge.includes("s")
      ? axis(from.y, from.height, dy, edge.includes("n"), least.height, room.height)
      : [from.y, from.height];
  return { x, y, width, height };
}

/**
 * The step of Ctrl+Alt with an arrow key: right and down make the card larger and left and up
 * smaller (Shift for a big step); null for any other key.
 */
export function sizeStep(key: string, big: boolean): { dx: number; dy: number } | null {
  const step = keyStep(key, big);
  return step ? { dx: step.x, dy: step.y } : null;
}

/**
 * The card after a key step: on each axis the side with more room in the map moves (the card
 * stands at the map's bottom right by default, so its left and top edges do), the other side
 * stays.
 */
export function resizeByKey(from: Rect, step: { dx: number; dy: number }, least: CardSize, room: CardSize): Rect {
  const west = step.dx !== 0 && from.x > room.width - from.x - from.width;
  const north = step.dy !== 0 && from.y > room.height - from.y - from.height;
  const edge = `${step.dy === 0 ? "" : north ? "n" : "s"}${step.dx === 0 ? "" : west ? "w" : "e"}` as Edge;
  return resizeRect(from, edge, west ? -step.dx : step.dx, north ? -step.dy : step.dy, least, room);
}
