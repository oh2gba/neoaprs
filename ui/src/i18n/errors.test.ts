// The sentences of the daemon's refusals on the page: ui/src/protocol/errors.json is what the daemon says (written from its source by scripts/gen-protocol.py), en/errors.ts is what the page says for the same code. Every code the
// daemon has a sentence for has one on the page, built of the values the daemon passes (and the lists the page adds), and it reads as the daemon's sentence does.
import { describe, expect, it } from "vitest";
import { setLocale, t } from "@/i18n";
import { en } from "@/i18n/en";
import { errorLine, errorReason, type Failure } from "@/i18n/errortext";
import { fill, placeholders, pick, texts, type Message, type Params } from "@/i18n/message";
import daemon from "@/protocol/errors.json";

interface Refusal {
  params: string[];
  text: string[];
}
const CODES = daemon as Record<string, Refusal>;
/** What the page puts in itself (errortext.ts): the lists, and `{reason}`, the sentence of the refusal's `why`. */
const ADDED = ["profiles", "settings", "forbidden", "name_forbidden", "reason"];
/** Refusals that only a page that is not the daemon's own can cause (a frame that is no JSON, a topic there is not): the page says them with the plain words of `error.failed`, the log has the daemon's. */
const TEXT_ONLY = ["not_json", "topic.unknown"];
/** The page's own refusal, which no daemon sends: a command while the socket is not open (composables/useDaemon.ts `send`). */
const PAGE_OWN = ["not_connected"];
/** The values a sentence is tried with when it chooses by one of them. */
const VARIANTS: Record<string, Record<string, string[]>> = {
  "object.name_length": { kind: ["object", "item"] },
  "object.comment_length": { motion: ["0", "1"] },
  "message.not_ascii": { chars: ["", "é"] },
  "radio.unknown": { removed: ["", "1"] },
  "radio.resource_held": { held_by: ["0", "3"] },
  "hf.held": { held: ["transmitting", "busy"] },
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
    expect(ours.filter((code) => !(code in CODES) && !PAGE_OWN.includes(code))).toEqual([]);
    expect(
      PAGE_OWN.filter((code) => code in CODES),
      "a code of the page's own that the daemon has too",
    ).toEqual([]);
  });

  it("are said on the page with the values the daemon passes (and the lists the page adds), no others", () => {
    for (const [code, refusal] of Object.entries(CODES)) {
      const m = message(code);
      if (!m) continue;
      const asked = new Set(texts(m).flatMap(placeholders));
      for (const name of asked)
        expect([...refusal.params, ...ADDED.filter((added) => added !== "reason" || refusal.params.includes("why"))], `${code}: {${name}}`).toContain(name);
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
    expect(errorLine(error), "the toast has no command name and no setting key: they say nothing to the person").toBe("95 is not between -90 and 90");
  });

  it("is the plain words of a failure, never the daemon's English and never the code, for a code it has no sentence for", () => {
    const text = "send_message: the daemon's words";
    try {
      for (const code of ["en", "de", "nl", "ja"]) {
        setLocale(code);
        const failures: Failure[] = [
          { cmd: "send_message", key: null, code: "other", params: {}, text },
          { cmd: "", key: null, code: "nope.nothing", params: {}, text },
          { cmd: "x", key: null, code: "invalid", params: {}, text },
          { cmd: "", key: null, code: "not_json", params: {}, text },
          { cmd: "status_now", key: null, code: "status.not_sent", params: { why: "nope.newer" }, text },
        ];
        for (const failure of failures) {
          expect(errorLine(failure), `${code} ${failure.code}`).toBe(t("error.failed"));
          expect(errorLine(failure)).not.toContain("daemon");
        }
      }
    } finally {
      setLocale("en");
    }
  });

  it("says the reason of a refusal that only passes on another's (nothing was sent, and why) from that reason's own sentence, in the page's language", () => {
    const failure = (params: Record<string, string | number>) => ({
      cmd: "status_now",
      key: null,
      code: "status.not_sent",
      params,
      text: "status_now: nothing was sent: there is no status text",
    });
    expect(errorLine(failure({ why: "status.no_text" }))).toBe("nothing was sent: there is no status text");
    expect(errorLine(failure({ why: "call.placeholder", call: "N0CALL" }))).toBe("nothing was sent: N0CALL is a placeholder, not a call: set your call first");
    try {
      setLocale("nl");
      expect(errorLine(failure({ why: "status.no_text" })), "the owner's case: all of it Dutch").toBe("er is niets verzonden: er is geen statustekst");
      expect(errorLine({ cmd: "radio_tune", key: null, code: "transmit.call", params: { why: "call.none" }, text: "" })).toBe(
        "er wordt niets verzonden: stel eerst je roepnaam in",
      );
    } finally {
      setLocale("en");
    }
  });

  it("is the page's own sentence, in the page's language, for a command the page could not send (the socket not open), and never names the daemon", () => {
    const failure = { cmd: "", key: null, code: "not_connected", params: {}, text: "Not connected to the daemon." } as const;
    try {
      for (const code of ["en", "de", "fi", "ja"]) {
        setLocale(code);
        expect(errorLine(failure), code).toBe(t("error.not_connected"));
        expect(errorLine(failure), code).not.toMatch(/daemon|デーモン/i);
      }
    } finally {
      setLocale("en");
    }
  });

  it("lists what the daemon does not pass: the settings, the types of radio, the characters", () => {
    expect(errorReason({ cmd: "set_config", key: "tnc/check_sec", code: "setting.unknown", params: {}, text: "x" })).toMatch(
      /^no such setting \(the settings are serial\/pattern, .*station\/call.*\)$/,
    );
    expect(errorReason({ cmd: "set_config", key: "tnc/check_sec", code: "setting.unknown", params: {}, text: "x" })).not.toContain("serial/last_port"); // (radio 1's state, no setting)
    expect(errorReason({ cmd: "set_config", key: "tnc/check_sec", code: "setting.unknown", params: {}, text: "x" })).not.toMatch(/tnc\/profile|serial\/port,/);
    expect(errorReason({ cmd: "set_config", key: "tnc/profile", code: "setting.not_profile", params: { value: "nope" }, text: "x" })).toMatch(
      /^'nope' is not a type of radio \(the types are .+\)$/,
    );
    expect(errorReason({ cmd: "send_message", key: null, code: "message.forbidden", params: { chars: "|" }, text: "x" })).toBe(
      "the text has |, which a message cannot carry (| ~ { are not allowed)",
    );
  });
});
