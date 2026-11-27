// No English left inside a text of the eight other languages: a run of two English words (or a name with an English word, as "RX only") in a translated text fails with its id and the words.
// A word counts as English when the English catalogue has it, it is not a name the languages share, and the language does not use it itself: a word of the language's texts that stands where the English text
// of the same id does not have it, in two texts or more, is the language's own (Dutch "is", French "messages"); the few the count does not see are listed by hand. Japanese has no such words.
// Beside it, the two places where an English word was left because it is a value the page shows: the Packets info line says the Dir column's own words, and the symbol search's examples find a symbol.
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { LOCALES, SOURCE } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";

const source = en as Record<string, Message>;

/** The names every language writes as the English does: programs, makers, protocols, units, systems, and the people the About tab and the map's credits name. */
const NAMES = new Set(
  `NeoAPRS APRS Packet Mercury Direwolf LoRa iGate Bluetooth Winlink Kenwood Kantronics Yaesu soundmodem OpenStreetMap Mobilinkd NinoTNC
  Firefox Chrome Chromium Edge Safari Android iOS Windows macOS Linux Keychain Raspberry Nominatim Dummy Internet GitHub gpsd rigctld
  PMTiles MHz kHz dBFS dB Mic-E https http Heikki Hannikainen John Langner tar1090 readsb dump1090 PiAware Matthias Wirth GPL`
    .split(/\s+/)
    .map((w) => w.toLowerCase()),
);

/** English words that tie a run together: one of them beside a name ("RX only") is English too. */
const FUNCTION_WORDS = new Set(
  `the a an is are was were be been being no not there with from your you this that these those and or but for when until again cannot can't could has have had will
  would only more less about after before each every which what where who how it its of to in on at by as if then than so do does did don't isn't doesn't won't any
  some all here one it's into out up over off yet still just also too very own same other such our their they we he she his her`.split(
    /\s+/,
  ),
);

/** Words of a language spelt as English words, which the count above does not find because the English of the same texts has them too. */
const OWN_WORDS: Record<string, string> = {
  de: "die was is not in an so man will also hat",
  nl: "die was is not in an op door van de en te",
  es: "no a de en un con es info local",
  it: "no a in con è non area picnic",
  "pt-BR": "no a de em um com",
  fr: "on a en de un non bulletins messages satellite mobile",
  fi: "on ei ja",
};

/** Texts rightly the same as the English, or with English in them for a reason; by language ("*" for every one), each with its reason. */
const ALLOWED: Record<string, Record<string, string>> = {
  "*": {
    "error.setting.status_source": "off, text and rig are the setting's own values, written so in the settings file",
  },
  de: {
    "symbol.primary.53": "German calls the craft by its English name, Space Shuttle",
    "settings.about.license_link": "the name of the licence, GNU General Public License, which is not translated",
  },
  nl: {
    "settings.about.license_link": "the name of the licence, GNU General Public License, which is not translated",
  },
  ja: {
    "settings.comment.tip2":
      "an example of a comment, which has to be printable ASCII: a Japanese operator writes it in English",
  },
};

/** One word a text of a language says as the English does, because the language says it so too (a loan or a cognate), by language: a new such word is looked at before it is let in. */
const SAME_WORD: Record<string, string> = {
  de: `doppler downlink elevation uplink app bits bulletin bulletins bus code details digipeater eyeball feedback filter gateway hotel igates item jogger km laptop locator mac monitor name
  normal omni pause port ports position radius rate restaurant rover signal skywarn station status symbol tanker terminal test text tornado update wind yacht`,
  es: "doppler bits digipeater digipeaters dir hospital hotel igates jeep km locator mac monitor normal omni radio radios rover skywarn terminal tornado",
  fi: "doppler km mac radio rover skywarn tornado",
  fr: `doppler mode satellites altitude ambulance bits bulletin bulletins bus code conversations cyan deg destination digipeater digipeaters direct eyeball igates item items jeep km
  latitude locator longitude mac message messages note notification notifications omni parking pause police port portable ports position positions radio radios
  restaurant rover satellite services signal simplex skywarn source station stations stop terminal test triangle type via violet yacht`,
  it: "doppler downlink uplink antenna app area beacon digipeater dir email feedback fix gateway item km locator mac monitor omni radio rover satellite simplex skywarn stop tornado via yacht",
  ja: "km mac skywarn",
  nl: `doppler downlink uplink ambulance app bits bulletin bulletins bus code details digipeater digipeaters direct eyeball feedback filter fix gateway help hops hotel igates in item items
  jeep km laptop locator mac monitor node object omni radio restaurant route rover school simplex skywarn spectrum station stations status storm tanker terminal timer
  tornado type update via violet wind`,
  "pt-BR": `doppler altitude beacon beacons bits digipeater digipeaters dir eyeball feedback gateway hospital hotel igates item km latitude locator longitude mac monitor
  normal omni rover simplex skywarn status terminal tornado van via`,
};

