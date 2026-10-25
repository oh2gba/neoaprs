// What is around us, from the station rows already on the page (the "local information" of the APRS specification: what the local APRS infrastructure is, at a glance). Four lists, each in the order of the distance from us (the
// nearest first, a station with no distance last, ties by the call):
//   digipeaters: the stations that repeated packets we heard (a call in the `heard_via` of any station) and the stations whose symbol is a digipeater's, with how many packets they repeated and the range they gave;
//   voice frequencies: every station, object and item that gave one, as the card words it, and who reported it;
//   iGates: the stations that put third-party packets on the air (`gated`), that said so in a capabilities packet (`igate`) or whose symbol is the iGate's;
//   heard direct: the stations heard with no digipeater between us, newest direct packet first among equals: the stations in simplex range.
// These are plain functions of rows; the page's words are the ones of the `nearby.*` messages.
import { t } from "@/i18n";
import { frequencyText } from "@/lib/details";
import { ageText } from "@/lib/format";
import { hasPosition } from "@/lib/stations";
import type { ExtensionValues, StationRow } from "@/protocol/protocol";

/** One line of a list: a station (or the name of a digipeater that was only heard repeating, `row` null), with the lines of words under its call. */
export interface NearbyItem {
  call: string;
  row: StationRow | null;
  lines: string[];
}

/** The table characters a digipeater symbol (`#`) has: the primary table, the alternate one and the overlays 0-9, A-Z (and a-j, the overlay of a compressed position). */
const DIGI_TABLES = /^[/\\0-9A-Za-j]$/;
/** The overlay `I` on the alternate `&` is the iGate (the specification's symbol list). */
const IGATE_TABLE = "I";
const IGATE_CODE = "&";

/** Whether the station draws itself as a digipeater: the code `#` in the primary table (the green star), the alternate table (the star with an overlay: `1#` is a WIDE1 fill-in) or any overlay of it. */
export function isDigipeaterSymbol(row: Pick<StationRow, "symbol_table" | "symbol_code">): boolean {
  return row.symbol_code === "#" && DIGI_TABLES.test(row.symbol_table);
}

/** Whether the station draws itself as an iGate (the overlay `I` on the gateway symbol). */
export function isIgateSymbol(row: Pick<StationRow, "symbol_table" | "symbol_code">): boolean {
  return row.symbol_table === IGATE_TABLE && row.symbol_code === IGATE_CODE;
}

/** A station of the air (not an object or an item, not ourselves): the kind of row the digipeater, iGate and direct lists are made of. */
const isOther = (row: StationRow): boolean => row.kind === "station" && !row.is_me;

/** The nearest first, a missing distance last. */
const nearer = (x: number | null, y: number | null): number => (x === y ? 0 : x === null ? 1 : y === null ? -1 : x - y);

/** Rows nearest first; of equal distance (a missing one is equal to another) `tie` decides, then the call. */
function nearestFirst(rows: StationRow[], tie: (a: StationRow, b: StationRow) => number = () => 0): StationRow[] {
  return rows.sort((a, b) => nearer(a.distance_km, b.distance_km) || tie(a, b) || a.call.localeCompare(b.call));
}

/** The packets each call repeated for us, from the `heard_via` of every station (`?`, a hop that gave no call, is no station and is left out). */
export function repeatedCounts(rows: Iterable<StationRow>): Map<string, number> {
  const counts = new Map<string, number>();
  for (const row of rows) for (const [call, n] of row.heard_via) if (call !== "?") counts.set(call, (counts.get(call) ?? 0) + n);
  return counts;
}

/** The radio range a station gave and how: the PHG range, else the pre-calculated RNG one; null for none. The PHG range is worked out by the daemon from the specification's formula (APRS101, chapter 7,
 * range in miles = sqrt(2 * height in feet * sqrt((power in watts / 10) * (gain as a power ratio / 2)))), in km as `phg.range_km`; the page takes it as it is. */
export function rangeOf(ext: ExtensionValues | null): { km: number; phg: boolean } | null {
  if (ext?.phg != null) return { km: ext.phg.range_km, phg: true };
  return ext?.range_km != null ? { km: ext.range_km, phg: false } : null;
}

export interface Digipeater {
  call: string;
  /** the station; null for a call that was only heard repeating, never sending a packet of its own */
  row: StationRow | null;
  /** the packets we heard that it repeated last (the station we heard is the last hop of the route) */
  repeated: number;
  range: { km: number; phg: boolean } | null;
}

