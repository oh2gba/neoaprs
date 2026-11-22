// Where the station cards stand over the map. A moved card has a `place` in the pixels of the row
// of cards; a card with a place leaves the row and never leaves the map. Moving a card never moves
// another: the first move pins every open card where it stands, closing a card keeps the later
// ones in place (`pinAfter`), and a new card goes to the first free slot (`placeNew`). Places last
// for the session only. Each write builds one object from the caller's `base`, because
// `places.value` changes only after the next render.
import type { Ref } from "vue";
import { clampPlace, freeSlot, type Area, type Place, type Placed } from "@/lib/cardmove";

export type Places = Record<string, Place>;

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

  function current(call: string, base: Places = places.value): Place | null {
    const card = stack.value ? cardOf(stack.value, call) : null;
    const at = stack.value?.getBoundingClientRect();
    if (!card || !at) return null;
    const box = card.getBoundingClientRect();
    return base[call] ?? { x: box.left - at.left, y: box.top - at.top };
  }

  function pins(calls: readonly string[], base: Places = places.value): Places {
    const stand = calls
      .filter((call) => base[call] === undefined)
      .flatMap((call) => {
        const at = current(call, base);
        return at ? [[call, { x: Math.round(at.x), y: Math.round(at.y) }] as const] : [];
      });
    return Object.fromEntries(stand);
  }

  /** Places that pin the cards behind the first closing card; ask before the next render. */
  function pinAfter(closing: readonly string[], staying: readonly string[]): Places {
    if (!enabled()) return {};
    const row = cards().filter((card) => card.dataset.call !== undefined && places.value[card.dataset.call] === undefined);
    const first = row.findIndex((card) => closing.includes(card.dataset.call ?? ""));
    return first < 0 ? {} : pins(callsOf(row.slice(first + 1)).filter((call) => staying.includes(call)));
  }

  function pinHere(call: string): void {
    const stand = pins([call]);
    if (Object.keys(stand).length > 0) places.value = { ...places.value, ...stand };
  }

  /** `base` with the card at `place` kept inside the map; null if the card is absent
   * or already there. */
  function putIn(base: Places, call: string, place: Place): Places | null {
    const card = stack.value ? cardOf(stack.value, call) : null;
    const room = stack.value ? areaOf(stack.value) : null;
    if (!card || !room) return null;
    const box = card.getBoundingClientRect();
    const clamped = clampPlace(place, { width: box.width, height: box.height }, room);
    const was = base[call];
    return was?.x === clamped.x && was?.y === clamped.y ? null : { ...base, [call]: clamped };
  }

  function put(call: string, place: Place): void {
    const pinned = pins(callsOf(cards()));
    const base = { ...places.value, ...pinned };
    const next = putIn(base, call, place) ?? (Object.keys(pinned).length > 0 ? base : null);
    if (next) places.value = next;
  }

  /** Put new cards on the first free slot while any card is pinned. */
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
        const waiting = name !== undefined && calls.includes(name) && base[name] === undefined;
        const stands = name !== undefined && name !== call && !waiting ? current(name, base) : null;
        const size = one.getBoundingClientRect();
        return stands ? [{ ...stands, width: size.width, height: size.height }] : [];
      });
      base = putIn(base, call, freeSlot({ width: box.width, height: box.height }, others, { width: at.width, height: at.height })) ?? base;
    }
    if (base !== places.value) places.value = base;
  }

  function keepInside(): void {
    if (!enabled()) return;
    let base = places.value;
    for (const [call, place] of Object.entries(places.value)) base = putIn(base, call, place) ?? base;
    if (base !== places.value) places.value = base;
  }

  return { current, put, pinHere, pinAfter, placeNew, keepInside };
}
