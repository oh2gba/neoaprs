// Where the station cards stand over the map (components/StationCards.vue, composables/useCardDrag.ts). A card that was moved has a `place`, in the pixels of the row of cards (lib/cardmove.ts); a card with a place is out of the row, over the map where it stands,
// never outside the map. Moving a card never moves another: the first time one is moved, every open card is pinned where it stands (it gets its place), so the row does not close up; a card that is closed lets the cards after it keep their places too
// (`pinAfter`), and a card that is opened while any are pinned goes to the first free slot (`placeNew`), never on top of one. The places are only kept for the session, in the page (not in the storage): Close all and Esc, and then a new card, are back in the row.
// (The places are the page's: what is written is seen in `places.value` only when the page has been drawn again, so what is to be written at once is made into one object, from the `base` the caller holds.)
import type { Ref } from "vue";
import { clampPlace, freeSlot, type Area, type Place, type Placed } from "@/lib/cardmove";

/** The cards that have a place, by the call of the station. */
export type Places = Record<string, Place>;

/** The map as the row of cards sees it (the origin is the row's top left corner). */
function areaOf(row: HTMLElement): Area | null {
  const wrap = row.closest(".mapwrap");
  if (!wrap) return null;
  const at = row.getBoundingClientRect();
  const map = wrap.getBoundingClientRect();
  return { left: map.left - at.left, top: map.top - at.top, right: map.right - at.left, bottom: map.bottom - at.top };
}

const cardOf = (row: HTMLElement, call: string): HTMLElement | null =>
  [...row.querySelectorAll<HTMLElement>(":scope > .card")].find((card) => card.dataset.call === call) ?? null;

const callsOf = (list: readonly HTMLElement[]): string[] => list.flatMap((card) => (card.dataset.call !== undefined ? [card.dataset.call] : []));

export function useCardPlaces(stack: Readonly<Ref<HTMLElement | null>>, places: Ref<Places>, enabled: () => boolean) {
  const cards = (): HTMLElement[] => (stack.value ? [...stack.value.querySelectorAll<HTMLElement>(":scope > .card")] : []);

  /** Where the card stands now: its place, or where it is in the row. */
  function current(call: string, base: Places = places.value): Place | null {
    const card = stack.value ? cardOf(stack.value, call) : null;
    const at = stack.value?.getBoundingClientRect();
    if (!card || !at) return null;
    const box = card.getBoundingClientRect();
    return base[call] ?? { x: box.left - at.left, y: box.top - at.top };
  }

  /** Where these cards stand now, as places, for those that have none in `base` yet: the cards of the row, pinned where they are. */
  function pins(calls: readonly string[], base: Places = places.value): Places {
    const stand = calls
      .filter((call) => base[call] === undefined)
      .flatMap((call) => {
        const at = current(call, base);
        return at ? [[call, { x: Math.round(at.x), y: Math.round(at.y) }] as const] : [];
      });
    return Object.fromEntries(stand);
  }

  /** Cards are going to close: the cards of the row behind the first of them would close up, so they are to be pinned where they stand (ask this before the page is drawn again, while they are still there). The places to add. */
  function pinAfter(closing: readonly string[], staying: readonly string[]): Places {
    if (!enabled()) return {};
    const row = cards().filter((card) => card.dataset.call !== undefined && places.value[card.dataset.call] === undefined);
    const first = row.findIndex((card) => closing.includes(card.dataset.call ?? ""));
    return first < 0 ? {} : pins(callsOf(row.slice(first + 1)).filter((call) => staying.includes(call)));
  }

  /** `base` with the card at `place`, kept inside the map; null when the card is not there, or is there already. */
  function putIn(base: Places, call: string, place: Place): Places | null {
    const card = stack.value ? cardOf(stack.value, call) : null;
    const room = stack.value ? areaOf(stack.value) : null;
    if (!card || !room) return null;
    const box = card.getBoundingClientRect();
    const clamped = clampPlace(place, { width: box.width, height: box.height }, room);
    const was = base[call];
    return was?.x === clamped.x && was?.y === clamped.y ? null : { ...base, [call]: clamped };
  }

  /** Moves a card; the cards that are in the row are pinned where they stand with it, in the one write. */
  function put(call: string, place: Place): void {
    const pinned = pins(callsOf(cards()));
    const base = { ...places.value, ...pinned };
    const next = putIn(base, call, place) ?? (Object.keys(pinned).length > 0 ? base : null);
    if (next) places.value = next;
  }

  /** Cards were opened (they are in the page, not yet put anywhere): while any card is pinned each goes to the first free slot, where it overlaps no card; with none pinned they take their places in the row. */
  function placeNew(calls: readonly string[]): void {
    const at = stack.value?.getBoundingClientRect();
    if (!enabled() || !at || Object.keys(places.value).length === 0) return;
    let base = places.value;
    for (const call of calls) {
      const card = stack.value ? cardOf(stack.value, call) : null;
      if (!card || base[call] !== undefined) continue;
      const box = card.getBoundingClientRect();
      const others = cards().flatMap((one): Placed[] => {
        const name = one.dataset.call;
        const waiting = name !== undefined && calls.includes(name) && base[name] === undefined; // (opened with this one, and not put yet)
        const stands = name !== undefined && name !== call && !waiting ? current(name, base) : null;
        const size = one.getBoundingClientRect();
        return stands ? [{ ...stands, width: size.width, height: size.height }] : [];
      });
      base = putIn(base, call, freeSlot({ width: box.width, height: box.height }, others, { width: at.width, height: at.height })) ?? base;
    }
    if (base !== places.value) places.value = base;
  }

  /** The map got smaller (the window, the panel), or a card grew: the cards that were moved are kept inside it. */
  function keepInside(): void {
    if (!enabled()) return;
    let base = places.value;
    for (const [call, place] of Object.entries(places.value)) base = putIn(base, call, place) ?? base;
    if (base !== places.value) places.value = base;
  }

  return { current, put, pinAfter, placeNew, keepInside };
}
