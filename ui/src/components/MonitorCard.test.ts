// The monitor card over the map (components/MonitorCard.vue): the scope of a radio larger, asked of the daemon while it is there, of the radio chosen in the map's menu (else the first with a scope), named where several radios are on; closed by its cross, dragged by its head like the statistics card and remembered where it was left;
// its menu (components/MonitorMenu.vue), opened as every menu of the page is, with the speed of its waterfall, which this browser remembers and the box in Settings does not follow.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { shallowRef } from "vue";
import HfScope from "@/components/HfScope.vue";
import MonitorCard from "@/components/MonitorCard.vue";
import { useScopeLooks } from "@/composables/useScopeLooks";
import { useScopeRows } from "@/composables/useScopeRows";
import type { ScopeRow } from "@/lib/scoperow";
import { BINS } from "@/lib/waterfall";
import { Waterfall } from "@/lib/waterfallpainter";
import { fakeDaemon, withDaemon, type Given } from "@/test/context";
import { cssRule, mediaRule } from "@/test/css";
import type { RadioRow } from "@/protocol/protocol";
import { configValues, hfState, radioRow, radiosTopic } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

const withScope = () => {
  const state = hfState();
  return { ...state, modem: { ...state.modem!, scope: true } };
};
/** A station whose one radio is the HF radio of before with a scope: the topic `hf`, the topic `radios` and the settings of before say it alike. */
const hfAlone = (over: Given = {}) =>
  fakeDaemon({
    hf: withScope(),
    config: configValues({ "fm/enabled": "false", "hf/enabled": "true" }),
    radios: radiosTopic(radioRow(1, "kenwood-tnc2", { enabled: false, state: "stopped" }), radioRow(2, "mercury", { modem: withScope().modem })),
    ...over,
  });
const rect = (x: number, y: number, w: number, h: number) =>
  ({ x, y, left: x, top: y, right: x + w, bottom: y + h, width: w, height: h, toJSON: () => ({}) }) as DOMRect;
const scopeCalls = (daemon: ReturnType<typeof fakeDaemon>) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "radio_scope");

/** The sizes of the strips the painter made, one for every look it took: a strip is one line of the picture. */
const images: [number, number][] = [];

