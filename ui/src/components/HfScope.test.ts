// The scope in the HF radio's box (HfScope.vue, composables/useHfScope.ts) and the Transmit level row (HfLevelRow.vue): the fold, folded at first and remembered in the browser; the pictures asked of the daemon only while it is open, this page is in
// front and the modem has the interface; the waterfall drawn from the pictures, started again when they are; the receive level as a bar with its zones; the gain buttons and the peak that turns red.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import { readStored, writeStored } from "@/lib/storage";
import type { HfScopeMessage } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { configValues, hfState, tncState } from "@/test/fixtures";

const HF_ON = { "hf/enabled": "true", "mercury/sound_card": "plughw:1,0", "mercury/keying": "vox" };
const picture = (over: Partial<HfScopeMessage> = {}): HfScopeMessage => ({
  type: "hf_scope",
  bins: Array.from({ length: 48 }, (_, i) => (i >= 18 && i < 30 ? 25 : 2)),
  level: -38,
  tx: false,
  ...over,
});
const withModem = (modem: Record<string, unknown>) => {
  const state = hfState();
  return { ...state, modem: { ...state.modem!, ...modem } };
};
const hfBox = (wrapper: ReturnType<typeof mount>) => {
  const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Radio");
  const box = group?.findAll("fieldset.subbox").find((f) => f.find("legend").text() === "HF radio");
  if (!box) throw new Error("no HF box");
  return box;
};
const calls: string[] = [];
const scopeCalls = (daemon: FakeDaemon) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "hf_scope");

function make(modem: Record<string, unknown> = { scope: true }, config: Record<string, string> = HF_ON) {
  const daemon = fakeDaemon({ config: configValues(config), tnc: tncState(), hf: withModem(modem) });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, attachTo: document.body, global: withDaemon(daemon) });
  return { wrapper, daemon, box: hfBox(wrapper) };
}

beforeEach(() => {
  calls.length = 0;
  localStorage.clear();
  const context = new Proxy(
    {},
    {
      get:
        (_t, name: string) =>
        (...args: unknown[]) =>
          calls.push(`${name}(${args.length})`),
      set: () => true,
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("the fold of the scope", () => {
  it("is one row with the page's arrow, folded at first, under Tune and the Transmit level in the HF radio's box", () => {
    const { box } = make();
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    expect(fold.exists()).toBe(true);
    expect(fold.element.open).toBe(false);
    expect(fold.find("summary").text()).toBe("Spectrum");
    const labels = box.findAll(".field label").map((l) => l.text());
    expect(labels.indexOf("Transmit level")).toBe(labels.indexOf("Tuning tone") + 1);
    expect(box.findAll("details.hf-scope")).toHaveLength(1);
  });

  it("is not there for a modem without the interface, and not for the FM radio's box", () => {
    const { box, wrapper } = make({ scope: false });
    expect(box.find("details.hf-scope").exists()).toBe(false);
    expect(wrapper.findAll("details.hf-scope")).toHaveLength(0);
  });

  it("is remembered in this browser: opened once, it is open the next time", async () => {
    const { box } = make();
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = true;
    await fold.trigger("toggle");
    expect(readStored("settings.fold.hf-scope")).toBe("open");
    document.body.innerHTML = "";
    const again = make();
    expect(again.box.find<HTMLDetailsElement>("details.hf-scope").element.open).toBe(true);
    writeStored("settings.fold.hf-scope", "folded");
  });
});

describe("the asking for the pictures", () => {
  it("asks only while the fold is open, and stops when it is closed", async () => {
    const { box, daemon } = make();
    expect(scopeCalls(daemon)).toEqual([]);
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = true;
    await fold.trigger("toggle");
    expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
    fold.element.open = false;
    await fold.trigger("toggle");
    expect(scopeCalls(daemon)).toEqual([
      { cmd: "hf_scope", on: true },
      { cmd: "hf_scope", on: false },
    ]);
  });

  it("asks at once when the fold was left open, says no more when the page goes, and asks again when the socket is open anew", async () => {
    writeStored("settings.fold.hf-scope", "open");
    const { wrapper, daemon } = make();
    expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
    await tell(daemon, { connection: "closed" });
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
    await tell(daemon, { connection: "open" });
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: true });
    const before = scopeCalls(daemon).length;
    wrapper.unmount();
    expect(scopeCalls(daemon)).toHaveLength(before + 1);
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
  });

  it("does not ask while the page is hidden, and asks when it is in front again", async () => {
    writeStored("settings.fold.hf-scope", "open");
    const { daemon } = make();
    const visibility = vi.spyOn(document, "visibilityState", "get");
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: true });
  });

  it("asks when the interface comes up after the fold was opened, not before", async () => {
    writeStored("settings.fold.hf-scope", "open");
    const { daemon } = make({ scope: false });
    expect(scopeCalls(daemon)).toEqual([]);
    await tell(daemon, { hf: withModem({ scope: true }) });
    expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
  });
});

