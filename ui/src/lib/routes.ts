// How the packets of a station reached us, as the page words it: the counts of the card and the path the daemon suggests to send by. The daemon works the routes out (neoaprs/route.py); these only format.
import { t } from "@/i18n";
import { ageSeconds } from "@/lib/format";
import { routeHops } from "@/lib/routeline";
import { hasPosition } from "@/lib/stations";
import type { StationRow } from "@/protocol/protocol";

type Counts = Pick<StationRow, "heard_direct" | "heard_via" | "heard_rf_gated" | "heard_is">;

/** A station heard direct within this long has a ring on its marker. */
const DIRECT_RECENT_SEC = 3600;
type Suggestion = Pick<StationRow, "best_route" | "suggested_path">;

/** A station we heard a packet from, in words: `?` is a repeater that put no call in the packet (WIDE1 and the like). */
export function viaName(call: string): string {
  return call === "?" ? t("route.unnamed_repeater") : call;
}

/** A route as the daemon writes it ("direct", "via OH2RCH-2", "via OH7JHF-1 (internet) → OH2RCH-3"), in the words of the page's language. `unnamed` is how a repeater that put no call in the packet (`?`) is written; text that is no route stays as it is. */
export function routeWords(text: string, unnamed = "?"): string {
  if (text === "direct") return t("route.direct");
  const route = routeHops(text);
  if (route === null) return text;
  const gate = route.gate === null ? [] : [t("route.hop.gate", { call: route.gate })];
  return t("route.via", { hops: [...gate, ...route.hops.map((hop) => (hop === "?" ? unnamed : hop))].join(" → ") });
}

/** "12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3, 2 via an iGate, 5 over the internet"; "-" before any packet is counted. */
export function heardText(row: Counts): string {
  const parts: string[] = [];
  if (row.heard_direct > 0) parts.push(t("route.heard.direct", { n: row.heard_direct }));
  for (const [call, count] of row.heard_via) parts.push(t("route.heard.via", { n: count, name: viaName(call) }));
  if (row.heard_rf_gated > 0) parts.push(t("route.heard.gated", { n: row.heard_rf_gated }));
  if (row.heard_is > 0) parts.push(t("route.heard.internet", { n: row.heard_is }));
  return parts.length === 0 ? "-" : parts.join(", ");
}

/** A path to send by as the path field shows it: an empty one is direct. */
export function pathWords(path: string): string {
  return path === "" ? t("route.direct") : path;
}

/** The route most packets came by and what is suggested from it: "via OH2RCH-2; send by OH2RCH-2", "direct; send direct", "via ? → OH2RCH-2; unknown repeater, send by WIDE1-1,WIDE2-1". */
export function bestText(row: Suggestion): string {
  if (row.best_route === "") return "-";
  const route = routeWords(row.best_route);
  if (row.suggested_path === null) return route;
  const unknown = row.best_route.includes("?");
  if (row.suggested_path === "") return t(unknown ? "route.best.unknown_send_direct" : "route.best.send_direct", { route });
  return t(unknown ? "route.best.unknown_send_by" : "route.best.send_by", { route, path: row.suggested_path });
}

/** Whether a packet of the station was heard direct within the last hour. */
export function heardDirectRecently(row: Pick<StationRow, "last_direct_at">, nowMs: number): boolean {
  return row.last_direct_at !== null && ageSeconds(row.last_direct_at, nowMs) <= DIRECT_RECENT_SEC;
}

/** Whether a station (not our own, not an object) was heard direct at some time: its call has the green check mark. */
export function heardDirect(row: Pick<StationRow, "kind" | "is_me" | "last_direct_at">): boolean {
  return row.kind === "station" && !row.is_me && row.last_direct_at !== null;
}

/** The way of the latest packet written for a person: "direct", "via OH2RCH-2", "via a repeater → OH2RCH-2" (a repeater that put no call in the packet), "via OH7JHF-1 (internet)"; before a route is known, the way most of its packets came by; null when none is known (a station known from the internet alone has no route). */
export function reachedText(row: Pick<StationRow, "last_route" | "heard_direct" | "heard_via" | "heard_rf_gated">): string | null {
  if (row.last_route !== "") return routeWords(row.last_route, t("route.hop.repeater"));
  if (row.heard_direct > 0) return t("route.direct");
  const first = row.heard_via[0];
  if (first !== undefined) return t("route.via", { hops: first[0] === "?" ? t("route.hop.repeater") : first[0] });
  return row.heard_rf_gated > 0 ? t("route.via_internet") : null;
}

/** How the latest packet that came over the internet got there, in one plain line: "Heard by iGate OH2GW-10 via OH2RCH-2", "Heard by iGate OH2GW-10 directly", "Sent from an internet app, never on the air"; an iGate whose place is not known says so (the map's line ends at the last hop that has one). Null when it is not known. */
export function internetText(row: Pick<StationRow, "internet_reach">, stations: ReadonlyMap<string, StationRow>): string | null {
  const reach = row.internet_reach;
  if (reach === null) return null;
  if (reach.kind === "app") return t("route.reach.app");
  const found = stations.get(reach.igate);
  const placed = found !== undefined && hasPosition(found);
  const igate = reach.igate;
  if (reach.hops.length === 0) return t(placed ? "route.reach.igate_direct" : "route.reach.igate_direct_unplaced", { igate });
  const hops = reach.hops.map((hop) => (hop === "?" ? t("route.hop.repeater") : hop)).join(" → ");
  return t(placed ? "route.reach.igate_via" : "route.reach.igate_via_unplaced", { igate, hops });
}
