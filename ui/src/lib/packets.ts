// The packets of the log: newest first, filtered by text, with the decoded part as JSON for the
// detail.
import { summaryText } from "@/lib/packetview";
import type { PacketRow } from "@/protocol/protocol";

export function newestFirst(rows: Iterable<PacketRow>): PacketRow[] {
  return [...rows].sort((a, b) => b.id - a.id);
}

/**
 * The rows that contain the text (any case) in their line, summary (in the page's words), source,
 * destination, kind or route (the word of their Via tag, components/PacketsLog.vue, which needs the
 * radios); all rows for empty text.
 */
export function filterPackets(rows: readonly PacketRow[], filter: string): PacketRow[] {
  const needle = filter.trim().toLowerCase();
  if (needle === "") return [...rows];
  return rows.filter((r) => `${r.tnc2} ${summaryText(r)} ${r.source} ${r.destination} ${r.kind} ${r.direction} ${r.route}`.toLowerCase().includes(needle));
}

export function decodedJson(row: PacketRow): string {
  return JSON.stringify(row.decoded, null, 2);
}
