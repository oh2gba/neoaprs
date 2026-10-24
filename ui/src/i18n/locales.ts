// The languages of the page, each with its own name (the name is never translated: a person who cannot read the page finds their language by it). English is the source of the others.
//
// To add a language: a file `xx.ts` here that exports its catalogue (`export const xx: Catalogue = { ... }`, every id of en.ts), and its import and one line in LOCALES. The browser's languages are tried in order against
// the codes of LOCALES (`detectLocale` in index.ts), English when none fits. A code is a language tag, `de`, `pt-BR`.
import type { Catalogue } from "@/i18n/catalogue";
import { de } from "@/i18n/de";
import { en } from "@/i18n/en";
import { fr } from "@/i18n/fr";

export interface LocaleInfo {
  /** A language tag: `de`, `pt-BR`. */
  readonly code: string;
  /** The language's name in itself: "Deutsch". */
  readonly name: string;
  readonly messages: Catalogue;
}

export const LOCALES: readonly LocaleInfo[] = [
  { code: "en", name: "English", messages: en },
  { code: "de", name: "Deutsch", messages: de },
  { code: "fr", name: "Français", messages: fr },
];

/** The language every missing message falls back to. */
export const SOURCE = "en";

/** The pseudo-locale of development and the tests (pseudo.ts): English made long and accented, so that a text that did not come through the catalogue shows. It is not offered in the built page. */
export const PSEUDO = "en-XA";
