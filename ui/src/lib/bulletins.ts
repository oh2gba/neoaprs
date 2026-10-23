// The message board as the Bulletins tab shows it: the rows of the topic `bulletins` grouped into announcements, bulletins, group messages and weather service bulletins, each newest first, what to call a row, and how many
// are new since the tab was last on show. The daemon decides what a bulletin is and that nothing on it ages out (neoaprs/bulletin.py); these only arrange and word it.
import { t } from "@/i18n";
import { ageText, untilText } from "@/lib/format";
import { sentText } from "@/lib/ownobjects";
import { LIMITS } from "@/protocol/lists";
import type { BulletinRow, Command, OwnBulletinRow } from "@/protocol/protocol";

type Kind = BulletinRow["kind"];

/** A row of the board: what was heard, or (`own`) what we post, written in the same columns: the sender is our call, `first_heard` is when it was posted, `last_heard` when it was last sent and `times_heard` how often. */
export interface BoardEntry extends BulletinRow {
  own?: OwnBulletinRow;
}

interface Section<T extends BulletinRow> {
  kind: Kind;
  title: string;
  rows: T[];
}

const SECTIONS: readonly Kind[] = ["announcement", "bulletin", "group", "nws"];

/** The board in its four sections (announcements, bulletins, group messages, weather service), each newest first by the last hearing; a section with nothing in it is left out. */
export function sections<T extends BulletinRow>(rows: Iterable<T>): Section<T>[] {
  const all = [...rows].sort((a, b) =>
    a.last_heard === b.last_heard ? a.sender.localeCompare(b.sender) || a.slot.localeCompare(b.slot) : a.last_heard < b.last_heard ? 1 : -1,
  );
  return SECTIONS.map((kind) => ({ kind, title: t(`bulletins.section.${kind}`), rows: all.filter((r) => r.kind === kind) })).filter((s) => s.rows.length > 0);
}

/** What a row is addressed to, as it is called: the group of a group bulletin ("HAMS"), else the slot ("BLN1", "BLNA", "QST"). */
export function targetOf(row: BulletinRow): string {
  return row.group === "" ? row.slot : row.group;
}

/** How often a bulletin was heard and how long ago it was last: "heard once, 3 min ago", "heard 3 times, 3 min ago". */
export function heardText(times: number, lastHeard: string | null, nowMs: number): string {
  return t("bulletins.heard", { n: times, span: ageText(lastHeard, nowMs) });
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

/** The bulletins of ours as rows of the board, under our call. */
export function ownEntries(rows: Iterable<OwnBulletinRow>, call: string): BoardEntry[] {
  return [...rows].map((own) => ({
    sender: call,
    slot: own.slot,
    group: own.group,
    kind: own.kind,
    text: own.text,
    first_heard: own.posted_at,
    last_heard: own.last_sent_at ?? own.posted_at,
    times_heard: Math.max(own.sent, 1),
    own,
  }));
}

/** What the board says of a bulletin of ours: how often it was sent and when it goes out next, "ended" once its schedule is over. */
export function ownMeta(own: OwnBulletinRow, nowMs: number): string {
  if (own.next_at === null) return own.sent === 0 ? sentText(0) : t("schedule.ended", { n: own.sent });
  return t("schedule.next", { n: own.sent, when: untilText(own.next_at, nowMs) });
}

export type PostKind = "bulletin" | "announcement" | "group";
type PostCommand = Extract<Command, { cmd: "bulletin_post" }>;

/** The kinds of what is posted, with the identifiers each has: a number for a bulletin and for a group bulletin, a capital letter for an announcement. */
export const POST_KINDS: { kind: PostKind; ids: string }[] = [
  { kind: "bulletin", ids: "0123456789" },
  { kind: "announcement", ids: "ABCDEFGHIJKLMNOPQRSTUVWXYZ" },
  { kind: "group", ids: "0123456789" },
];

/** What a kind of post is called in the choice of the compose box. */
export function kindTitle(kind: PostKind): string {
  return t(`bulletins.kind.${kind}`);
}
export const GROUP_MAX = LIMITS.bulletin.groupMax;

/** What the compose box holds: the kind, the identifier, the group of a group bulletin and the text. */
export interface PostDraft {
  kind: PostKind;
  id: string;
  group: string;
  text: string;
}

/** The identifiers a kind has. */
export function idsOf(kind: PostKind): string {
  return POST_KINDS.find((k) => k.kind === kind)?.ids ?? "";
}

/** The group as it is sent: capitals, no blanks. */
export function groupOf(text: string): string {
  return text.trim().toUpperCase();
}

/** The slot a draft is for: `BLN1`, `BLNA`, `BLN3HAMS`. */
export function slotOf(draft: PostDraft): string {
  return `BLN${draft.id}${draft.kind === "group" ? groupOf(draft.group) : ""}`;
}

/** Whether the group is one the daemon takes: one to five letters and digits. */
export function groupOk(text: string): boolean {
  return /^[A-Z0-9]{1,5}$/.test(groupOf(text));
}

/** Whether the text can be sent as it is: printable ASCII without `| ~ {`, at most as many characters as a message has. */
export function textOk(text: string): boolean {
  return /^[\x20-\x7e]+$/.test(text.trim()) && !/[|~{]/.test(text) && text.trim().length <= LIMITS.message.textMax;
}

/** How many characters more the text may have; negative when it is too long. */
export function charsLeft(text: string): number {
  return LIMITS.message.textMax - text.trim().length;
}

/** Whether Post is on: a text that fits and, for a group bulletin, a group. */
export function canPost(draft: PostDraft): boolean {
  return textOk(draft.text) && idsOf(draft.kind).includes(draft.id) && (draft.kind !== "group" || groupOk(draft.group));
}

/** The command that posts the draft; null while it cannot be posted. */
export function postCommand(draft: PostDraft): PostCommand | null {
  return canPost(draft) ? { cmd: "bulletin_post", slot: slotOf(draft), text: draft.text.trim() } : null;
}
