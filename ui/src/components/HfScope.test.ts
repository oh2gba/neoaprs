// The scope in the HF radio's box (HfScope.vue, HfWaterfall.vue, composables/useHfScope.ts) and the Transmit level row (HfLevelRow.vue): the fold, folded at first and remembered in the browser; the rows asked of the daemon only while it is open, this page is
// in front and the modem has the interface; the waterfall drawn from the rows and from what the page keeps of them, whole at once when it is mounted again, with the stations heard on the HF radio written on it; the receive
// level as a bar with its zones; the gain buttons and the peak that turns orange.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, shallowReactive, shallowRef } from "vue";
import HfScope from "@/components/HfScope.vue";
import SettingsForm from "@/components/SettingsForm.vue";
import { useScopeLooks } from "@/composables/useScopeLooks";
import { useScopeRows } from "@/composables/useScopeRows";
import type { ScopeRow } from "@/lib/scoperow";
import { readStored, writeStored } from "@/lib/storage";
import { BINS } from "@/lib/waterfall";
import type { ModemState, PacketRow, RadioRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { NOW, configValues, modemState, packet, radioRow, radiosTopic } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

const HF_ON = { "radio/2/beacon": "true", "radio/2/sound_card": "plughw:1,0", "radio/2/keying": "vox", "radio/2/tx_gain_db": "0" };
/** A row as the daemon sends it: every bin at `db` on the modem's scale. */
const scopeRow = (over: Partial<ScopeRow> = {}, db = -40): ScopeRow => ({ db: new Float32Array(BINS).fill(db), level: -38, tx: false, ...over });
const withModem = (modem: Partial<ModemState>): ModemState => modemState(modem);
const hfBox = (wrapper: ReturnType<typeof mount>) => {
  const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Radio");
  const box = group?.findAll("fieldset.subbox").find((f) => f.find("legend").text() === "HF radio");
  if (!box) throw new Error("no HF box");
  return box;
};
/** The topic `radios`: radio 1 the FM radio, radio 2 the Mercury radio with this modem. */
const radiosBeside = (modem: ModemState | null) => radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { modem }));
const calls: string[] = [];
const clock = { now: NOW };
let packets = shallowReactive(new Map<string, PacketRow>());
let hf = shallowRef<ModemState | null>(null);
let rows = useScopeRows(packets, () => clock.now);
/** Rows of the daemon, one after the other, a tenth of a second apart (two to a line of the picture). */
const say = async (...told: ScopeRow[]): Promise<void> => {
  for (const row of told) {
    rows.hfScopeRow(row, 2);
    clock.now += 100;
  }
  await flushPromises();
};
/** The time of a packet heard `ago` milliseconds before now, as the daemon writes it (whole seconds). */
const heardNow = (ago = 0): string => new Date(clock.now - ago).toISOString().replace(/\.\d+Z$/, "Z");
const scopeCalls = (daemon: FakeDaemon) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "radio_scope");

/** Radio 2's modem as its row tells it anew. */
const tellModem = async (modem: ModemState): Promise<void> => {
  hf.value = modem;
  await flushPromises();
};

function make(modem: Partial<ModemState> = { scope: true }, config: Record<string, string> = HF_ON) {
  hf.value = withModem(modem);
  const daemon = fakeDaemon({
    config: configValues({}, config),
    radios: computed(() => radiosBeside(hf.value)),
    scopeOf: rows.of,
    packets,
  });
  const wrapper = mount(SettingsForm, { props: { scope: "settings" }, attachTo: document.body, global: withDaemon(daemon) });
  return { wrapper, daemon, box: hfBox(wrapper) };
}

