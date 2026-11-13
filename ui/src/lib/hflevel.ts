// The HF radio's levels as the page shows them, the parts that are not a component: the zones of the receive level and where it is on its bar (the scope's fold, components/HfScope.vue), and the gain and the peak of the
// Transmit level row (components/HfLevelRow.vue) as text. Every number is the daemon's, through LIMITS (neoaprs/mercuryscope.py).
import { LIMITS } from "@/protocol/lists";

const { levelMinDbfs, levelMaxDbfs, levelGoodDbfs, peakClipDbfs } = LIMITS.scope;

export type Zone = "low" | "good" | "high" | "clip";

/** The zone of a receive level in dBFS: under the good range (too little audio for the modem to work with), in it, over it, and near full scale, where the sound card clips. */
export function levelZone(level: number): Zone {
  if (level < levelGoodDbfs[0]) return "low";
  if (level <= levelGoodDbfs[1]) return "good";
  return level < -10 ? "high" : "clip";
}

/** Where a level is on the bar, 0 to 100 percent. */
export function levelPercent(level: number): number {
  const span = levelMaxDbfs - levelMinDbfs;
  return Math.max(0, Math.min(100, ((level - levelMinDbfs) / span) * 100));
}

/** The good range as the parts of the bar it covers, in percent from the left: [from, to]. */
export const GOOD_PERCENT: readonly [number, number] = [levelPercent(levelGoodDbfs[0]), levelPercent(levelGoodDbfs[1])];

/** A level or a peak as the number the page shows, "-38"; the minus is the one of the keyboard (the same in every language); null (nothing yet) is a dash. */
export function dbText(value: number | null): string {
  return value === null ? "–" : String(value);
}

/** A gain as the number on the Transmit level control: "+3", "0", "-6". */
export function gainText(db: number): string {
  return db > 0 ? `+${db}` : String(db);
}

/** Whether a transmission peaking at this many dBFS clips in the sound card. */
export const clips = (peak: number | null): boolean => peak !== null && peak >= peakClipDbfs;
