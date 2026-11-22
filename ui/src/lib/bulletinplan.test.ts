// The Sent for choices of the Bulletins form follow the daemon's (neoaprs/ownbulletin.py, sent as
// LIMITS.bulletin): with other choices the list shows other numbers in every language, and no
// catalogue holds a number of its own.
import { afterEach, describe, expect, it, vi } from "vitest";
import { setLocale } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { kindTitle, POST_KINDS, rememberedHours, sentForChoices, sentForText } from "@/lib/bulletins";
import type * as Lists from "@/protocol/lists";

vi.mock("@/protocol/lists", async (importOriginal) => {
  const lists = await importOriginal<typeof Lists>();
  return {
    ...lists,
    LIMITS: {
      ...lists.LIMITS,
      bulletin: {
        ...lists.LIMITS.bulletin,
        hours: [3, 6],
        announcementHours: [48, 96],
        defaultHours: 6,
        defaultAnnouncementHours: 48,
      },
    },
  };
});

afterEach(() => setLocale("en"));

describe("the Sent for of a post, with choices of 3 and 6 hours and 2 and 4 days", () => {
  it("offers those choices, an announcement's in days, and starts at the defaults", () => {
    expect(sentForChoices("bulletin").map((h) => sentForText("bulletin", h))).toEqual(["3 hours", "6 hours"]);
    expect(sentForChoices("announcement").map((h) => sentForText("announcement", h))).toEqual(["2 days", "4 days"]);
    expect(POST_KINDS.map((kind) => rememberedHours(kind, null))).toEqual([6, 48, 6]);
    expect(rememberedHours("bulletin", { bulletin: 4, announcement: 72, group: 3 }), "4 is no choice now").toBe(6);
  });

  it("says them in every language, each with its number and nothing left to fill", () => {
    for (const locale of LOCALES) {
      setLocale(locale.code);
      const words = [
        ...sentForChoices("group").map((h) => sentForText("group", h)),
        ...sentForChoices("announcement").map((h) => sentForText("announcement", h)),
      ];
      expect(
        words.map((w) => w.match(/\d+/)?.[0]),
        locale.code,
      ).toEqual(["3", "6", "2", "4"]);
      for (const text of words) expect(text, locale.code).not.toMatch(/[{}]/);
    }
  });

  it("names the kinds with no number in any language", () => {
    for (const locale of LOCALES) {
      setLocale(locale.code);
      const names = POST_KINDS.map(kindTitle);
      expect(new Set(names).size, locale.code).toBe(3);
      for (const name of names) expect(name, locale.code).not.toMatch(/\d|[{}]/);
    }
  });
});
