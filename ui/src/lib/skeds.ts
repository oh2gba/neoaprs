// The sked board as the Skeds tab shows it and the form posts it. The daemon decides what a sked is and drops the ones that ended (neoaprs/skeds.py); these only arrange and word the rows (skeds with the same times and dial are one row that
// lists their calls), count the ones not seen, and hold the form to the rules the project's server holds a post to: the day is one of the next 30 UTC days, From and To are half hours, a To that is not after From is the next day (a sked is at
// most 24 hours long), the dial is written `7.0541 MHz USB`, the note is one line of at most 80 characters.
import { t, dayText } from "@/i18n";
import { untilText } from "@/lib/format";
import { joinCall, mayTransmitAs, splitCall } from "@/lib/calls";
import type { Command, SkedFrequency, SkedRow } from "@/protocol/protocol";

/** The longest note, in characters: the same as the board's. */
export const NOTE_MAX = 80;
/** The days the Day choice offers, today first. A sked may start 30 days ahead at the most; the last day's latest half hour is less than that after any moment of today. */
export const DAYS = 30;
const MINUTE = 60_000;
const HALF_HOUR = 30 * MINUTE;
const DAY_MS = 24 * 60 * MINUTE;

/** The half hours of a day, `00:00` to `23:30`: the choices of From and To. */
export const TIMES: readonly string[] = Array.from({ length: 48 }, (_, i) => `${String(Math.floor(i / 2)).padStart(2, "0")}:${i % 2 === 0 ? "00" : "30"}`);

/** What a dial looks like as the page names it: `7.0541 MHz USB`. */
const DIAL = /^(\d{1,2}\.\d{3,4}) ?MHz (USB|LSB)$/i;

/** A dial written in the form the board takes (`7.0541 MHz USB`) from what was typed (`7.0541mhz usb`, a blank too much); null for text that is none. */
export function dialOf(text: string): string | null {
  const found = DIAL.exec(text.trim().replace(/\s+/g, " "));
  return found === null ? null : `${found[1] ?? ""} MHz ${(found[2] ?? "").toUpperCase()}`;
}

/** An instant as the wire writes it: UTC, whole seconds, `2026-11-14T18:00:00Z`. */
function wire(ms: number): string {
  return `${new Date(ms).toISOString().slice(0, 19)}Z`;
}

/** The UTC day of an instant, `2026-11-14`. */
export function utcDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** The next `DAYS` UTC days from `nowMs`, today first: the value of each (`2026-11-14`) and the day written in the language of the page ("Sat 14 Nov"). */
export function dayChoices(nowMs: number): { value: string; label: string }[] {
  const start = Date.parse(`${utcDay(nowMs)}T00:00:00Z`);
  return Array.from({ length: DAYS }, (_, i) => ({ value: utcDay(start + i * DAY_MS), label: dayText(new Date(start + i * DAY_MS), true) }));
}

/** What the form holds: the UTC day, the two half hours, the dial (one the project suggests, or typed when `typed`) and the note. */
export interface SkedDraft {
  day: string;
  from: string;
  to: string;
  dial: string;
  typed: boolean;
  note: string;
}

/** The form as it opens: from the next half hour for an hour, on the first dial the project suggests. */
export function startDraft(nowMs: number, frequencies: readonly SkedFrequency[]): SkedDraft {
  const start = Math.ceil(nowMs / HALF_HOUR) * HALF_HOUR;
  const clock = (ms: number): string => new Date(ms).toISOString().slice(11, 16);
  return {
    day: utcDay(start),
    from: clock(start),
    to: clock(start + 2 * HALF_HOUR),
    dial: frequencies[0]?.dial ?? "",
    typed: frequencies.length === 0,
    note: "",
  };
}

/** The two instants of the draft in ms since 1970; To at or before From is the next day. Null when the day or a time is not one of the choices. */
export function instants(draft: SkedDraft): { from: number; to: number } | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.day) || !TIMES.includes(draft.from) || !TIMES.includes(draft.to)) return null;
  const from = Date.parse(`${draft.day}T${draft.from}:00Z`);
  const to = Date.parse(`${draft.day}T${draft.to}:00Z`);
  return Number.isNaN(from) || Number.isNaN(to) ? null : { from, to: to <= from ? to + DAY_MS : to };
}

/** The dial the draft names, in the form of the board; null when it is not one. */
export function draftDial(draft: SkedDraft): string | null {
  return dialOf(draft.dial);
}

/** Whether the sked has ended already (or the draft is not one): Post is off, and the To of the form says so. */
export function ended(draft: SkedDraft, nowMs: number): boolean {
  const at = instants(draft);
  return at === null || at.to <= nowMs;
}

/** Whether the sked would start more than the 30 days ahead the board takes (the Day choice does not offer such a day). */
export function tooFar(draft: SkedDraft, nowMs: number): boolean {
  const at = instants(draft);
  return at !== null && at.from - nowMs > DAYS * DAY_MS;
}

