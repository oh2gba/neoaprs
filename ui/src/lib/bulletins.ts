// The Bulletins tab's board: rows of the topic `bulletins` grouped into announcements, bulletins,
// group messages and weather service bulletins, newest first, plus naming and the new-row count.
// The daemon decides what a bulletin is and that none ages out (neoaprs/bulletin.py).
import { t } from "@/i18n";
import { ageText, untilText } from "@/lib/format";
import { sentText } from "@/lib/ownobjects";
import { textRefusal } from "@/lib/recipients";
import { LIMITS } from "@/protocol/lists";
import type { BulletinRow, Command, OwnBulletinRow, PostHours } from "@/protocol/protocol";

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
export type PostCommand = Extract<Command, { cmd: "bulletin_post" }>;

/** The post kinds, in the order of the Kind list. */
export const POST_KINDS: readonly PostKind[] = ["bulletin", "announcement", "group"];

/** The identifiers of a kind's slots: digits for bulletins, capitals for announcements. */
const IDS: Record<PostKind, string> = {
  bulletin: "0123456789",
  announcement: "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  group: "0123456789",
};

/** The compose box's name for a kind: "Bulletin". */
export function kindTitle(kind: PostKind): string {
  return t(`bulletins.kind_name.${kind}`);
}

/** The Sent for choices of a kind in hours, from the daemon (LIMITS.bulletin, neoaprs/ownbulletin.py). */
export function sentForChoices(kind: PostKind): readonly number[] {
  return kind === "announcement" ? LIMITS.bulletin.announcementHours : LIMITS.bulletin.hours;
}

/** A Sent for choice in the page's words: "4 hours", an announcement's in days ("3 days"). */
export function sentForText(kind: PostKind, hours: number): string {
  return kind === "announcement" ? t("bulletins.tip.days", { n: hours / 24 }) : t("bulletins.tip.hours", { n: hours });
}

/**
 * The Sent for a new post of the kind starts with: the station's (`status.new_bulletin_hours`) while
 * it is one of the kind's choices, else the daemon's default.
 */
export function rememberedHours(kind: PostKind, remembered: PostHours | null | undefined): number {
  const hours = remembered?.[kind];
  if (hours !== undefined && sentForChoices(kind).includes(hours)) return hours;
  return kind === "announcement" ? LIMITS.bulletin.defaultAnnouncementHours : LIMITS.bulletin.defaultHours;
}

export const GROUP_MAX = LIMITS.bulletin.groupMax;

/** What the compose box holds; `hours` is null until chosen, so it follows the station's. */
export interface PostDraft {
  kind: PostKind;
  hours: number | null;
  group: string;
  text: string;
}

/** The group as sent: capitals, no blanks. */
export function groupOf(text: string): string {
  return text.trim().toUpperCase();
}

const GROUP = new RegExp(`^[A-Z0-9]{1,${GROUP_MAX}}$`);

/** Whether the daemon accepts the group: 1 to `GROUP_MAX` letters and digits. */
export function groupOk(text: string): boolean {
  return GROUP.test(groupOf(text));
}

/**
 * The slot a new post of the kind (of the group) takes: the lowest that none of ours (`taken`, ended
 * ones included) holds; null when all are taken or the group is no group. The daemon decides; this
 * mirrors it (ui/src/protocol/vectors.json).
 */
export function freeSlot(kind: PostKind, group: string, taken: Iterable<string>): string | null {
  const name = kind === "group" ? groupOf(group) : "";
  if (kind === "group" && !groupOk(name)) return null;
  const held = new Set(taken);
  for (const id of IDS[kind]) if (!held.has(`BLN${id}${name}`)) return `BLN${id}${name}`;
  return null;
}

/** Whether the text can be sent: printable ASCII without `| ~ {`, within the message length. */
export function textOk(text: string): boolean {
  const trimmed = text.trim();
  return trimmed !== "" && textRefusal(trimmed) === null && trimmed.length <= LIMITS.message.textMax;
}

/**
 * Whether Post is enabled: a fitting text, for a group bulletin a group, and a free slot of the kind
 * among our posts (`own`), which are fewer than the daemon takes.
 */
export function canPost(draft: PostDraft, own: ReadonlyMap<string, OwnBulletinRow>): boolean {
  return (
    textOk(draft.text) &&
    (draft.kind !== "group" || groupOk(draft.group)) &&
    own.size < LIMITS.bulletin.postedMax &&
    freeSlot(draft.kind, draft.group, own.keys()) !== null
  );
}

/** The command that posts the draft for `hours`, on `radios` when given; null if it cannot be posted. */
export function postCommand(
  draft: PostDraft,
  hours: number,
  own: ReadonlyMap<string, OwnBulletinRow>,
  radios?: number[],
): PostCommand | null {
  if (!canPost(draft, own)) return null;
  return {
    cmd: "bulletin_post",
    kind: draft.kind,
    ...(draft.kind === "group" ? { group: groupOf(draft.group) } : {}),
    text: draft.text.trim(),
    hours,
    ...(radios === undefined ? {} : { radios }),
  };
}
