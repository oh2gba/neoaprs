// The notes of the (i) are short, in every language: one or two lines of a sentence, with the details in the manual. A line over the limit means a paragraph has crept back in.
import { describe, expect, it } from "vitest";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";

/** The ids of the lines of a note: `x.tip`, `x.tip1`, `x.tip_moving`, `x.about1`, `x.mode_tip`, `x.kinds_help`, `x.igates_tip` and the like. */
const NOTE = /\.(tip\d?|tip_moving|about\d|[a-z]+_tip\d?|kinds_help|overheard_help)$/;
/** The longest a line of a note is, in characters, for the languages that write words (Japanese is far shorter in characters). */
const MOST = 145;

describe("the notes of the (i)", () => {
  for (const locale of LOCALES) {
    it(`are short in ${locale.name}`, () => {
      const lines = Object.entries(locale.messages as Record<string, Message>)
        .filter(([id]) => NOTE.test(id) && !id.startsWith("help."))
        .flatMap(([id, message]) => texts(message).map((text) => ({ id, length: text.length })));
      expect(lines.length).toBeGreaterThan(60);
      expect(lines.filter((l) => l.length > MOST)).toEqual([]);
    });
  }
});
