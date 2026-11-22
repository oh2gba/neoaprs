// The Packets and Monitor cards are sized by their edges and corners and by Ctrl and Alt with
// the arrow keys (composables/useCardSize.ts, CardSizer.vue), within the least size the content
// can be read at and the map's room. The size is kept with the position, and a smaller window
// brings the card back inside. The statistics card has no handles.
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MonitorCard from "@/components/MonitorCard.vue";
import PacketsCard from "@/components/PacketsCard.vue";
import StatsCard from "@/components/StatsCard.vue";
import { fakeDaemon, withDaemon } from "@/test/context";

const rect = (x: number, y: number, w: number, h: number) =>
  ({ x, y, left: x, top: y, right: x + w, bottom: y + h, width: w, height: h, toJSON: () => ({}) }) as DOMRect;
const MAP = { width: 1200, height: 800 };

/** The map is 1200 by 800; a card stands where its style puts it, else at the bottom right at
 * 560 by 480. */
function standIn(): void {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (!/card/.test(this.className) || this.className.includes("card-")) return rect(0, 0, MAP.width, MAP.height);
    const w = parseFloat(this.style.width) || 560;
    const h = parseFloat(this.style.height) || 480;
    return this.style.left ? rect(parseFloat(this.style.left), parseFloat(this.style.top), w, h) : rect(MAP.width - 10 - w, MAP.height - 30 - h, w, h);
  });
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(MAP.width);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(MAP.height);
}
const packets = (movable = true) => mount(PacketsCard, { props: { packets: new Map(), movable }, global: withDaemon(fakeDaemon()), attachTo: document.body });
const monitor = (movable = true) => mount(MonitorCard, { props: { movable }, global: withDaemon(fakeDaemon()), attachTo: document.body });
const pointer = (target: Element, type: string, x: number, y: number) =>
  target.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true }));

