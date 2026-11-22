// The Bulletins tab's board: rows of the topic `bulletins` grouped into announcements, bulletins,
// group messages and weather service bulletins, newest first, plus naming and the new-row count.
// The daemon decides what a bulletin is and that none ages out (neoaprs/bulletin.py).
import { t } from "@/i18n";
import { ageText, untilText } from "@/lib/format";
import { sentText } from "@/lib/ownobjects";
import { textRefusal } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";
import type { BulletinRow, Command, OwnBulletinRow } from "@/protocol/protocol";

type Kind = BulletinRow["kind"];

/**
 * A board row: heard, or (`own`) posted by us. For our own the sender is our call, `first_heard` is
 * the post time, `last_heard` the last send and `times_heard` the send count.
 */
export interface BoardEntry extends BulletinRow {
  own?: OwnBulletinRow;
}

interface Section<T extends BulletinRow> {
  kind: Kind;
  title: string;
  rows: T[];
}

const SECTIONS: readonly Kind[] = ["announcement", "bulletin", "group", "nws"];

/** The board in four sections, each newest first by last hearing; empty sections are left out. */
export function sections<T extends BulletinRow>(rows: Iterable<T>): Section<T>[] {
  const all = [...rows].sort((a, b) =>
    a.last_heard === b.last_heard
      ? a.sender.localeCompare(b.sender) || a.slot.localeCompare(b.slot)
      : a.last_heard < b.last_heard
        ? 1
        : -1,
  );
  return SECTIONS.map((kind) => ({
    kind,
    title: t(`bulletins.section.${kind}`),
    rows: all.filter((r) => r.kind === kind),
  })).filter((s) => s.rows.length > 0);
}

/** What a row is addressed to: the group of a group bulletin ("HAMS"), else the slot ("BLN1"). */
export function targetOf(row: BulletinRow): string {
  return row.group === "" ? row.slot : row.group;
}

/** How often and how long ago a bulletin was heard: "heard 3 times, 3 min ago". */
export function heardText(times: number, lastHeard: string | null, nowMs: number): string {
  return t("bulletins.heard", { n: times, span: ageText(lastHeard, nowMs) });
}

/** When the newest text was first heard, in ms since 1970; 0 for an empty board. */
export function newestFirstHeard(rows: Iterable<BulletinRow>): number {
  let newest = 0;
  for (const row of rows) newest = Math.max(newest, Date.parse(row.first_heard) || 0);
  return newest;
}

/** How many rows have a text first heard after `seenUpTo` (new bulletins and changed texts). */
export function newCount(rows: Iterable<BulletinRow>, seenUpTo: number): number {
  let count = 0;
  for (const row of rows) if ((Date.parse(row.first_heard) || 0) > seenUpTo) count++;
  return count;
}

/** Our bulletins as board rows under our call. */
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

/** The board text for our bulletin: send count and next send, or "ended" once finished. */
export function ownMeta(own: OwnBulletinRow, nowMs: number): string {
  if (own.next_at === null) return own.sent === 0 ? sentText(0) : t("schedule.ended", { n: own.sent });
  return t("schedule.next", { n: own.sent, when: untilText(own.next_at, nowMs) });
}

export type PostKind = "bulletin" | "announcement" | "group";
type PostCommand = Extract<Command, { cmd: "bulletin_post" }>;

/** The post kinds with their identifiers: digits for bulletins, capitals for announcements. */
export const POST_KINDS: { kind: PostKind; ids: string }[] = [
  { kind: "bulletin", ids: "0123456789" },
  { kind: "announcement", ids: "ABCDEFGHIJKLMNOPQRSTUVWXYZ" },
  { kind: "group", ids: "0123456789" },
];

/**
 * How long a post of each kind is sent (hours; days for an announcement), from the daemon's plan
 * (LIMITS.bulletin, neoaprs/decay.py). A group bulletin is sent like a bulletin.
 */
const REPEATED: Record<PostKind, number> = {
  bulletin: LIMITS.bulletin.repeatHours,
  announcement: LIMITS.bulletin.announcementRepeatDays,
  group: LIMITS.bulletin.repeatHours,
};

/** The compose box's name for a kind: "Bulletin (sent for 4 hours)". */
export function kindTitle(kind: PostKind): string {
  return t(`bulletins.kind.${kind}`, { n: REPEATED[kind] });
}
export const GROUP_MAX = LIMITS.bulletin.groupMax;

/** What the compose box holds. */
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

/** The group as sent: capitals, no blanks. */
export function groupOf(text: string): string {
  return text.trim().toUpperCase();
}

/** The slot of a draft: `BLN1`, `BLNA`, `BLN3HAMS`. */
export function slotOf(draft: PostDraft): string {
  return `BLN${draft.id}${draft.kind === "group" ? groupOf(draft.group) : ""}`;
}

const GROUP = new RegExp(`^[A-Z0-9]{1,${GROUP_MAX}}$`);

/** Whether the daemon accepts the group: 1 to `GROUP_MAX` letters and digits. */
export function groupOk(text: string): boolean {
  return GROUP.test(groupOf(text));
}

/** Whether the text can be sent: printable ASCII without `| ~ {`, within the message length. */
export function textOk(text: string): boolean {
  const trimmed = text.trim();
  return trimmed !== "" && textRefusal(trimmed) === null && trimmed.length <= LIMITS.message.textMax;
}

/** How many characters more the text may have; negative when too long. */
export function charsLeft(text: string): number {
  return LIMITS.message.textMax - text.trim().length;
}

/** Whether Post is enabled: a fitting text and, for a group bulletin, a group. */
export function canPost(draft: PostDraft): boolean {
  return textOk(draft.text) && idsOf(draft.kind).includes(draft.id) && (draft.kind !== "group" || groupOk(draft.group));
}

/** The command that posts the draft; null if it cannot be posted. */
export function postCommand(draft: PostDraft): PostCommand | null {
  return canPost(draft) ? { cmd: "bulletin_post", slot: slotOf(draft), text: draft.text.trim() } : null;
}