beforeEach(() => {
  localStorage.clear();
  images.length = 0;
  const context = new Proxy(
    {},
    {
      get: (_t, name: string) =>
        name === "measureText"
          ? () => ({ width: 10 })
          : name === "createImageData"
            ? (w: number, h: number) => (images.push([w, h]), { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) })
            : () => undefined,
      set: () => true,
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(540); // (the room the card gives the picture)
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe("MonitorCard", () => {
  it("has the waterfall and the receive level under its head, asks for the rows while it is there and stops when it goes", () => {
    const daemon = hfAlone();
    const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    expect(wrapper.find(".card-head strong").text()).toBe("Monitor");
    expect(wrapper.attributes("aria-label")).toBe("Monitor");
    expect(wrapper.find(".monitor-picture canvas").exists()).toBe(true);
    expect(wrapper.find("[role='meter']").exists()).toBe(true);
    expect(wrapper.find(".info-tip, .infotip").exists()).toBe(false);
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    wrapper.unmount();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
  });

  it("shows the level of the rows that come", async () => {
    const rows = useScopeRows();
    const daemon = hfAlone({ scopeRows: rows.memory });
    const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    await flushPromises(); // (the picture has room once it is mounted, and then the rows are asked for)
    const row: ScopeRow = { db: new Float32Array(BINS).fill(-40), level: -20, tx: false };
    rows.hfScopeRow(row);
    await flushPromises();
    expect(wrapper.find(".levelvalue").text()).toBe("-20 dBFS");
  });

  it("its cross closes it", async () => {
    const wrapper = mount(MonitorCard, { global: withDaemon(hfAlone()), attachTo: document.body });
    await wrapper.find(".card-close").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);
  });

  it("is dragged by its head where moving is on, stays inside the map, remembers where it was left, and is not dragged on a phone", async () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      if (!this.classList.contains("monitorcard")) return rect(0, 0, 1200, 800);
      return this.classList.contains("moved") ? rect(parseFloat(this.style.left), parseFloat(this.style.top), 560, 500) : rect(630, 270, 560, 500);
    });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1200);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(800);
    const mounted = (movable: boolean) => mount(MonitorCard, { props: { movable }, global: withDaemon(hfAlone()), attachTo: document.body });
    const wrapper = mounted(true);
    const el = wrapper.find(".monitorcard").element as HTMLElement;
    const head = wrapper.find(".card-head strong").element;
    const pointer = (type: string, x: number, y: number) =>
      head.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true }));
    expect(el.classList.contains("movable")).toBe(true);
    pointer("pointerdown", 700, 290);
    pointer("pointermove", 600, 190);
    await wrapper.vm.$nextTick();
    expect([el.style.left, el.style.top]).toEqual(["530px", "170px"]);
    pointer("pointermove", 2000, 2000); // (far beyond the map: kept inside it)
    pointer("pointerup", 2000, 2000);
    await wrapper.vm.$nextTick();
    expect([el.style.left, el.style.top]).toEqual(["640px", "300px"]);
    expect(localStorage.getItem("NeoAPRS.monitorplace")).toBe("640,300");
    wrapper.unmount();
    const again = mounted(true);
    expect((again.find(".monitorcard").element as HTMLElement).style.left).toBe("640px"); // (where it was left)
    again.unmount();
    const phone = mounted(false);
    const sheet = phone.find(".monitorcard").element as HTMLElement;
    expect(sheet.classList.contains("moved")).toBe(false);
    const grip = phone.find(".card-head strong").element;
    grip.dispatchEvent(new MouseEvent("pointerdown", { clientX: 900, clientY: 510, bubbles: true }));
    grip.dispatchEvent(new MouseEvent("pointermove", { clientX: 800, clientY: 400, bubbles: true }));
    await phone.vm.$nextTick();
    expect(sheet.classList.contains("moved")).toBe(false);
  });
});

describe("the card that has no room for its picture", () => {
  it("asks for no rows while its picture is not shown (a phone's panel tab hides the map), and asks when it is", async () => {
    const width = stubWidth(0);
    try {
      const daemon = hfAlone();
      const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([]);
      width.set(540);
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
      width.set(0);
      await flushPromises();
      expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
      wrapper.unmount();
    } finally {
      width.restore();
    }
  });
});

describe("the one counting place", () => {
  it("keeps asking for the rows while the card or the box in Settings shows them, and stops when neither does", () => {
    localStorage.setItem("NeoAPRS.settings.fold.hf-scope", "open");
    const daemon = hfAlone();
    const box = mount(HfScope, { global: withDaemon(daemon), attachTo: document.body });
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    const card = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    expect(scopeCalls(daemon)).toHaveLength(1);
    box.unmount();
    expect(scopeCalls(daemon)).toHaveLength(1);
    card.unmount();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
    expect(scopeCalls(daemon)).toHaveLength(2);
  });

  it("has the box in Settings and the card draw from the same rows the page keeps: the card closed and opened again is whole at once, and the box goes on meanwhile", () => {
    localStorage.setItem("NeoAPRS.settings.fold.hf-scope", "open");
    const clock = { now: Date.UTC(2026, 10, 14, 12, 0, 0) };
    const rows = useScopeRows(undefined, undefined, () => clock.now);
    const daemon = hfAlone({ scopeRows: rows.memory });
    const box = mount(HfScope, { global: withDaemon(daemon), attachTo: document.body });
    const card = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    const tell = (count: number): void => {
      for (let i = 0; i < count; i++) {
        rows.hfScopeRow({ db: new Float32Array(BINS).fill(-40), level: -20, tx: false });
        clock.now += 100;
      }
    };
    tell(10);
    card.unmount();
    tell(10);
    expect(rows.memory.rows).toHaveLength(20); // (kept for the page, not for the card)
    const shows = vi.spyOn(Waterfall.prototype, "show");
    const again = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    expect(shows).toHaveBeenCalledTimes(1);
    expect(shows.mock.calls[0][0]).toHaveLength(20); // (the card's picture at once from the page's rows, those it did not see among them)
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]); // (the box looked all the time: the page asked once)
    again.unmount();
    box.unmount();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "radio_scope", radio: 2, on: false, named: true });
  });
});

