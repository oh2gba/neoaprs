// A refusal that names a radio, as the page says it: the daemon names the radio in its own English ("radio HF 2", "in use by radio Packet") and sends its id beside (`radio`, `held_by`); given the page's radios, the
// sentence says the radio as the page calls it (lib/radios.ts), in the page's language, and a radio the page does not know, the GPS receiver, and a page that gives no radios keep the daemon's words.
import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { errorLine, errorReason, type Failure, type RadioNames } from "@/i18n/errortext";
import { pageRadios, radioLabel } from "@/lib/radios";
import { radioRow, radiosTopic } from "@/test/fixtures";

/** The page's radios, named in the language of the page now (the page makes them again when the language changes). */
function names(): RadioNames {
  const radios = pageRadios(
    radiosTopic(
      radioRow(1, "kenwood-tnc2"),
      radioRow(2, "mercury"),
      radioRow(3, "mercury", { number: 2 }),
      radioRow(4, "dummy", { name: "Shack", number: 2 }),
      radioRow(5, "kiss", { number: 3, enabled: false, removed: true }),
    ),
    null,
  );
  return { byId: (id) => radios.find((radio) => radio.id === id) };
}

const refusal = (code: string, params: Record<string, string | number>, cmd = "radio_tune"): Failure => ({
  cmd,
  key: null,
  code,
  params,
  text: `${cmd}: the daemon's words`,
});

afterEach(() => setLocale("en"));

describe("a refusal that names a radio", () => {
  it("says the radio by the page's name for it, from its id", () => {
    expect(errorReason(refusal("radio.no_modem", { name: "Mercury 2", radio: 3 }), names())).toBe(
      "radio Mercury 2 has no modem running",
    );
    expect(errorReason(refusal("radio.off", { name: "Shack", radio: 4 }, "qru_ask"), names())).toBe(
      "radio Shack is off: turn it on first",
    );
    expect(errorLine(refusal("radio.no_scope", { name: "Mercury", radio: 2 }, "radio_scope"), names())).toBe(
      "radio Mercury has no scope",
    );
  });

  it("says it in the page's language, the radio's name with the sentence around it", () => {
    setLocale("de");
    expect(errorReason(refusal("radio.no_modem", { name: "Mercury 2", radio: 3 }), names())).toBe(
      "beim Funkgerät Mercury 2 läuft kein Modem",
    );
    expect(
      errorReason(
        refusal("radio.resource_held", { resource: "serial", holder: "Mercury", held_by: 2 }, "set_config"),
        names(),
      ),
    ).toBe("das Gerät ist vom Funkgerät Mercury belegt: wähle ein anderes");
    expect(errorReason(refusal("radio.no_modem", { name: "Mercury 2", radio: 3 }))).toBe(
      "beim Funkgerät Mercury 2 läuft kein Modem",
    );
  });

  it("says why a status went on no radio by the radio's own name, inside nothing was sent, all of it in the page's language", () => {
    const why = (name: string, radio: number) =>
      refusal("status.not_sent", { why: "status.too_long_for_radio", name, radio }, "status_now");
    expect(errorLine(why("Shack", 4), names())).toBe("nothing was sent: the status is too long for radio Shack");
    expect(errorLine(why("LoRa", 9), names()), "a radio the page does not know: the daemon's name").toBe(
      "nothing was sent: the status is too long for radio LoRa",
    );
    setLocale("nl");
    expect(errorLine(why("Mercury 2", 3), names())).toBe(
      "er is niets verzonden: de status is te lang voor radio Mercury 2",
    );
    expect(errorLine(refusal("status.not_sent", { why: "radio.none" }, "status_now"), names())).not.toMatch(
      /there is|no radio/,
    );
  });

  it("names the holder of a device by its id, and the GPS receiver by its own words", () => {
    expect(
      errorReason(
        refusal("radio.resource_held", { resource: "serial", holder: "Shack", held_by: 4 }, "set_config"),
        names(),
      ),
    ).toBe("the device is in use by radio Shack: choose another");
    expect(
      errorReason(
        refusal("radio.resource_held", { resource: "gps", holder: "GPS", held_by: 0 }, "set_config"),
        names(),
      ),
    ).toBe("the device is in use by the GPS receiver: choose another");
  });

  it("keeps the daemon's words for a radio the page does not know, and the name typed of a name that is taken", () => {
    expect(errorReason(refusal("radio.no_line", { name: "Packet 4", radio: 9 }, "find_radio"), names())).toBe(
      "radio Packet 4 has no serial line to look for",
    );
    expect(errorReason(refusal("radio.name_taken", { name: "Mobile", radio: 4 }, "radio_add"), names())).toBe(
      "the name 'Mobile' is another radio's already: give this one another",
    );
  });

  it("says a removed radio is removed, by its name, and a radio that never was by its number", () => {
    expect(
      errorReason(refusal("radio.unknown", { radio: 5, name: "Packet 3", removed: 1 }, "radio_change"), names()),
    ).toBe("radio Packet 3 is removed");
    expect(errorReason(refusal("radio.unknown", { radio: 9 }, "radio_change"), names())).toBe("there is no radio 9");
    setLocale("de");
    expect(
      errorReason(refusal("radio.unknown", { radio: 3, name: "Mercury 2", removed: 1 }, "radio_change"), names()),
    ).toBe("das Funkgerät Mercury 2 wurde entfernt");
  });

  it("says the kind of a radio that takes only a type of its own kind by the page's word for it", () => {
    setLocale("de");
    expect(
      errorReason(
        refusal("radio.type_kind", { type: "kiss", kind: "Mercury", name: "Mercury 2", radio: 3 }, "radio_change"),
        names(),
      ),
    ).toBe("das Funkgerät Mercury 2 nimmt nur einen Typ seiner Art (Mercury)");
    expect(
      errorReason(
        refusal("radio.type_kind", { type: "kiss", kind: "Mercury", name: "Mercury 2", radio: 3 }, "radio_change"),
      ),
    ).toBe("das Funkgerät Mercury 2 nimmt nur einen Typ seiner Art (Mercury)");
    const sentence = {
      en: (word: string) => `radio Mast takes only a type of its own kind (${word})`,
      de: (word: string) => `das Funkgerät Mast nimmt nur einen Typ seiner Art (${word})`,
    };
    for (const locale of ["en", "de"] as const) {
      setLocale(locale);
      for (const kind of ["fm", "hf", "lora"] as const) {
        const one: RadioNames = { byId: () => ({ name: "Mast", kind }) };
        expect(
          errorReason(
            refusal("radio.type_kind", { type: "kiss", kind: "LoRa", name: "LoRa", radio: 7 }, "radio_change"),
            one,
          ),
        ).toBe(sentence[locale](radioLabel({ name: "", kind, number: 1 })));
      }
    }
  });
});
