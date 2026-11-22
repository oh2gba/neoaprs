// What the statistics card (components/StatsCard.vue) shows of the daemon's answer to
// `packet_stats`:
// bars of the last 24 hours split by radio (and the internet), each radio's heard and sent counts,
// what we sent by kind, copies that came again by another way, the busiest and quietest hour, and
// what went through us in the last hour.
// Plain functions of the answer and the radios; the words are the `stats.*` messages. Lines keep
// their shape as numbers tick (a dash until the first answer, 0 for a kind sent none of) so the
// card, which is anchored at its bottom edge, does not move. Only a line that cannot apply is left
// out (the iGate's while off, the repeated line while no radio repeats and none did).
import { formatNumber, t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { Point } from "@/lib/chart";
import { HOUR_MS, pad2 } from "@/lib/format";
import { senders, type PageRadio } from "@/lib/radios";
import type { StatLine } from "@/lib/stats";
import type { PacketStatsMessage, RadioSent } from "@/protocol/protocol";

/** The hours of the graph. */
export const CHART_HOURS = 24;
/** The colours a radio's part of a bar may have, in radio order (classes of styles/card.css); the
 * internet's is `series-net`. */
const SERIES = ["series-0", "series-1", "series-2", "series-3", "series-4", "series-5"] as const;
/** The value of a line before the daemon's first answer. */
const NONE = "–";

/** A radio's colour: by its place among the page's radios (silent ones counted), so it stays the
 * same. */
const toneOf = (radio: PageRadio, radios: readonly PageRadio[]): string => SERIES[radios.indexOf(radio) % SERIES.length] ?? "series-net";

/** One radio's or the internet's part of the graph and lines: name, colour, and what it heard in
 * each of the last CHART_HOURS hours. */
export interface Channel {
  key: string;
  radio: number | null;
  label: string;
  tone: string;
  points: Point[];
  heard: number;
}

const whole = (n: number): string => formatNumber(n, 0);
const line = (label: MessageId, value: string | null, tone?: string): StatLine[] =>
  value === null ? [] : [tone === undefined ? { label, value } : { label, value, tone }];

/** The first hour of the graph in the answer's lists, and the time of each hour (its middle). */
function chartSpan(stats: PacketStatsMessage): { from: number; to: number; first: number } {
  const start = Date.parse(stats.start);
  const to = start + stats.hours * HOUR_MS;
  return { from: to - CHART_HOURS * HOUR_MS, to, first: stats.hours - CHART_HOURS };
}

/** The channels that heard anything: each known radio by name (removed too), in the daemon's order,
 * the internet last. */
function channels(stats: PacketStatsMessage, radios: readonly PageRadio[]): Channel[] {
  const { from, first } = chartSpan(stats);
  const found: Channel[] = [];
  for (const { radio, counts } of stats.heard) {
    const known = radio === null ? undefined : radios.find((one) => one.id === radio);
    if (radio !== null && known === undefined) continue;
    const points = Array.from({ length: CHART_HOURS }, (_, i) => ({ t: from + i * HOUR_MS + HOUR_MS / 2, v: counts[first + i] ?? 0 }));
    const label = known === undefined ? t("channel.is") : known.name;
    const tone = known === undefined ? "series-net" : toneOf(known, radios);
    found.push({ key: radio === null ? "is" : `radio-${radio}`, radio, label, tone, points, heard: points.reduce((sum, p) => sum + (p.v ?? 0), 0) });
  }
  return found;
}

/** The bars of the graph: each whole hour (axis and reading) and each channel's part of it. */
export function chartOf(stats: PacketStatsMessage, radios: readonly PageRadio[]): { from: number; to: number; points: Point[]; parts: Channel[] } {
  const { from, to } = chartSpan(stats);
  const parts = channels(stats, radios);
  const points = Array.from({ length: CHART_HOURS }, (_, i) => ({
    t: from + i * HOUR_MS + HOUR_MS / 2,
    v: parts.reduce((sum, part) => sum + (part.points[i]?.v ?? 0), 0),
  }));
  return { from, to, points, parts };
}

const sentOf = (row: RadioSent): number => row.beacons + row.messages + row.acks + row.objects + row.other + row.repeated;

/** A radio's line for the last 24 hours: "1 204 heard · 45 sent", or "1 204 heard"; dashes until
 * the answer; null for an off or removed radio with nothing that day. */
function radioLine(stats: PacketStatsMessage | null, parts: readonly Channel[], radio: PageRadio, radios: readonly PageRadio[]): StatLine | null {
  const heard = parts.find((part) => part.radio === radio.id)?.heard;
  const sent = stats?.sent.find((row) => row.radio === radio.id);
  if (!radio.enabled && heard === undefined && sent === undefined) return null;
  const counted = (n: number): string => (stats === null ? NONE : whole(n));
  const value =
    senders(radios).includes(radio) || sent !== undefined
      ? t("stats.heard_sent", { heard: counted(heard ?? 0), sent: counted(sent === undefined ? 0 : sentOf(sent)) })
      : t("stats.heard_value", { n: counted(heard ?? 0) });
  return { label: "stats.channel", params: { name: radio.name }, value, tone: toneOf(radio, radios), key: `radio-${radio.id}` };
}

/** Each radio by name with its colour, what it heard and (if it can send) sent over the last 24
 * hours, the internet's "240 heard", and the copies. Radios that are on always have their line
 * (a dash until the answer), and so has the internet while `internet` is on; others only where
 * the day has something of them. */
export function channelLines(stats: PacketStatsMessage | null, radios: readonly PageRadio[], internet: boolean): StatLine[] {
  const parts = stats === null ? [] : channels(stats, radios);
  const lines = radios.map((radio) => radioLine(stats, parts, radio, radios)).filter((one): one is StatLine => one !== null);
  const net = parts.find((part) => part.radio === null);
  if (internet || (net !== undefined && net.heard > 0)) {
    const value = t("stats.heard_value", { n: stats === null ? NONE : whole(net?.heard ?? 0) });
    lines.push({ label: "stats.channel", params: { name: t("channel.is") }, value, tone: "series-net", key: "is" });
  }
  const copies = stats === null ? NONE : t("stats.copies_value", { n: whole(stats.frames - stats.packets), packets: whole(stats.packets) });
  return [...lines, ...line("stats.copies", copies)];
}

/** What we sent over the last 24 hours on all radios together, by kind: 0 for a kind not sent, a
 * dash until the answer. */
export function ownLines(stats: PacketStatsMessage | null): StatLine[] {
  const sum = (field: "beacons" | "messages" | "acks" | "objects" | "other"): string =>
    stats === null ? NONE : whole(stats.sent.reduce((n, row) => n + row[field], 0));
  return [
    ...line("stats.own.beacons", sum("beacons")),
    ...line("stats.own.messages", sum("messages")),
    ...line("stats.own.acks", sum("acks")),
    ...line("stats.own.objects", sum("objects")),
    ...line("stats.own.other", sum("other")),
  ];
}

/** What went through us: copies the digipeater sent and what the iGate gated, in the last hour
 * (a dash until the answer) and since the daemon started (`since`; the iGate's is null while it is
 * off; `digipeater`: a radio that is on repeats). The repeated line shows while a radio repeats or
 * something was repeated. */
export function throughLines(stats: PacketStatsMessage | null, since: { repeated: number; gated: number | null; digipeater: boolean }): StatLine[] {
  const both = (hour: number | null | undefined, all: number): string =>
    t("stats.hour_and_all", { hour: stats === null ? NONE : whole(hour ?? 0), all: whole(all) });
  const repeated = since.digipeater || (stats?.repeated_hour ?? 0) > 0 || since.repeated > 0 ? both(stats?.repeated_hour, since.repeated) : null;
  return [...line("stats.digipeated", repeated), ...line("stats.gated", since.gated === null ? null : both(stats?.gated_hour, since.gated))];
}

/** The hour of the day as written, "17:00–18:00". */
const hourSpan = (hour: number): string => t("stats.hour_span", { from: `${pad2(hour)}:00`, to: `${pad2((hour + 1) % 24)}:00` });

/** The busiest and quietest hour in the viewer's time, by packets heard per hour on average over
 * the hours that are over; null until a whole day is counted. The daemon's hours are whole UTC
 * hours: in a zone with a fractional offset, the span is the local hour the UTC hour starts in. */
export function dayHours(stats: PacketStatsMessage): { busiest: number; quietest: number } | null {
  const whole = stats.hours - 1;
  if (whole < 24) return null;
  const start = Date.parse(stats.start);
  const sums = Array.from({ length: 24 }, () => 0);
  const seen = Array.from({ length: 24 }, () => 0);
  for (let i = 0; i < whole; i++) {
    const hour = new Date(start + i * HOUR_MS).getHours();
    sums[hour] = (sums[hour] ?? 0) + stats.heard.reduce((n, channel) => n + (channel.counts[i] ?? 0), 0);
    seen[hour] = (seen[hour] ?? 0) + 1;
  }
  const mean = sums.map((n, hour) => n / Math.max(1, seen[hour] ?? 1));
  const busiest = mean.reduce((best, n, hour) => (n > (mean[best] ?? 0) ? hour : best), 0);
  const quietest = mean.reduce((best, n, hour) => (n < (mean[best] ?? 0) ? hour : best), 0);
  return { busiest, quietest };
}

/** The busiest and quietest hour, a dash for each until a whole day is counted. */
export function dayHourLines(stats: PacketStatsMessage | null): StatLine[] {
  const hours = stats === null ? null : dayHours(stats);
  return [
    ...line("stats.busiest_hour", hours === null ? NONE : hourSpan(hours.busiest)),
    ...line("stats.quietest_hour", hours === null ? NONE : hourSpan(hours.quietest)),
  ];
}