describe("the picture and the receive level", () => {
  const open = async () => {
    writeStored("settings.fold.hf-scope", "open");
    const made = make();
    await flushPromises();
    return made;
  };

  it("draws the canvas when a picture comes, and shows its level on the bar with the zone it is in", async () => {
    const { box, daemon } = await open();
    expect(box.find(".levelvalue").text()).toBe("– dBFS");
    calls.length = 0;
    await tell(daemon, { hfScope: picture() });
    await vi.waitFor(() => expect(calls.filter((c) => c === "fillRect(4)").length).toBeGreaterThan(1));
    expect(box.find(".levelvalue").text()).toBe("-38 dBFS");
    expect(box.find(".levelfill").classes()).toContain("good");
    expect(box.find<HTMLElement>(".levelfill").element.style.width).toBe(`${((90 - 38) / 90) * 100}%`);
    await tell(daemon, { hfScope: picture({ level: -70 }) });
    expect(box.find(".levelfill").classes()).toContain("low");
    await tell(daemon, { hfScope: picture({ level: -5 }) });
    expect(box.find(".levelfill").classes()).toContain("clip");
    await tell(daemon, { hfScope: picture({ level: -18 }) });
    expect(box.find(".levelfill").classes()).toContain("high");
  });

  it("draws each picture as a row of the waterfall and starts it again when the fold is opened again", async () => {
    const { box, daemon } = await open();
    const cells = () => calls.filter((c) => c === "fillRect(4)").length;
    calls.length = 0;
    await tell(daemon, { hfScope: picture() });
    expect(cells()).toBe(2 + 48); // (the background, the 48 cells of the row and the band over them)
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = false;
    await fold.trigger("toggle");
    fold.element.open = true;
    await fold.trigger("toggle");
    await flushPromises();
    calls.length = 0;
    await tell(daemon, { hfScope: picture({ bins: new Array<number>(48).fill(0) }) });
    expect(cells()).toBe(2); // (the background and the band: a row at the floor draws nothing)
  });

  it("shows the good range as a part of the bar", async () => {
    const { box } = await open();
    const good = box.find<HTMLElement>(".levelgood").element.style;
    expect(parseFloat(good.left)).toBeCloseTo(((90 - 55) / 90) * 100);
    expect(parseFloat(good.width)).toBeCloseTo((30 / 90) * 100);
  });

  it("holds the level at the last one received while the radio transmits, and dims the bar", async () => {
    const { box, daemon } = await open();
    await tell(daemon, { hfScope: picture({ level: -41 }) });
    await tell(daemon, { hfScope: picture({ level: -12, tx: true }) });
    expect(box.find(".levelvalue").text()).toBe("-41 dBFS");
    expect(box.find(".levelbar").classes()).toContain("held");
    await tell(daemon, { hfScope: picture({ level: -39 }) });
    expect(box.find(".levelvalue").text()).toBe("-39 dBFS");
    expect(box.find(".levelbar").classes()).not.toContain("held");
  });

  it("does not draw a picture from before the asking", async () => {
    writeStored("settings.fold.hf-scope", "folded");
    const { box, daemon } = make();
    await tell(daemon, { hfScope: picture({ level: -20 }) });
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = true;
    await fold.trigger("toggle");
    expect(box.find(".levelvalue").text()).toBe("– dBFS");
    await tell(daemon, { hfScope: picture({ level: -33 }) });
    expect(box.find(".levelvalue").text()).toBe("-33 dBFS");
  });

  it("has the canvas described for a screen reader and the level named, and an (i) with the picture of the scope", async () => {
    const { box } = await open();
    expect(box.find("canvas").attributes("role")).toBe("img");
    expect(box.find("canvas").attributes("aria-label")).toContain("300 to 2700 Hz");
    expect(box.find(".levelbar").attributes("aria-label")).toBe("Receive level");
    const tip = box.find("details.hf-scope .infotip button");
    await tip.trigger("click");
    await flushPromises();
    expect(document.body.querySelector("svg[data-picture='scope']")).not.toBeNull();
  });
});

