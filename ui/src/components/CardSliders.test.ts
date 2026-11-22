// The sliders of a sound card's own levels (CardSlider.vue) in a radio's box. The Transmit level
// row has the card's slider in place of the - and + buttons where the card has a playback
// control and the modem gain is 0. The Receive level row has the capture slider before its bar,
// or an empty room where the card has none or its levels are not known yet. The slider follows
// the pointer and saves `tx_card` or `rx_card` on release. No slider adds or removes a row, on a
// phone (375 px) too. The Mercury radio's box uses the same components.
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
import { stubWidth } from "@/test/width";

const HERE = dirname(fileURLToPath(import.meta.url));
const RESPONSIVE = readFileSync(join(HERE, "..", "styles", "responsive.css"), "utf8");
const SLIDER = readFileSync(join(HERE, "CardSlider.vue"), "utf8");
const TXLEVEL = readFileSync(join(HERE, "HfLevelRow.vue"), "utf8");
/** The body of the rule of `selector` in a component's or a sheet's source (jsdom lays nothing
 * out: the rules are what place and draw the slider). */
function rule(source: string, selector: string): string {
  const at = source.indexOf(`\n${selector} {`);
  if (at < 0) throw new Error(`no rule ${selector}`);
  return source.slice(at + selector.length + 3, source.indexOf("}", at));
}
const OWN = {
  "radio/3/sound_card": "plughw:CARD=Device,DEV=0",
  "radio/3/keying": "rts:/dev/ttyUSB1",
  "radio/3/tx_gain_db": "0",
  "radio/3/tx_card": "",
  "radio/3/rx_card": "",
  "radio/3/beacon": "true",
};
const FTX1: CardLevelsRow = { tx: 38, rx: 50, read: true };
const CODEC: CardLevelsRow = { tx: 100, rx: null, read: true };
const NO_CONTROLS: CardLevelsRow = { tx: null, rx: null, read: true };
const NOT_READ: CardLevelsRow = { tx: null, rx: null, read: false };

function radios(card: CardLevelsRow): Map<string, RadioRow> {
  return radiosTopic(
    radioRow(1, "kenwood-tnc2"),
    radioRow(3, "direwolf", { name: "FTX1", number: 2, modem: soundCardModem({ rx_level: 48 }), card }),
  );
}

function settingsWith(own: Record<string, string> = {}) {
  const config = configValues({});
  return {
    ...config,
    radio_values: { ...config.radio_values, ...OWN, ...own },
    radio_defaults: { ...config.radio_defaults, ...OWN },
  };
}