/** The digipeaters: the calls that repeated packets we heard and the stations with a digipeater symbol, nearest first. */
export function digipeaters(source: Iterable<StationRow>): Digipeater[] {
  const rows = [...source];
  const byCall = new Map(rows.map((row) => [row.call, row]));
  const counts = repeatedCounts(rows);
  const calls = new Set([...counts.keys(), ...rows.filter((row) => isOther(row) && isDigipeaterSymbol(row)).map((row) => row.call)]);
  const found: Digipeater[] = [];
  for (const call of calls) {
    const row = byCall.get(call) ?? null;
    if (row !== null && !isOther(row)) continue;
    found.push({ call, row, repeated: counts.get(call) ?? 0, range: row === null ? null : rangeOf(row.extensions) });
  }
  return found.sort((a, b) => nearer(a.row?.distance_km ?? null, b.row?.distance_km ?? null) || a.call.localeCompare(b.call));
}

export interface RangeCircle {
  call: string;
  lat: number;
  lon: number;
  km: number;
}

/** What the map draws for the selected station: its range circle when it is a digipeater of the list (`digipeaters`) that gave a range and has a position, else null (no selection, another station, no range). The station's own timeout does not hide it: a selected station is drawn whatever its age. */
export function rangeCircleOf(source: Iterable<StationRow>, call: string | null): RangeCircle | null {
  if (call === null) return null;
  const found = digipeaters(source).find((one) => one.call === call);
  if (found === undefined || found.row === null || found.range === null || !(found.range.km > 0) || !hasPosition(found.row)) return null;
  return { call, lat: found.row.lat, lon: found.row.lon, km: found.range.km };
}

/** The voice frequencies given: every row (a station, an object, an item) that has one, nearest first. */
export function voiceRows(rows: Iterable<StationRow>): StationRow[] {
  return nearestFirst([...rows].filter((row) => row.frequency !== null));
}

/** The stations that put third-party packets on the air, said they are an iGate, or look like one, nearest first. */
export function gateRows(rows: Iterable<StationRow>): StationRow[] {
  return nearestFirst([...rows].filter((row) => isOther(row) && (row.gated > 0 || row.igate || isIgateSymbol(row))));
}

/** The stations heard direct, nearest first; of equal distance (a missing one is equal to another) the one whose direct packet is the newest. */
export function directRows(rows: Iterable<StationRow>): StationRow[] {
  const time = (row: StationRow): number => (row.last_direct_at === null ? 0 : Date.parse(row.last_direct_at));
  const newest = (a: StationRow, b: StationRow): number => time(b) - time(a);
  return nearestFirst(
    [...rows].filter((row) => isOther(row) && row.heard_direct > 0),
    newest,
  );
}

/** The words under a digipeater's call: what it repeated and the range it gave ("12 packets repeated, PHG range 13 km"); a call heard repeating that never sent a packet of its own says so. */
export function digipeaterLines(d: Digipeater): string[] {
  const parts = [d.repeated > 0 ? t("nearby.repeated", { n: d.repeated }) : t("nearby.symbol_only")];
  if (d.range !== null) parts.push(t(d.range.phg ? "nearby.range_phg" : "nearby.range", { km: Math.round(d.range.km) }));
  return [parts.join(", "), ...(d.row === null ? [t("nearby.not_heard")] : [])];
}

/** The words under a frequency's owner: the frequency as the card words it, and who reported an object or an item. */
export function voiceLines(row: StationRow): string[] {
  const lines = row.frequency === null ? [] : [frequencyText(row.frequency)];
  if (row.kind !== "station" && row.reported_by !== "") lines.push(t("nearby.reported_by", { call: row.reported_by }));
  return lines;
}

/** How a station shows to be an iGate: the third-party packets it put on the air, else that it said so, else its symbol. */
export function gateLines(row: StationRow): string[] {
  if (row.gated > 0) return [t("nearby.gated", { n: row.gated })];
  return [t(row.igate ? "nearby.igate_says" : "nearby.igate_symbol")];
}

/** When a station was last heard direct: "last heard direct 3 min ago". */
export function directLines(row: StationRow, nowMs: number): string[] {
  return row.last_direct_at === null ? [] : [t("nearby.direct_last", { when: t("time.ago", { span: ageText(row.last_direct_at, nowMs) }) })];
}
