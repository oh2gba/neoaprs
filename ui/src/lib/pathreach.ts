// What a path means, hop by hop, for the path builder (components/PathBuilderDialog.vue): its picture (PathDrawing.vue), its number of hops and whether it is sound, and the Hops choice that makes the aliases (PathReach.vue).
// The New-N paradigm of the APRS networks of Europe and North America:
//   WIDEn-N: n is how many hops the path asked for in all, N how many are left; each digipeater that repeats the packet takes one off N, and at 0 none repeats it again. WIDE2-2 is two hops, WIDE2-1 one (or the second after WIDE1-1).
//   WIDE1-1 is one hop that a home (fill-in) digipeater takes as well as a wide-area one; the fill-ins answer WIDE1-1 only. A WIDEn-N with n of 2 or more is taken by the wide-area digipeaters only, N times.
//   An N over n (WIDE1-2, WIDE2-3), an N of 0 (WIDE2-0, and WIDE2 with none) or an n or N out of 1 to 7 is no path: nothing answers it as it is meant, so it is no hop, and the builder refuses it.
//   A named digipeater (OH2RDK-7) is one hop by that one; another alias (RELAY, TRACE3-3, TEMP1-1) one hop by whoever answers it.
//   The hops of a path are the Ns of its WIDE aliases and one for each other element; more than USUAL_HOPS is more than most networks allow (many digipeaters cut or trap an N over 2), which the builder marks without refusing.
// The Hops choice (Direct, 1, 2, 3) is the number of hops in all. The named digipeaters at the start of the path (`lead`: what comes before the aliases at its end) are kept as far as they go, and the hops left are aliases after them:
// with none named, WIDE1-1 first when home digipeaters may take the first hop (WIDE1-1; WIDE1-1,WIDE2-1; WIDE1-1,WIDE2-2) and else wide ones (WIDE2-1; WIDE2-2; WIDE3-3); after a named one always wide ones, as the first hop is
// the named one. Direct is no hop at all. A digipeater picked from the ones heard goes after the named ones and takes the place of an alias hop, so that the path keeps its number of hops (WIDE1-1,WIDE2-1 and OH2RDK-7 is
// OH2RDK-7,WIDE2-1).
import { t } from "@/i18n";
import { isAlias } from "@/lib/chain";

/** The most hops in all that most networks allow; a path of more is marked (amber), not refused. */
export const USUAL_HOPS = 2;
/** The choices of the Hops control: Direct (none) and 1 to 3 hops in all. */
export const REACHES = [0, 1, 2, 3] as const;
/** The largest n and N of a WIDEn-N. */
const MOST_N = 7;
const WIDE = /^WIDE(\d*)(?:-(\d{1,2}))?$/;

/** Who takes a hop: any digipeater (WIDE1-1: a home one too), a wide-area one (WIDEn-N), the one named (a call, or another alias by whoever answers it), or none (an alias that is no path). */
export type HopKind = "any" | "wide" | "named" | "none";

/** One element of a path as the picture draws it: its text, the hops it makes (one node each), and what is wrong with it ("" for nothing). */
export interface PathPart {
  text: string;
  kinds: HopKind[];
  /** the number of the first of its hops in the path, from 1 */
  first: number;
  /** n and N of a WIDEn-N that is sound, for its hover title; null for anything else */
  wide: { n: number; left: number } | null;
  problem: string;
}

/** A path as the builder shows it: its parts, its hops in all, and whether it is sound (`ok`), more than the network usually allows (`many`) or impossible (`bad`), with the reason. */
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

/** The path as the Hops choice reads it: the elements before the aliases at its end (the named digipeaters), and those aliases. */
export function splitPath(hops: readonly string[]): { lead: string[]; tail: string[] } {
  let at = hops.length;
  while (at > 0 && isAlias(hops[at - 1] ?? "")) at--;
  return { lead: hops.slice(0, at), tail: hops.slice(at) };
}

/** The aliases for `count` hops: WIDE1-1 first when `home` digipeaters may take the first hop, the rest by wide-area digipeaters. */
export function aliasesFor(count: number, home: boolean): string[] {
  if (count <= 0) return [];
  if (home) return ["WIDE1-1", ...aliasesFor(count - 1, false)];
  const n = Math.min(count, MOST_N);
  return [n === 1 ? "WIDE2-1" : `WIDE${n}-${n}`];
}

/** The path with `count` hops in all: its named digipeaters as far as they go, then aliases for the hops left (WIDE1-1 first only when nothing is named and `home` is on). */
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

/** The path with `call` after its named digipeaters, in the place of one of its alias hops: as many hops in all as before, or one more when it had no alias hop to give. */
export function withCall(hops: readonly string[], call: string): string[] {
  const lead = [...splitPath(hops).lead, call];
  const left = Math.max(0, hopTotal(hops) - hopTotal(lead));
  return [...lead, ...aliasesFor(left, false)];
}

/** The Hops choice a path is: its hops in all when it is sound and has no more than three; null for any other. */
export function reachOf(hops: readonly string[]): number | null {
  const meaning = meaningOf(hops);
  return meaning.level !== "bad" && meaning.hops <= REACHES[REACHES.length - 1] ? meaning.hops : null;
}

/** Whether a path lets home digipeaters take its first hop: true when it starts with WIDE1-1, false when it starts with a WIDEn-N of n 2 or more, null when it says nothing of it (none, a call, another alias). */
export function homeFirst(hops: readonly string[]): boolean | null {
  const first = hops[0];
  if (first === undefined) return null;
  const wide = partOf(first).wide;
  return wide === null ? null : wide.n === 1;
}
