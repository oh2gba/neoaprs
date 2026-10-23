// How the packets of a station reached us, as the page words it: the counts of the card and the path the daemon suggests to send by. The daemon works the routes out (neoaprs/route.py); these only format.
import { ageSeconds, ageText } from "@/lib/format";
import type { StationRow } from "@/protocol/protocol";

type Counts = Pick<StationRow, "heard_direct" | "heard_via" | "heard_gated">;
type Direct = Pick<StationRow, "heard_direct" | "heard_via" | "heard_gated" | "last_direct_at">;

/** A station heard direct within this long has a ring on its marker. */
const DIRECT_RECENT_SEC = 3600;
type Suggestion = Pick<StationRow, "best_route" | "suggested_path">;

/** A station we heard a packet from, in words: `?` is a repeater that put no call in the packet (WIDE1 and the like). */
export function viaName(call: string): string {
  return call === "?" ? "an unnamed repeater" : call;
}

/** "12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3, 2 from the internet"; "-" before any packet is counted. */
export function heardText(row: Counts): string {
  const parts: string[] = [];
  if (row.heard_direct > 0) parts.push(`${row.heard_direct} direct`);
  for (const [call, count] of row.heard_via) parts.push(`${count} via ${viaName(call)}`);
  if (row.heard_gated > 0) parts.push(`${row.heard_gated} from the internet`);
  return parts.length === 0 ? "-" : parts.join(", ");
}

/** A path to send by as the path field shows it: an empty one is direct. */
export function pathWords(path: string): string {
  return path === "" ? "direct" : path;
}

/** The route most packets came by and what is suggested from it: "via OH2RCH-2; send by OH2RCH-2", "direct; send direct", "via ? → OH2RCH-2; unknown repeater, send by WIDE1-1,WIDE2-1". */
export function bestText(row: Suggestion): string {
  if (row.best_route === "") return "-";
  if (row.suggested_path === null) return row.best_route;
  const unknown = row.best_route.includes("?") ? "unknown repeater, " : "";
  return `${row.best_route}; ${unknown}${row.suggested_path === "" ? "send direct" : `send by ${row.suggested_path}`}`;
}

/** The share of the packets counted for the station that came direct, in whole percent; null before any packet is counted. */
export function directShare(row: Counts): number | null {
  const counted = row.heard_direct + row.heard_gated + row.heard_via.reduce((sum, [, count]) => sum + count, 0);
  return counted === 0 ? null : Math.round((100 * row.heard_direct) / counted);
}

/** Whether a packet of the station was heard direct within the last hour. */
export function heardDirectRecently(row: Pick<StationRow, "last_direct_at">, nowMs: number): boolean {
  return row.last_direct_at !== null && ageSeconds(row.last_direct_at, nowMs) <= DIRECT_RECENT_SEC;
}

/** The Direct column: when the station was last heard direct and the share of its packets that came direct, "5 min, 40 %"; "-" for a station never heard direct. */
export function directText(row: Direct, nowMs: number): string {
  if (row.last_direct_at === null) return "-";
  const share = directShare(row);
  return share === null ? ageText(row.last_direct_at, nowMs) : `${ageText(row.last_direct_at, nowMs)}, ${share} %`;
}

/** The same for the card, in words: "heard direct 5 min ago, 40 % of its packets"; "never heard direct" for a station that was not. */
export function directWords(row: Direct, nowMs: number): string {
  if (row.last_direct_at === null) return "not heard direct";
  const share = directShare(row);
  return `heard direct ${ageText(row.last_direct_at, nowMs)} ago${share === null ? "" : `, ${share} % of its packets`}`;
}
