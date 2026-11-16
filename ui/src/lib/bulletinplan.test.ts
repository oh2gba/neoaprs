// The words of the three kinds of the Bulletins form follow the daemon's plan (neoaprs/decay.py, on the wire as LIMITS.bulletin): with another plan the choice says the other numbers, in every language, and
// no catalogue holds a number of its own.
import { afterEach, describe, expect, it, vi } from "vitest";
import { setLocale } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";
import { kindTitle, POST_KINDS } from "@/lib/bulletins";
import type * as Lists from "@/protocol/lists";

vi.mock("@/protocol/lists", async (importOriginal) => {
  const lists = await importOriginal<typeof Lists>();
  return { ...lists, LIMITS: { ...lists.LIMITS, bulletin: { ...lists.LIMITS.bulletin, repeatHours: 6, announcementRepeatDays: 1 } } };
});

afterEach(() => setLocale("en"));

describe("the kinds of a post, with a plan of 6 hours and 1 day", () => {
  it("say the plan's numbers, one day in the singular", () => {
    expect(POST_KINDS.map((k) => kindTitle(k.kind))).toEqual([
      "Bulletin (sent for 6 hours)",
      "Announcement (sent for 1 day)",
      "Group bulletin (to one group, sent for 6 hours)",
    ]);
  });

  it("say them in every language: the number of each kind is in its words, and nothing of the text is left to fill", () => {
    for (const locale of LOCALES) {
      setLocale(locale.code);
      const [bulletin, announcement, group] = POST_KINDS.map((k) => kindTitle(k.kind));
      expect(bulletin, locale.code).toMatch(/6/);
      expect(announcement, locale.code).toMatch(/1/);
      expect(group, locale.code).toMatch(/6/);
      expect(new Set([bulletin, announcement, group]).size, locale.code).toBe(3);
      for (const text of [bulletin, announcement, group]) expect(text, locale.code).not.toMatch(/[{}]/);
    }
  });

  it("have no number written into a catalogue: only {n}", () => {
    for (const locale of LOCALES) {
      const messages = locale.messages as Record<string, Message>;
      for (const { kind } of POST_KINDS) {
        const forms = texts(messages[`bulletins.kind.${kind}`] ?? "");
        expect(forms.length, `${locale.code} ${kind}`).toBeGreaterThan(0);
        for (const form of forms) {
          expect(form, `${locale.code} ${kind}`).toContain("{n}");
          expect(form.replace("{n}", ""), `${locale.code} ${kind}`).not.toMatch(/\d/);
        }
      }
    }
  });
});