describe("the card's menu", () => {
  const mounted = () => mount(MonitorCard, { global: withDaemon(hfAlone()), attachTo: document.body });
  const menu = (): HTMLElement | null => document.body.querySelector<HTMLElement>(".monitormenu");
  const items = (): HTMLButtonElement[] => [...document.body.querySelectorAll<HTMLButtonElement>(".monitormenu [role='menuitemradio']")];
  const words = (): string[] => items().map((item) => (item.textContent ?? "").replace("\u2713", "").trim());
  const checked = (): string[] => items().map((item) => item.getAttribute("aria-checked") ?? "");
  const settle = async (wrapper: { vm: { $nextTick: () => Promise<void> } }): Promise<void> => {
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
  };
  async function rightClick(wrapper: ReturnType<typeof mounted>, selector: string, x = 300, y = 200): Promise<MouseEvent> {
    const event = new MouseEvent("contextmenu", { clientX: x, clientY: y, bubbles: true, cancelable: true });
    wrapper.find(selector).element.dispatchEvent(event);
    await settle(wrapper);
    return event;
  }

  it("opens on a right-click on the picture, at the pointer, without the browser's own menu: Speed, and Slow, Normal and Fast, with Normal on", async () => {
    const wrapper = mounted();
    const event = await rightClick(wrapper, ".monitor-picture canvas", 300, 200);
    expect(event.defaultPrevented).toBe(true);
    expect(menu()?.getAttribute("role")).toBe("menu");
    expect(menu()?.getAttribute("aria-label")).toBe("Monitor");
    expect(menu()?.getAttribute("style")).toContain("left: 300px");
    expect(menu()?.getAttribute("style")).toContain("top: 200px");
    expect(menu()?.querySelector(".ctxmenu-title")?.textContent).toBe("Speed");
    expect(menu()?.querySelector("[role='group']")?.getAttribute("aria-labelledby")).toBe("monitormenu-speed");
    expect(words()).toEqual(["Slow", "Normal", "Fast"]);
    expect(checked()).toEqual(["false", "true", "false"]);
    expect(document.activeElement).toBe(items()[0]); // (the first item takes the focus, as in every menu of the page)
    wrapper.unmount();
    expect(menu()).toBeNull();
  });

  it("opens on a right-click anywhere on the card, its head too, and a right-click on the open menu opens nothing new", async () => {
    const wrapper = mounted();
    await rightClick(wrapper, ".card-head strong", 120, 40);
    expect(menu()?.getAttribute("style")).toContain("left: 120px");
    const again = new MouseEvent("contextmenu", { clientX: 10, clientY: 10, bubbles: true, cancelable: true });
    items()[1]?.dispatchEvent(again);
    await settle(wrapper);
    expect(again.defaultPrevented).toBe(true);
    expect(menu()?.getAttribute("style")).toContain("left: 120px");
    wrapper.unmount();
  });

  it("opens for the menu key on the picture, which takes the focus, a little in from its left edge and under it", async () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("monitor-picture") ? rect(400, 150, 540, 300) : rect(0, 0, 0, 0);
    });
    const wrapper = mounted();
    const picture = wrapper.find(".monitor-picture");
    expect(picture.attributes("tabindex")).toBe("0");
    expect(picture.attributes("aria-haspopup")).toBe("menu");
    (picture.element as HTMLElement).focus();
    await rightClick(wrapper, ".monitor-picture", 0, 0);
    expect(menu()?.getAttribute("style")).toContain("left: 424px");
    expect(menu()?.getAttribute("style")).toContain("top: 450px");
    expect(cssRule(".monitor-picture:focus-visible")).toMatch(/outline:\s*2px solid var\(--accent\)/);
    wrapper.unmount();
  });

  it("opens on a long press on the card's body, where the finger is", async () => {
    vi.useFakeTimers();
    try {
      const wrapper = mounted();
      await wrapper.find(".monitor-picture").trigger("pointerdown", { pointerType: "touch", isPrimary: true, clientX: 60, clientY: 80 });
      vi.advanceTimersByTime(600);
      await settle(wrapper);
      expect(words()).toEqual(["Slow", "Normal", "Fast"]);
      expect(menu()?.getAttribute("style")).toContain("left: 60px");
      await wrapper.find("[role='meter']").trigger("pointerdown", { pointerType: "touch", isPrimary: true, clientX: 70, clientY: 400 });
      vi.advanceTimersByTime(600);
      await settle(wrapper);
      expect(menu()?.getAttribute("style")).toContain("top: 400px"); // (on the receive level too)
      for (const rule of [/-webkit-touch-callout:\s*none/, /-webkit-user-select:\s*none/, /(^|[^-])user-select:\s*none/])
        expect(mediaRule("(pointer: coarse)", ".monitorcard .card-body")).toMatch(rule); // (the element that hears the long press: no callout and no selection over the menu)
      wrapper.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("closes on Esc, which closes nothing else, with the focus back on the picture, and on a press outside it", async () => {
    const wrapper = mounted();
    const heard: KeyboardEvent[] = [];
    const listen = (event: KeyboardEvent): number => heard.push(event);
    document.addEventListener("keydown", listen);
    try {
      await rightClick(wrapper, ".monitor-picture canvas");
      const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
      items()[0]?.dispatchEvent(esc);
      await settle(wrapper);
      expect(menu()).toBeNull();
      expect(esc.defaultPrevented).toBe(true);
      expect(heard).toEqual([]); // (the station cards and the card itself, which close on Esc, do not hear it)
      expect(wrapper.emitted("close")).toBeUndefined();
      expect(document.activeElement).toBe(wrapper.find(".monitor-picture").element);
      await rightClick(wrapper, ".monitor-picture canvas");
      document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
      await settle(wrapper);
      expect(menu()).toBeNull();
    } finally {
      document.removeEventListener("keydown", listen);
      wrapper.unmount();
    }
  });

  it("moves in its items with Up, Down, Home and End, and Tab leaves it from the picture", async () => {
    const wrapper = mounted();
    await rightClick(wrapper, ".monitor-picture canvas");
    const key = (name: string): void =>
      void document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));
    const on = (): string | null => (document.activeElement as HTMLElement | null)?.dataset.speed ?? null;
    expect(on()).toBe("slow");
    key("ArrowDown");
    expect(on()).toBe("normal");
    key("ArrowDown");
    expect(on()).toBe("fast");
    key("Home");
    expect(on()).toBe("slow");
    key("ArrowUp");
    expect(on()).toBe("fast"); // (round from the first to the last, as in every menu of the page)
    key("Home");
    key("End");
    expect(on()).toBe("fast");
    key("Tab");
    await settle(wrapper);
    expect(menu()).toBeNull();
    expect(document.activeElement).toBe(wrapper.find(".monitor-picture").element); // (the browser's Tab goes on from there to what comes after the card)
    wrapper.unmount();
  });

  it("closes on a choice, draws the same rows again at once at the new speed, and this browser remembers it", async () => {
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(380); // (the picture has room: the painter draws)
    const rows = useScopeRows();
    const mountedWith = () => mount(MonitorCard, { global: withDaemon(hfAlone({ scopeRows: rows.memory })), attachTo: document.body });
    const speeds = vi.spyOn(Waterfall.prototype, "setSpeed");
    const shows = vi.spyOn(Waterfall.prototype, "show");
    const tall = (): number | undefined => images.at(-1)?.[1]; // (how many pixels high the painter's line is)
    const wrapper = mountedWith();
    await flushPromises();
    expect(tall()).toBe(1);
    await rightClick(wrapper, ".monitor-picture canvas");
    let before = shows.mock.calls.length;
    items()[2]?.click();
    await settle(wrapper);
    expect(menu()).toBeNull();
    expect(localStorage.getItem("NeoAPRS.monitorspeed")).toBe("fast");
    expect(speeds.mock.calls).toEqual([["fast"]]);
    expect(shows.mock.calls.length).toBe(before + 1); // (drawn again at once, from the page's rows, after the speed was set)
    expect(shows.mock.calls.at(-1)?.[0]).toBe(rows.memory.rows);
    expect(speeds.mock.invocationCallOrder[0]).toBeLessThan(shows.mock.invocationCallOrder.at(-1) ?? 0);
    expect(tall()).toBe(2); // (Fast: the lines of Normal drawn twice as high)
    wrapper.unmount();

    images.length = 0;
    before = shows.mock.calls.length;
    const again = mountedWith(); // (a reload)
    await flushPromises();
    expect(images[0]?.[1]).toBe(2); // (drawn at the kept speed from the first)
    expect((shows.mock.contexts[before] as Waterfall).slot(1000)).toBe(5);
    await rightClick(again, ".monitor-picture canvas");
    expect(checked()).toEqual(["false", "false", "true"]);
    before = shows.mock.calls.length;
    items()[0]?.click();
    await settle(again);
    expect(localStorage.getItem("NeoAPRS.monitorspeed")).toBe("slow");
    expect(shows.mock.calls.length).toBe(before + 1);
    expect((shows.mock.contexts.at(-1) as Waterfall).slot(1000)).toBe(2); // (lines of two fifths of a second)
    expect(tall()).toBe(1);
    again.unmount();

    before = shows.mock.calls.length;
    const third = mountedWith(); // (another reload: Slow is kept as well)
    expect((shows.mock.contexts[before] as Waterfall).slot(1000)).toBe(2);
    third.unmount();
  });

  it("is at Normal when what this browser has kept is not a speed", async () => {
    localStorage.setItem("NeoAPRS.monitorspeed", "warp");
    const wrapper = mounted();
    await rightClick(wrapper, ".monitor-picture canvas");
    expect(checked()).toEqual(["false", "true", "false"]);
    wrapper.unmount();
  });

  it("keeps the room of the check mark on every item and shows it on the one that is on, so that choosing moves no word", async () => {
    const wrapper = mounted();
    await rightClick(wrapper, ".monitor-picture canvas");
    for (const item of items()) {
      const mark = item.firstElementChild;
      expect(mark?.classList.contains("ctxmenu-mark")).toBe(true);
      expect(mark?.getAttribute("aria-hidden")).toBe("true");
    }
    expect(cssRule(".ctxmenu-mark")).toMatch(/visibility:\s*hidden/);
    expect(cssRule(".ctxmenu-mark")).toMatch(/width:\s*1\.25em/);
    expect(cssRule('[aria-checked="true"] > .ctxmenu-mark')).toMatch(/visibility:\s*visible/);
    wrapper.unmount();
  });

  it("is not on the box in Settings, which stays at Normal whatever the card was set to", async () => {
    localStorage.setItem("NeoAPRS.settings.fold.hf-scope", "open");
    localStorage.setItem("NeoAPRS.monitorspeed", "slow");
    const shows = vi.spyOn(Waterfall.prototype, "show");
    const box = mount(HfScope, { global: withDaemon(hfAlone()), attachTo: document.body });
    expect((shows.mock.contexts[0] as Waterfall).slot(1000)).toBe(5);
    const event = new MouseEvent("contextmenu", { clientX: 100, clientY: 100, bubbles: true, cancelable: true });
    box.find(".scope-picture canvas").element.dispatchEvent(event);
    await box.vm.$nextTick();
    expect(event.defaultPrevented).toBe(false);
    expect(document.body.querySelector("[role='menu']")).toBeNull();
    box.unmount();
  });
});

