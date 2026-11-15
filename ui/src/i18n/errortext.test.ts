// A refusal that names a radio, as the page says it: the daemon names the radio in its own English ("the HF 2 radio", "in use by FM") and sends its id beside (`radio`, `held_by`); given the page's radios, the
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
    expect(errorReason(refusal("radio.no_modem", { name: "HF 2", radio: 3 }), names())).toBe("the HF 2 radio has no modem running");
    expect(errorReason(refusal("radio.off", { name: "Shack", radio: 4 }, "qru_ask"), names())).toBe("the Shack radio is off: turn it on first");
    expect(errorLine(refusal("radio.no_scope", { name: "HF", radio: 2 }, "radio_scope"), names())).toBe("the HF radio has no scope");
  });

  it("says it in the page's language, also where the sentence around it is not translated yet", () => {
    setLocale("de");
    expect(errorReason(refusal("radio.no_modem", { name: "HF 2", radio: 3 }), names())).toBe("the KW 2 radio has no modem running");
    expect(errorReason(refusal("radio.resource_held", { resource: "serial", holder: "HF", held_by: 2 }, "set_config"), names())).toBe(
      "that device is in use by KW: choose another",
    );
    expect(errorReason(refusal("radio.no_modem", { name: "HF 2", radio: 3 }))).toBe("the HF 2 radio has no modem running");
  });

  it("names the holder of a device by its id, and the GPS receiver as the daemon does", () => {
    expect(errorReason(refusal("radio.resource_held", { resource: "serial", holder: "Shack", held_by: 4 }, "set_config"), names())).toBe(
      "that device is in use by Shack: choose another",
    );
    expect(errorReason(refusal("radio.resource_held", { resource: "gps", holder: "GPS", held_by: 0 }, "set_config"), names())).toBe(
      "that device is in use by GPS: choose another",
    );
  });

  it("keeps the daemon's words for a radio the page does not know, and the name typed of a name that is taken", () => {
    expect(errorReason(refusal("radio.no_line", { name: "FM 4", radio: 9 }, "find_radio"), names())).toBe("the FM 4 radio has no serial line to look for");
    expect(errorReason(refusal("radio.name_taken", { name: "Mobile", radio: 4 }, "radio_add"), names())).toBe(
      "the name 'Mobile' is another radio's already: give this one another",
    );
  });

  it("says a removed radio is removed, by its name, and a radio that never was by its number", () => {
    expect(errorReason(refusal("radio.unknown", { radio: 5, name: "FM 3", removed: 1 }, "radio_change"), names())).toBe("the FM 3 radio is removed");
    expect(errorReason(refusal("radio.unknown", { radio: 9 }, "radio_change"), names())).toBe("there is no radio 9");
    setLocale("de");
    expect(errorReason(refusal("radio.unknown", { radio: 3, name: "HF 2", removed: 1 }, "radio_change"), names())).toBe("the KW 2 radio is removed");
  });

  it("says the kind of a radio that takes only a type of its own kind by the page's word for it", () => {
    setLocale("de");
    expect(errorReason(refusal("radio.type_kind", { type: "kiss", kind: "HF", name: "HF 2", radio: 3 }, "radio_change"), names())).toBe(
      "the KW 2 radio takes only a type of its own kind (KW)",
    );
    expect(errorReason(refusal("radio.type_kind", { type: "kiss", kind: "HF", name: "HF 2", radio: 3 }, "radio_change"))).toBe(
      "the HF 2 radio takes only a type of its own kind (HF)",
    );
    for (const locale of ["en", "de"] as const) {
      setLocale(locale);
      for (const kind of ["fm", "hf", "lora"] as const) {
        const one: RadioNames = { byId: () => ({ name: "Mast", kind }) };
        expect(errorReason(refusal("radio.type_kind", { type: "kiss", kind: "LoRa", name: "LoRa", radio: 7 }, "radio_change"), one)).toBe(
          `the Mast radio takes only a type of its own kind (${radioLabel({ name: "", kind, number: 1 })})`,
        );
      }
    }
  });
});