describe("the Transmit level row", () => {
  const level = (box: ReturnType<typeof hfBox>) => box.find(".txlevel");
  const buttons = (box: ReturnType<typeof hfBox>) => level(box).findAll("button.btn");
  const sent = (daemon: FakeDaemon) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "set_config");

  it("shows the gain from the settings and the peak from the modem, with a button to lower it and one to raise it", () => {
    const { box } = make({ scope: true, tx_gain_db: 3, tx_peak_dbfs: -6 }, { ...HF_ON, "mercury/tx_gain_db": "3" });
    expect(level(box).find("label").text()).toBe("Transmit level");
    expect(level(box).find(".txlevel-value").text()).toBe("+3 dB");
    expect(level(box).find(".txlevel-peak").text()).toBe("Peak -6 dBFS");
    expect(level(box).find(".txlevel-peak").classes()).not.toContain("clip");
    expect(buttons(box).map((b) => b.attributes("aria-label"))).toEqual(["Lower the transmit level", "Raise the transmit level"]);
  });

  it("saves one dB less or more at each press, and stops at Mercury's limits", async () => {
    const { box, daemon } = make({ scope: true }, { ...HF_ON, "mercury/tx_gain_db": "0" });
    await buttons(box)[1].trigger("click");
    await tell(daemon, { config: configValues({ ...HF_ON, "mercury/tx_gain_db": "1" }) }); // (the daemon has saved it and says so: only then is the next press taken)
    expect(level(box).find(".txlevel-value").text()).toBe("+1 dB");
    await buttons(box)[0].trigger("click");
    await buttons(box)[0].trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "set_config", values: { "mercury/tx_gain_db": "1" } },
      { cmd: "set_config", values: { "mercury/tx_gain_db": "0" } },
    ]);
    const top = make({ scope: true }, { ...HF_ON, "mercury/tx_gain_db": "20" });
    expect(buttons(top.box)[1].attributes("disabled")).toBeDefined();
    expect(buttons(top.box)[0].attributes("disabled")).toBeUndefined();
    const bottom = make({ scope: true }, { ...HF_ON, "mercury/tx_gain_db": "-20" });
    expect(buttons(bottom.box)[0].attributes("disabled")).toBeDefined();
  });

  it("turns the peak red at 0 dBFS and over, and shows a dash before there is one", () => {
    expect(
      level(make({ scope: true, tx_peak_dbfs: 0 }).box)
        .find(".txlevel-peak")
        .classes(),
    ).toContain("clip");
    expect(
      level(make({ scope: true, tx_peak_dbfs: 7 }).box)
        .find(".txlevel-peak")
        .classes(),
    ).toContain("clip");
    expect(
      level(make({ scope: true, tx_peak_dbfs: null }).box)
        .find(".txlevel-peak")
        .text(),
    ).toBe("Peak – dBFS");
  });

  it("is there for a modem without the scope too (the gain is a setting), and has no field of the generic list", () => {
    const { box } = make({ scope: false });
    expect(level(box).exists()).toBe(true);
    expect(box.find("#set-mercury-tx_gain_db").exists()).toBe(false);
  });
});
