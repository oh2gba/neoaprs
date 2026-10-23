// The packets of the log: newest first, filtered by a text, and the decoded part as JSON for the detail.
import type { PacketRow } from "@/protocol/protocol";

/** Newest first: the highest id is the newest. */
export function newestFirst(rows: Iterable<PacketRow>): PacketRow[] {
  return [...rows].sort((a, b) => b.id - a.id);
}

/** The rows that have the text (any case) in their line, summary, source, destination, kind or route; all for an empty text. */
export function filterPackets(rows: readonly PacketRow[], filter: string): PacketRow[] {
  const needle = filter.trim().toLowerCase();
  if (needle === "") return [...rows];
  return rows.filter((r) => `${r.tnc2} ${r.summary} ${r.source} ${r.destination} ${r.kind} ${r.direction} ${r.route}`.toLowerCase().includes(needle));
}

export function decodedJson(row: PacketRow): string {
  return JSON.stringify(row.decoded, null, 2);
}