/** A Mercury radio whose modem has the interface (or has not, `scope` false). */
const mercury = (id: number, extra: Partial<RadioRow> = {}, scope = true): RadioRow =>
  radioRow(id, "mercury", { modem: { ...hfState().modem!, scope }, ...extra });

/** The settings of before that agree with the radios 1 and 2 of the topic (the page takes their Enable from them while they exist). */
const before = (rows: RadioRow[]) => {
  const on = (id: number) => String(rows.some((row) => row.id === id && row.enabled));
  return configValues({ "fm/enabled": on(1), "hf/enabled": on(2) });
};

/** The page's context with these radios, its counting of who looks given the topic `radios` and the page's rows, as the page makes it. */
function station(...rows: RadioRow[]) {
  const scopeRows = useScopeRows();
  const daemon = fakeDaemon({ radios: radiosTopic(...rows), config: before(rows) });
  daemon.scopeRows = scopeRows.memory;
  daemon.scopeOf = scopeRows.of;
  daemon.scope = useScopeLooks(daemon.send, daemon.hf, daemon.connection, shallowRef(true), { radios: daemon.radios });
  const card = () => mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
  return { daemon, scopeRows, card };
}
const head = (wrapper: ReturnType<typeof mount>) => wrapper.find(".card-head strong").text();
const row = () => ({ db: new Float32Array(BINS).fill(-40), level: -20, tx: false });

