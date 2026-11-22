// What a path means, hop by hop, for the path builder (components/PathBuilderDialog.vue): its
// picture, its number of hops, whether it is sound, and the Hops choice that makes the aliases.
// The New-N paradigm of the APRS networks of Europe and North America:
//   WIDEn-N: n is how many hops were asked for in all, N how many are left; each digipeater that
//   repeats the packet takes one off N, and at 0 none repeats it again.
//   WIDE1-1 is one hop that a home (fill-in) digipeater takes as well as a wide-area one. A WIDEn-N
//   with n of 2 or more is taken by the wide-area digipeaters only.
//   An N over n (WIDE1-2), an N of 0 (WIDE2-0, or WIDE2 alone) or an n or N outside 1 to 7 is no
//   path: nothing answers it as meant, so it is no hop and the builder refuses it.
//   A named digipeater (OH2RDK-7) is one hop by that one; another alias (RELAY, TRACE3-3) is one
//   hop by whoever answers it.
//   The hops of a path are the Ns of its WIDE aliases and one for each other element; more than
//   USUAL_HOPS is more than most networks allow, which the builder marks without refusing.
// The Hops choice (Direct, 1, 2, 3) is the number of hops in all. The named digipeaters at the
// start of the path (`lead`) are kept as far as they go, and the hops left are aliases after them:
// with none named, WIDE1-1 first when home digipeaters may take the first hop, else wide ones;
// after a named one always wide ones. Direct is no hop at all. A digipeater picked from the heard
// ones goes after the named ones in place of an alias hop, keeping the number of hops
// (WIDE1-1,WIDE2-1 and OH2RDK-7 become OH2RDK-7,WIDE2-1).
import { t } from "@/i18n";
import { isAlias } from "@/lib/chain";

/** The most hops in all that most networks allow; a longer path is marked, not refused. */
export const USUAL_HOPS = 2;
/** The choices of the Hops control: Direct (none) and 1 to 3 hops in all. */
export const REACHES = [0, 1, 2, 3] as const;
/** The largest n and N of a WIDEn-N. */
const MOST_N = 7;
const WIDE = /^WIDE(\d*)(?:-(\d{1,2}))?$/;

/** Who takes a hop: any digipeater, a wide-area one, the one named, or none (an alias that is no
 * path). */
export type HopKind = "any" | "wide" | "named" | "none";

/** One element of a path as the picture draws it: its text, its hops, and what is wrong with it (""
 * for nothing). */
export interface PathPart {
  text: string;
  kinds: HopKind[];
  /** The number of its first hop in the path, from 1. */
  first: number;
  /** n and N of a sound WIDEn-N, for its hover title; null for anything else. */
  wide: { n: number; left: number } | null;
  problem: string;
}

/** A path as the builder shows it: its parts, its hops in all, and whether it is sound (`ok`),
 * longer than usual (`many`) or impossible (`bad`), with the reason. */
export interface PathMeaning {
  parts: PathPart[];
  hops: number;
  level: "ok" | "many" | "bad";
  reason: string;
}

/** One element of a path, with its hops numbered from `first`. */
function partOf(text: string, first = 1): PathPart {
  const found = WIDE.exec(text);
  if (found === null) return { text, kinds: ["named"], first, wide: null, problem: "" };
  const n = Number(found[1] ?? "");
  const left = Number(found[2] ?? "0");
  const problem =
    found[1] === "" || n < 1 || n > MOST_N || left > MOST_N
      ? t("pathbuilder.bad.shape", { alias: text })
      : left === 0
        ? t("pathbuilder.bad.used_up", { alias: text })
        : left > n
          ? t("pathbuilder.bad.more_left", { alias: text, n, left })
          : "";
  if (problem !== "") return { text, kinds: ["none"], first, wide: null, problem };
  const kinds: HopKind[] = n === 1 ? ["any"] : Array.from({ length: left }, () => "wide" as const);
  return { text, kinds, first, wide: { n, left }, problem };
}

const hopsOfPart = (part: PathPart): number => part.kinds.filter((kind) => kind !== "none").length;

/** What a path means: its parts with their hops numbered, its hops in all, and its soundness. */
export function meaningOf(hops: readonly string[]): PathMeaning {
  const parts: PathPart[] = [];
  let next = 1;
  for (const hop of hops) {
    const part = partOf(hop, next);
    parts.push(part);
    next += hopsOfPart(part);
  }
  const total = next - 1;
  const bad = parts.find((part) => part.problem !== "");
  if (bad !== undefined) return { parts, hops: total, level: "bad", reason: bad.problem };
  if (total > USUAL_HOPS) return { parts, hops: total, level: "many", reason: t("pathbuilder.many", { n: total, most: USUAL_HOPS }) };
  return { parts, hops: total, level: "ok", reason: "" };
}

/** The hops of a path in all. */
const hopTotal = (hops: readonly string[]): number => meaningOf(hops).hops;

/** The path as the Hops choice reads it: the named digipeaters before the aliases at its end, and
 * those aliases. */
export function splitPath(hops: readonly string[]): { lead: string[]; tail: string[] } {
  let at = hops.length;
  while (at > 0 && isAlias(hops[at - 1] ?? "")) at--;
  return { lead: hops.slice(0, at), tail: hops.slice(at) };
}

/** The aliases for `count` hops: WIDE1-1 first when `home` digipeaters may take the first hop, then
 * wide-area ones. */
export function aliasesFor(count: number, home: boolean): string[] {
  if (count <= 0) return [];
  if (home) return ["WIDE1-1", ...aliasesFor(count - 1, false)];
  const n = Math.min(count, MOST_N);
  return [n === 1 ? "WIDE2-1" : `WIDE${n}-${n}`];
}

/** The path with `count` hops in all: its named digipeaters, then aliases for the hops left
 * (WIDE1-1 first only if nothing is named and `home` is on). */
export function withReach(hops: readonly string[], count: number, home: boolean): string[] {
  const kept: string[] = [];
  let used = 0;
  for (const hop of splitPath(hops).lead) {
    const more = hopsOfPart(partOf(hop));
    if (used + more > count) break;
    kept.push(hop);
    used += more;
  }
  return [...kept, ...aliasesFor(count - used, home && kept.length === 0)];
}

/** The path with `call` after its named digipeaters, replacing an alias hop: the same hops in all,
 * or one more if it had none to give. */
export function withCall(hops: readonly string[], call: string): string[] {
  const lead = [...splitPath(hops).lead, call];
  const left = Math.max(0, hopTotal(hops) - hopTotal(lead));
  return [...lead, ...aliasesFor(left, false)];
}

/** The Hops choice a path is: its hops in all when it is sound and at most three; else null. */
export function reachOf(hops: readonly string[]): number | null {
  const meaning = meaningOf(hops);
  return meaning.level !== "bad" && meaning.hops <= REACHES[REACHES.length - 1] ? meaning.hops : null;
}

/** Whether a path lets home digipeaters take its first hop: true if it starts with WIDE1-1, false
 * if with a WIDEn-N of n 2 or more, null if it says nothing of it. */
export function homeFirst(hops: readonly string[]): boolean | null {
  const first = hops[0];
  if (first === undefined) return null;
  const wide = partOf(first).wide;
  return wide === null ? null : wide.n === 1;
}
