// The station rows as the page lists and draws them: which have a position, the filter and the
// table order.
import { t } from "@/i18n";
import { qrzUrl } from "@/lib/calls";
import { onAir } from "@/lib/channels";
import { symbolText } from "@/lib/symbols";
import { isWeatherStation } from "@/lib/weather";
import type { StationRow } from "@/protocol/protocol";

type Positioned = StationRow & { lat: number; lon: number };

export function hasPosition(row: StationRow): row is Positioned {
  return row.lat !== null && row.lon !== null;
}

/** Whether a station's Message is offered: not ourselves, not our objects or items, and not one the
 * daemon says cannot be messaged. */
export function canMessage(row: Pick<StationRow, "kind" | "can_message" | "is_me" | "own">): boolean {
  return row.kind === "station" && row.can_message && !row.is_me && !row.own;
}

/** Whether a station's Forget is offered: not ourselves, and not our own object or item (those are
 * killed instead). */
export function canForget(row: Pick<StationRow, "is_me" | "own">): boolean {
  return !row.is_me && !row.own;
}

/** The directed queries the station panel offers (the daemon's command `query`): `?APRSP` position,
 * `?APRSS` status, `?APRSD` heard direct, `?APRST` route, `?WX?` weather (weather stations only).
 */
const QUERY_KINDS = ["position", "status", "heard", "trace", "weather"] as const;
export type QueryKind = (typeof QUERY_KINDS)[number];

/** The buttons of the station panel, in order: Message and the queries where the card has Message
 * (Ask for weather only to a weather station), Show, Copy and QRZ for any station, Forget where
 * the card has it. */
export type PanelItem = "message" | `ask_${QueryKind}` | MenuItem | "forget";
/** What a row's menu (right-click, long press) offers: Copy call, Show on map (or its card) and
 * QRZ. */
export type MenuItem = "copy" | "show" | "qrz";

export function menuItems(row: Pick<StationRow, "call" | "kind">): MenuItem[] {
  return row.kind === "station" && qrzUrl(row.call) !== null ? ["copy", "show", "qrz"] : ["copy", "show"];
}

export function panelItems(row: StationRow): PanelItem[] {
  const kinds = QUERY_KINDS.filter((kind) => kind !== "weather" || isWeatherStation(row));
  const items: PanelItem[] = canMessage(row) ? ["message", ...kinds.map((k): PanelItem => `ask_${k}`)] : [];
  items.push("show", "copy");
  if (row.kind === "station" && qrzUrl(row.call) !== null) items.push("qrz");
  if (canForget(row)) items.push("forget");
  return items;
}

/** Whether a panel item talks to the station (Message and the queries) or only looks at it. */
export function talksTo(item: PanelItem): boolean {
  return item === "message" || item.startsWith("ask_");
}

/** The query a panel item sends, null for an item that is not one. */
export function itemQuery(item: PanelItem): QueryKind | null {
  return QUERY_KINDS.find((kind) => `ask_${kind}` === item) ?? null;
}

/** The words of a panel or menu item: Show is "Open its card" for a station with no position, and
 * an armed Forget is "Really forget?". */
export function itemLabel(item: PanelItem, row: StationRow, armed: boolean): string {
  switch (item) {
    case "message":
      return t("station.card.message");
    case "show":
      return hasPosition(row) ? t("station.menu.show_map") : t("station.menu.show_card");
    case "copy":
      return t("station.menu.copy");
    case "qrz":
      return t("station.menu.qrz");
    case "forget":
      return armed ? t("station.menu.forget_sure") : t("station.menu.forget");
    case "ask_position":
      return t("station.menu.ask_position");
    case "ask_status":
      return t("station.menu.ask_status");
    case "ask_heard":
      return t("station.menu.ask_heard");
    case "ask_trace":
      return t("station.menu.ask_trace");
    case "ask_weather":
      return t("station.menu.ask_weather");
  }
}

export type SortKey =
  | "call"
  | "distance_km"
  | "bearing_deg"
  | "last_heard"
  | "last_position_at"
  | "last_direct_at"
  | "packets"
  | "last_path"
  | "temp_c";
export interface Sort {
  key: SortKey;
  /** 1 ascending, -1 descending. */
  dir: 1 | -1;
}

/** The order a column starts in when clicked: call and path from A, the rest (distance, age,
 * packets) nearest, newest, most first. */
export function firstDirection(key: SortKey): 1 | -1 {
  return key === "last_heard" ||
    key === "last_position_at" ||
    key === "last_direct_at" ||
    key === "packets" ||
    key === "temp_c"
    ? -1
    : 1;
}