describe("the card by radio", () => {
  it("says Monitor alone on a station with one radio, and asks for that radio's rows", () => {
    const { daemon, card } = station(mercury(3, { name: "Shack" }));
    const wrapper = card();
    expect(head(wrapper)).toBe("Monitor");
    expect(wrapper.attributes("aria-label")).toBe("Monitor");
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 3, on: true, named: true }]);
  });

  it("names the HF radio on a station with an FM and an HF radio", () => {
    const { card } = station(radioRow(1, "kenwood-tnc2"), mercury(2));
    expect(head(card())).toBe("HF: Monitor");
  });

  it("with several radios with a scope, shows the first until another is chosen in the map's menu, then that one's, and names it", async () => {
    const { daemon, card } = station(radioRow(1, "kenwood-tnc2"), mercury(2, { name: "20 m" }), mercury(5, { name: "40 m" }));
    const wrapper = card();
    await flushPromises();
    expect(head(wrapper)).toBe("20 m: Monitor");
    expect(wrapper.attributes("aria-label")).toBe("20 m: Monitor");
    expect(scopeCalls(daemon)).toEqual([{ cmd: "radio_scope", radio: 2, on: true, named: true }]);
    daemon.scope.showOnMonitor(5);
    await flushPromises();
    expect(head(wrapper)).toBe("40 m: Monitor");
    expect(scopeCalls(daemon).slice(1)).toEqual([
      { cmd: "radio_scope", radio: 2, on: false, named: true },
      { cmd: "radio_scope", radio: 5, on: true, named: true },
    ]);
    wrapper.unmount();
    expect(head(card())).toBe("40 m: Monitor"); // (this browser remembers the radio chosen)
  });

  it("goes to the first radio with a scope when its radio is switched off or removed", async () => {
    for (const gone of [
      { enabled: false, state: "stopped" as const },
      { removed: true, enabled: false },
    ]) {
      localStorage.clear();
      const { daemon, card } = station(mercury(2, { name: "20 m" }), mercury(5, { name: "40 m" }));
      daemon.scope.showOnMonitor(5);
      const wrapper = card();
      expect(head(wrapper)).toBe("40 m: Monitor");
      const left = [mercury(2, { name: "20 m" }), mercury(5, { name: "40 m", ...gone })];
      daemon.radios.value = radiosTopic(...left);
      daemon.config.value = before(left);
      await flushPromises();
      expect(head(wrapper)).toBe("Monitor"); // (one radio is on: it is not named)
      expect(scopeCalls(daemon).slice(-2)).toEqual([
        { cmd: "radio_scope", radio: 5, on: false, named: true },
        { cmd: "radio_scope", radio: 2, on: true, named: true },
      ]);
      wrapper.unmount();
    }
  });

  it("stays on its radio, with its picture, while that radio's modem is without the interface for a moment, chosen or not", async () => {
    for (const chosen of [5, 2]) {
      localStorage.clear();
      const rows = [mercury(2, { name: "20 m" }), mercury(5, { name: "40 m" })];
      const { daemon, scopeRows, card } = station(...rows);
      if (chosen === 5) daemon.scope.showOnMonitor(5);
      const name = chosen === 5 ? "40 m" : "20 m";
      const wrapper = card();
      await flushPromises();
      for (let i = 0; i < 5; i++) scopeRows.hfScopeRow(row(), chosen);
      const shows = vi.spyOn(Waterfall.prototype, "show");
      daemon.radios.value = radiosTopic(...rows.map((radio) => (radio.id === chosen ? mercury(chosen, { name }, false) : radio)));
      await flushPromises();
      expect(head(wrapper)).toBe(`${name}: Monitor`);
      expect(scopeRows.of(chosen).rows).toHaveLength(5);
      daemon.radios.value = radiosTopic(...rows);
      await flushPromises();
      expect(head(wrapper)).toBe(`${name}: Monitor`);
      expect(scopeRows.of(chosen).rows).toHaveLength(5);
      expect(shows.mock.calls.map(([kept]) => kept.length)).toEqual([5]); // (drawn again as its scope came back: its own picture, not another radio's)
      expect(scopeCalls(daemon)).toEqual([
        { cmd: "radio_scope", radio: chosen, on: true, named: true },
        { cmd: "radio_scope", radio: chosen, on: false, named: true },
        { cmd: "radio_scope", radio: chosen, on: true, named: true },
      ]);
      wrapper.unmount();
      shows.mockRestore();
    }
  });

  it("goes on with its own radio's rows while another radio's box in Settings looks at that one's: both are asked for at once, and each picture is drawn from its own radio's frames", async () => {
    const { daemon, scopeRows, card } = station(mercury(2, { name: "20 m" }), mercury(5, { name: "40 m" }));
    const wrapper = card();
    await flushPromises();
    for (let i = 0; i < 5; i++) scopeRows.hfScopeRow(row(), 2);
    const pushes = vi.spyOn(Waterfall.prototype, "push");
    localStorage.setItem("NeoAPRS.settings.fold.radio-5-scope", "open");
    const box = mount(HfScope, { props: { radio: 5 }, global: withDaemon(daemon), attachTo: document.body });
    await flushPromises();
    expect(daemon.scope.asked.value).toEqual([2, 5]);
    expect(scopeCalls(daemon)).toEqual([
      { cmd: "radio_scope", radio: 2, on: true, named: true },
      { cmd: "radio_scope", radio: 5, on: true, named: true },
    ]);
    scopeRows.hfScopeRow(row(), 5);
    expect(pushes).toHaveBeenCalledTimes(1); // (the box's picture alone: the card is radio 2's)
    const boxPainter = pushes.mock.contexts[0];
    scopeRows.hfScopeRow(row(), 2);
    expect(pushes).toHaveBeenCalledTimes(2); // (the card's)
    expect(pushes.mock.contexts[1]).not.toBe(boxPainter);
    expect(scopeRows.of(2).rows).toHaveLength(6);
    box.unmount();
    await flushPromises();
    expect(daemon.scope.asked.value).toEqual([2]);
    expect(head(wrapper)).toBe("20 m: Monitor");
  });

  it("names a radio of eight characters with six radios on, its head with nothing that cuts it, and the card within the phone's width (the look at 375 px is the coordinator's, in a browser)", () => {
    const names = ["WWWWWWWW", "MMMMMMMM", "Shack 20", "Mast 40m", "Mobile 2", "Base HF3"];
    const { daemon, card } = station(...names.map((name, i) => mercury(i + 1, { name, number: i + 1 })));
    daemon.scope.showOnMonitor(1);
    const wrapper = card();
    expect(head(wrapper)).toBe("WWWWWWWW: Monitor");
    for (const rule of [".card-head", ".card-title", ".card-call"]) expect(cssRule(rule)).not.toMatch(/text-overflow|white-space:\s*nowrap|overflow:\s*hidden/);
    expect(cssRule(".monitorcard")).toMatch(/width:\s*min\(560px, calc\(100% - 20px\)\)/);
  });
});
