// What every language in LOCALES owes the English catalogue: the same ids, the same {values} in each message (a translator may drop one from a form of a plural, not invent one), the plural forms its language has, and its own name.
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { placeholders, texts, type Message } from "@/i18n/message";

const source = en as Record<string, Message>;
/** The button that chooses the place on the map (the My station tab, the Objects form, the setup guide), in each language; nothing says "pick" in it. */
const CHOOSE_ON_MAP: Record<string, string> = {
  en: "Choose on map",
  de: "Auf Karte wählen",
  es: "Elegir en el mapa",
  fr: "Choisir sur la carte",
  it: "Scegli sulla mappa",
  ja: "地図で選択",
  "pt-BR": "Escolher no mapa",
};
const names = (m: Message): string[] => [...new Set(texts(m).flatMap(placeholders))].sort();

describe("the languages of the page", () => {
  it("start with English, which is the source, and have a code and a name of their own", () => {
    expect(LOCALES[0]?.code).toBe("en");
    expect(LOCALES.every((l) => /^[a-z]{2,3}(-[A-Z]{2})?$/.test(l.code) && l.name.trim() !== "")).toBe(true);
    expect(new Set(LOCALES.map((l) => l.code)).size).toBe(LOCALES.length);
  });

  for (const locale of LOCALES) {
    describe(locale.name, () => {
      const messages = locale.messages as Record<string, Message>;

      it("has every id of the English catalogue and no other", () => {
        expect(Object.keys(messages).sort()).toEqual(Object.keys(source).sort());
      });

      it("has nothing of the Mobile switch, the Mobile group, the SmartBeaconing numbers and the GPS source choice, which the position choice and Travelling replaced", () => {
        const gone = /^(settings\.(mobile|smart_|gps_source|group\.mobile|fold\.smart)|error\.setting\.smart_|beacon\.(last_beacon|not_yet))/;
        expect(Object.keys(messages).filter((id) => gone.test(id))).toEqual([]);
        expect(Object.keys(messages)).toEqual(expect.arrayContaining(["settings.position.label", "settings.travel.label", "beacon.line.timed"]));
      });

      it("calls the button that chooses a place on the map by its words, once, and has no id of the Objects form for it", () => {
        expect(messages["settings.location.pick"]).toBe(CHOOSE_ON_MAP[locale.code]);
        expect(messages["objects.form.pick"]).toBeUndefined();
      });

      it("asks for the values the English asks for", () => {
        const wrong = Object.entries(source).filter(([id, m]) => JSON.stringify(names(messages[id] ?? m)) !== JSON.stringify(names(m)));
        expect(wrong.map(([id]) => id)).toEqual([]);
      });

      it("has the plural forms of its language, and the form other", () => {
        const categories = new Intl.PluralRules(locale.code).resolvedOptions().pluralCategories;
        const wrong = Object.entries(messages).filter(
          ([, m]) =>
            typeof m === "object" &&
            !("select" in m) &&
            (!("other" in m) || Object.keys(m).some((k) => !k.startsWith("=") && !(categories as string[]).includes(k) && k !== "other")),
        );
        expect(wrong.map(([id]) => id)).toEqual([]);
      });
    });
  }

  it("writes French with a no-break space before : ; ? ! and %, and Italian with the curly apostrophe", () => {
    const strings = (code: string) => Object.values(LOCALES.find((l) => l.code === code)?.messages ?? {}).flatMap((m) => texts(m));
    expect(strings("fr").filter((text) => / [:;?!%]/.test(text))).toEqual([]);
    expect(strings("it").filter((text) => /[A-Za-zÀ-ÿ]'[A-Za-zÀ-ÿ]/.test(text))).toEqual([]);
  });
});
