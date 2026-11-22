// The length a typed text may have, counted as the daemon counts it, and what a field keeps of
// typed input: one rule for every field with a counter ("12 left", LeftCounter.vue). Input beyond
// the limit is cut at the limit, never refused whole (a character that does not fit whole is not
// taken). A value already longer stays as it is, the counter shows how many are over, and typing
// can only shorten it. A composing keyboard (an IME, a phone's word entry) is let finish and fitted
// when composition ends. The daemon checks the value again.
import type { CountKind } from "@/lib/compose";
import { textBytes } from "@/lib/messages";
import { LIMITS } from "@/protocol/lists";

/**
 * How the daemon counts a text: characters as Python counts them (code points: an emoji is one), or
 * UTF-8 bytes.
 */
export type Measure = (text: string) => number;

export const characters: Measure = (text) => [...text].length;
export const bytes: Measure = textBytes;
/** Characters of the text without its end blanks, which the daemon cuts off before counting. */
export const trimmedCharacters: Measure = (text) => characters(text.trim());

/**
 * A field's limit: the most it may hold, how that is counted, and the unit the counter's title
 * names.
 */
export interface TextLimit {
  max: number;
  measure: Measure;
  kind: CountKind;
}

/** How much more the text may have; negative when it is already longer (the counter's "3 over"). */
export function leftOf(text: string, limit: TextLimit): number {
  return limit.max - limit.measure(text);
}

/**
 * What a field keeps when its text goes from `before` to `after`: `after` when it fits; else the
 * typed or pasted part (what `after` has between the text it shares with `before` at the start and
 * at the end) is cut from its end until the text fits, by whole characters. When `before` is
 * already over the limit, the text may not grow past it. `at` is where the caret goes after a cut:
 * the end of what was kept.
 */
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

/**
 * Each field's text from when a composition began, so the composed text is fitted against it, not
 * its own long end.
 */
const composedFrom = new WeakMap<EventTarget, string>();

/**
 * What a field with a limit keeps of an `input` or `compositionend` event: its text fitted as
 * `fitted` says, put back with the caret at the end of what was kept when it was cut. While a
 * composition is going on the field is left alone (cutting would eat a half-written character).
 * `before` is the field's text before the event.
 */
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

/**
 * A status template counted as the daemon checks it: each field it names ({freq}, {mode}) at its
 * widest value.
 */
const BRACES = /\{([^{}]*)\}/g;
const WIDEST: Readonly<Record<string, string>> = LIMITS.status.widest;
export const templateLength: Measure = (text) => characters(text.replace(BRACES, (whole, name: string) => WIDEST[name] ?? whole));

/**
 * The beacon comment limit: 43 characters, 36 when the PHG extension is sent (a power is set); the
 * daemon's Config.comment_limit.
 */
export function commentLimit(values: Readonly<Record<string, string>>): number {
  return (values["beacon/power_w"] ?? "").trim() === "" ? LIMITS.comment.max : LIMITS.comment.maxWithPhg;
}

/**
 * The limit of a typed setting for the form's values, or undefined without a counter: beacon
 * comment, status text and template.
 */
export function settingLimit(key: string, values: Readonly<Record<string, string>>): TextLimit | undefined {
  if (key === "station/comment") return { max: commentLimit(values), measure: characters, kind: "characters" };
  if (key === "station/status") return { max: LIMITS.status.max, measure: characters, kind: "characters" };
  if (key === "status/template") return { max: LIMITS.status.max, measure: templateLength, kind: "characters" };
  return undefined;
}
