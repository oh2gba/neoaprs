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
const ANY_RADIO = [
  "compose.tnc_not_connected",
  "stats.frames",
  "settings.tnc.terminal_label",
  "pill.radio_waiting_why",
];
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
  id.startsWith("phone.") ||
  ["radio.type.direwolf", "settings.tnc.hf.keying", "settings.tnc.hf.not_installed"].includes(id);
/** The texts of the two boxes of the Notifications group, in a browser and in the app's own window: the computer NeoAPRS runs on is a computer, never a server. */
const ALERT_BOXES = (id: string): boolean =>
  id.startsWith("settings.alerts.") || id.startsWith("settings.browser.") || id === "settings.alert.tip1";
/** The lines of the list of types that only receive. */
const RECEIVE_ONLY_TYPES = ["radio.type.tnc_text", "radio.type.lora_console"];
/** The one type whose name says Direwolf: the operator's own, which he runs himself and NeoAPRS reaches over the network. The Sound card type, whose Dire Wolf NeoAPRS carries and starts, is named by what the operator
 * has in hand (John, 16 Nov 2026: "so people don't get confused whether to still install direwolf"). */
const OWN_PROGRAM = "radio.type.kiss_tcp";
/** The types of the Mercury kind: Mercury is in their names, because the other station must run the same modem to be heard, and in no other type's. */
const MERCURY_TYPES = ["radio.type.mercury", "radio.type.dummy_hf"];
/** What no type's name says: a band or a mode the radio may not be on (a Mercury radio works on 2 m and through an FM radio's audio too), nor how the program reaches it. */
const BAND_OR_LINK = /(?<![\p{L}\p{N}])(HF|KW|VHF|UHF|SSB|TCP)(?![\p{L}\p{N}])/u;
/** The longest a type's name is, in characters: the list of Add radio is as wide as its widest line, on a phone too (the longest English line is the KISS TNC's, 41). */
const WIDEST_TYPE = 43;

/** The refusals and reasons that name a field or a switch of the page, and the labels they name. */
const NAMED_LABELS: Record<string, string[]> = {
  "error.beacon.not_on_radio": ["radio.send_on"],
  "error.status.no_rig": ["settings.status_rigctld.label"],
  "error.map.no_position": ["settings.lat.label", "settings.lon.label"],
  "settings.map.problem.no_position": ["settings.lat.label", "settings.lon.label"],
  "error.station.email_rf_only": ["route.rf_only"],
};

const all = (m: Message | undefined): string => (m === undefined ? "" : texts(m).join(" | "));

for (const locale of LOCALES) {
  const messages = locale.messages as Record<string, Message>;
  const say = (id: string) => all(messages[id]);
  const has = (id: string, word: string) =>
    say(id).toLocaleLowerCase(locale.code).includes(word.toLocaleLowerCase(locale.code));

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
      expect(
        brought
          .flatMap((id) => [...say(id).matchAll(/neo[\s-]*aprs/giu)].map((m) => m[0]))
          .filter((name) => name !== "NeoAPRS"),
      ).toEqual([]);
      expect(
        brought.filter((id) => /daemon|démon|デーモン|server|serveur|servidor|palvelin|サーバ/iu.test(say(id))),
      ).toEqual([]);
    });

    it("call the computer of the alert boxes a computer, never the server, in a browser and in the app's window", () => {
      const boxes = Object.keys(messages).filter(ALERT_BOXES);
      expect(boxes.length).toBeGreaterThanOrEqual(18);
      expect(
        boxes.filter((id) => /daemon|démon|デーモン|server|serveur|servidor|palvelin|サーバ/iu.test(say(id))),
      ).toEqual([]);
      expect(
        boxes.filter((id) => id.endsWith("_app") && /browser|navigateur|navegador|selain|ブラウザ/iu.test(say(id))),
      ).toEqual([]);
    });

    it("say receive-only with the word of the RX only switch, in the list of types too", () => {
      const word = say("pill.rx");
      expect(["error.transmit.off", ...RECEIVE_ONLY_TYPES].filter((id) => !has(id, word))).toEqual([]);
    });

    it("have one word for the Dummy, and not the word of the HF tests", () => {
      const word = DUMMY[locale.code] ?? "";
      expect(DUMMY_IDS.filter((id) => !has(id, word))).toEqual([]);
      expect(has("tab.skeds", word)).toBe(false);
      if (locale.code === "fi") expect(DUMMY_IDS.filter((id) => has(id, "testi"))).toEqual([]);
    });

    it("name a type of radio by what the operator has in hand: Direwolf only in his own, Mercury only in the Mercury kind's, no band, mode or link, and no line wider than the list has room for", () => {
      const types = Object.keys(messages).filter((id) => id.startsWith("radio.type."));
      expect(types.length).toBeGreaterThanOrEqual(14);
      expect(types.filter((id) => /dire\s*wolf/iu.test(say(id)))).toEqual([OWN_PROGRAM]);
      expect(say(OWN_PROGRAM)).toContain("soundmodem");
      expect(types.filter((id) => say(id).includes("Mercury")).sort()).toEqual([...MERCURY_TYPES].sort());
      expect(types.filter((id) => BAND_OR_LINK.test(say(id)))).toEqual([]);
      expect(types.filter((id) => say(id).length > WIDEST_TYPE)).toEqual([]);
      expect(new Set(types.map(say)).size).toBe(types.length);
    });

    it("call the Sound card type by the word of the Sound card field, and nothing else by it", () => {
      expect(say("radio.type.direwolf")).toBe(say("settings.sound_card.label"));
    });

    it("have one word for each kind of signal, the same in every language: the heading of its group in Add radio, the tag of a radio with no name, and in its box and its Dummy", () => {
      expect([say("channel.fm"), say("channel.hf"), say("channel.lora")]).toEqual(["FM", "Mercury", "LoRa"]);
      for (const [word, ids] of [
        ["FM", ["settings.group.fm_radio", "radio.type.dummy"]],
        [
          "Mercury",
          ["settings.group.hf_radio", "settings.hf_enabled.name", "radio.type.dummy_hf", "settings.tnc.dummy_hf"],
        ],
        ["LoRa", ["settings.group.lora_radio", "radio.type.dummy_lora"]],
      ] as const)
        expect(
          ids.filter((id) => !say(id).includes(word)),
          word,
        ).toEqual([]);
    });

    it("end the name of a type that only receives with the words of RX only, and start or end a Dummy's with the Dummy's", () => {
      const rx = say("pill.rx").toLocaleLowerCase(locale.code);
      expect(RECEIVE_ONLY_TYPES.filter((id) => !say(id).toLocaleLowerCase(locale.code).endsWith(`(${rx})`))).toEqual(
        [],
      );
      const dummy = DUMMY[locale.code] ?? "";
      const edge = (id: string) =>
        say(id)
          .toLocaleLowerCase(locale.code)
          .split(/[\s-]+/);
      expect(
        ["radio.type.dummy", "radio.type.dummy_hf", "radio.type.dummy_lora"].filter(
          (id) => !(edge(id)[0]?.startsWith(dummy) || edge(id).at(-1)?.startsWith(dummy)),
        ),
      ).toEqual([]);
    });

    it("name a field or a switch in a refusal or a reason by its label", () => {
      expect(
        Object.entries(NAMED_LABELS).flatMap(([id, labels]) =>
          labels.filter((label) => !has(id, say(label))).map((label) => `${id}: ${label}`),
        ),
      ).toEqual([]);
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