beforeEach(() => {
  calls.length = 0;
  clock.now = NOW;
  packets = shallowReactive(new Map<string, PacketRow>());
  hf = shallowRef<ModemState | null>(null);
  rows = useScopeRows(packets, () => clock.now);
  localStorage.clear();
  const special: Record<string, (...args: never[]) => unknown> = {
    createImageData: (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    measureText: (text: string) => ({ width: text.length * 6 }),
  };
  const context = new Proxy(
    {},
    {
      get: (_t, name: string) =>
        special[name] ??
        ((...args: unknown[]) => {
          calls.push(name === "fillText" ? `fillText(${String(args[0])})` : `${name}(${args.length})`);
        }),
      set: () => true,
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(420); // (the room the box in Settings gives the picture)
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(240);
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
    expect(readStored("settings.fold.radio-2-scope")).toBe("open");
    document.body.innerHTML = "";
    const again = make();
    expect(again.box.find<HTMLDetailsElement>("details.hf-scope").element.open).toBe(true);
    writeStored("settings.fold.radio-2-scope", "folded");
  });
});

describe("the asking for the rows", () => {
  it("asks only while the fold is open, and stops when it is closed", async () => {
    const { box, daemon } = make();
    expect(scopeCalls(daemon)).toEqual([]);
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = true;
    await fold.trigger("toggle");
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true }]);
    fold.element.open = false;
    await fold.trigger("toggle");
    expect(scopeCalls(daemon)).toEqual([
      { cmd: "radio_scope", radio: 2, on: true },
      { cmd: "radio_scope", radio: 2, on: false },
    ]);
  });

  it("asks at once when the fold was left open, says no more when the page goes, and asks again when the socket is open anew", async () => {
    writeStored("settings.fold.radio-2-scope", "open");
    const { wrapper, daemon } = make();
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true }]);
    await tell(daemon, { connection: "closed" });
    expect(scopeCalls(daemon)).toHaveLength(1); // (a closed socket is told nothing: the toast would say it was refused)
    await tell(daemon, { connection: "open" });
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: true });
    const before = scopeCalls(daemon).length;
    wrapper.unmount();
    expect(scopeCalls(daemon)).toHaveLength(before + 1);
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false });
  });

  it("does not ask while the page is hidden, and asks when it is in front again", async () => {
    writeStored("settings.fold.radio-2-scope", "open");
    const { daemon } = make();
    const visibility = vi.spyOn(document, "visibilityState", "get");
    visibility.mockReturnValue("hidden");
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false });
    visibility.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: true });
  });

  it("asks when the interface comes up after the fold was opened, not before", async () => {
    writeStored("settings.fold.radio-2-scope", "open");
    const { daemon } = make({ scope: false });
    expect(scopeCalls(daemon)).toEqual([]);
    await tellModem(withModem({ scope: true }));
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true }]);
  });
});

