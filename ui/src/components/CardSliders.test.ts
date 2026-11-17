// The sliders of a sound card's own levels (CardSlider.vue) in a radio's box: the Transmit level row has the card's slider in the place of - and + where the card has a playback control (the FTX-1's C-Media chip,
// a TI codec), and is today's row where it has none; the Receive level row has the slider of the card's capture control before its bar, and none where the card has none (the codec). The slider stands at the card's
// own level as the row says it, follows the pointer, saves the radio's `tx_card` or `rx_card` when it is let go and stays there until the row says the card's level; no row is added or taken away by a slider, on a
// phone (375 px) too, where the Receive level's slider has its own line in the row. The Mercury radio's box has the same two by the same components (the Transmit level row with its peak, and the scope's receive level).
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import HfLevelBar from "@/components/HfLevelBar.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import type { SettingsFormState } from "@/composables/useSettingsForm";
import { pageRadio } from "@/lib/radios";
import type { CardLevelsRow, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { configValues, modemState, radioRow, radiosTopic, soundCardModem, status } from "@/test/fixtures";

const RESPONSIVE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "styles", "responsive.css"), "utf8");
const OWN = {
  "radio/3/sound_card": "plughw:CARD=Device,DEV=0",
  "radio/3/keying": "rts:/dev/ttyUSB1",
  "radio/3/tx_gain_db": "0",
  "radio/3/tx_card": "",
  "radio/3/rx_card": "",
  "radio/3/beacon": "true",
};
const FTX1: CardLevelsRow = { tx: 38, rx: 50 };
const CODEC: CardLevelsRow = { tx: 100, rx: null };
const NO_CONTROLS: CardLevelsRow = { tx: null, rx: null };

function radios(card: CardLevelsRow): Map<string, RadioRow> {
  return radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(3, "direwolf", { name: "FTX1", number: 2, modem: soundCardModem({ rx_level: 48 }), card }));
}

function settingsWith(own: Record<string, string> = {}) {
  const config = configValues({});
  return { ...config, radio_values: { ...config.radio_values, ...OWN, ...own }, radio_defaults: { ...config.radio_defaults, ...OWN } };
}

function make(card: CardLevelsRow) {
  const daemon = fakeDaemon({ config: settingsWith(), radios: radios(card), status: status({}) });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
  const box = () => {
    const found = wrapper.findAll("fieldset.subbox").find((f) => f.find("legend").text() === "FTX1");
    if (!found) throw new Error("no box of the Sound card radio");
    return found;
  };
  const labels = () =>
    box()
      .findAll(".field")
      .map((row) => row.find("label").text());
  return { daemon, wrapper, box, labels };
}

let mounted: { unmount(): void } | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
  document.documentElement.classList.remove("size-phone");
});

