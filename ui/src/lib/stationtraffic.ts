// The traffic of one station, as its panel in the Stations tab lists it (components/StationTraffic.vue): the packets it sent (its own, or inside a third-party packet: `sender`) and the messages we sent to it (a message,
// an ack, a directed query), the newest first, at most TRAFFIC_SHOWN. They come from two places: the daemon's answer to `station_traffic` (read from the packet log, so older than the 200 of the Packets tab) and the packets
// that come after it (the topic `packets`); the same packet in both is one line (`trafficKey`: its time, its direction and its line; their ids differ). And the state of a directed query of ours in that list: "waiting…"
// until the answer it asks for comes from the station, "answered" once it has, "no answer" after ANSWER_WAIT_MS without (`queryState`). The answer each query asks for (`answers`): ?APRSP a position, ?APRSS a status,
// ?APRSD a message that begins "Directs=", ?APRST and ?PING? a message, ?WX? a weather report, any other query any packet of the station after it.
import type { DecodedMessage, PacketRow } from "@/protocol/protocol";

export const TRAFFIC_SHOWN = 50;
export const ANSWER_WAIT_MS = 120_000;
export type QueryState = "waiting" | "answered" | "no_answer";

const time = (row: PacketRow): number => Date.parse(row.heard_at);

/** A message to `call` (not an ack, not a reject) that we sent, when the packet is one. */
function ourMessageTo(row: PacketRow, call: string): DecodedMessage | null {
  const d = row.decoded;
  return row.direction === "out" && d.type === "message" && d.addressee === call ? d : null;
}

/** Whether the packet is traffic of the station: it sent it, or we sent it a message. */
export function isTrafficOf(row: PacketRow, call: string): boolean {
  return row.sender === call || ourMessageTo(row, call) !== null;
}

/** One packet whichever way it came (the log's answer has the log's numbers as ids, the topic its own). */
export const trafficKey = (row: PacketRow): string => `${row.heard_at} ${row.direction} ${row.tnc2}`;

/** The lines of the list: the packets of both places once each, the newest first (the order they came in where the times are equal), without those from the internet while `internet` is off, at most TRAFFIC_SHOWN. */
export function mergeTraffic(live: Iterable<PacketRow>, logged: readonly PacketRow[], internet: boolean): PacketRow[] {
  const seen = new Map<string, PacketRow>();
  for (const row of [...live].sort((a, b) => b.id - a.id)) seen.set(trafficKey(row), row);
  for (const row of logged) if (!seen.has(trafficKey(row))) seen.set(trafficKey(row), row);
  return [...seen.values()]
    .filter((row) => internet || row.via !== "is")
    .sort((a, b) => time(b) - time(a))
    .slice(0, TRAFFIC_SHOWN);
}

/** The query a packet of ours to `call` is (a message with no id whose text begins with "?"), upper-cased; null for any other packet. */
export function queryAsked(row: PacketRow, call: string): string | null {
  const d = ourMessageTo(row, call);
  return d !== null && d.msg_id === null && d.ack_id === null && d.rej_id === null && d.text.startsWith("?") ? d.text.toUpperCase() : null;
}

/** Whether `reply`, a packet the station sent, is the answer the query asks for. */
export function answers(query: string, reply: PacketRow): boolean {
  const d = reply.decoded;
  const message = d.type === "message" && d.ack_id === null && d.rej_id === null ? d.text : null;
  if (query.startsWith("?APRSP")) return d.type === "position";
  if (query.startsWith("?APRSS")) return d.type === "status";
  if (query.startsWith("?APRSD")) return message?.toUpperCase().startsWith("DIRECTS=") ?? false;
  if (query.startsWith("?APRST") || query.startsWith("?PING?")) return message !== null;
  if (query.startsWith("?WX?")) return (d.type === "position" || d.type === "other") && d.weather !== null;
  return true;
}

/** The state of a query of ours (null for a packet that is none): answered when the station sent the answer after it, else waiting for ANSWER_WAIT_MS and then no answer. `rows` are the lines of the list. */
export function queryState(row: PacketRow, call: string, rows: readonly PacketRow[], now: number): QueryState | null {
  const query = queryAsked(row, call);
  if (query === null) return null;
  const sent = time(row);
  if (rows.some((reply) => reply.direction === "in" && reply.sender === call && time(reply) > sent && answers(query, reply))) return "answered";
  return now - sent >= ANSWER_WAIT_MS ? "no_answer" : "waiting";
}

/** When the list is next to change by the clock alone: the earliest moment a query that waits has waited long enough; null when none waits. */
export function nextDeadline(call: string, rows: readonly PacketRow[], now: number): number | null {
  const due = rows.filter((row) => queryState(row, call, rows, now) === "waiting").map((row) => time(row) + ANSWER_WAIT_MS);
  return due.length === 0 ? null : Math.min(...due);
}
