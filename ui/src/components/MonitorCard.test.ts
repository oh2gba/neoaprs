// The monitor card over the map (components/MonitorCard.vue): the scope of the HF radio larger, asked of the daemon while it is there; closed by its cross, dragged by its head like the statistics card and remembered where it was left.
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HfScope from "@/components/HfScope.vue";
import MonitorCard from "@/components/MonitorCard.vue";
import { useScopeRows } from "@/composables/useScopeRows";
import type { ScopeRow } from "@/lib/scoperow";
import { BINS } from "@/lib/waterfall";
import { fakeDaemon, withDaemon } from "@/test/context";
import { hfState } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

const withScope = () => {
  const state = hfState();
  return { ...state, modem: { ...state.modem!, scope: true } };
};
const rect = (x: number, y: number, w: number, h: number) =>
  ({ x, y, left: x, top: y, right: x + w, bottom: y + h, width: w, height: h, toJSON: () => ({}) }) as DOMRect;
const scopeCalls = (daemon: ReturnType<typeof fakeDaemon>) => daemon.send.mock.calls.map(([c]) => c).filter((c) => c.cmd === "hf_scope");

beforeEach(() => {
  localStorage.clear();
  const context = new Proxy(
    {},
    {
      get: (_t, name: string) =>
        name === "measureText"
          ? () => ({ width: 10 })
          : name === "createImageData"
            ? (w: number, h: number) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) })
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
    const daemon = fakeDaemon({ hf: withScope() });
    const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    expect(wrapper.find(".card-head strong").text()).toBe("Monitor");
    expect(wrapper.attributes("aria-label")).toBe("Monitor");
    expect(wrapper.find(".monitor-picture canvas").exists()).toBe(true);
    expect(wrapper.find("[role='meter']").exists()).toBe(true);
    expect(wrapper.find(".info-tip, .infotip").exists()).toBe(false);
    expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
    wrapper.unmount();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
  });

  it("shows the level of the rows that come", async () => {
    const rows = useScopeRows();
    const daemon = fakeDaemon({ hf: withScope(), onScopeRow: rows.onScopeRow });
    const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    await flushPromises(); // (the picture has room once it is mounted, and then the rows are asked for)
    const row: ScopeRow = { db: new Float32Array(BINS).fill(-40), level: -20, tx: false };
    rows.hfScopeRow(row);
    await flushPromises();
    expect(wrapper.find(".levelvalue").text()).toBe("-20 dBFS");
  });

  it("its cross closes it", async () => {
    const wrapper = mount(MonitorCard, { global: withDaemon(fakeDaemon({ hf: withScope() })), attachTo: document.body });
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
    const mounted = (movable: boolean) =>
      mount(MonitorCard, { props: { movable }, global: withDaemon(fakeDaemon({ hf: withScope() })), attachTo: document.body });
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
      const daemon = fakeDaemon({ hf: withScope() });
      const wrapper = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([]);
      width.set(540);
      await flushPromises();
      expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
      width.set(0);
      await flushPromises();
      expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
      wrapper.unmount();
    } finally {
      width.restore();
    }
  });
});

describe("the one counting place", () => {
  it("keeps asking for the rows while the card or the box in Settings shows them, and stops when neither does", () => {
    localStorage.setItem("NeoAPRS.settings.fold.hf-scope", "open");
    const daemon = fakeDaemon({ hf: withScope() });
    const box = mount(HfScope, { global: withDaemon(daemon), attachTo: document.body });
    expect(scopeCalls(daemon)).toEqual([{ cmd: "hf_scope", on: true }]);
    const card = mount(MonitorCard, { global: withDaemon(daemon), attachTo: document.body });
    expect(scopeCalls(daemon)).toHaveLength(1);
    box.unmount();
    expect(scopeCalls(daemon)).toHaveLength(1);
    card.unmount();
    expect(scopeCalls(daemon).at(-1)).toEqual({ cmd: "hf_scope", on: false });
    expect(scopeCalls(daemon)).toHaveLength(2);
  });
});