describe("the sound card's own levels in a Sound card radio's box", () => {
  it("are two sliders at the card's own levels where the card has both controls, in the Transmit level row and before the Receive level's bar", async () => {
    const { wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    expect(tx.attributes("id")).toBe("set-radio-3-txlevel-up");
    expect((tx.element as HTMLInputElement).value).toBe("38");
    expect(box().find(".txlevel .txlevel-value").text()).toBe("38 %");
    expect(box().find(".txlevel .stepbtn").exists()).toBe(false); // (one transmit level: the card's, not the modem's beside it)
    const level = box().find(".scope-level");
    const rx = level.find("input[type=range]");
    expect((rx.element as HTMLInputElement).value).toBe("50");
    expect(rx.attributes("aria-label")).toBe("Sound card input level");
    expect([...level.element.children].map((c) => c.className.split(" ")[0])).toEqual(["cardslider", "levelbar", "mono", "infotip"]); // (one row: the slider sets, the bar shows)
    expect(level.find(".levelvalue").text()).toBe("48");
  });

  it("has no slider where the card has no control: the codec's Receive level is the bar alone, and a card of neither has today's - and +", async () => {
    const codec = make(CODEC);
    mounted = codec.wrapper;
    await flushPromises();
    expect(codec.box().find(".txlevel input[type=range]").exists()).toBe(true);
    expect(codec.box().find(".scope-level input[type=range]").exists()).toBe(false);
    const withSliders = codec.labels();
    codec.wrapper.unmount();
    const none = make(NO_CONTROLS);
    mounted = none.wrapper;
    await flushPromises();
    expect(none.box().find("input[type=range]").exists()).toBe(false);
    expect(none.box().findAll(".txlevel .stepbtn")).toHaveLength(2);
    expect(none.labels()).toEqual(withSliders); // (no row is added or taken away, and no label: the rows are the same with the sliders and without)
  });

  it("saves the value when the slider is let go, keeps the thumb there until the card says its level, and restarts nothing", async () => {
    const { daemon, wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    (tx.element as HTMLInputElement).value = "55";
    await tx.trigger("input"); // (dragged: the thumb and the number follow, nothing is sent)
    expect(box().find(".txlevel .txlevel-value").text()).toBe("55 %");
    expect(daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config")).toHaveLength(0);
    await tx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/tx_card": "55" } });
    await tell(daemon, { radios: radios(FTX1) }); // (a row that still says the old level: the poll before the card was set)
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("55");
    await tell(daemon, { radios: radios({ tx: 55, rx: 50 }) });
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("55");
    await tell(daemon, { config: settingsWith({ "radio/3/tx_card": "55" }) }); // (the daemon has saved it: the next change is sent)
    const rx = box().find(".scope-level input[type=range]");
    (rx.element as HTMLInputElement).value = "20";
    await rx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/rx_card": "20" } });
    expect(daemon.send.mock.calls.map(([c]) => c.cmd)).not.toContain("radio_change"); // (a level is a setting of the radio, not a change of it that restarts it)
  });

  it("leaves the thumb under the pointer while it is dragged, whatever level the row says meanwhile", async () => {
    const { daemon, wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    (tx.element as HTMLInputElement).value = "70";
    await tx.trigger("input");
    await tell(daemon, { radios: radios({ tx: 40, rx: 50 }) }); // (the desktop moved the card while the operator drags)
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("70");
    expect(box().find(".txlevel .txlevel-value").text()).toBe("70 %");
    await tx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/tx_card": "70" } });
  });

  it("keeps the rows on a phone (375 px), where the Receive level's slider has the control's line above the bar", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    document.documentElement.classList.add("size-phone");
    const { wrapper, labels } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const phone = labels();
    wrapper.unmount();
    const none = make(NO_CONTROLS);
    mounted = none.wrapper;
    await flushPromises();
    expect(none.labels()).toEqual(phone);
    expect(RESPONSIVE).toMatch(/\.size-phone \.scope-level:has\(> \.cardslider\) \{\s*flex-wrap: wrap;/); // (jsdom has no layout: the rule is what puts the slider on its own line)
    expect(RESPONSIVE).toMatch(/\.size-phone \.scope-level > \.cardslider \{\s*flex: 1 1 100%;/);
  });
});

describe("the sound card's own levels in a Mercury radio's box", () => {
  const HF = {
    "radio/2/beacon": "true",
    "radio/2/sound_card": "plughw:1,0",
    "radio/2/keying": "vox",
    "radio/2/tx_gain_db": "0",
    "radio/2/tx_card": "",
    "radio/2/rx_card": "",
  };

  it("has the card's slider in the Transmit level row with the peak under it", async () => {
    const daemon = fakeDaemon({
      config: configValues({}, HF),
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { modem: modemState({ scope: true, tx_peak_dbfs: -6 }), card: FTX1 })),
    });
    const wrapper = mount(SettingsForm, { props: { scope: "settings" }, global: withDaemon(daemon), attachTo: document.body });
    mounted = wrapper;
    await flushPromises();
    const row = wrapper.find("#set-radio-2-txlevel-up").element.closest(".txlevel");
    expect(row?.querySelector("input[type=range]")?.getAttribute("id")).toBe("set-radio-2-txlevel-up");
    expect(row?.querySelector(".txlevel-peak")?.textContent).toBe("Peak -6 dBFS");
    expect(row?.querySelectorAll(".stepbtn")).toHaveLength(0);
  });

  it("has the slider of the card's capture level before the scope's receive level bar, and the monitor card over the map has the bar alone", async () => {
    const row = radioRow(2, "mercury", { modem: modemState({ scope: true }), card: FTX1 });
    const daemon = fakeDaemon({ radios: radiosTopic(row) });
    const form = { choose: vi.fn() } as unknown as SettingsFormState;
    const box = mount(HfLevelBar, { props: { on: true, radio: 2, tip: true, card: { radio: pageRadio(row), form } }, global: withDaemon(daemon) });
    mounted = box;
    const slider = box.find(".scope-level input[type=range]");
    expect((slider.element as HTMLInputElement).value).toBe("50");
    (slider.element as HTMLInputElement).value = "64";
    await slider.trigger("change");
    expect(form.choose).toHaveBeenCalledWith({ "radio/2/rx_card": "64" });
    box.unmount();
    const monitor = mount(HfLevelBar, { props: { on: true, radio: 2 }, global: withDaemon(daemon) });
    mounted = monitor;
    expect(monitor.find("input[type=range]").exists()).toBe(false);
  });
});
