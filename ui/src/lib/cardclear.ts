// Where a marker has to stand so that the card over the map does not cover it: the card sits at the bottom left of the map, so the marker of the station that was picked goes above it, or at its right when there is room there.
// Pure geometry in the pixels of the map; components/StationMap.vue asks it after a station is picked and moves the map by the answer.

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

/** The marker is 26 px wide and has its call under it; the room it needs round its centre, and the room to keep from the card. */
const ROOM_SIDE = 22;
const ROOM_ABOVE = 16;
const ROOM_BELOW = 40;
/** The map's zoom buttons are in the top left corner: a marker is not put higher than this. */
const TOP_FREE = 84;
/** The marker stands this far from the card once moved, and from the edge of the map. */
const GAP = 40;
const EDGE = 30;

/** Whether the card covers the marker (or the call under it). */
export function covers(card: Box, marker: Point): boolean {
  return marker.x >= card.left - ROOM_SIDE && marker.x <= card.right + ROOM_SIDE && marker.y >= card.top - ROOM_ABOVE && marker.y <= card.bottom + ROOM_BELOW;
}

/** How far the marker has to move on the screen (to the right, downwards) so that the card does not cover it: the shorter of the ways above the card and at its right, the ones that leave the marker on the map and clear of the zoom buttons; null when it is not covered, or when no way is left. */
export function moveClearOf(card: Box, marker: Point, view: Box): Point | null {
  if (!covers(card, marker)) return null;
  const ways: Point[] = [];
  const above = card.top - GAP;
  if (above >= view.top + TOP_FREE) ways.push({ x: 0, y: above - marker.y });
  const beside = card.right + GAP;
  if (beside <= view.right - EDGE) ways.push({ x: beside - marker.x, y: 0 });
  ways.sort((a, b) => Math.abs(a.x) + Math.abs(a.y) - (Math.abs(b.x) + Math.abs(b.y)));
  return ways[0] ?? null;
}
