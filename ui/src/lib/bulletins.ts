// The message board as the Bulletins tab shows it: the rows of the topic `bulletins` grouped into announcements, bulletins, group messages and weather service bulletins, each newest first, what to call a row, and how many
// are new since the tab was last on show. The daemon decides what a bulletin is and that nothing on it ages out (neoaprs/bulletin.py); these only arrange and word it.
import type { BulletinRow } from "@/protocol/protocol";

type Kind = BulletinRow["kind"];

interface Section {
  kind: Kind;
  title: string;
  rows: BulletinRow[];
}

const SECTIONS: { kind: Kind; title: string }[] = [
  { kind: "announcement", title: "Announcements" },
  { kind: "bulletin", title: "Bulletins" },
  { kind: "group", title: "Group messages" },
  { kind: "nws", title: "Weather service" },
];

/** The board in its four sections (announcements, bulletins, group messages, weather service), each newest first by the last hearing; a section with nothing in it is left out. */
export function sections(rows: Iterable<BulletinRow>): Section[] {
  const all = [...rows].sort((a, b) =>
    a.last_heard === b.last_heard ? a.sender.localeCompare(b.sender) || a.slot.localeCompare(b.slot) : a.last_heard < b.last_heard ? 1 : -1,
  );
  return SECTIONS.map(({ kind, title }) => ({ kind, title, rows: all.filter((r) => r.kind === kind) })).filter((s) => s.rows.length > 0);
}

/** What a row is addressed to, as it is called: the group of a group bulletin ("HAMS"), else the slot ("BLN1", "BLNA", "QST"). */
export function targetOf(row: BulletinRow): string {
  return row.group === "" ? row.slot : row.group;
}

/** "heard once", "heard 3 times". */
export function timesText(times: number): string {
  return times === 1 ? "heard once" : `heard ${times} times`;
}

/** When the newest text on the board was first heard, in ms since 1970; 0 for an empty board. */
export function newestFirstHeard(rows: Iterable<BulletinRow>): number {
  let newest = 0;
  for (const row of rows) newest = Math.max(newest, Date.parse(row.first_heard) || 0);
  return newest;
}

/** How many rows have a text first heard after `seenUpTo` (ms since 1970): a bulletin new on the board, or one whose sender changed the text. */
export function newCount(rows: Iterable<BulletinRow>, seenUpTo: number): number {
  let count = 0;
  for (const row of rows) if ((Date.parse(row.first_heard) || 0) > seenUpTo) count++;
  return count;
}
