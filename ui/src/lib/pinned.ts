// The pinned station cards (components/StationCard.vue, composables/useSelection.ts), kept in this
// browser (lib/storage.ts, so each device decides): the calls, and where each card stands over the
// map (a place, or null). Read at page start, written when a pin or place changes; a value that is
// not what was written is ignored.
import { readStored, removeStored, writeStored } from "@/lib/storage";
import type { Place } from "@/lib/cardmove";

const KEY = "pinnedcards";

/** The pinned cards by station call, each with its place in the card row (null: none). */
export type Pinned = Record<string, Place | null>;

const isCoordinate = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

/** What was stored, leaving out whatever is not a call with a place or null. */
export function loadPinned(): Pinned {
  const text = readStored(KEY);
  if (text === null) return {};
  try {
    const found: unknown = JSON.parse(text);
    if (typeof found !== "object" || found === null || Array.isArray(found)) return {};
    const out: Pinned = {};
    for (const [call, place] of Object.entries(found)) {
      if (place === null) out[call] = null;
      else if (typeof place === "object" && isCoordinate((place as Place).x) && isCoordinate((place as Place).y))
        out[call] = { x: (place as Place).x, y: (place as Place).y };
    }
    return out;
  } catch {
    return {};
  }
}

/**
 * Remembers the pinned cards: `calls` in pinning order, each with its place in `places` (null if
 * none). Nothing pinned stores nothing.
 */
export function savePinned(calls: readonly string[], places: Readonly<Record<string, Place | undefined>>): void {
  if (calls.length === 0) return removeStored(KEY);
  const out: Pinned = {};
  for (const call of calls) out[call] = places[call] ?? null;
  writeStored(KEY, JSON.stringify(out));
}
