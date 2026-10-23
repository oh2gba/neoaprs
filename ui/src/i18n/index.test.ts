import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { availableLocales, detectLocale, formatNumber, hasMessage, locale, setLocale, startLocale, t, weekdayShort } from "@/i18n";
import type { Catalogue } from "@/i18n/catalogue";
import { LOCALES, type LocaleInfo } from "@/i18n/locales";

// Two languages that are not in the page yet, put in the list for these tests: the catalogue of one is whole but for one id (which falls back to English), the other has a plural.
const list = LOCALES as LocaleInfo[];
const added: LocaleInfo[] = [
  {
    code: "de",
    name: "Deutsch",
    messages: {
      "tab.stations": "Stationen",
      "unread.not_seen": { one: "{n} Nachricht ungesehen", other: "{n} Nachrichten ungesehen" },
    } as unknown as Catalogue,
  },
  { code: "pt-BR", name: "Português (Brasil)", messages: { "tab.stations": "Estações" } as unknown as Catalogue },
];
beforeAll(() => list.push(...added));
afterAll(() => list.splice(list.length - added.length, added.length));
beforeEach(() => localStorage.clear());

describe("detectLocale", () => {
  it("takes the first language of the browser that the page has, by its language", () => {
    expect(detectLocale(["de-AT", "en"])).toBe("de");
    expect(detectLocale(["DE"])).toBe("de");
    expect(detectLocale(["sv", "de-CH", "en"])).toBe("de");
  });

  it("takes pt and pt-PT for pt-BR, and pt-BR for itself", () => {
    expect(detectLocale(["pt"])).toBe("pt-BR");
    expect(detectLocale(["pt-PT"])).toBe("pt-BR");
    expect(detectLocale(["pt-BR"])).toBe("pt-BR");
  });

  it("is English when the browser asks for nothing the page has", () => {
    expect(detectLocale(["sv", "fi"])).toBe("en");
    expect(detectLocale([])).toBe("en");
  });
});

describe("the language of the page", () => {
  it("is set on the page's html and in the reactive locale, an unknown one is ignored, and only a choice is remembered", () => {
    setLocale("de");
    expect(locale.value).toBe("de");
    expect(document.documentElement.lang).toBe("de");
    expect(localStorage.getItem("NeoAPRS.language")).toBeNull();
    setLocale("xx");
    expect(locale.value).toBe("de");
    setLocale("pt-BR", true);
    expect(localStorage.getItem("NeoAPRS.language")).toBe("pt-BR");
    expect(document.documentElement.lang).toBe("pt-BR");
  });

  it("starts with the choice that was kept, else the browser's own language, else English", () => {
    startLocale(["de-AT"]);
    expect(locale.value).toBe("de");
    localStorage.setItem("NeoAPRS.language", "pt-BR");
    startLocale(["de-AT"]);
    expect(locale.value).toBe("pt-BR");
    localStorage.setItem("NeoAPRS.language", "tlh");
    startLocale(["sv"]);
    expect(locale.value).toBe("en");
  });

  it("is offered with each language's own name, and the pseudo-locale in development", () => {
    expect(availableLocales().map((l) => l.name)).toEqual(expect.arrayContaining(["English", "Deutsch", "Português (Brasil)", "Pseudo (en-XA)"]));
  });
});

describe("t", () => {
  it("gives the English of the catalogue, with the values", () => {
    expect(t("tab.stations")).toBe("Stations");
    expect(t("footer.update", { version: "0.7.0" })).toBe("Update to 0.7.0");
  });

  it("gives the language's own message, and English for an id that language does not have", () => {
    setLocale("de");
    expect(t("tab.stations")).toBe("Stationen");
    expect(t("tab.packets")).toBe("Packets");
    setLocale("pt-BR");
    expect(t("tab.stations")).toBe("Estações");
  });

  it("chooses the plural form by the language", () => {
    expect(t("unread.not_seen", { n: 1 })).toBe("1 message not seen yet");
    expect(t("unread.not_seen", { n: 2 })).toBe("2 messages not seen yet");
    setLocale("de");
    expect(t("unread.not_seen", { n: 1 })).toBe("1 Nachricht ungesehen");
    expect(t("unread.not_seen", { n: 5 })).toBe("5 Nachrichten ungesehen");
  });

  it("changes with the language: what reads it is drawn again", async () => {
    const { computed, nextTick } = await import("vue");
    const title = computed(() => t("tab.stations"));
    expect(title.value).toBe("Stations");
    setLocale("de");
    await nextTick();
    expect(title.value).toBe("Stationen");
  });

  it("is made long and accented in the pseudo-locale", () => {
    setLocale("en-XA");
    expect(t("tab.stations")).toMatch(/^\[!! .* !!\]$/);
    expect(t("unread.not_seen", { n: 1 })).toContain("1");
    expect(t("unread.not_seen", { n: 2 })).not.toBe(t("unread.not_seen", { n: 1 }));
  });

  it("knows the ids it has", () => {
    expect(hasMessage("tab.stations")).toBe(true);
    expect(hasMessage("tab.nothing")).toBe(false);
    expect(hasMessage("toString")).toBe(false);
  });
});

describe("numbers and weekdays", () => {
  it("are written by the language", () => {
    expect(formatNumber(0.3, 1)).toBe("0.3");
    setLocale("de");
    expect(formatNumber(0.3, 1)).toBe("0,3");
    expect(weekdayShort(new Date(2026, 9, 19))).toBe("Mo");
    setLocale("en");
    expect(weekdayShort(new Date(2026, 9, 19))).toBe("Mon");
  });
});
