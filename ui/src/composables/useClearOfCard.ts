// Keeps the station that was picked from being under its card: the card (or the column of cards, or the sheet of a phone: `.cardstack`) is in the same `.mapwrap` as the map and covers a corner of it. This reads where the card is on the screen and asks lib/cardclear.ts how far a marker has to move; the map does the moving
// (components/StationMap.vue: a flight to a station ends with it clear of the card, a marker that is picked is moved out from under it).
import type { Map as MapLibreMap } from "maplibre-gl";
import type { Ref } from "vue";
import { moveClearOf, type Box, type Point } from "@/lib/cardclear";

export function useClearOfCard(root: Readonly<Ref<HTMLElement | null>>, host: Readonly<Ref<HTMLElement | null>>) {
  /** The card over the map, in the pixels of the map; null when there is none. */
  function cardBox(): Box | null {
    const card = root.value?.closest(".mapwrap")?.querySelector(".cardstack, .card");
    const at = host.value?.getBoundingClientRect();
    if (!card || !at) return null;
    const c = card.getBoundingClientRect();
    return { left: c.left - at.left, top: c.top - at.top, right: c.right - at.left, bottom: c.bottom - at.top };
  }

  const viewBox = (): Box => ({ left: 0, top: 0, right: host.value?.clientWidth ?? 0, bottom: host.value?.clientHeight ?? 0 });

  /** How far a marker at this place on the map has to move on the screen to be clear of the card; null when it is, or there is no card. */
  function moveFor(at: Point): Point | null {
    const card = cardBox();
    return card === null ? null : moveClearOf(card, at, viewBox());
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
