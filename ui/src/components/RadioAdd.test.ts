// Add radio's list of every type, in groups under headings: Packet (classic APRS), Mercury (DATAC3),
// LoRa (each kind's heading; types in the daemon's order, receive-only last) and Without a radio
// (the Dummy types, by the type's own fact `dummy`). A line is the type's own name with a capital,
// and the band after it where the type is for one. The placeholder comes first, outside the
// groups; a type this installation does not carry is left out, and an empty group is not drawn.
// Choosing a type and Add still add that type.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import RadioAdd from "@/components/RadioAdd.vue";
import { setLocale } from "@/i18n";
import { FIELDS } from "@/lib/settings";
import { addTypeChoices } from "@/lib/settingsradio";
import { fakeDaemon, withDaemon } from "@/test/context";
import { status } from "@/test/fixtures";

afterEach(() => setLocale("en"));

function make(unavailable: string[] = []) {
  const daemon = fakeDaemon({ status: status({ unavailable_types: unavailable }) });
  const wrapper = mount(RadioAdd, { global: withDaemon(daemon) });
  return { wrapper, send: daemon.send };
}

/**
 * The list as drawn: each child of the select, an option by its words, a group by its heading and
 * its options.
 */
const drawn = (wrapper: VueWrapper) =>
  [...wrapper.find<HTMLSelectElement>("select").element.children].map((child) =>
    child instanceof HTMLOptGroupElement
      ? { [child.label]: [...child.children].map((o) => o.textContent?.trim()) }
      : child.textContent?.trim(),
  );

const PACKET = [
  "Sound card, 1200 (VHF/UHF)",
  "Sound card, 300 (HF)",
  "KISS TNC",
  "Kenwood TM-D710 / TH-D72",
  "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2",
  "Kantronics KPC-3+",
  "Direwolf",
  "Yaesu FTM, TNC in monitor mode (RX only)",
];
const MERCURY = ["Sound card"];
const LORA = ["Tracker or iGate on Wi-Fi", "Tracker or iGate on USB or Bluetooth", "iGate on USB (RX only)"];
const WITHOUT = ["Dummy packet radio", "Dummy Mercury radio", "Dummy LoRa radio"];

describe("Add radio's list", () => {
  it("has the placeholder first, then the four groups in order with their types, those that only receive last in their group", () => {
    const { wrapper } = make();
    expect(drawn(wrapper)).toEqual([
      "Radio type",
      { "Packet (classic APRS)": PACKET },
      { "Mercury (DATAC3)": MERCURY },
      { LoRa: LORA },
      { "Without a radio": WITHOUT },
    ]);
  });

  it("leaves out the types this installation does not carry (Direwolf's two), their group stays", () => {
    const { wrapper } = make(["direwolf", "direwolf-300"]);
    expect(drawn(wrapper)).toEqual([
      "Radio type",
      { "Packet (classic APRS)": PACKET.filter((words) => !words.startsWith("Sound card")) },
      { "Mercury (DATAC3)": MERCURY },
      { LoRa: LORA },
      { "Without a radio": WITHOUT },
    ]);
  });

  it("draws no heading for a group with nothing in it", () => {
    const { wrapper } = make(["mercury"]);
    expect(drawn(wrapper)).toEqual([
      "Radio type",
      { "Packet (classic APRS)": PACKET },
      { LoRa: LORA },
      { "Without a radio": WITHOUT },
    ]);
    expect(addTypeChoices(["mercury"]).map((choice) => choice.group)).not.toContain("Mercury (DATAC3)");
  });

  it("names its groups and its lines in the page's language", () => {
    setLocale("de");
    const { wrapper } = make();
    expect(wrapper.findAll("optgroup").map((group) => group.attributes("label"))).toEqual([
      "Packet (klassisches APRS)",
      "Mercury (DATAC3)",
      "LoRa",
      "Ohne Funkgerät",
    ]);
    expect(addTypeChoices().find((choice) => choice.value === "direwolf-300")?.label).toBe("Soundkarte, 300 (KW)");
  });

  it("has the (i) of Radio type: who each kind reaches, and the KISS TNCs by example", () => {
    expect(FIELDS["tnc/profile"]?.tip).toEqual([
      "Packet reaches classic APRS stations; Mercury only Mercury stations; LoRa only LoRa stations.",
      "A Kenwood TH-D74/D75, a Mobilinkd and most other TNCs are KISS TNC.",
    ]);
  });

  it("adds the type chosen in a group, as before", async () => {
    const { wrapper, send } = make();
    await wrapper.find("select").setValue("lora-console");
    expect(send).not.toHaveBeenCalled();
    await wrapper.find("button").trigger("click");
    expect(send.mock.calls).toEqual([[{ cmd: "radio_add", type: "lora-console" }]]);
    expect(wrapper.find<HTMLSelectElement>("select").element.value).toBe("");
    expect(wrapper.emitted("added")).toEqual([["lora-console"]]);
  });
});
