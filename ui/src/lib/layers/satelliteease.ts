// A satellite's mark eased onto the points of a new message instead of hopping: the new points put
// it a little off where the last ones had it (each is a chord of the orbit), so the difference is
// eased away as lib/layers/glide.ts eases a thing onto its new report.
import { EASE_MS, easeOut, type LonLat } from "@/lib/layers/glide";
import { positionAt, wrapLon } from "@/lib/layers/satellite";
import type { SatelliteMark } from "@/protocol/protocol";

/** What is eased away from `fromMs` on. */
export interface MarkEase {
  offset: LonLat;
  fromMs: number;
}

/** A difference further than this (degrees) is jumped. */
const JUMP_DEG = 0.5;

/** Where a mark is drawn at `nowMs`: where its points put it, and what is left of its ease. */
export function easedAt(at: LonLat, ease: MarkEase | undefined, nowMs: number): LonLat {
  if (!ease) return at;
  const left = 1 - easeOut((nowMs - ease.fromMs) / EASE_MS);
  if (left <= 0) return at;
  return [wrapLon(at[0] + ease.offset[0] * left), at[1] + ease.offset[1] * left];
}

/** The eases after a new message at `nowMs`: each mark from where it is drawn onto its new points. */
export function nextEases(
  was: readonly SatelliteMark[],
  wasEases: ReadonlyMap<number, MarkEase>,
  now: readonly SatelliteMark[],
  nowMs: number,
): Map<number, MarkEase> {
  const eases = new Map<number, MarkEase>();
  for (const mark of now) {
    const old = was.find((one) => one.id === mark.id);
    const before = old ? positionAt(old.points, nowMs) : null;
    const after = positionAt(mark.points, nowMs);
    if (!before || !after) continue;
    const shown = easedAt(before, wasEases.get(mark.id), nowMs);
    const offset: LonLat = [wrapLon(shown[0] - after[0]), shown[1] - after[1]];
    if (Math.abs(offset[0]) <= JUMP_DEG && Math.abs(offset[1]) <= JUMP_DEG)
      eases.set(mark.id, { offset, fromMs: nowMs });
  }
  return eases;
}
