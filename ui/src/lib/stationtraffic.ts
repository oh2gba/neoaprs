// The traffic of one station, for its panel in the Stations tab (components/StationTraffic.vue):
// the packets it sent (its own or inside a third-party packet: `sender`) and the messages we sent
// it, newest first, at most TRAFFIC_SHOWN. They come from the daemon's answer to `station_traffic`
// (the packet log, older than the Packets tab's 200) and the later packets of the topic `packets`;
// the same packet in both is one line (`trafficKey`). Also the state of a directed query of ours:
// "waiting" until the station answers, "answered", or "no answer" after ANSWER_WAIT_MS. The answer
// a query asks for (`answers`): ?APRSP a position, ?APRSS a status, ?APRSD a message starting
// "Directs=", ?APRST and ?PING? a message, ?WX? a weather report, any other query any packet.
import type { DecodedMessage, PacketRow } from "@/protocol/protocol";

export const TRAFFIC_SHOWN = 50;
export const ANSWER_WAIT_MS = 120_000;
export type QueryState = "waiting" | "answered" | "no_answer";

const time = (row: PacketRow): number => Date.parse(row.heard_at);

/** Our message to `call` (not an ack or reject), if the packet is one. */
function ourMessageTo(row: PacketRow, call: string): DecodedMessage | null {
  const d = row.decoded;
  return row.direction === "out" && d.type === "message" && d.addressee === call ? d : null;
}

/** Whether the packet is traffic of the station: it sent it, or we sent it a message. */
export function isTrafficOf(row: PacketRow, call: string): boolean {
  return row.sender === call || ourMessageTo(row, call) !== null;
}

/** One packet whichever way it came (the log and the topic use different ids). */
export const trafficKey = (row: PacketRow): string =>
  `${row.heard_at} ${row.direction} ${row.radio_id ?? ""} ${row.tnc2}`;

/**
 * The lines of the list: packets of both sources once each, newest first (arrival order for equal
 * times), without internet packets while `internet` is off, at most TRAFFIC_SHOWN.
 */
export function mergeTraffic(live: Iterable<PacketRow>, logged: readonly PacketRow[], internet: boolean): PacketRow[] {
  const seen = new Map<string, PacketRow>();
  for (const row of [...live].sort((a, b) => b.id - a.id)) seen.set(trafficKey(row), row);
  for (const row of logged) if (!seen.has(trafficKey(row))) seen.set(trafficKey(row), row);
  return [...seen.values()]
    .filter((row) => internet || row.via !== "is")
    .sort((a, b) => time(b) - time(a))
    .slice(0, TRAFFIC_SHOWN);
}

/**
 * The query our packet to `call` is (a message with no id starting with "?"), upper-cased; else
 * null.
 */
export function queryAsked(row: PacketRow, call: string): string | null {
  const d = ourMessageTo(row, call);
  return d !== null && d.msg_id === null && d.ack_id === null && d.rej_id === null && d.text.startsWith("?")
    ? d.text.toUpperCase()
    : null;
}

/** Whether `reply`, a packet the station sent, answers the query. */
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

/**
 * The state of our query (null if the packet is none): answered once the station sent the answer
 * after it, else waiting for ANSWER_WAIT_MS, then no answer. `rows` are the list's lines.
 */
export function queryState(row: PacketRow, call: string, rows: readonly PacketRow[], now: number): QueryState | null {
  const query = queryAsked(row, call);
  if (query === null) return null;
  const sent = time(row);
  if (
    rows.some(
      (reply) => reply.direction === "in" && reply.sender === call && time(reply) > sent && answers(query, reply),
    )
  )
    return "answered";
  return now - sent >= ANSWER_WAIT_MS ? "no_answer" : "waiting";
}

/** The earliest moment a waiting query times out; null if none waits. */
export function nextDeadline(call: string, rows: readonly PacketRow[], now: number): number | null {
  const due = rows
    .filter((row) => queryState(row, call, rows, now) === "waiting")
    .map((row) => time(row) + ANSWER_WAIT_MS);
  return due.length === 0 ? null : Math.min(...due);
}
