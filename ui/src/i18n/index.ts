// The words of the page. `t(id, { name })` is the text of a catalogue entry (en.ts is the source, another language falls back to it for an id it lacks) in the language of the page; it reads the reactive `locale`, so
// whatever shows its result is drawn again when the language is changed. The language is the person's choice in Settings, kept in this browser (lib/storage.ts); until they choose it is the first of the browser's languages
// that the page has, else English. `<html lang>` follows it. Numbers and weekdays are written by Intl for the same language (`formatNumber`, `weekdayShort`).
import { readonly, ref } from "vue";
import type { MessageId } from "@/i18n/catalogue";
import { en } from "@/i18n/en";
import { LOCALES, PSEUDO, SOURCE, type LocaleInfo } from "@/i18n/locales";
import { fill, numberText, pick, type Message, type Params } from "@/i18n/message";
import { pseudoMessage } from "@/i18n/pseudo";
import { readStored, writeStored } from "@/lib/storage";

const STORED = "language";
/** The pseudo-locale is for development and the tests; the built page does not have it. */
const PSEUDO_ON = import.meta.env.DEV;

/** The languages the person can choose from, each with its own name. */
export function availableLocales(): readonly LocaleInfo[] {
  return PSEUDO_ON ? [...LOCALES, { code: PSEUDO, name: "Pseudo (en-XA)", messages: en }] : LOCALES;
}

const known = (code: string | null | undefined): code is string => code != null && availableLocales().some((l) => l.code === code);

/** The language for a list of language tags (`navigator.languages`): the first tag that is a language of the page, whole (`pt-BR`) or by its language (`de-AT` is `de`, `pt` is `pt-BR`); English when none is. */
export function detectLocale(languages: readonly string[]): string {
  for (const tag of languages) {
    const wanted = tag.toLowerCase();
    const whole = LOCALES.find((l) => l.code.toLowerCase() === wanted);
    if (whole) return whole.code;
    const language = wanted.split("-")[0];
    const near = LOCALES.find((l) => l.code.toLowerCase().split("-")[0] === language);
    if (near) return near.code;
  }
  return SOURCE;
}

const current = ref(SOURCE);
/** The code of the language of the page (reactive). */
export const locale = readonly(current);

/** Takes `code` for the language of the page (an unknown one is ignored); `remember` keeps it in this browser. */
export function setLocale(code: string, remember = false): void {
  if (!known(code)) return;
  current.value = code;
  if (typeof document !== "undefined") document.documentElement.lang = code;
  if (remember) writeStored(STORED, code);
}

/** The language at the start: the person's choice, kept in this browser, else the browser's own. */
export function startLocale(languages: readonly string[] = typeof navigator === "undefined" ? [] : navigator.languages): void {
  const stored = readStored(STORED);
  setLocale(known(stored) ? stored : detectLocale(languages));
}

/** The tag Intl is given: the pseudo-locale is English. */
function tag(): string {
  return current.value === PSEUDO ? SOURCE : current.value;
}

const pseudo = new Map<string, Message>();
function messageFor(id: MessageId): Message {
  if (current.value === PSEUDO) {
    let found = pseudo.get(id);
    if (!found) pseudo.set(id, (found = pseudoMessage(en[id])));
    return found;
  }
  return LOCALES.find((l) => l.code === current.value)?.messages[id] ?? en[id];
}

/** The text of a message in the language of the page. `params` are its {values}; a plural is chosen by `n`. */
export function t(id: MessageId, params: Params = {}): string {
  return fill(pick(messageFor(id), params, tag()), params, tag());
}

/** Whether the catalogue has this id (for an id made at run time, such as the code of an error). */
export function hasMessage(id: string): id is MessageId {
  return Object.hasOwn(en, id);
}

/** A number the way the language writes it, with `digits` decimals ("1.5", "1,5"); no thousands separator. */
export function formatNumber(n: number, digits?: number): string {
  return numberText(n, tag(), digits);
}

/** The short name of the weekday of a date, in the viewer's time: "Mon". */
export function weekdayShort(date: Date): string {
  return new Intl.DateTimeFormat(tag(), { weekday: "short" }).format(date);
}

/** The short name of the month of a date, in the viewer's time: "Oct". */
export function monthShort(date: Date): string {
  return new Intl.DateTimeFormat(tag(), { month: "short" }).format(date);
}

startLocale();