describe("the picture and the receive level", () => {
  const open = async () => {
    writeStored("settings.fold.radio-2-scope", "open");
    const made = make();
    await flushPromises();
    return made;
  };
  const lines = () => calls.filter((c) => c === "putImageData(3)").length;
  const texts = () => calls.filter((c) => c.startsWith("fillText(")).map((c) => c.slice("fillText(".length, -1));

  it("draws the ruler and the curve at once, and a line of the waterfall for every fifth of a second", async () => {
    await open();
    expect([...new Set(texts())]).toEqual(["500", "1000", "1500", "2000", "2500"]);
    calls.length = 0;
    await say(scopeRow(), scopeRow());
    expect(lines()).toBe(0);
    await say(scopeRow(), scopeRow(), scopeRow());
    expect(lines()).toBe(2);
    expect(calls.filter((c) => c === "drawImage(9)")).toHaveLength(2); // (what is there is moved down, not drawn again)
  });

  it("shows the level of the rows on the bar with the zone it is in", async () => {
    const { box } = await open();
    expect(box.find(".levelvalue").text()).toBe("– dBFS");
    await say(scopeRow());
    expect(box.find(".levelvalue").text()).toBe("-38 dBFS");
    expect(box.find(".levelfill").classes()).toContain("good");
    expect(box.find<HTMLElement>(".levelfill").element.style.width).toBe(`${((90 - 38) / 90) * 100}%`);
    await say(scopeRow({ level: -70 }));
    expect(box.find(".levelfill").classes()).toContain("low");
    await say(scopeRow({ level: -5 }));
    expect(box.find(".levelfill").classes()).toContain("clip");
    await say(scopeRow({ level: -18 }));
    expect(box.find(".levelfill").classes()).toContain("high");
  });

  it("shows the good range as a part of the bar", async () => {
    const { box } = await open();
    const good = box.find<HTMLElement>(".levelgood").element.style;
    expect(parseFloat(good.left)).toBeCloseTo(((90 - 55) / 90) * 100);
    expect(parseFloat(good.width)).toBeCloseTo((30 / 90) * 100);
  });

  it("holds the level at the last one received while the radio transmits, and dims the bar", async () => {
    const { box } = await open();
    await say(scopeRow({ level: -41 }), scopeRow({ level: -12, tx: true }));
    expect(box.find(".levelvalue").text()).toBe("-41 dBFS");
    expect(box.find(".levelbar").classes()).toContain("held");
    await say(scopeRow({ level: -39 }));
    expect(box.find(".levelvalue").text()).toBe("-39 dBFS");
    expect(box.find(".levelbar").classes()).not.toContain("held");
  });

  it("keeps the picture while the fold is closed, draws it whole as it stands when it is opened again, and forgets it when the daemon kept nothing", async () => {
    const { box } = await open();
    await say(scopeRow({ level: -30 }), scopeRow({ level: -30 }), scopeRow(), scopeRow(), scopeRow());
    const fold = box.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = false;
    await fold.trigger("toggle");
    clock.now += 10_000;
    calls.length = 0;
    fold.element.open = true;
    await fold.trigger("toggle");
    await flushPromises();
    expect(box.find(".levelvalue").text()).toBe("– dBFS"); // (the level is of the rows that come, and of the newest the daemon kept)
    expect(lines()).toBe(52); // (as it stands at 10.5 s: the half second of rows ten seconds down, the time away the ground over it)
    calls.length = 0;
    rows.hfScopeHistory({ rows: [], clock: clock.now }, 2); // (the daemon kept nothing: the modem was started anew)
    await flushPromises();
    expect(rows.of(2).rows).toEqual([]);
    expect(calls.filter((c) => c === "putImageData(3)")).toHaveLength(0);
  });

  it("draws the picture whole from what the page keeps when it is mounted anew, and the rows the daemon kept fill the time it was away, none twice", async () => {
    const first = await open();
    await say(...Array.from({ length: 10 }, () => scopeRow({}, -60))); // (a second of rows)
    first.wrapper.unmount(); // (another tab of the panel)
    clock.now += 30_000;
    calls.length = 0;
    const again = make();
    await flushPromises();
    expect(lines()).toBe(5 + 150); // (from memory at once: the five lines of that second, and the 30 s since at the top, as the ground)
    const made = rows.of(2).rows.map((kept) => kept.at);
    const daemon = Array.from({ length: 310 }, (_, i) => ({ row: scopeRow({}, -60), age: clock.now - (NOW + i * 100 + 5) }));
    calls.length = 0;
    rows.hfScopeHistory({ rows: daemon, clock: clock.now }, 2);
    await flushPromises();
    expect(
      rows
        .of(2)
        .rows.slice(0, 10)
        .map((kept) => kept.at),
    ).toEqual(made); // (the rows held stay where they were)
    expect(rows.of(2).rows).toHaveLength(310);
    expect(lines()).toBe(155); // (drawn again, the same height: nothing moved down)
    expect(again.box.find(".levelvalue").text()).toBe("-38 dBFS");
  });

  it("writes the call and the SNR of a frame heard on the HF radio where its line is, the call alone of one heard before it was told, and nothing for the FM radio, the internet or our own", async () => {
    packets.set("1", packet(1, { source: "OH2OLD", radio_id: 2 })); // (heard 99 s ago, before the page had any packet)
    await open();
    await say(scopeRow(), scopeRow(), scopeRow());
    calls.length = 0;
    packets.set("2", packet(2, { source: "OH2GAX", radio_id: 2, heard_at: heardNow(), snr: -3.2 })); // (the SNR the radio measured of the frame)
    packets.set("3", packet(3, { source: "OH2FM", radio_id: 1 }));
    packets.set("4", packet(4, { source: "OH2IS", radio_id: 2, via: "is" }));
    packets.set("5", packet(5, { source: "OH2GBA", radio_id: 2, direction: "out" }));
    await flushPromises();
    await say(scopeRow(), scopeRow());
    expect(texts()).toEqual(["OH2GAX −3 dB"]);
    packets.set("6", packet(6, { source: "OH2XYZ", radio_id: 2, heard_at: heardNow(), snr: null }));
    await flushPromises();
    await say(scopeRow(), scopeRow());
    expect(texts()).toEqual(["OH2GAX −3 dB", "OH2XYZ"]);
    expect(rows.of(2).heard.map((heard) => [heard.call, heard.snr])).toEqual([
      ["OH2OLD", null],
      ["OH2GAX", -3.2],
      ["OH2XYZ", null],
    ]);
  });

  it("writes a station told late (the socket came back after a drop, the browser held the page) where it was heard, with the call alone", async () => {
    await open();
    await say(scopeRow(), scopeRow(), scopeRow());
    clock.now += 20_000;
    packets.set("2", packet(2, { source: "OH2LATE", radio_id: 2, heard_at: heardNow(15_000) }));
    await flushPromises();
    expect(rows.of(2).heard.map((heard) => [heard.call, Math.round((clock.now - heard.at) / 1000), heard.snr])).toEqual([["OH2LATE", 15, null]]);
  });

  it("writes on the rows of the past a station heard while no picture looked, where it was heard", async () => {
    const first = await open();
    await say(scopeRow(), scopeRow(), scopeRow());
    first.wrapper.unmount();
    packets.set("7", packet(7, { source: "OH2AWAY", radio_id: 2, heard_at: heardNow() })); // (told while the page showed another tab: written down all the same)
    await flushPromises();
    clock.now += 5_000;
    calls.length = 0;
    make();
    await flushPromises();
    expect(texts()).toContain("OH2AWAY");
  });

  it("asks for no rows while the picture has no room (a fold open under another tab), and asks when it has", async () => {
    const width = stubWidth(0);
    try {
      writeStored("settings.fold.radio-2-scope", "open");
      const { daemon } = make();
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([]);
      width.set(420);
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true }]);
      await say(scopeRow(), scopeRow(), scopeRow());
      expect(lines()).toBe(1);
      width.set(0);
      await flushPromises();
      expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false });
    } finally {
      width.restore();
    }
  });

  it("has the picture described for a screen reader and the level named, and an (i) with the picture of the scope", async () => {
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
    const { box } = make({ scope: true, tx_gain_db: 3, tx_peak_dbfs: -6 }, { ...HF_ON, "radio/2/tx_gain_db": "3" });
    expect(level(box).find("label").text()).toBe("Transmit level");
    expect(level(box).find(".txlevel-value").text()).toBe("+3 dB");
    expect(level(box).find(".txlevel-peak").text()).toBe("Peak -6 dBFS");
    expect(level(box).find(".txlevel-peak").classes()).not.toContain("clip");
    expect(buttons(box).map((b) => b.attributes("aria-label"))).toEqual(["Lower the transmit level", "Raise the transmit level"]);
  });

  it("saves one dB less or more at each press, and stops at Mercury's limits", async () => {
    const { box, daemon } = make({ scope: true }, { ...HF_ON, "radio/2/tx_gain_db": "0" });
    await buttons(box)[1].trigger("click");
    await tell(daemon, { config: configValues({}, { ...HF_ON, "radio/2/tx_gain_db": "1" }) }); // (the daemon has saved it and says so: only then is the next press taken)
    expect(level(box).find(".txlevel-value").text()).toBe("+1 dB");
    await buttons(box)[0].trigger("click");
    await buttons(box)[0].trigger("click");
    expect(sent(daemon)).toEqual([
      { cmd: "set_config", values: { "radio/2/tx_gain_db": "1" } },
      { cmd: "set_config", values: { "radio/2/tx_gain_db": "0" } },
    ]);
    const top = make({ scope: true }, { ...HF_ON, "radio/2/tx_gain_db": "20" });
    expect(buttons(top.box)[1].attributes("disabled")).toBeDefined();
    expect(buttons(top.box)[0].attributes("disabled")).toBeUndefined();
    const bottom = make({ scope: true }, { ...HF_ON, "radio/2/tx_gain_db": "-20" });
    expect(buttons(bottom.box)[0].attributes("disabled")).toBeDefined();
  });

  it("turns the peak orange at 0 dBFS and over, and shows a dash before there is one", () => {
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
    expect(box.find("#set-radio-2-tx_gain_db").exists()).toBe(false);
  });
});