const PLACEHOLDER = /\{\{|\}\}|\{\w+\}/g;
const ADDRESS = /https?:\/\/\S+|\S+\/\S+|\S+\.(py|md|ts|json|exe)\b/g;
const TOKEN = /[\p{L}\p{N}_'’.-]+|,|\S/gu;
const ASCII_WORD = /^[A-Za-z][A-Za-z'’-]*$/;

const low = (w: string): string => w.toLowerCase().replace(/’/g, "'");
const tokens = (text: string): string[] =>
  (text.replace(PLACEHOLDER, " ¤ ").replace(ADDRESS, " ¤ ").match(TOKEN) ?? []).map(
    (t) => t.replace(/^[.-]+|[.-]+$/g, "") || t,
  );
const all = (m: Message | undefined): string[] => (m === undefined ? [] : texts(m));
const isName = (w: string): boolean => NAMES.has(low(w)) || /^[A-Z0-9/-]+$/.test(w) || /\d/.test(w);

const ENGLISH = new Set(
  Object.values(source)
    .flatMap(all)
    .flatMap(tokens)
    .filter((w) => ASCII_WORD.test(w))
    .map(low),
);

/** The words of a language that stand, in two of its texts or more, where the English of the same id does not have them. */
function ownWords(messages: Record<string, Message>): Set<string> {
  const seen = new Map<string, number>();
  for (const [id, m] of Object.entries(messages)) {
    const english = new Set(all(source[id]).flatMap(tokens).map(low));
    for (const w of new Set(all(m).flatMap(tokens).map(low))) if (!english.has(w)) seen.set(w, (seen.get(w) ?? 0) + 1);
  }
  return new Set([...seen].filter(([, n]) => n >= 2).map(([w]) => w));
}

/** The runs of English in a text: two English words or more, or a name with one of the function words. */
function englishRuns(text: string, own: Set<string>): string[] {
  const runs: string[] = [];
  let run: { kind: "name" | "word" | "function"; word: string }[] = [];
  const end = (): void => {
    const words = run.filter((r) => r.kind !== "name");
    if (words.length >= 2 || (words.length >= 1 && run.length >= 2 && run.some((r) => r.kind === "function")))
      runs.push(run.map((r) => r.word).join(" "));
    run = [];
  };
  for (const tok of tokens(text)) {
    const word = ASCII_WORD.test(tok);
    if (tok === "," && run.length > 0) continue;
    if (word && isName(tok)) run.push({ kind: "name", word: tok });
    else if (word && tok.length > 1 && (ENGLISH.has(low(tok)) || FUNCTION_WORDS.has(low(tok))) && !own.has(low(tok)))
      run.push({ kind: FUNCTION_WORDS.has(low(tok)) ? "function" : "word", word: tok });
    else end();
  }
  end();
  return runs;
}

for (const locale of LOCALES.filter((l) => l.code !== SOURCE)) {
  const messages = locale.messages as Record<string, Message>;
  const allowed = { ...ALLOWED["*"], ...ALLOWED[locale.code] };
  const own = new Set([
    ...(locale.code === "ja" ? [] : ownWords(messages)),
    ...(OWN_WORDS[locale.code] ?? "").split(" ").filter(Boolean),
  ]);

  describe(`the texts of ${locale.name}`, () => {
    it("have no English in them", () => {
      const mixed = Object.entries(messages)
        .filter(([id]) => !(id in allowed))
        .flatMap(([id, m]) => {
          const runs = all(m).flatMap((t) => englishRuns(t, own));
          return runs.length > 0 ? [`${id}: ${runs.join(" / ")}`] : [];
        });
      expect(
        mixed,
        "English inside a translated text: translate it (a label by the language's own text of it), or allow it here with the reason",
      ).toEqual([]);
    });

    it("allow only texts that are there and still have the English the allowance is for", () => {
      const stale = Object.keys(ALLOWED[locale.code] ?? {}).filter(
        (id) => all(messages[id]).flatMap((t) => englishRuns(t, own)).length === 0,
      );
      expect(stale).toEqual([]);
    });

    it("have no text that is one English word, unless the language says it so too", () => {
      const same = new Set((SAME_WORD[locale.code] ?? "").split(/\s+/).filter(Boolean));
      const english = Object.entries(messages).flatMap(([id, m]) => {
        const text = all(m)[0] ?? "";
        const wholly = all(source[id])[0] === text && ASCII_WORD.test(text);
        const shape = /^x+(-x+)*$/.test(text); // the shape of an access key, which no language words
        return wholly && !shape && !isName(text) && !same.has(low(text)) ? [`${id}: ${text}`] : [];
      });
      expect(
        english,
        "an English word left as a text: translate it, or add the word to SAME_WORD if the language says it so",
      ).toEqual([]);
    });

    it("name the Dir column's values in the Packets info line by the column's own words", () => {
      const line = all(messages["packets.about1"]).join(" ");
      expect(
        [all(messages["packets.dir.in"])[0] ?? "", all(messages["packets.dir.out"])[0] ?? ""].filter(
          (word) => !line.includes(word),
        ),
      ).toEqual([]);
    });

    it("give the symbol search examples that find a symbol by its name in the language", () => {
      // The search's synonyms (wx, home, plane …) are English words; in the other languages an example has to be in a symbol's own name.
      const names = Object.keys(messages)
        .filter((id) => id.startsWith("symbol."))
        .flatMap((id) => all(messages[id]))
        .map((n) => n.toLocaleLowerCase(locale.code));
      const examples = (all(messages["settings.picker.placeholder"])[0] ?? "")
        .replace(/^[^:：]*[:：]\s*/, "")
        .split(/[,、]/)
        .map((w) =>
          w
            .replace(/(\.\.\.|…)$/, "")
            .trim()
            .toLocaleLowerCase(locale.code),
        )
        .filter(Boolean);
      expect(examples.length).toBeGreaterThanOrEqual(3);
      expect(examples.filter((w) => !names.some((n) => n.includes(w)))).toEqual([]);
    });
  });
}
