// Keeps a picked station from lying under its card. Reads where the cards are on screen and asks
// lib/cardclear.ts how far a marker must move; the map does the moving. The cards of the row are
// one box and each moved card (`.moved`) is a box of its own.
import type { Map as MapLibreMap } from "maplibre-gl";
import type { Ref } from "vue";
import { moveClearOf, type Box, type Point } from "@/lib/cardclear";

export function useClearOfCard(root: Readonly<Ref<HTMLElement | null>>, host: Readonly<Ref<HTMLElement | null>>) {
  /** The boxes the cards cover, in map pixels; none without a card. */
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

  /** How far a marker at this place must move on screen to be clear of the cards; null if clear. */
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

  function flightOffset(): { offset: [number, number] } | undefined {
    const view = viewBox();
    const move = moveFor({ x: view.right / 2, y: view.bottom / 2 });
    return move ? { offset: [move.x, move.y] } : undefined;
  }

  function panClear(map: Pick<MapLibreMap, "isMoving" | "project" | "panBy">, place: { lon: number; lat: number }): void {
    if (map.isMoving()) return;
    const move = moveFor(map.project([place.lon, place.lat]));
    if (move) map.panBy([0 - move.x, 0 - move.y], { duration: 300 });
  }

  return { panClear, flightOffset };
}
