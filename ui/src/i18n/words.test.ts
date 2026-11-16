// The words that are one word in each language, whatever text they stand in: the radio (the device, any radio of any type: never "TNC" where any radio is meant), the program (NeoAPRS, never "daemon" or "server"),
// receive-only (the word of the RX only switch, in the list of types too), the Dummy (one word for the tag, the pill, the types and their lines, and never the word of the HF tests), and French's one apostrophe.
import { describe, expect, it } from "vitest";
import { LOCALES } from "@/i18n/locales";
import { texts, type Message } from "@/i18n/message";

/** Each language's word for a radio, the device (the translators' glossary): the choice of a radio is called by it. */
const RADIO: Record<string, string> = {
  en: "Radio",
  de: "Funkgerät",
  es: "Radio",
  fi: "Radio",
  fr: "Radio",
  it: "Radio",
  ja: "無線機",
  nl: "Radio",
  "pt-BR": "Rádio",
};
/** The texts that mean whichever radio the station has, of any type. */
const ANY_RADIO = ["compose.tnc_not_connected", "stats.frames", "settings.tnc.terminal_label", "pill.radio_waiting_why"];
/** The texts that name the program. */
const PROGRAM = [
  "pill.daemon",
  "pill.daemon_connecting",
  "pill.daemon_offline",
  "settings.no_answer",
  "settings.not_sent",
  "settings.no_word",
  "settings.alerts.title",
  "settings.alerts.title_app",
  "settings.help.problem.unreachable",
  "stats.section.radio",
  "error.lock.off",
];
/** The start of each language's word for the Dummy, and the texts that say it. */
const DUMMY: Record<string, string> = {
  en: "dummy",
  de: "dummy",
  es: "simulad",
  fi: "simulo",
  fr: "factice",
  it: "fint",
  ja: "ダミー",
  nl: "dummy",
  "pt-BR": "simulad",
};
const DUMMY_IDS = [
  "channel.dummy",
  "channel.title.dummy",
  "settings.tnc.dummy_pill",
  "settings.tnc.dummy",
  "settings.tnc.dummy_hf",
  "pill.radio_dummy_title",
  "radio.type.dummy",
  "radio.type.dummy_hf",
  "radio.type.dummy_lora",
  "settings.profile.tip2",
];
/** The texts the phone's code, the Sound card type and the modem-neutral words of a radio brought: the program in them is NeoAPRS, written one way, and never the server. */
const BROUGHT = (id: string): boolean =>
  id.startsWith("phone.") || ["radio.type.direwolf", "settings.tnc.hf.keying", "settings.tnc.hf.not_installed"].includes(id);
/** The texts of the two boxes of the Notifications group, in a browser and in the app's own window: the computer NeoAPRS runs on is a computer, never a server. */
const ALERT_BOXES = (id: string): boolean => id.startsWith("settings.alerts.") || id.startsWith("settings.browser.") || id === "settings.alert.tip1";
/** The lines of the list of types that only receive. */
const RECEIVE_ONLY_TYPES = ["radio.type.tnc_text", "radio.type.lora_console"];

const all = (m: Message | undefined): string => (m === undefined ? "" : texts(m).join(" | "));

for (const locale of LOCALES) {
  const messages = locale.messages as Record<string, Message>;
  const say = (id: string) => all(messages[id]);
  const has = (id: string, word: string) => say(id).toLocaleLowerCase(locale.code).includes(word.toLocaleLowerCase(locale.code));

  describe(`the words of ${locale.name}`, () => {
    it("call the choice of a radio by the word for a radio", () => {
      expect(say("radio.choice")).toBe(RADIO[locale.code]);
    });

    it("say radio, not TNC, where any radio is meant", () => {
      expect(ANY_RADIO.filter((id) => !has(id, RADIO[locale.code] ?? "") || /TNC/.test(say(id)))).toEqual([]);
    });

    it("call the program NeoAPRS, never the daemon", () => {
      expect(PROGRAM.filter((id) => !say(id).includes("NeoAPRS"))).toEqual([]);
      expect(Object.keys(messages).filter((id) => /daemon|démon|デーモン/i.test(say(id)))).toEqual([]);
    });

    it("call the program NeoAPRS one way in the texts of the phone's code and of the Sound card type, and never the server", () => {
      const brought = Object.keys(messages).filter(BROUGHT);
      expect(brought.length).toBeGreaterThanOrEqual(7);
      expect(brought.flatMap((id) => [...say(id).matchAll(/neo[\s-]*aprs/giu)].map((m) => m[0])).filter((name) => name !== "NeoAPRS")).toEqual([]);
      expect(brought.filter((id) => /daemon|démon|デーモン|server|serveur|servidor|palvelin|サーバ/iu.test(say(id)))).toEqual([]);
    });

    it("call the computer of the alert boxes a computer, never the server, in a browser and in the app's window", () => {
      const boxes = Object.keys(messages).filter(ALERT_BOXES);
      expect(boxes.length).toBeGreaterThanOrEqual(18);
      expect(boxes.filter((id) => /daemon|démon|デーモン|server|serveur|servidor|palvelin|サーバ/iu.test(say(id)))).toEqual([]);
      expect(boxes.filter((id) => id.endsWith("_app") && /browser|navigateur|navegador|selain|ブラウザ/iu.test(say(id)))).toEqual([]);
    });

    it("say receive-only with the word of the RX only switch, in the list of types too", () => {
      const word = say("pill.rx");
      expect([say("settings.transmit.label"), say("settings.transmit.name")]).toEqual([word, word]);
      expect(["error.transmit.off", ...RECEIVE_ONLY_TYPES].filter((id) => !has(id, word))).toEqual([]);
    });

    it("have one word for the Dummy, and not the word of the HF tests", () => {
      const word = DUMMY[locale.code] ?? "";
      expect(DUMMY_IDS.filter((id) => !has(id, word))).toEqual([]);
      expect(has("tab.skeds", word)).toBe(false);
      if (locale.code === "fi") expect(DUMMY_IDS.filter((id) => has(id, "testi"))).toEqual([]);
    });

    it("refuse an email with no gated radio in the words of the page's own line, from a small letter", () => {
      const line = say("email.no_gated_radio");
      expect(say("error.message.email_fm_off")).toBe(line.charAt(0).toLocaleLowerCase(locale.code) + line.slice(1));
    });
  });
}

describe("French", () => {
  it("writes one apostrophe, the straight one", () => {
    const fr = LOCALES.find((l) => l.code === "fr")?.messages as Record<string, Message>;
    expect(Object.keys(fr).filter((id) => /\p{L}’\p{L}/u.test(all(fr[id])))).toEqual([]);
  });
});

describe("Finnish", () => {
  it("declines NeoAPRS one way, with a colon, as a name that ends in an abbreviation", () => {
    const fi = LOCALES.find((l) => l.code === "fi")?.messages as Record<string, Message>;
    expect(Object.keys(fi).filter((id) => /NeoAPRS\p{L}/u.test(all(fi[id])))).toEqual([]);
  });
});
