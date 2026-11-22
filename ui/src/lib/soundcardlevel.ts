// The receive level of a Sound card radio as the page shows it, the parts that are not a
// component: the zones of the level on Direwolf's own scale, and where it is on its bar
// (components/SoundCardLevel.vue). Every number comes from the daemon through LIMITS
// (neoaprs/direwolf.py): about 50 is most stations, over `levelHigh` Direwolf itself calls too
// high (red: the sound card clips); under the good band it is low, which between packets it
// mostly is.
import type { Zone } from "@/lib/hflevel";
import { LIMITS } from "@/protocol/lists";

const { levelMax, levelHigh, levelGood } = LIMITS.soundCard;

/**
 * The zone of a level: too high by Direwolf's own limit (red), in the good band round 50, low
 * under it (no packet now, squelch closed, radio off), else between the two.
 */
export function levelZone(level: number): Zone {
  if (level > levelHigh) return "clip";
  if (level < levelGood[0]) return "low";
  return level <= levelGood[1] ? "good" : "high";
}

/** Where a level is on the bar, 0 to 100 percent. */
export const levelPercent = (level: number): number => Math.max(0, Math.min(100, (level / levelMax) * 100));

/** The good band as the parts of the bar it covers, in percent from the left: [from, to]. */
export const GOOD_PERCENT: readonly [number, number] = [levelPercent(levelGood[0]), levelPercent(levelGood[1])];

/** A level as the number the page shows; null (its Direwolf is not running) is a dash. */
export const levelText = (level: number | null): string => (level === null ? "–" : String(level));
