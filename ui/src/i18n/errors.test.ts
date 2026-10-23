// The sentences of the daemon's refusals on the page: ui/src/protocol/errors.json is what the daemon says (written from its source by scripts/gen-protocol.py), en/errors.ts is what the page says for the same code. Every code the
// daemon has a sentence for has one on the page, built of the values the daemon passes (and the lists the page adds), and it reads as the daemon's sentence does.
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { errorLine, errorReason } from "@/i18n/errortext";
import { fill, placeholders, pick, texts, type Message, type Params } from "@/i18n/message";
import daemon from "@/protocol/errors.json";

interface Refusal {
  params: string[];
  text: string[];
}
const CODES = daemon as Record<string, Refusal>;
/** What the page puts in itself (errortext.ts). */
const ADDED = ["profiles", "settings", "forbidden", "name_forbidden"];
/** Refusals with a sentence the page cannot make: the daemon's own words are a detail it does not pass on (a parser's message, a list of the topics). They are shown in the daemon's English. */
const TEXT_ONLY = ["not_json", "topic.unknown"];
/** The values a sentence is tried with when it chooses by one of them. */
const VARIANTS: Record<string, Record<string, string[]>> = {
  "object.name_length": { kind: ["object", "item"] },
  "object.comment_length": { motion: ["0", "1"] },
  "message.not_ascii": { chars: ["", "é"] },
};

const message = (code: string): Message | undefined => (en as Record<string, Message>)[`error.${code}`];

const escape = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The regular expression a daemon sentence makes: its text, the sample where it has `{name}`, anything where it has `{*}`. */
function pattern(template: string, sample: Params): RegExp {
  const parts = template.replaceAll("{*}", "\uE000").split(/(\{\{|\}\}|\{\w+\}|\uE000)/);
  const source = parts
    .map((p) => (p === "{{" ? "\\{" : p === "}}" ? "\\}" : p === "\uE000" ? ".*" : /^\{\w+\}$/.test(p) ? escape(String(sample[p.slice(1, -1)])) : escape(p)))
    .join("");
  return new RegExp(`^${source}$`, "s");
}

describe("the refusals of the daemon", () => {
  it("are found in its source", () => {
    expect(Object.keys(CODES).length).toBeGreaterThan(50);
  });

  it("each have a sentence on the page, except those whose words the page cannot make", () => {
    expect(Object.keys(CODES).filter((code) => !message(code) && !TEXT_ONLY.includes(code))).toEqual([]);
  });

  it("have no sentence on the page for a code the daemon does not have", () => {
    const ours = Object.keys(en)
      .filter((id) => id.startsWith("error."))
      .map((id) => id.slice(6));
    expect(ours.filter((code) => !(code in CODES))).toEqual([]);
  });

  it("are said on the page with the values the daemon passes (and the lists the page adds), no others", () => {
    for (const [code, refusal] of Object.entries(CODES)) {
      const m = message(code);
      if (!m) continue;
      const asked = new Set(texts(m).flatMap(placeholders));
      for (const name of asked) expect([...refusal.params, ...ADDED], `${code}: {${name}}`).toContain(name);
      const select = typeof m === "object" && "select" in m ? m.select : undefined;
      if (select !== undefined) expect(refusal.params, `${code}: select`).toContain(select);
    }
  });

  it("read as the daemon's sentence does", () => {
    for (const [code, refusal] of Object.entries(CODES)) {
      const m = message(code);
      if (!m) continue;
      const base = Object.fromEntries([...refusal.params, ...ADDED].map((name) => [name, `<${name}>`]));
      const choices = Object.entries(VARIANTS[code] ?? {});
      const samples = choices.reduce<Params[]>((all, [name, values]) => all.flatMap((p) => values.map((v) => ({ ...p, [name]: v }))), [base]);
      for (const sample of samples) {
        const english = fill(pick(m, sample, "en"), sample, "en");
        const says = refusal.text.map((template) => pattern(template, sample));
        expect(
          says.some((re) => re.test(english)),
          `${code}: "${english}" is not ${JSON.stringify(refusal.text)}`,
        ).toBe(true);
      }
    }
  });
});

describe("a refusal on the page", () => {
  it("is the page's sentence for a code it has, with the values", () => {
    const error = {
      cmd: "set_config",
      key: "station/lat",
      code: "setting.range",
      params: { value: 95, min: -90, max: 90 },
      text: "set_config: station/lat: 95 is not between -90 and 90",
    };
    expect(errorReason(error)).toBe("95 is not between -90 and 90");
    expect(errorLine(error)).toBe(error.text);
  });

  it("is the daemon's English one, without the command and the setting in front, for a code it has none for", () => {
    const text = "send_message: OH2GBA is our own call";
    expect(errorReason({ cmd: "send_message", key: null, code: "other", params: {}, text })).toBe("OH2GBA is our own call");
    expect(errorLine({ cmd: "send_message", key: null, code: "other", params: {}, text })).toBe(text);
    expect(errorReason({ cmd: "", key: null, code: "nope.nothing", params: {}, text: "Not connected to the daemon." })).toBe("Not connected to the daemon.");
  });

  it("lists what the daemon does not pass: the settings, the profiles, the characters", () => {
    expect(errorReason({ cmd: "set_config", key: "tnc/check_sec", code: "setting.unknown", params: {}, text: "x" })).toMatch(
      /^no such setting \(the settings are tnc\/profile, .*station\/call.*\)$/,
    );
    expect(errorReason({ cmd: "set_config", key: "tnc/profile", code: "setting.not_profile", params: { value: "nope" }, text: "x" })).toMatch(
      /^'nope' is not a TNC profile \(the profiles are .+\)$/,
    );
    expect(errorReason({ cmd: "send_message", key: null, code: "message.forbidden", params: { chars: "|" }, text: "x" })).toBe(
      "the text has |, which a message cannot carry (| ~ { are not allowed)",
    );
  });
});
