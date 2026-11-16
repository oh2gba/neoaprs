// Add radio's list of every type, in groups under their headings: FM, Mercury, LoRa (each kind's word, which is the tag of an unnamed radio too; each kind's real types in the order of the daemon's list, those that only receive last), and Without a radio (the Dummy types, by the type's own fact `dummy`); the
// placeholder first, outside the groups; a type this installation does not carry left out, and a group with nothing in it not drawn; choosing a type and Add still add that type.
import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import RadioAdd from "@/components/RadioAdd.vue";
import { setLocale } from "@/i18n";
import { addTypeChoices } from "@/lib/settingsradio";
import { fakeDaemon, withDaemon } from "@/test/context";
import { status } from "@/test/fixtures";

afterEach(() => setLocale("en"));

function make(unavailable: string[] = []) {
  const daemon = fakeDaemon({ status: status({ unavailable_types: unavailable }) });
  const wrapper = mount(RadioAdd, { global: withDaemon(daemon) });
  return { wrapper, send: daemon.send };
}

/** The list as it is drawn: each child of the select, an option by its words, a group by its heading with its options' words. */
const drawn = (wrapper: VueWrapper) =>
  [...wrapper.find<HTMLSelectElement>("select").element.children].map((child) =>
    child instanceof HTMLOptGroupElement ? { [child.label]: [...child.children].map((o) => o.textContent?.trim()) } : child.textContent?.trim(),
  );

const FM = [
  "Sound card",
  "KISS TNC (Kenwood TH-D74/D75, Mobilinkd…)",
  "Kenwood TM-D710 / TH-D72",
  "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2",
  "Kantronics KPC-3+",
  "Your own Direwolf or soundmodem",
  "Yaesu FTM, TNC in monitor mode (RX only)",
];
const MERCURY = ["Mercury modem (sound card)"];
const LORA = ["LoRa APRS board on the network", "LoRa APRS board on USB or Bluetooth", "LoRa APRS iGate on USB (RX only)"];
const WITHOUT = ["Dummy FM radio", "Dummy Mercury radio", "Dummy LoRa radio"];

describe("Add radio's list", () => {
  it("has the placeholder first, then the four groups in order with their types, those that only receive last in their group", () => {
    const { wrapper } = make();
    expect(drawn(wrapper)).toEqual(["Radio type", { FM }, { Mercury: MERCURY }, { LoRa: LORA }, { "Without a radio": WITHOUT }]);
  });

  it("leaves out a type this installation does not carry (Direwolf), its group stays", () => {
    const { wrapper } = make(["direwolf"]);
    expect(drawn(wrapper)).toEqual([
      "Radio type",
      { FM: FM.filter((words) => words !== "Sound card") },
      { Mercury: MERCURY },
      { LoRa: LORA },
      { "Without a radio": WITHOUT },
    ]);
  });

  it("draws no heading for a group with nothing in it", () => {
    const { wrapper } = make(["mercury"]);
    expect(drawn(wrapper)).toEqual(["Radio type", { FM }, { LoRa: LORA }, { "Without a radio": WITHOUT }]);
    expect(addTypeChoices(["mercury"]).map((choice) => choice.group)).not.toContain("Mercury");
  });

  it("names its groups in the page's language: the kind words, and Without a radio", () => {
    setLocale("de");
    const { wrapper } = make();
    expect(wrapper.findAll("optgroup").map((group) => group.attributes("label"))).toEqual(["FM", "Mercury", "LoRa", "Ohne Funkgerät"]);
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
