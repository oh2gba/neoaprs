// Where a marker must stand so the card over the map does not cover it. The card sits at the
// bottom left, so a picked station's marker goes above it, or to its right if there is room. Pure
// geometry in map pixels; components/StationMap.vue moves the map by the answer.

/** A rectangle in the pixels of the map, the origin at its top left corner. */
export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Point {
  x: number;
  y: number;
}

/** The marker is 26 px wide with its call under it: the room it needs round its centre. */
const ROOM_SIDE = 22;
const ROOM_ABOVE = 16;
const ROOM_BELOW = 40;
/** The map's buttons run along its top (zoom, Follow me, Close all); a marker is not put higher. */
const TOP_FREE = 84;
/**
 * The Layers button stands under the zoom buttons in the top left (to 141 px where a finger sizes
 * them; the station cards' row starts at 150 px there, styles/responsive.css): keep markers out.
 */
const CORNER = { right: 72, bottom: 150 };
/** The distance of the moved marker from the card and from the map edge. */
const GAP = 40;
const EDGE = 30;

/** Whether the card covers the marker (or the call under it). */
export function covers(card: Box, marker: Point): boolean {
  return marker.x >= card.left - ROOM_SIDE && marker.x <= card.right + ROOM_SIDE && marker.y >= card.top - ROOM_ABOVE && marker.y <= card.bottom + ROOM_BELOW;
}

/**
 * How far the marker must move (right, down) to clear the card: the shorter of above the card or
 * to its right, staying on the map and clear of the zoom buttons; null if not covered or no way.
 */
export function moveClearOf(card: Box, marker: Point, view: Box): Point | null {
  if (!covers(card, marker)) return null;
  const ways: Point[] = [];
  const above = card.top - GAP;
  const clearOfCorner = above >= view.top + CORNER.bottom || marker.x >= view.left + CORNER.right;
  if (above >= view.top + TOP_FREE && clearOfCorner) ways.push({ x: 0, y: above - marker.y });
  const beside = card.right + GAP;
  if (beside <= view.right - EDGE) ways.push({ x: beside - marker.x, y: 0 });
  ways.sort((a, b) => Math.abs(a.x) + Math.abs(a.y) - (Math.abs(b.x) + Math.abs(b.y)));
  return ways[0] ?? null;
}