/** A Mercury radio whose modem has the interface (or has not, `scope` false). */
const mercury = (id: number, extra: Partial<RadioRow> = {}, scope = true): RadioRow => radioRow(id, "mercury", { modem: modemState({ scope }), ...extra });

describe("the scope in each radio's box", () => {
  /** The page's context with these radios, its counting of who looks given the topic `radios` and the page's rows, as the page makes it. */
  function station(...radios: RadioRow[]) {
    const daemon = fakeDaemon({ radios: radiosTopic(...radios), scopeOf: rows.of, packets });
    daemon.scope = useScopeLooks(daemon.send, daemon.connection, shallowRef(true), { radios: daemon.radios });
    const box = (radio: number) => mount(HfScope, { props: { radio }, global: withDaemon(daemon), attachTo: document.body });
    return { daemon, box };
  }

  it("is there in the box of a radio that has a scope now, and not in that of one switched off, whose modem has no interface, or of a type without one", () => {
    const { box } = station(
      mercury(3),
      mercury(4, { enabled: false, state: "stopped" }),
      mercury(5, {}, false),
      radioRow(6, "dummy-hf"),
      radioRow(1, "kenwood-tnc2"),
    );
    expect([3, 4, 5, 6, 1].map((radio) => box(radio).find("details.hf-scope").exists())).toEqual([true, false, false, false, false]);
  });

  it("asks for its own radio's rows while its fold is open, and its fold is remembered for that radio alone", async () => {
    const { daemon, box } = station(mercury(3), mercury(5));
    const three = box(3);
    const five = box(5);
    expect(scopeCalls(daemon)).toEqual([]);
    const fold = five.find<HTMLDetailsElement>("details.hf-scope");
    fold.element.open = true;
    await fold.trigger("toggle");
    await flushPromises();
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 5, on: true }]);
    expect(readStored("settings.fold.radio-5-scope")).toBe("open");
    expect(readStored("settings.fold.radio-3-scope")).toBeNull();
    expect(three.find<HTMLDetailsElement>("details.hf-scope").element.open).toBe(false);
    fold.element.open = false;
    await fold.trigger("toggle");
    await flushPromises();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 5, on: false });
  });
});
