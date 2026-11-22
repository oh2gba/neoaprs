// A measured value comes with its unit from lib/units.ts, so no message writes a metric unit after
// a value, in any language, but where the value is one the operator typed (it stays metric).
import { describe, expect, it } from "vitest";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";

const AFTER_A_VALUE = /\}[\s\u00a0\u202f]*(?:km\/h|km|m|mm|°C|hPa|m\/s)(?![A-Za-z/])/u;
/** The messages that repeat a value as the operator typed it. */
const TYPED = [
  "station.alert.part.within",
  "settings.igate.fold.filter",
  "settings.igate.line.receiving",
  "objects.problem.speed",
];
const typed = (id: string): boolean => id.startsWith("error.") || TYPED.includes(id);
const CONVERTED = /\{(?:distance|height|range|speed)\}/;
const TYPED_VALUE = /\{(?:km|max|min)\}/;

describe.each(LOCALES.map((l) => [l.code, l.messages as Record<string, Message>] as const))(
  "the catalogue %s",
  (_code, messages) => {
    it("writes no metric unit after a value but a typed one's", () => {
      const wrong = Object.entries(messages)
        .filter(([id, m]) => !typed(id) && texts(m).some((text) => AFTER_A_VALUE.test(text)))
        .map(([id]) => id);
      expect(wrong).toEqual([]);
    });

    it("has no message with both a converted value and a typed one", () => {
      const mixed = Object.entries(messages)
        .filter(([, m]) => texts(m).some((text) => CONVERTED.test(text) && TYPED_VALUE.test(text)))
        .map(([id]) => id);
      expect(mixed).toEqual([]);
    });
  },
);

describe("the typed values", () => {
  it("are listed by ids the English has", () => {
    const en = LOCALES.find((l) => l.code === "en")?.messages ?? {};
    expect(TYPED.filter((id) => !(id in en))).toEqual([]);
  });
});
