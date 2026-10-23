// The pseudo-locale `en-XA`, for development and the tests only: every message of the English catalogue with accents on its letters, about a third longer and in brackets, "Send" becomes "[!! Śéñđ ~ !!]". A text of the page that
// is still plain English (it does not come through the catalogue) stands out at once, and a layout that does not take longer words shows. The values `{name}` are left alone.
import { TOKEN, type Message, type Plural, type Select } from "@/i18n/message";

const FROM = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
const TO = "áƀçđéƒĝĥíĵķļɱñóþǫŕśţúṽŵẋýžÁßÇĐÉFĜĤÍĴĶĻMÑÓÞQŖŚŢÚṼŴẊÝŽ";
const ACCENTED = new Map([...FROM].map((letter, i) => [letter, TO[i] ?? letter]));
/** About a third more characters than the English. */
const EXTRA = 0.35;

function accent(text: string): string {
  return [...text].map((c) => ACCENTED.get(c) ?? c).join("");
}

/** One text: accented outside its `{name}`, a little longer, in `[!! ... !!]`. */
export function pseudoText(text: string): string {
  let body = "";
  let last = 0;
  for (const m of text.matchAll(TOKEN)) {
    body += accent(text.slice(last, m.index)) + m[0];
    last = m.index + m[0].length;
  }
  body += accent(text.slice(last));
  return `[!! ${body}${" ~".repeat(Math.ceil((text.length * EXTRA) / 2))} !!]`;
}

/** An entry with all its texts made pseudo. */
export function pseudoMessage(message: Message): Message {
  if (typeof message === "string") return pseudoText(message);
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(message)) if (value !== undefined) out[key] = key === "select" ? value : pseudoText(value);
  return out as Plural | Select;
}
