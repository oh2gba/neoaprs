// A radio's name stands in a text in two forms only, so that no language has to inflect it (en/radio.ts, the plan's section "Texts"): the name and a colon ("{name}: {line}"), or after the language's noun for a radio,
// which carries the grammar ("Heard on radio {name}", "das Funkgerät {name}", "無線機「{name}」"). This holds, in every catalogue, every text whose value is a radio's name: the refusals that name a radio (the daemon
// passes its id, `radio` or `held_by`) and the words of the radios. A text not translated yet (untranslated.json) is the English, and holds the English noun.
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";
import untranslated from "@/i18n/untranslated.json";
import daemon from "@/protocol/errors.json";

/** Each language's noun for a radio, the device (the translators' glossary): the start of the word, so that a case ending (fi "radiolla", "radiota") is the noun still. */
const NOUN: Record<string, string> = {
  en: "radio",
  de: "funkgerät",
  es: "radio",
  fi: "radio",
  fr: "radio",
  it: "radio",
  ja: "無線機",
  nl: "radio",
  "pt-BR": "rádio",
};
/** The values that are a radio's name (or, for `radio`, its number after the noun). */
const NAME = /\{(name|radio|holder)\}/g;
/** The ids of the words of the radios whose values name a radio. */
const WORDS = [
  /^radio\./,
  /^pill\.radio_named/,
  /^(chain|objects)\.sent_on$/,
  /^packets\.came_by\.radio$/,
  /^(messages|email)\.radio_title$/,
  /^route\.radio_auto$/,
  /^settings\.path\.on_radio$/,
];
/** The refusals whose name is a radio's: the daemon passes the radio's id with them. The `name_*` ones quote the name typed, which is no radio's yet. */
const REFUSALS = Object.entries(daemon as Record<string, { params: string[] }>)
  .filter(([code, r]) => code.startsWith("radio.") && !code.startsWith("radio.name_") && (r.params.includes("radio") || r.params.includes("held_by")))
  .map(([code]) => `error.${code}`);
const IDS = Object.keys(en).filter((id) => REFUSALS.includes(id) || WORDS.some((re) => re.test(id)));
const LISTED = untranslated as Record<string, string[]>;

/** Whether the name at `at` stands in one of the two forms: the whole text, the start of the text before a colon, after the noun, or after a label's colon at the end ("Automatic: {name}"). */
function inForm(text: string, at: number, length: number, nouns: string[], cjk: boolean): boolean {
  const before = text.slice(0, at);
  const after = text.slice(at + length);
  if (before === "" && (after === "" || /^\s*:/.test(after))) return true;
  if (after === "" && /:\s*$/.test(before)) return true;
  return nouns.some((noun) => new RegExp(`${cjk ? "" : "(?<!\\p{L})"}${noun}\\p{L}*[\\s「]*$`, "iu").test(before));
}

function offForm(code: string, messages: Record<string, Message>): string[] {
  const nouns = (id: string) => [NOUN[code] ?? NOUN.en ?? "radio", ...((LISTED[code] ?? []).includes(id) ? [NOUN.en ?? "radio"] : [])];
  return IDS.flatMap((id) =>
    texts(messages[id] ?? "")
      .filter((text) => [...text.matchAll(NAME)].some((m) => !inForm(text, m.index, m[0].length, nouns(id), code === "ja")))
      .map((text) => `${id}: ${text}`),
  );
}

describe("a radio's name in a text", () => {
  it("is looked at in the refusals that name a radio and in the words of the radios", () => {
    expect(REFUSALS).toEqual(
      expect.arrayContaining(["error.radio.not_connected", "error.radio.off", "error.radio.resource_held", "error.radio.type_kind", "error.radio.unknown"]),
    );
    expect(IDS).toEqual(expect.arrayContaining(["radio.heard_on", "radio.line", "chain.sent_on", "pill.radio_named", "error.radio.no_line"]));
    expect(IDS.filter((id) => id.startsWith("error.radio.name_"))).toEqual([]);
  });

  for (const locale of LOCALES)
    it(`stands in ${locale.name} as the name and a colon, or after the noun for a radio`, () => {
      expect(offForm(locale.code, locale.messages as Record<string, Message>)).toEqual([]);
    });

  it("is told apart from a text in neither form", () => {
    const at = (text: string) => inForm(text, text.indexOf("{name}"), 6, ["radio"], false);
    expect([at("{name}: not connected"), at("Heard on radio {name}"), at("Automatic: {name}"), at("{name}")]).toEqual([true, true, true, true]);
    expect([at("the {name} radio is off"), at("that device is in use by {name}: choose another"), at("the stereo {name} is off")]).toEqual([
      false,
      false,
      false,
    ]);
  });
});
