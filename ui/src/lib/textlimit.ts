// The length a typed text may have, counted the way the daemon counts it, and what a field keeps of what is typed into it: one rule for every field with a counter ("12 left", LeftCounter.vue). A field never takes
// more than the daemon takes: what is typed or pasted beyond the room is cut at the limit (a letter that does not fit whole is not taken), never refused whole; a value that is already longer (stored by an older
// version, or the limit shrank when another setting changed: a power, the padlock, a course) stays as it is, the counter says how many are over, and typing can then only make it shorter. A keyboard that
// composes (an IME writing Japanese, a phone's keyboard writing a word) is let finish: what it composed is fitted when it ends. The daemon checks the value again itself.
import type { CountKind } from "@/lib/compose";
import { textBytes } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";

/** How the daemon counts a text: characters as Python counts them (code points: an emoji is one, as is ä), or the bytes of its UTF-8. */
export type Measure = (text: string) => number;

export const characters: Measure = (text) => [...text].length;
export const bytes: Measure = textBytes;
/** Characters of the text without its blanks at the ends, which the daemon cuts off before it counts (a bulletin, the note of a sked, the comment of an object). */
export const trimmedCharacters: Measure = (text) => characters(text.trim());

/** A field's limit: the most it may hold, how that is counted, and what the counter's title calls the unit. */
export interface TextLimit {
  max: number;
  measure: Measure;
  kind: CountKind;
}

/** How much more the text may have; negative when it is already longer (the counter's "3 over"). */
export function leftOf(text: string, limit: TextLimit): number {
  return limit.max - limit.measure(text);
}

/** What a field keeps when its text goes from `before` to `after`: `after` when it fits; else the part that was typed or pasted (what `after` has between what it shares with `before` at its start and at its end) is
 * cut from its end until the text fits, by whole characters. When `before` is already over the limit, the text may not grow past it. `at` is where the caret goes when the text was cut: the end of what was kept of the typing. */
export function fitted(before: string, after: string, limit: TextLimit): { text: string; at?: number } {
  const bound = Math.max(limit.max, limit.measure(before));
  if (limit.measure(after) <= bound) return { text: after };
  const old = [...before];
  const now = [...after];
  let head = 0;
  while (head < old.length && head < now.length && old[head] === now[head]) head++;
  let tail = 0;
  while (tail < old.length - head && tail < now.length - head && old[old.length - 1 - tail] === now[now.length - 1 - tail]) tail++;
  const start = now.slice(0, head).join("");
  const end = now.slice(now.length - tail).join("");
  const typed = now.slice(head, now.length - tail);
  let keep = typed.length;
  while (keep > 0 && limit.measure(start + typed.slice(0, keep).join("") + end) > bound) keep--;
  const kept = start + typed.slice(0, keep).join("");
  return { text: kept + end, at: kept.length };
}

/** The text of each field as it was when a composition began (an IME's, a phone keyboard's word), so that what it composed is fitted against the text before it, not against its own over-long end. */
const composedFrom = new WeakMap<EventTarget, string>();

/** What a field with a limit keeps of an `input` (or `compositionend`) event: its text fitted as `fitted` says, put back into the field with the caret at the end of what was kept when it was cut. While a
 * composition is going on the field is left alone (cutting it would eat a half-written character); it is fitted when the composition ends. `before` is the field's text before the event. */
export function typedInto(event: Event, before: string, limit: TextLimit): string {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) return before;
  if (event instanceof InputEvent && event.isComposing) {
    if (!composedFrom.has(target)) composedFrom.set(target, before);
    return target.value;
  }
  const from = composedFrom.get(target) ?? before;
  composedFrom.delete(target);
  const kept = fitted(from, target.value, limit);
  if (kept.at !== undefined) {
    target.value = kept.text;
    target.setSelectionRange(kept.at, kept.at);
  }
  return kept.text;
}

/** A status template counts as the daemon checks it: each field it names ({freq}, {mode}) as the widest value it can come out as, so that what is sent always fits. */
const BRACES = /\{([^{}]*)\}/g;
const WIDEST: Readonly<Record<string, string>> = LIMITS.status.widest;
export const templateLength: Measure = (text) => characters(text.replace(BRACES, (whole, name: string) => WIDEST[name] ?? whole));

/** The comment of the beacon: 43 characters, 36 when the PHG extension is sent (a power is set), as the daemon's Config.comment_limit. */
export function commentLimit(values: Readonly<Record<string, string>>): number {
  return (values["beacon/power_w"] ?? "").trim() === "" ? LIMITS.comment.max : LIMITS.comment.maxWithPhg;
}

/** The limit of a typed setting for the values the form holds, or undefined for a setting with no counter: the beacon's comment, the status text and the status template. */
export function settingLimit(key: string, values: Readonly<Record<string, string>>): TextLimit | undefined {
  if (key === "station/comment") return { max: commentLimit(values), measure: characters, kind: "characters" };
  if (key === "station/status") return { max: LIMITS.status.max, measure: characters, kind: "characters" };
  if (key === "status/template") return { max: LIMITS.status.max, measure: templateLength, kind: "characters" };
  return undefined;
}
