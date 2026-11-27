// Classic APRS on HF in the Radio group: a KISS TNC's box has the tick On HF, which stores the
// radio's own `on_hf`; a radio of the type "Sound card, 300 (HF)" has the Sound card box with no
// speed row, its type named clear alone, and the (i) of its Enable names the usual dial.
import { DOMWrapper, flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { configValues, radioRow, radiosTopic, soundCardModem, status } from "@/test/fixtures";

const OWN = {
  "radio/3/port": "/dev/ttyUSB0",
  "radio/3/baud": "",
  "radio/3/on_hf": "false",
  "radio/4/sound_card": "plughw:1,0",
  "radio/4/keying": "vox",
  "radio/4/tx_gain_db": "0",
};

function make() {
  const config = configValues({});
  const daemon = fakeDaemon({
    config: {
      ...config,
      radio_values: { ...config.radio_values, ...OWN },
      radio_defaults: { ...config.radio_defaults, ...OWN },
    },
    radios: radiosTopic(
      radioRow(1, "kenwood-tnc2"),
      radioRow(3, "kiss", { name: "Attic", number: 2 }),
      radioRow(4, "direwolf-300", { name: "30 m", number: 3, modem: soundCardModem() }),
    ),
    status: status({ unheard_radio: 1 }),
  });
  const wrapper = mount(SettingsForm, {
    props: { scope: "settings" },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
  const box = (legend: string) => {
    const found = wrapper.findAll("fieldset.subbox").find((f) => f.find("legend").text() === legend);
    if (!found) throw new Error(`no box ${legend}`);
    return found;
  };
  const sets = () =>
    daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config").map(([c]) => (c as { values: unknown }).values);
  return { daemon, wrapper, box, sets };
}

let mounted: ReturnType<typeof make>["wrapper"] | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
});

describe("classic APRS on HF in the Radio group", () => {
  it("gives a KISS TNC the tick On HF, which stores the radio's own setting", async () => {
    const { wrapper, box, sets } = make();
    mounted = wrapper;
    await flushPromises();
    const tick = box("Attic").find<HTMLInputElement>("#set-radio-3-on_hf");
    expect(tick.exists() && tick.element.type).toBe("checkbox");
    expect(tick.element.checked).toBe(false);
    expect(box("Attic").text()).toContain("On HF");
    await tick.setValue(true);
    await flushPromises();
    expect(sets()).toContainEqual({ "radio/3/on_hf": "true" });
  });

  it("gives the 300 type the Sound card box with no speed and no On HF, and names it clear alone in Radio type", async () => {
    const { wrapper, box } = make();
    mounted = wrapper;
    await flushPromises();
    const hf = box("30 m");
    expect(hf.find("#set-radio-4-sound_card").exists() && hf.find("#set-radio-4-keying").exists()).toBe(true);
    expect(hf.find("#set-radio-4-baud").exists() || hf.find("#set-radio-4-on_hf").exists()).toBe(false);
    const type = hf.find<HTMLSelectElement>("#set-radio-4-type");
    expect(type.element.selectedOptions[0]?.textContent?.trim()).toBe("Packet, sound card, 300");
  });

  it("names the usual dial in the (i) of the 300 radio's Enable, in one line, and not in a KISS TNC's", async () => {
    const { wrapper, box } = make();
    mounted = wrapper;
    await flushPromises();
    const open = async (id: string) => {
      const toggle = wrapper.find(`#${id}`).element.closest(".field")?.querySelector<HTMLButtonElement>(".info-toggle");
      if (!toggle) throw new Error(`no (i) beside ${id}`);
      await new DOMWrapper(toggle).trigger("click");
      return wrapper.find(".info-text").text();
    };
    expect(await open("set-radio-4-enabled")).toMatch(/^The usual classic APRS dial on HF is 10\.1476 MHz USB\./);
    expect(await open("set-radio-3-enabled")).not.toContain("10.1476");
    expect(box("30 m").exists()).toBe(true);
  });
});
