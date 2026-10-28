// The statistics card (components/StatsCard.vue): what the page knows, counted up in a few lines a person would ask for. All of it is made from what the page has already, the station book, the latest packets, the
// status and the radio's counters; nothing is asked of the daemon. Four sections: the stations (how many, how heard, what they run), how far we reach (the farthest heard direct and on the radio, the digipeaters most
// used, the ALOHA circle), the packets (the database, the last hour, the busiest station, and the latest 200 by kind and by channel), and the radio since the daemon started. A line with nothing to say is left out, and so is an empty section.
// Plain functions of what the page has; the words are the `stats.*` messages.
import { formatNumber, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import { timedOut, type Aging } from "@/lib/aging";
import { internetOnly, onAir, packetLabel } from "@/lib/channels";
import { ageText, bytesText, distanceText } from "@/lib/format";
import { digipeaters, gateRows, repeatedCounts } from "@/lib/nearby";
import { hasPosition } from "@/lib/stations";
import { isWeatherStation } from "@/lib/weather";
import type { IgateState, MapState, PacketRow, StationRow, StatusMessage, TncState } from "@/protocol/protocol";

interface StatLine {
  label: MessageId;
  /** what the label's message takes ("Latest {n} by kind") */
  params?: Record<string, string | number>;
  value: string;
}

export interface StatSection {
  title: MessageId;
  lines: StatLine[];
}

export interface StatsInput {
  stations: ReadonlyMap<string, StationRow>;
  packets: ReadonlyMap<string, PacketRow>;
  status: StatusMessage | null;
  tnc: TncState | null;
  igate: IgateState | null;
  /** the map's state: the ALOHA circle's radius is in it */
  map: MapState | null;
  aging: Aging;
  now: number;
}

/** How many of a list are named: the devices most run, the digipeaters most used. */
const TOP = 3;
const KINDS = ["position", "message", "object", "item", "status", "other", "undecoded"] as const satisfies readonly PacketRow["kind"][];

const whole = (n: number): string => formatNumber(n, 0);
/** A station that is heard: not ourselves, not our objects. */
const heard = (row: StationRow): boolean => !row.is_me && !row.own;
const isStation = (row: StationRow): boolean => row.kind === "station" && heard(row);

/** "OH2RCH-2 (120), OH2RCH-1 (45)": the `TOP` most counted, the most first, ties by the name. */
function topText(counts: ReadonlyMap<string, number>): string {
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, TOP)
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

function reachLines(rows: readonly StationRow[], map: MapState | null): StatLine[] {
  const stations = rows.filter((row) => isStation(row) && onAir(row));
  const repeated = repeatedCounts(rows);
  const aloha = map?.aloha_km ?? null;
  return [
    ...line("stats.aloha", aloha === null ? null : t("stats.km", { km: distanceText(aloha) })),
    ...line("stats.farthest_direct", farthestText(stations.filter((row) => row.heard_direct > 0))),
    ...line("stats.farthest_rf", farthestText(stations.filter((row) => row.heard_rf > 0))),
    ...line("stats.most_used", repeated.size > 0 ? topText(repeated) : null),
  ];
}

/** The latest packets as the page has them (the daemon keeps 200): the ones heard, not those we sent. */
function latestLines(packets: ReadonlyMap<string, PacketRow>): StatLine[] {
  const rows = [...packets.values()].filter((row) => row.direction === "in");
  if (rows.length === 0) return [];
  const kinds = new Map<string, number>();
  const channels = new Map<string, number>();
  for (const row of rows) {
    kinds.set(row.kind, (kinds.get(row.kind) ?? 0) + 1);
    channels.set(row.via, (channels.get(row.via) ?? 0) + 1);
  }
  const byKind = KINDS.filter((kind) => kinds.has(kind))
    .map((kind) => t("stats.kind_count", { n: whole(kinds.get(kind) ?? 0), kind: t(`stats.kind.${kind}`) }))
    .join(" · ");
  const byChannel = [...channels.entries()].map(([via, n]) => t("stats.kind_count", { n: whole(n), kind: packetLabel(via as PacketRow["via"]) })).join(" · ");
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
  const busiest = stations.filter((row) => row.packets_hour > 0).sort((a, b) => b.packets_hour - a.packets_hour || a.call.localeCompare(b.call))[0];
  return [
    ...line("stats.packets_total", status === null ? null : whole(status.packets)),
    ...line("stats.packets_hour", whole(hour)),
    ...line("stats.busiest", busiest === undefined ? null : t("stats.busiest_value", { call: busiest.call, n: whole(busiest.packets_hour) })),
  ];
}

function radioLines(status: StatusMessage | null, tnc: TncState | null, igate: IgateState | null, now: number): StatLine[] {
  const stats = tnc?.stats ?? null;
  return [
    ...line("stats.running", status === null ? null : ageText(status.started_at, now)),
    ...line(
      "stats.frames",
      stats === null ? null : stats.rejected > 0 ? t("stats.frames_value", { n: whole(stats.frames_in), bad: whole(stats.rejected) }) : whole(stats.frames_in),
    ),
    ...line("stats.bytes", stats === null ? null : t("stats.in_out", { in: bytesText(stats.bytes_in), out: bytesText(stats.bytes_out) })),
    ...some("stats.digipeated", stats?.digipeated ?? 0),
    ...line("stats.gated", igate !== null && igate.enabled ? whole(igate.gated) : null),
  ];
}

/** The sections of the card, each with its lines; a section with no line is left out. */
export function mapStats(input: StatsInput): StatSection[] {
  const rows = [...input.stations.values()];
  const sections: StatSection[] = [
    { title: "stats.section.stations", lines: stationLines(rows, input.aging, input.now) },
    { title: "stats.section.reach", lines: reachLines(rows, input.map) },
    { title: "stats.section.packets", lines: [...packetLines(rows, input.status), ...latestLines(input.packets)] },
    { title: "stats.section.radio", lines: radioLines(input.status, input.tnc, input.igate, input.now) },
  ];
  return sections.filter((section) => section.lines.length > 0);
}