/** Whether the note fits: at most `NOTE_MAX` characters once trimmed. */
function noteOk(note: string): boolean {
  return [...note.trim()].length <= NOTE_MAX;
}

/** How many characters more the note may have; negative when it is too long. */
export function noteLeft(note: string): number {
  return NOTE_MAX - [...note.trim()].length;
}

/** Whether the form is right: a day and times of the choices, not ended, not too far, a dial of the form and a note that fits. */
export function draftOk(draft: SkedDraft, nowMs: number): boolean {
  return !ended(draft, nowMs) && !tooFar(draft, nowMs) && draftDial(draft) !== null && noteOk(draft.note);
}

/** The command that posts the draft (the call is the daemon's setting, never the page's); null while the form is not right. */
export function postCommand(draft: SkedDraft, nowMs: number): Extract<Command, { cmd: "sked_post" }> | null {
  const at = instants(draft);
  const dial = draftDial(draft);
  if (at === null || dial === null || !draftOk(draft, nowMs)) return null;
  return { cmd: "sked_post", from: wire(at.from), to: wire(at.to), dial, note: draft.note.trim() };
}

/** Whether the call is one a sked may be posted under: set, of an amateur's shape and no placeholder. */
export function mayPostAs(call: string | null): boolean {
  return call !== null && mayTransmitAs(call);
}

/** A row of the board for the page: skeds with the same times and dial are one, which lists the calls (ours among them) and has the id of each. */
export interface SkedGroup {
  key: string;
  from: string;
  to: string;
  dial: string;
  rows: SkedRow[];
  ours: SkedRow[];
}

/** The skeds to come in rows, the nearest first: a sked whose end has passed by the page's clock is left out (the daemon drops them too, but not at the second), the ones with the same times and dial are one row. */
export function groups(rows: Iterable<SkedRow>, nowMs: number): SkedGroup[] {
  const found = new Map<string, SkedGroup>();
  for (const row of rows) {
    if (!(Date.parse(row.to) > nowMs)) continue;
    const key = `${row.from}|${row.to}|${row.dial}`;
    const group = found.get(key) ?? { key, from: row.from, to: row.to, dial: row.dial, rows: [], ours: [] };
    group.rows.push(row);
    if (row.ours) group.ours.push(row);
    found.set(key, group);
  }
  return [...found.values()].sort((a, b) => Date.parse(a.from) - Date.parse(b.from) || Date.parse(a.to) - Date.parse(b.to) || a.dial.localeCompare(b.dial));
}

/** Whether a call is on the row already (a row of our call that this installation did not post counts: Join would be a second one). */
export function hasCall(group: SkedGroup, call: string | null): boolean {
  if (call === null) return false;
  const { base, ssid } = splitCall(call);
  return group.rows.some((r) => r.call === joinCall(base, ssid));
}

/** The calls on a row, in the order the board has them. */
export function callsOf(group: SkedGroup): string[] {
  return group.rows.map((r) => r.call);
}

/** The note of a row on one line: the one note, or the notes with the call that wrote each when the row has several. Empty when nobody wrote one. */
export function noteOf(group: SkedGroup): string {
  const written = group.rows.filter((r) => r.note !== "");
  return written.length === 1 && group.rows.length === 1 ? (written[0]?.note ?? "") : written.map((r) => `${r.call}: ${r.note}`).join("; ");
}

const clock = (d: Date, utc: boolean): string =>
  utc ? d.toISOString().slice(11, 16) : `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

/** The two ends written for a place in a sentence: "Sat 14 Nov 18:00" and "20:00", the end with its day when it is another one. */
function ends(from: string, to: string, utc: boolean): { from: string; to: string } {
  const start = new Date(from);
  const end = new Date(to);
  const day = (d: Date): string => dayText(d, utc);
  return { from: `${day(start)} ${clock(start, utc)}`, to: day(start) === day(end) ? clock(end, utc) : `${day(end)} ${clock(end, utc)}` };
}

/** When a sked is: "Sat 14 Nov 18:00 to 20:00 UTC" (the end with its day when it is the next one). */
export function whenText(from: string, to: string): string {
  return t("skeds.when", ends(from, to, true));
}

/** The same in the viewer's own time, for a title: "Your time: Sat 14 Nov 20:00 to 22:00". */
export function localText(from: string, to: string): string {
  return t("skeds.local", ends(from, to, false));
}

/** How long until a sked starts, "in 3 h", "now" while it runs. */
export function inText(from: string, nowMs: number): string {
  return untilText(from, nowMs);
}

/** How many of the others' skeds are not seen yet (`seen` is the ids that were); ours are never new. */
export function newCount(rows: Iterable<SkedRow>, seen: ReadonlySet<string>): number {
  let count = 0;
  for (const row of rows) if (!row.ours && !seen.has(row.id)) count++;
  return count;
}