beforeEach(() => {
  localStorage.clear();
  standIn();
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe.each([
  { name: "Packets card", make: packets, selector: ".packetscard", sizeKey: "NeoAPRS.packetssize", placeKey: "NeoAPRS.packetsplace", least: [380, 240] },
  { name: "Monitor card", make: monitor, selector: ".monitorcard", sizeKey: "NeoAPRS.monitorsize", placeKey: "NeoAPRS.monitorplace", least: [340, 300] },
])("$name", ({ make, selector, sizeKey, placeKey, least }) => {
  it("has a handle on each edge and corner for the pointer, hidden from a screen reader that has the card's keys, and none on a phone", () => {
    const wrapper = make(true);
    const handles = wrapper.findAll(".sizer");
    expect(handles).toHaveLength(8);
    expect(new Set(handles.map((h) => h.attributes("aria-hidden")))).toEqual(new Set(["true"]));
    expect(wrapper.find(selector).attributes("aria-keyshortcuts")).toContain("Control+Alt+ArrowRight");
    expect(wrapper.find(".card-head").attributes("title")).toContain("Ctrl+Alt+arrow keys size it");
    wrapper.unmount();
    const phone = make(false);
    expect(phone.findAll(".sizer")).toHaveLength(0);
    expect(phone.find(selector).attributes("aria-keyshortcuts")).toBeUndefined();
    expect(phone.find(selector).classes()).not.toContain("sized");
  });

  it("is sized by its left edge with the pointer, keeps its right side, and remembers size and place", async () => {
    const wrapper = make(true);
    const el = wrapper.find(selector).element as HTMLElement;
    const handle = wrapper.find(".sizer-w").element;
    pointer(handle, "pointerdown", 630, 500);
    pointer(handle, "pointermove", 530, 500);
    pointer(handle, "pointerup", 530, 500);
    await wrapper.vm.$nextTick();
    expect([el.style.left, el.style.width, el.style.height]).toEqual(["530px", "660px", "480px"]);
    expect(el.classList.contains("sized")).toBe(true);
    expect(el.classList.contains("moved")).toBe(true);
    expect(localStorage.getItem(sizeKey)).toBe("660,480");
    expect(localStorage.getItem(placeKey)).toBe("530,290");
    wrapper.unmount();
    const again = make(true);
    const back = again.find(selector).element as HTMLElement;
    expect([back.style.left, back.style.width, back.style.height]).toEqual(["530px", "660px", "480px"]);
    expect(document.body.classList.contains("card-sizing")).toBe(false);
  });

  it("is sized by its corner, never below the least and never beyond the map", async () => {
    const wrapper = make(true);
    const el = wrapper.find(selector).element as HTMLElement;
    const corner = wrapper.find(".sizer-se").element;
    pointer(corner, "pointerdown", 1190, 770);
    pointer(corner, "pointermove", 100, 100);
    await wrapper.vm.$nextTick();
    expect([el.style.width, el.style.height]).toEqual([`${least[0]}px`, `${least[1]}px`]);
    pointer(corner, "pointermove", 5000, 5000);
    pointer(corner, "pointerup", 5000, 5000);
    await wrapper.vm.$nextTick();
    expect(parseFloat(el.style.width)).toBeLessThanOrEqual(MAP.width - parseFloat(el.style.left));
    expect(parseFloat(el.style.height)).toBeLessThanOrEqual(MAP.height - parseFloat(el.style.top));
  });

  it("is sized with Ctrl and Alt and the arrow keys, which Alt alone does not do", async () => {
    const wrapper = make(true);
    const el = wrapper.find(selector).element as HTMLElement;
    await wrapper.find(selector).trigger("keydown", { key: "ArrowLeft", altKey: true, ctrlKey: true });
    expect([el.style.width, el.style.height]).toEqual(["536px", "480px"]);
    expect(el.style.left).toBe("654px"); // (the side with room moves, the corner at the map's edge stays)
    await wrapper.find(selector).trigger("keydown", { key: "ArrowUp", altKey: true, ctrlKey: true, shiftKey: true });
    expect([el.style.width, el.style.height]).toEqual(["536px", "384px"]);
    await wrapper.find(selector).trigger("keydown", { key: "ArrowRight", altKey: true });
    expect(el.style.width).toBe("536px"); // (Alt alone moves it)
    expect(el.style.left).toBe("664px");
  });

  it("is made larger with Ctrl and Alt and Right and Down where it stands by default, at the map's bottom right", async () => {
    const wrapper = make(true);
    const el = wrapper.find(selector).element as HTMLElement;
    for (let n = 0; n < 3; n++) await wrapper.find(selector).trigger("keydown", { key: "ArrowRight", altKey: true, ctrlKey: true });
    await wrapper.find(selector).trigger("keydown", { key: "ArrowDown", altKey: true, ctrlKey: true, shiftKey: true });
    expect([el.style.width, el.style.height]).toEqual(["632px", "576px"]);
    expect([el.style.left, el.style.top]).toEqual(["558px", "194px"]); // (right and bottom sides stayed)
    expect(localStorage.getItem(sizeKey)).toBe("632,576");
  });

  it("keeps the size and the place only when the pointer is let go, not at every move", () => {
    const wrapper = make(true);
    const handle = wrapper.find(".sizer-w").element;
    pointer(handle, "pointerdown", 630, 500);
    pointer(handle, "pointermove", 600, 500);
    expect(localStorage.getItem(sizeKey)).toBeNull();
    expect(localStorage.getItem(placeKey)).toBeNull();
    pointer(handle, "pointerup", 600, 500);
    expect(localStorage.getItem(sizeKey)).toBe("590,480");
    expect(localStorage.getItem(placeKey)).toBe("600,290");
  });

  it("is brought back inside when the map is made smaller", async () => {
    const watchers: ResizeObserverCallback[] = [];
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          watchers.push(callback);
        }
        observe(): void {}
        disconnect(): void {}
      },
    );
    localStorage.setItem(sizeKey, "900,700");
    localStorage.setItem(placeKey, "0,0");
    const wrapper = make(true);
    await wrapper.vm.$nextTick();
    const el = wrapper.find(selector).element as HTMLElement;
    expect([el.style.width, el.style.height]).toEqual(["900px", "700px"]);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(600);
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
    for (const callback of watchers) callback([], {} as ResizeObserver);
    await wrapper.vm.$nextTick();
    expect([el.style.width, el.style.height]).toEqual(["600px", "400px"]);
    expect(localStorage.getItem(sizeKey)).toBe("900,700"); // (the chosen size is kept for when the map is large again)
    vi.unstubAllGlobals();
  });
});

describe("StatsCard", () => {
  it("has no handles: its content has its size", () => {
    const wrapper = mount(StatsCard, { props: { packets: new Map(), movable: true }, global: withDaemon(fakeDaemon()), attachTo: document.body });
    expect(wrapper.findAll(".sizer")).toHaveLength(0);
    expect(wrapper.find(".statscard").classes()).not.toContain("sized");
  });
});