function make(card: CardLevelsRow, own: Record<string, string> = {}) {
  const daemon = fakeDaemon({ config: settingsWith(own), radios: radios(card), status: status({}) });
  const wrapper = mount(SettingsForm, {
    props: { scope: "settings" },
    global: withDaemon(daemon),
    attachTo: document.body,
  });
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
    expect(box().find(".txlevel .cardslider-value").text()).toBe("38 %");
    expect(box().find(".txlevel .stepbtn").exists()).toBe(false);
    const level = box().find(".scope-level");
    const rx = level.find("input[type=range]");
    expect((rx.element as HTMLInputElement).value).toBe("50");
    expect(rx.attributes("aria-label")).toBe("Sound card input level");
    expect([...level.element.children].map((c) => c.className.split(" ")[0])).toEqual([
      "cardslider",
      "levelbar",
      "mono",
      "infotip",
    ]);
    expect(level.find(".levelvalue").text()).toBe("48");
  });

  it("has both sliders in rooms of one share of the control column, each with its percent in a room every value fits, and the (i) of both rows at the column's end", async () => {
    const { wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const parts = (room: Element) => [...room.children].map((c) => `${c.tagName}.${c.className.split(" ").at(-1)}`);
    const tx = box().find(".txlevel .txlevel-control > .cardslider");
    const rx = box().find(".scope-level > .cardslider");
    expect(parts(tx.element)).toEqual(["INPUT.cardslider-input", "OUTPUT.cardslider-value"]);
    expect(parts(rx.element)).toEqual(["INPUT.cardslider-input", "OUTPUT.cardslider-value"]);
    expect(tx.find(".cardslider-value").text()).toBe("38 %");
    expect(rx.find(".cardslider-value").text()).toBe("50 %");
    expect(box().find(".txlevel .txlevel-control").element.lastElementChild?.className).toContain("infotip");
    expect(rule(SLIDER, ".cardslider")).toMatch(
      /flex: 0 0 min\(40%, calc\(100% - 104px - 9ch\)\);\s*font-family: var\(--mono\);/,
    );
    expect(rule(SLIDER, ".cardslider-value")).toMatch(/width: 5ch;[^]*text-align: right;/);
    expect(rule(TXLEVEL, ".txlevel-control > .infotip")).toMatch(/margin-left: auto;/);
  });

  it("has both sliders on lines of their own in a control column too narrow for them beside the bar, the Receive level's under its bar, and both in one line again in a wider one", async () => {
    const width = stubWidth(258); // (the control column of the 480 px panel every window under 1280 px has)
    try {
      const { wrapper, box } = make(FTX1);
      mounted = wrapper;
      await flushPromises();
      const narrow = () =>
        box()
          .findAll(".cardslider")
          .map((room) => room.classes("narrow"));
      expect(narrow()).toEqual([true, true]);
      width.set(309); // (a 560 px panel)
      await flushPromises();
      expect(narrow()).toEqual([false, false]);
      width.set(220); // (a tablet's panel)
      await flushPromises();
      expect(narrow()).toEqual([true, true]);
      expect(RESPONSIVE).toMatch(
        /\.size-phone \.field-control > \.cardslider,\s*\.field-control > \.cardslider\.narrow \{\s*flex-basis: calc\(100% - 28px\);/,
      );
      expect(RESPONSIVE).toMatch(
        /\.size-phone \.scope-level > \.cardslider,\s*\.scope-level > \.cardslider\.narrow \{\s*order: 1;/,
      );
      expect(RESPONSIVE).toMatch(/\n\.scope-level:has\(> \.cardslider\) \{\s*flex-wrap: wrap;/);
    } finally {
      width.restore();
    }
  });

  it("is a slider of the page's own drawing: a thin track, the accent up to the thumb, a round thumb with the buttons' border, and the focus ring and the dimming of the other controls", async () => {
    const { wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    expect((tx.element as HTMLInputElement).style.getPropertyValue("--fill")).toBe("38%");
    (tx.element as HTMLInputElement).value = "55";
    await tx.trigger("input");
    expect((tx.element as HTMLInputElement).style.getPropertyValue("--fill")).toBe("55%");
    expect(SLIDER).not.toMatch(/accent-color/); // (not the engine's own slider, which every engine draws its way)
    expect(rule(SLIDER, ".cardslider-input")).toMatch(/appearance: none;/);
    expect(rule(SLIDER, ".cardslider-input::-webkit-slider-runnable-track")).toMatch(
      /height: 4px;[^]*background: linear-gradient\(to right, var\(--accent\) var\(--fill\), var\(--border\) var\(--fill\)\);/,
    );
    expect(rule(SLIDER, ".cardslider-input::-moz-range-track")).toMatch(/height: 4px;[^]*background: var\(--border\);/);
    expect(rule(SLIDER, ".cardslider-input::-moz-range-progress")).toMatch(/background: var\(--accent\);/);
    for (const thumb of ["::-webkit-slider-thumb", "::-moz-range-thumb"]) {
      expect(rule(SLIDER, `.cardslider-input${thumb}`)).toMatch(
        /width: 16px;\s*height: 16px;[^]*border: 1px solid var\(--border\);\s*border-radius: 50%;/,
      );
      expect(rule(SLIDER, `.cardslider-input:focus-visible${thumb}`)).toMatch(/outline: 2px solid var\(--accent\);/);
    }
    expect(rule(SLIDER, ".cardslider-input:disabled")).toMatch(/opacity: 0\.5;/);
  });

  it("has no slider where the card has no control: the codec's Receive level has the bar and the slider's empty room, and a card of neither has today's - and +", async () => {
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
    expect(none.labels()).toEqual(withSliders);
  });

  it("saves the value when the slider is let go, keeps the thumb there until the card says its level, and restarts nothing", async () => {
    const { daemon, wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    (tx.element as HTMLInputElement).value = "55";
    await tx.trigger("input"); // (dragged: the thumb and the number follow, nothing is sent)
    expect(box().find(".txlevel .cardslider-value").text()).toBe("55 %");
    expect(daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config")).toHaveLength(0);
    await tx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/tx_card": "55" } });
    await tell(daemon, { radios: radios(FTX1) });
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("55");
    await tell(daemon, { radios: radios({ tx: 55, rx: 50, read: true }) });
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("55");
    await tell(daemon, { config: settingsWith({ "radio/3/tx_card": "55" }) });
    const rx = box().find(".scope-level input[type=range]");
    (rx.element as HTMLInputElement).value = "20";
    await rx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/rx_card": "20" } });
    expect(daemon.send.mock.calls.map(([c]) => c.cmd)).not.toContain("radio_change");
  });

  it("leaves the thumb under the pointer while it is dragged, whatever level the row says meanwhile", async () => {
    const { daemon, wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    (tx.element as HTMLInputElement).value = "70";
    await tx.trigger("input");
    await tell(daemon, { radios: radios({ tx: 40, rx: 50, read: true }) });
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("70");
    expect(box().find(".txlevel .cardslider-value").text()).toBe("70 %");
    await tx.trigger("change");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/tx_card": "70" } });
  });

  it("follows the card again after a drag let go where it was pressed, which saves nothing", async () => {
    const { daemon, wrapper, box } = make(FTX1);
    mounted = wrapper;
    await flushPromises();
    const tx = box().find(".txlevel input[type=range]");
    (tx.element as HTMLInputElement).value = "70";
    await tx.trigger("input");
    (tx.element as HTMLInputElement).value = "38";
    await tx.trigger("input");
    await tx.trigger("pointerup"); // (back where it was pressed: the browser fires no change)
    await tell(daemon, { radios: radios({ tx: 45, rx: 50, read: true }) });
    expect((box().find(".txlevel input[type=range]").element as HTMLInputElement).value).toBe("45");
    expect(box().find(".txlevel .cardslider-value").text()).toBe("45 %");
    expect(daemon.send.mock.calls.filter(([c]) => c.cmd === "set_config")).toHaveLength(0);
  });

  it("draws neither the slider nor the - and + until the card's levels are known, and nothing in the Receive level row moves when its slider comes", async () => {
    const { daemon, wrapper, box, labels } = make(NOT_READ);
    mounted = wrapper;
    await flushPromises();
    const before = labels();
    expect(box().find(".txlevel .txlevel-control").exists()).toBe(true);
    expect(box().find(".txlevel input[type=range]").exists()).toBe(false);
    expect(box().find(".txlevel .stepbtn").exists()).toBe(false);
    const children = () =>
      [...box().find(".scope-level").element.children].map((c) => `${c.tagName}.${c.className.split(" ")[0]}`);
    expect(children()).toEqual(["SPAN.cardslider", "DIV.levelbar", "OUTPUT.mono", "SPAN.infotip"]);
    await tell(daemon, { radios: radios(FTX1) });
    expect(box().find(".txlevel input[type=range]").exists()).toBe(true);
    expect(children()).toEqual(["SPAN.cardslider", "DIV.levelbar", "OUTPUT.mono", "SPAN.infotip"]);
    expect(labels()).toEqual(before);
    await tell(daemon, { radios: radios(CODEC) });
    expect(children()).toEqual(["SPAN.cardslider", "DIV.levelbar", "OUTPUT.mono", "SPAN.infotip"]);
    expect(box().find(".scope-level > .cardslider").element.children).toHaveLength(0);
  });

  it("keeps the modem's - and + where the gain is not 0, and keeps them while the row is in sight when + reaches 0", async () => {
    const original = globalThis.IntersectionObserver;
    const observers: { target: Element | null; run: (entries: { isIntersecting: boolean }[]) => void }[] = [];
    globalThis.IntersectionObserver = class {
      constructor(run: (entries: { isIntersecting: boolean }[]) => void) {
        observers.push({ target: null, run });
      }
      observe(target: Element): void {
        const made = observers[observers.length - 1];
        if (made) made.target = target;
      }
      disconnect(): void {}
    } as unknown as typeof IntersectionObserver;
    const { daemon, wrapper, box } = make(FTX1, { "radio/3/tx_gain_db": "-1" });
    mounted = wrapper;
    globalThis.IntersectionObserver = original;
    const sight = async (shown: boolean) => {
      const row = box().find(".txlevel").element;
      observers.filter((o) => o.target === row).forEach((o) => o.run([{ isIntersecting: shown }]));
      await flushPromises();
    };
    await flushPromises();
    await sight(true);
    expect(box().find(".txlevel input[type=range]").exists()).toBe(false);
    expect(box().findAll(".txlevel .stepbtn")).toHaveLength(2);
    expect(box().find(".txlevel .txlevel-value").text()).toBe("-1 dB");
    const control = box().find(".txlevel .txlevel-control").element;
    expect([control.firstElementChild?.className, control.lastElementChild?.className]).toEqual([
      "btn stepbtn",
      "infotip",
    ]);
    await box().find("#set-radio-3-txlevel-up").trigger("click");
    expect(daemon.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "radio/3/tx_gain_db": "0" } });
    await tell(daemon, { config: settingsWith({ "radio/3/tx_gain_db": "0" }) });
    expect(box().findAll(".txlevel .stepbtn")).toHaveLength(2); // (no slider under the pointer)
    expect(box().find(".txlevel .txlevel-value").text()).toBe("0 dB");
    await sight(false); // (the radio's fold closed, or another tab opened)
    await sight(true);
    expect(box().find(".txlevel input[type=range]").exists()).toBe(true);
    expect(box().findAll(".txlevel .stepbtn")).toHaveLength(0);
  });

  it("keeps the rows on a phone (375 px), where the Receive level's slider has the control's line under the bar, as long as the Transmit level's", async () => {
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
    expect(RESPONSIVE).toMatch(/\n\.scope-level:has\(> \.cardslider\) \{\s*flex-wrap: wrap;/);
    expect(RESPONSIVE).toMatch(/\.size-phone \.scope-level > \.cardslider,[^{]*\{\s*order: 1;/);
    expect(RESPONSIVE).toMatch(
      /\.size-phone \.field-control > \.cardslider,[^{]*\{\s*flex-basis: calc\(100% - 28px\);/,
    );
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
      radios: radiosTopic(
        radioRow(1, "kenwood-tnc2"),
        radioRow(2, "mercury", { modem: modemState({ scope: true, tx_peak_dbfs: -6 }), card: FTX1 }),
      ),
    });
    const wrapper = mount(SettingsForm, {
      props: { scope: "settings" },
      global: withDaemon(daemon),
      attachTo: document.body,
    });
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
    const box = mount(HfLevelBar, {
      props: { on: true, radio: 2, tip: true, card: { radio: pageRadio(row), form } },
      global: withDaemon(daemon),
    });
    mounted = box;
    const slider = box.find(".scope-level input[type=range]");
    expect((slider.element as HTMLInputElement).value).toBe("50");
    expect(box.find(".scope-level .cardslider-value").text()).toBe("50 %");
    (slider.element as HTMLInputElement).value = "64";
    await slider.trigger("change");
    expect(form.choose).toHaveBeenCalledWith({ "radio/2/rx_card": "64" });
    box.unmount();
    const monitor = mount(HfLevelBar, { props: { on: true, radio: 2 }, global: withDaemon(daemon) });
    mounted = monitor;
    expect(monitor.find("input[type=range]").exists()).toBe(false);
  });
});
