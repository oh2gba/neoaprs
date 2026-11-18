// The statistics card (components/StatsCard.vue): what the page knows, counted up in a few lines a person would ask for, in sections: the stations (how many, how heard, what they run), how far we reach (the farthest
// heard direct and on the radio, the digipeaters most used, the ALOHA circle), the packets (the database, the last hour, the five busiest stations, the busiest and the quietest hour of the day, and the latest 200 by kind
// and by channel), each radio by its name over the last 24 hours, what we sent ourselves, what went through us (the digipeater's copies and the iGate's, the last hour and since the start), and the radios since the
// daemon started. Most of it is made from what the page has already, the station book, the latest packets, the status and the radios' counters; what the station book cannot say is the daemon's answer to
// `packet_stats` (lib/packetstats.ts), whose sections and lines keep their shape from before the first answer on. A line with nothing to say is left out, and so is an empty section.
// Plain functions of what the page has; the words are the `stats.*` messages.
import { formatNumber, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { timedOut, type Aging } from "@/lib/aging";
import { internetOnly, onAir, packetTag } from "@/lib/channels";
import { HOUR_MS, ageText, bytesText, distanceText } from "@/lib/format";
import { digipeaters, gateRows, repeatedCounts } from "@/lib/nearby";
import { hasPosition } from "@/lib/stations";
import { isWeatherStation } from "@/lib/weather";
import type { Point } from "@/lib/chart";
import { enabledRadios, type PageRadio } from "@/lib/radios";
import { channelLines, dayHourLines, ownLines, throughLines } from "@/lib/packetstats";
import type { IgateState, MapState, PacketHistoryMessage, PacketRow, PacketStatsMessage, StationRow, StatusMessage, TncStats } from "@/protocol/protocol";

export interface StatLine {
  label: MessageId;
  /** what the label's message takes ("Latest {n} by kind") */
  params?: Record<string, string | number>;
  value: string;
  /** the colour of the line's part of the graph (a radio's, the internet's: lib/packetstats.ts) */
  tone?: string;
  /** what tells the line from the others of its label (a radio's line: its channel's key, `radio-1`, `is`); else the label does */
  key?: string;
}

export interface StatSection {
  title: MessageId;
  lines: StatLine[];
}

export interface StatsInput {
  stations: ReadonlyMap<string, StationRow>;
  packets: ReadonlyMap<string, PacketRow>;
  status: StatusMessage | null;
  /** every radio, in the order of their boxes (composables/useRadios.ts `all`): the packets are counted by radio, and the counters of those that are on added up */
  radios: readonly PageRadio[];
  igate: IgateState | null;
  /** the map's state: the ALOHA circle's radius is in it */
  map: MapState | null;
  aging: Aging;
  now: number;
  /** the daemon's answer to `packet_stats`; null until one came */
  packetStats: PacketStatsMessage | null;
}

/** How many of a list are named: the devices most run, the digipeaters most used; the busiest stations. */
const TOP = 3;
const BUSIEST = 5;
const KINDS = ["position", "message", "object", "item", "status", "other", "undecoded"] as const satisfies readonly PacketRow["kind"][];

const whole = (n: number): string => formatNumber(n, 0);
/** A station that is heard: not ourselves, not our objects. */
const heard = (row: StationRow): boolean => !row.is_me && !row.own;
const isStation = (row: StationRow): boolean => row.kind === "station" && heard(row);

/** "OH2RCH-2 (120), OH2RCH-1 (45)": the `top` most counted, the most first, ties by the name. */
function topText(counts: ReadonlyMap<string, number>, top = TOP): string {
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, top)
    .map(([name, n]) => t("stats.counted", { name, n: whole(n) }))
    .join(", ");
}

/** The row farthest from us among `rows`, as "OH2XYZ, 87 km"; null when none has a distance. */
function farthestText(rows: readonly StationRow[]): string | null {
  const far = rows.filter((row) => row.distance_km !== null).sort((a, b) => (b.distance_km ?? 0) - (a.distance_km ?? 0) || a.call.localeCompare(b.call))[0];
  return far === undefined ? null : t("stats.station_km", { call: far.call, km: distanceText(far.distance_km) });
}

function line(label: MessageId, value: string | null, params?: Record<string, string | number>): StatLine[] {
  return value === null ? [] : [params === undefined ? { label, value } : { label, params, value }];
}

/** A count that says nothing while it is 0. */
const some = (label: MessageId, n: number): StatLine[] => line(label, n > 0 ? whole(n) : null);

