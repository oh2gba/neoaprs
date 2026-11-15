// The receive level of a Sound card radio as the page shows it, the parts that are not a component: the zones of the level of the latest packet heard, on Direwolf's own scale, and where it is on its bar
// (components/SoundCardLevel.vue). Every number is the daemon's, through LIMITS (neoaprs/direwolf.py): about 50 is most stations, under `levelLow` and over `levelHigh` Direwolf itself calls too low and too high.
import type { Zone } from "@/lib/hflevel";
import { LIMITS } from "@/protocol/lists";

const { levelMax, levelLow, levelHigh, levelGood } = LIMITS.soundCard;

/** The zone of a level: too low or too high by Direwolf's own limits (red), in the good band round 50, else between the two. */
export function levelZone(level: number): Zone {
  if (level < levelLow || level > levelHigh) return "clip";
  if (level < levelGood[0]) return "low";
  return level <= levelGood[1] ? "good" : "high";
}

/** Where a level is on the bar, 0 to 100 percent. */
export const levelPercent = (level: number): number => Math.max(0, Math.min(100, (level / levelMax) * 100));

/** The good band as the parts of the bar it covers, in percent from the left: [from, to]. */
export const GOOD_PERCENT: readonly [number, number] = [levelPercent(levelGood[0]), levelPercent(levelGood[1])];

/** A level as the number the page shows; null (no packet heard yet) is a dash. */
export const levelText = (level: number | null): string => (level === null ? "–" : String(level));
