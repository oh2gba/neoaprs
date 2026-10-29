// What the path builder (components/PathBuilder.vue) offers, worked out from the station rows already on the page; it has no command of its own. The aliases (Direct to 3 hops in all, WIDE1-1 first or not) and what a path
// means hop by hop are lib/pathreach.ts; here are the digipeaters to name:
//   The first hop through a digipeater we hear: the digipeaters of the Nearby tab (lib/nearby.ts) that we hear direct, a call that was the last hop of a route we heard (the station whose transmission reached us) or a station with a
//   digipeater's symbol whose packets came direct; the one that repeated the most packets for us first, then the one heard direct last, then the nearest.
//   A hop after a digipeater: the digipeaters next to it in the routes the daemon counted for the stations (each station's best route, its latest route and the two routes the map draws), the one seen next to it for the most stations first.
//   A route heard A → B says that B hears A; a path sent B,A needs A to hear B, and the daemon's suggested path takes the two for the same (it turns a route round), so a pair counts either way round.
//   As its packets come: the best route of a station turned round, the daemon's `suggested_path` (a hop with no call in the route makes it WIDE1-1,WIDE2-1).
// Choices are offered for the first SUGGESTED_HOPS hops, and only after a hop that is a call: no one station answers an alias (WIDE2-1), so nothing is known of who hears it. A path is held as its hops; none at all is DIRECT in the field it goes to.
import { t } from "@/i18n";
import { isAlias } from "@/lib/chain";
import { DIRECT, callList, parsePathSetting, validCall } from "@/lib/calls";
import { digipeaters } from "@/lib/nearby";
import { routeHops } from "@/lib/routeline";
import { LIMITS } from "@/protocol/lists";
import type { StationRow } from "@/protocol/protocol";

/** How many hops the builder has choices for; more are typed. */
const SUGGESTED_HOPS = 3;

/** One digipeater offered as the next hop: how often it was seen (packets it repeated for us, for the first hop; stations whose routes have it next to the hop before, for a later one), when it was last heard direct and how far it is. */
export interface HopChoice {
  call: string;
  count: number;
  at: string | null;
  km: number | null;
}

/** The hops of a path as a field writes it: DIRECT (and an empty field) is none. */
export function hopsOf(text: string): string[] {
  const calls = callList(text);
  return calls.length === 1 && calls[0] === DIRECT ? [] : calls;
}

/** The path as the field takes it: the hops separated by commas, DIRECT for none. */
export function pathOf(hops: readonly string[]): string {
  return hops.length === 0 ? DIRECT : hops.join(",");
}

/** What is wrong with a path for the fields that take calls separated by commas, at most as many as a frame carries, or DIRECT (a station's path, the path of an object): the reason, "" for nothing. */
export function callsProblem(text: string): string {
  return parsePathSetting(text) === null ? t("route.calls_hint", { max: LIMITS.path.maxCalls }) : "";
}

/** The hops typed into the builder's own field (one, or several separated by commas), as a path writes them; null when one of them is no call or alias (DIRECT is none: it stands alone). */
export function typedHops(text: string): string[] | null {
  const calls = callList(text);
  return calls.length > 0 && calls.every((call) => call !== DIRECT && validCall(call)) ? calls : null;
}

const time = (iso: string | null): number => (iso === null ? 0 : Date.parse(iso));
const nearer = (x: number | null, y: number | null): number => (x === y ? 0 : x === null ? 1 : y === null ? -1 : x - y);

/** The digipeaters we hear direct, the most useful first. */
export function firstHops(rows: Iterable<StationRow>): HopChoice[] {
  return digipeaters(rows)
    .filter((digi) => digi.repeated > 0 || (digi.row?.heard_direct ?? 0) > 0)
    .map((digi) => ({ call: digi.call, count: digi.repeated, at: digi.row?.last_direct_at ?? null, km: digi.row?.distance_km ?? null }))
    .sort((a, b) => b.count - a.count || time(b.at) - time(a.at) || nearer(a.km, b.km) || a.call.localeCompare(b.call));
}

/** The routes counted for a station, each as its hops in order. */
function routesOf(row: StationRow): string[][] {
  const texts = [row.best_route, row.last_route].map((text) => routeHops(text)?.hops ?? []);
  return [...texts, ...row.route_marks.map((mark) => mark.hops)].filter((hops) => hops.length > 1);
}

/** For each digipeater, the digipeaters seen next to it in the routes and for how many stations. */
function neighbours(rows: Iterable<StationRow>): Map<string, Map<string, number>> {
  const found = new Map<string, Map<string, number>>();
  const count = (a: string, b: string): void => {
    const near = found.get(a) ?? new Map<string, number>();
    near.set(b, (near.get(b) ?? 0) + 1);
    found.set(a, near);
  };
  for (const row of rows) {
    const pairs = new Set<string>();
    for (const hops of routesOf(row))
      for (let i = 1; i < hops.length; i++) {
        const [a, b] = [hops[i - 1] ?? "?", hops[i] ?? "?"];
        if (a !== "?" && b !== "?" && a !== b) pairs.add([a, b].sort().join(","));
      }
    for (const pair of pairs) {
      const [a = "", b = ""] = pair.split(",");
      count(a, b);
      count(b, a);
    }
  }
  return found;
}

/** The digipeaters seen next to `after` in the routes, the most often seen first; the calls already in the path and our own are left out. */
export function nextHops(source: Iterable<StationRow>, after: string, used: readonly string[]): HopChoice[] {
  const rows = [...source];
  const byCall = new Map(rows.map((row) => [row.call, row]));
  const skip = new Set([...used, ...rows.filter((row) => row.is_me).map((row) => row.call)]);
  return [...(neighbours(rows).get(after) ?? new Map<string, number>())]
    .filter(([call]) => !skip.has(call))
    .map(([call, count]) => ({ call, count, at: byCall.get(call)?.last_direct_at ?? null, km: byCall.get(call)?.distance_km ?? null }))
    .sort((a, b) => b.count - a.count || nearer(a.km, b.km) || a.call.localeCompare(b.call));
}

/** What the builder offers for the next hop of `hops`: the digipeaters we hear for the first, those next to the last hop for a later one (`after`); null when it offers none (enough hops, or an alias last). */
export function choicesFor(rows: Iterable<StationRow>, hops: readonly string[]): { after: string | null; choices: HopChoice[] } | null {
  if (hops.length >= SUGGESTED_HOPS) return null;
  const last = hops[hops.length - 1];
  if (last === undefined) return { after: null, choices: firstHops(rows) };
  return isAlias(last) ? null : { after: last, choices: nextHops(rows, last, hops) };
}

/** The station's best route turned round, as hops (none for a station heard direct); null when no route of it is known. */
export function reversedRoute(rows: ReadonlyMap<string, StationRow>, call: string): string[] | null {
  const path = rows.get(call)?.suggested_path ?? null;
  return path === null ? null : callList(path);
}