function stationLines(rows: readonly StationRow[], aging: Aging, now: number): StatLine[] {
  const stations = rows.filter(isStation);
  const devices = new Map<string, number>();
  for (const row of stations) if (row.device !== "") devices.set(row.device, (devices.get(row.device) ?? 0) + 1);
  return [
    ...line("stats.stations", whole(stations.length)),
    ...line("stats.on_map", whole(rows.filter((row) => heard(row) && hasPosition(row) && !timedOut(aging, row, now)).length)),
    ...line("stats.direct", whole(stations.filter((row) => onAir(row) && row.heard_direct > 0).length)),
    ...some("stats.internet_only", stations.filter(internetOnly).length),
    ...some("stats.objects", rows.filter((row) => heard(row) && row.kind !== "station").length),
    ...line("stats.digipeaters", whole(digipeaters(rows).length)),
    ...line("stats.igates", whole(gateRows(rows).length)),
    ...some("stats.weather", stations.filter(isWeatherStation).length),
    ...line("stats.devices", devices.size > 0 ? topText(devices) : null),
  ];
}

/** The radius of each ALOHA circle, "37 km", and where radios are named (several on) each after its radio's name, "FM: 37 km · FM 2: 12 km"; null for none. */
function alohaText(map: MapState | null, radios: readonly PageRadio[]): string | null {
  const circles = map?.aloha ?? [];
  if (circles.length === 0) return null;
  const named = enabledRadios(radios).length > 1;
  return circles
    .map(({ radio, km }) => {
      const words = t("stats.km", { km: distanceText(km) });
      const name = radios.find((one) => one.id === radio)?.name;
      return named && name !== undefined ? t("radio.line", { name, line: words }) : words;
    })
    .join(" · ");
}

function reachLines(rows: readonly StationRow[], map: MapState | null, radios: readonly PageRadio[]): StatLine[] {
  const stations = rows.filter((row) => isStation(row) && onAir(row));
  const repeated = repeatedCounts(rows);
  return [
    ...line("stats.aloha", alohaText(map, radios)),
    ...line("stats.farthest_direct", farthestText(stations.filter((row) => row.heard_direct > 0))),
    ...line("stats.farthest_rf", farthestText(stations.filter((row) => row.heard_rf > 0))),
    ...line("stats.most_used", repeated.size > 0 ? topText(repeated) : null),
  ];
}

/** The latest packets as the page has them (the daemon keeps 200): the ones heard, not those we sent. "By channel" counts them by their tag (lib/channels.ts `packetTag`), said by its word: by the radio that heard
 * them (its name, "FM", "HF", "20 m", with one radio on as with several), iGate and Internet; two radios are never added together, even where their words are the same (a removed radio beside a live one). */
function latestLines(packets: ReadonlyMap<string, PacketRow>, radios: readonly PageRadio[]): StatLine[] {
  const rows = [...packets.values()].filter((row) => row.direction === "in");
  if (rows.length === 0) return [];
  const kinds = new Map<string, number>();
  const channels = new Map<string, { label: string; n: number }>(); // (by the tag's key: a radio's is its id's)
  for (const row of rows) {
    kinds.set(row.kind, (kinds.get(row.kind) ?? 0) + 1);
    const tag = packetTag(row, radios);
    if (tag === null) continue; // (a radio the page does not know yet: no tag, so not counted under one)
    const { key, label } = tag;
    const counted = channels.get(key);
    if (counted === undefined) channels.set(key, { label, n: 1 });
    else counted.n++;
  }
  const byKind = KINDS.filter((kind) => kinds.has(kind))
    .map((kind) => t("stats.kind_count", { n: whole(kinds.get(kind) ?? 0), kind: t(`stats.kind.${kind}`) }))
    .join(" · ");
  const byChannel = [...channels.values()].map(({ label, n }) => t("stats.kind_count", { n: whole(n), kind: label })).join(" · ");
  const onRadio = rows.filter((row) => row.via === "rf" || row.via === "dummy");
  const direct = onRadio.filter((row) => row.route === "direct").length;
  const times = rows.map((row) => Date.parse(row.heard_at)).filter((ms) => !Number.isNaN(ms));
  const spanMin = times.length > 1 ? (Math.max(...times) - Math.min(...times)) / 60_000 : 0;
  return [
    ...line("stats.by_kind", byKind, { n: whole(rows.length) }),
    ...line("stats.by_channel", byChannel),
    ...line("stats.direct_share", onRadio.length > 0 ? t("stats.percent_of_radio", { percent: Math.round((100 * direct) / onRadio.length) }) : null),
    ...line("stats.rate", spanMin >= 1 ? t("stats.per_minute", { n: formatNumber(rows.length / spanMin, 1) }) : null),
  ];
}

