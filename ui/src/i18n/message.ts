// What a catalogue entry is and how it becomes text: pure functions of the entry, the values and a locale (the current locale and the state are in index.ts).
//
//   "Hello {name}"                                     a string; {name} is a value (a number is written the way the locale writes numbers, without a thousands separator)
//   { one: "{n} message", other: "{n} messages" }      a plural, chosen by the value `n` with Intl.PluralRules (zero, one, two, few, many, other); "=0" is an exact number
//   { select: "kind", object: "...", other: "..." }    a choice by the text of a value (a number is compared as text)
// `{{` and `}}` are a literal `{` and `}`.

export type Params = Readonly<Record<string, string | number>>;

type PluralForm = "zero" | "one" | "two" | "few" | "many" | "other";
export type Plural = { readonly [form in PluralForm | `=${number}`]?: string } & { readonly other: string };
export type Select = { readonly select: string; readonly other: string } & { readonly [value: string]: string };
export type Message = string | Plural | Select;

/** The placeholders of a text: `{{`, `}}` and `{name}`. */
export const TOKEN = /\{\{|\}\}|\{(\w+)\}/g;

const rules = new Map<string, Intl.PluralRules>();
function pluralRules(locale: string): Intl.PluralRules {
  let found = rules.get(locale);
  if (!found) rules.set(locale, (found = new Intl.PluralRules(locale)));
  return found;
}

const numbers = new Map<string, Intl.NumberFormat>();
/** A number as the locale writes it: `digits` decimals (as many as the number has when undefined), no thousands separator. */
export function numberText(n: number, locale: string, digits?: number): string {
  const key = `${locale}/${digits ?? ""}`;
  let format = numbers.get(key);
  if (!format) {
    const fixed = digits === undefined ? { maximumFractionDigits: 20 } : { minimumFractionDigits: digits, maximumFractionDigits: digits };
    numbers.set(key, (format = new Intl.NumberFormat(locale, { useGrouping: false, ...fixed })));
  }
  return format.format(n);
}

/** The text of an entry for these values: the form of a plural or the branch of a select that fits, else `other`. */
export function pick(message: Message, params: Params, locale: string): string {
  if (typeof message === "string") return message;
  if ("select" in message && typeof message.select === "string") {
    const value = String(params[message.select] ?? "");
    return value === "select" ? message.other : (message[value] ?? message.other);
  }
  const forms = message as Plural;
  const n = Number(params["n"]);
  if (Number.isNaN(n)) return forms.other;
  return forms[`=${n}`] ?? forms[pluralRules(locale).select(n)] ?? forms.other;
}

/** The text with its `{name}` replaced by the values (a name that is not given stays as it is, so that a missing value is seen). */
export function fill(text: string, params: Params, locale: string): string {
  return text.replace(TOKEN, (whole, name: string | undefined) => {
    if (name === undefined) return whole === "{{" ? "{" : "}";
    const value = params[name];
    if (value === undefined) return whole;
    return typeof value === "number" ? numberText(value, locale) : value;
  });
}

/** The names of the values a text asks for, in the order they appear. */
export function placeholders(text: string): string[] {
  return [...text.matchAll(TOKEN)].flatMap((m) => (m[1] === undefined ? [] : [m[1]]));
}

/** Every text of an entry (a string, the forms of a plural, the branches of a select). */
export function texts(message: Message): string[] {
  if (typeof message === "string") return [message];
  return Object.entries(message)
    .filter(([key, value]) => key !== "select" && typeof value === "string")
    .map(([, value]) => value as string);
}
