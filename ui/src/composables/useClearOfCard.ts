// Keeps the station that was picked from being under its card: the card (or the row of cards, or the sheet of a phone: `.cardstack`) is in the same `.mapwrap` as the map and covers a corner of it. This reads where the cards are on the screen and asks lib/cardclear.ts how far a marker has to move; the map does the moving
// (components/StationMap.vue: a flight to a station ends with it clear of the card, a marker that is picked is moved out from under it). The cards in the row are one box; a card the user has moved (`.moved`) is a box of its own, where it really stands now, so the marker is kept clear of it
// there too.
import type { Map as MapLibreMap } from "maplibre-gl";
import type { Ref } from "vue";
import { moveClearOf, type Box, type Point } from "@/lib/cardclear";

export function useClearOfCard(root: Readonly<Ref<HTMLElement | null>>, host: Readonly<Ref<HTMLElement | null>>) {
  /** The boxes the cards cover over the map, in the pixels of the map: the sheet of a phone, or the row of cards as one box and each moved card as a box of its own; none when there is no card. */
  function cardBoxes(): Box[] {
    const wrap = root.value?.closest(".mapwrap");
    const at = host.value?.getBoundingClientRect();
    const sheet = wrap?.querySelector(".cardstack.sheet");
    const cards = sheet ? [sheet] : [...(wrap?.querySelectorAll(".card") ?? [])];
    if (cards.length === 0 || !at) return [];
    const around = (rects: DOMRect[]): Box => ({
      left: Math.min(...rects.map((c) => c.left)) - at.left,
      top: Math.min(...rects.map((c) => c.top)) - at.top,
      right: Math.max(...rects.map((c) => c.right)) - at.left,
      bottom: Math.max(...rects.map((c) => c.bottom)) - at.top,
    });
    const inRow = cards.filter((card) => !card.classList.contains("moved")).map((card) => card.getBoundingClientRect());
    const moved = cards.filter((card) => card.classList.contains("moved")).map((card) => around([card.getBoundingClientRect()]));
    return [...(inRow.length > 0 ? [around(inRow)] : []), ...moved];
  }

  const viewBox = (): Box => ({ left: 0, top: 0, right: host.value?.clientWidth ?? 0, bottom: host.value?.clientHeight ?? 0 });

  /** How far a marker at this place on the map has to move on the screen to be clear of the cards; null when it is, or there is no card. Moved clear of one card, it is looked at against the next. */
  function moveFor(at: Point): Point | null {
    const view = viewBox();
    let total: Point = { x: 0, y: 0 };
    let moved = false;
    let where = at;
    for (const card of cardBoxes()) {
      const move = moveClearOf(card, where, view);
      if (!move) continue;
      where = { x: where.x + move.x, y: where.y + move.y };
      total = { x: total.x + move.x, y: total.y + move.y };
      moved = true;
    }
    return moved ? total : null;
  }

  /** Where the marker stands, from the middle of the map, when the map has flown to it with the card in the way: clear of the card. */
  function flightOffset(): { offset: [number, number] } | undefined {
    const view = viewBox();
    const move = moveFor({ x: view.right / 2, y: view.bottom / 2 });
    return move ? { offset: [move.x, move.y] } : undefined;
  }

  /** The marker of the station that was picked is under the card: the map moves so that it is not (a map that is on its way to the station is left to arrive). */
  function panClear(map: Pick<MapLibreMap, "isMoving" | "project" | "panBy">, place: { lon: number; lat: number }): void {
    if (map.isMoving()) return;
    const move = moveFor(map.project([place.lon, place.lat]));
    if (move) map.panBy([0 - move.x, 0 - move.y], { duration: 300 });
  }

  return { panClear, flightOffset };
}