function sortValue(row: StationRow, key: SortKey): string | number | null {
  switch (key) {
    case "call":
      return row.call;
    case "last_path":
      return row.last_path.join(",");
    case "temp_c":
      return row.weather?.temp_c ?? null;
    case "last_heard":
    case "last_position_at":
    case "last_direct_at":
      return row[key] === null ? null : Date.parse(row[key]);
    default:
      return row[key];
  }
}

/** Two values in ascending order, a missing one (null) last whichever way the order goes (`dir` is
 * applied by the caller to present values only). */
function compare(a: string | number | null, b: string | number | null, dir: 1 | -1): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  if (typeof a === "string" && typeof b === "string") return dir * a.localeCompare(b, "en", { numeric: true });
  return dir * (Number(a) - Number(b));
}

export type Direct = Pick<StationRow, "last_direct_at"> & Partial<Pick<StationRow, "last_direct_any_at">>;

/** When a packet of the station was last heard direct on any radio, HF too. Against a daemon that
 * does not say, the radios that may carry a path count. */
export const directAt = (row: Direct): string | null => row.last_direct_any_at ?? row.last_direct_at;

interface ListOptions {
  filter: string;
  /** Keep only stations heard direct on any radio at some time (`directAt`). */
  directOnly?: boolean;
  /** Keep only stations heard on a radio (an iGate's too), leaving out those known from the
   * internet alone. */
  rfOnly?: boolean;
  /** Drop the stations `timedOut` says have passed their timeout. */
  hideTimedOut?: boolean;
  timedOut?: (row: StationRow) => boolean;
  sort: Sort;
}

/** The name of the station's symbol in the page's language ("Car"); "unknown" for a station with
 * none. */
export function rowSymbolName(row: Pick<StationRow, "symbol_table" | "symbol_code">): string {
  return symbolText(row.symbol_table, row.symbol_code);
}

/** The symbol name with its owner: "Car (ours)" for our object or item, and with `me` "Car (our
 * station)" for our own station. */
export function symbolLabel(
  row: Pick<StationRow, "symbol_table" | "symbol_code" | "own" | "is_me">,
  me = false,
): string {
  const name = rowSymbolName(row);
  return me && row.is_me ? t("station.symbol.me", { name }) : row.own ? t("station.symbol.own", { name }) : name;
}

function matches(row: StationRow, needle: string): boolean {
  if (needle === "") return true;
  const text =
    `${row.call} ${rowSymbolName(row)} ${row.last_comment} ${row.last_status} ${row.last_path.join(",")} ${row.reported_by}`.toLowerCase();
  return text.includes(needle);
}

/** The rows of the table: filtered by text (call, symbol name, comment, status, path), by heard
 * direct, by heard on a radio and by not timed out; sorted, our own station first and the timed-out
 * ones last. */
export function listStations(rows: Iterable<StationRow>, options: ListOptions): StationRow[] {
  const needle = options.filter.trim().toLowerCase();
  const gone = options.hideTimedOut === true && options.timedOut ? options.timedOut : () => false;
  const kept = [...rows].filter(
    (r) =>
      r.is_me ||
      ((options.directOnly !== true || directAt(r) !== null) &&
        (options.rfOnly !== true || onAir(r)) &&
        !gone(r) &&
        matches(r, needle)),
  );
  const { key, dir } = options.sort;
  // A station past its timeout sorts after the live ones, whatever the column.
  const out = options.timedOut ?? (() => false);
  return kept.sort(
    (a, b) =>
      Number(b.is_me) - Number(a.is_me) ||
      Number(out(a)) - Number(out(b)) ||
      compare(sortValue(a, key), sortValue(b, key), dir) ||
      a.call.localeCompare(b.call),
  );
}

/** The rows with our own station drawn as the settings say when its row has no symbol of its own;
 * the same array when nothing changes. */
export function withOwnSymbol(
  rows: ReadonlyMap<string, StationRow>,
  settings: Readonly<Record<string, string>> | undefined,
): ReadonlyMap<string, StationRow> {
  const table = settings?.["station/symbol_table"] ?? "";
  const code = settings?.["station/symbol_code"] ?? "";
  if (table === "" || code === "") return rows;
  let changed: Map<string, StationRow> | null = null;
  for (const [call, row] of rows) {
    if (!row.is_me || row.symbol_table !== "" || row.symbol_code !== "") continue;
    changed ??= new Map(rows);
    changed.set(call, { ...row, symbol_table: table, symbol_code: code });
  }
  return changed ?? rows;
}

/** The id of a station's row in the Stations table, which a link from another tab scrolls to and
 * flashes (lib/attention.ts). */
export const stationRowId = (call: string): string => `station-${call}`;