function packetLines(rows: readonly StationRow[], status: StatusMessage | null): StatLine[] {
  const stations = rows.filter(heard);
  const hour = stations.reduce((sum, row) => sum + row.packets_hour, 0);
  const busiest = new Map(stations.filter((row) => row.packets_hour > 0).map((row) => [row.call, row.packets_hour] as const));
  return [
    ...line("stats.packets_total", status === null ? null : whole(status.packets)),
    ...line("stats.packets_hour", whole(hour)),
    ...line("stats.busiest", busiest.size > 0 ? topText(busiest, BUSIEST) : "–"),
  ];
}

/** What the radios that are on counted since the daemon started, added up. */
type Totals = Pick<TncStats, "frames_in" | "rejected" | "bytes_in" | "bytes_out" | "digipeated">;

function radioTotals(counted: readonly TncStats[]): Totals | null {
  if (counted.length === 0) return null;
  const sum = (field: keyof Totals): number => counted.reduce((n, one) => n + one[field], 0);
  return { frames_in: sum("frames_in"), rejected: sum("rejected"), bytes_in: sum("bytes_in"), bytes_out: sum("bytes_out"), digipeated: sum("digipeated") };
}

function sinceLines(status: StatusMessage | null, stats: Totals | null, now: number): StatLine[] {
  return [
    ...line("stats.running", status === null ? null : ageText(status.started_at, now)),
    ...line(
      "stats.frames",
      stats === null ? null : stats.rejected > 0 ? t("stats.frames_value", { n: whole(stats.frames_in), bad: whole(stats.rejected) }) : whole(stats.frames_in),
    ),
    ...line("stats.bytes", stats === null ? null : t("stats.in_out", { in: bytesText(stats.bytes_in), out: bytesText(stats.bytes_out) })),
  ];
}

/** The sections of the card, each with its lines; a section with no line is left out. */
export function mapStats(input: StatsInput): StatSection[] {
  const rows = [...input.stations.values()];
  const radios = input.radios;
  const totals = radioTotals(enabledRadios(radios).map((radio) => radio.row.stats));
  const day = input.packetStats;
  const igate = input.igate;
  const sections: StatSection[] = [
    { title: "stats.section.stations", lines: stationLines(rows, input.aging, input.now) },
    { title: "stats.section.reach", lines: reachLines(rows, input.map, radios) },
    { title: "stats.section.packets", lines: [...packetLines(rows, input.status), ...dayHourLines(day), ...latestLines(input.packets, radios)] },
    { title: "stats.section.day", lines: channelLines(day, radios, igate?.enabled ?? false) },
    { title: "stats.section.own", lines: ownLines(day) },
    {
      title: "stats.section.through",
      lines: throughLines(day, {
        repeated: totals?.digipeated ?? 0,
        gated: igate !== null && igate.enabled ? igate.gated : null,
        digipeater: enabledRadios(radios).some((radio) => radio.row.choices.digipeat === true),
      }),
    },
    { title: "stats.section.radio", lines: sinceLines(input.status, totals, input.now) },
  ];
  return sections.filter((section) => section.lines.length > 0);
}

/** How far back the graph of the packets by the hour goes. */
export const HISTORY_HOURS = 24;

/** The bars of the graph: one point in the middle of each hour counted, and the span of the axis, the whole hours from the first to the end of the running one. */
export function historyPoints(history: PacketHistoryMessage): { from: number; to: number; points: Point[] } {
  const from = Date.parse(history.start);
  const points = history.counts.map((n, i) => ({ t: from + i * HOUR_MS + HOUR_MS / 2, v: n }));
  return { from, to: from + history.counts.length * HOUR_MS, points };
}

/** The frame of the graph before the daemon's answer came: the same span of whole hours that the answer will have (the running one last), with no bar, so that the graph keeps its place and only fills in. */
export function emptyHistory(now: number, hours = HISTORY_HOURS): { from: number; to: number; points: Point[] } {
  const to = Math.floor(now / HOUR_MS) * HOUR_MS + HOUR_MS;
  return { from: to - hours * HOUR_MS, to, points: [] };
}
