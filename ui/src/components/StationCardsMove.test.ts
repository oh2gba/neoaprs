import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StationCards from "@/components/StationCards.vue";
import type { Places } from "@/composables/useCardDrag";
import type { SizeClass } from "@/lib/layout";
import { fakeDaemon, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { station } from "@/test/fixtures";

// The map is 1200 by 800 pixels; the row of cards (`.cardstack`) is inside it from (10, 84) to (1190, 770); a card is 340 by 300 and, in the row, stands at its bottom, the cards side by side from the row's left.
const rect = (left: number, top: number, width: number, height: number): DOMRect => ({
  left,
  top,
  width,
  height,
  right: left + width,
  bottom: top + height,
  x: left,
  y: top,
  toJSON: () => ({}),
});
const CARD = { width: 340, height: 300 };

const A = station("OH2ZWA", { lat: 60.1, lon: 24.8 });
const B = station("OH2ZWB", { lat: 60.2, lon: 24.9 });
const C = station("OH2ZWC", { lat: 60.3, lon: 25 });

let wrap: HTMLElement;

type Wrapper = VueWrapper<InstanceType<typeof StationCards>>;
function make(rows = [A, B], size: SizeClass = "desktop"): Wrapper {
  wrap = document.createElement("div");
  wrap.className = "mapwrap";
  document.body.append(wrap);
  // (the places are the page's, as in the page: a write comes back as the prop only when the page has been drawn again, so a second write at once does not see the first)
  const wrapper: Wrapper = mount(StationCards, {
    props: { rows, size, places: {}, "onUpdate:places": (places: Places) => void wrapper.setProps({ places }) },
    global: withDaemon(fakeDaemon()),
    attachTo: wrap,
  });
  return wrapper;
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.classList.contains("mapwrap")) return rect(0, 0, 1200, 800);
    if (this.classList.contains("cardstack")) return rect(10, 84, 1180, 686);
    if (this.classList.contains("card")) {
      if (this.classList.contains("moved")) return rect(10 + parseFloat(this.style.left), 84 + parseFloat(this.style.top), CARD.width, CARD.height);
      const inRow = [...(this.parentElement?.querySelectorAll(":scope > .card:not(.moved)") ?? [])];
      return rect(10 + inRow.indexOf(this) * 348, 770 - CARD.height, CARD.width, CARD.height);
    }
    return rect(0, 0, 0, 0);
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

/** A pointer event of the mouse, a finger or a pen (the events of a pointer have no pointer id here: the same one, so, for all). */
const pointer = (type: string, x: number, y: number, target: Element) =>
  target.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, cancelable: true }));
const card = (wrapper: Wrapper, call: string) => wrapper.find(`.card[data-call="${call}"]`);
const style = (wrapper: Wrapper, call: string) => {
  const el = card(wrapper, call).element as HTMLElement;
  return { left: el.style.left, top: el.style.top };
};
function drag(wrapper: Wrapper, call: string, from: [number, number], to: [number, number], target?: Element) {
  const start = target ?? card(wrapper, call).find(".card-head strong").element;
  pointer("pointerdown", from[0], from[1], start);
  pointer("pointermove", to[0], to[1], start);
  pointer("pointerup", to[0], to[1], start);
}

describe("StationCards: moving a card by its head", () => {
  it("stands the cards in the row, none of them moved, with the grab cursor on the head and the hint", () => {
    const wrapper = make();
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
    expect(wrapper.find(".card-head").attributes("title")).toContain("Drag to move");
    expect(cssRule(".cardstack:not(.sheet) .card-head")).toContain("cursor: grab");
    expect(cssRule(".cardstack:not(.sheet) .card-head")).toContain("touch-action: none");
    expect(cssRule(".cardstack:not(.sheet) .card-head")).toContain("user-select: none");
    expect(cssRule(".card-dragging *")).toContain("cursor: grabbing");
    expect(cssRule(".cardstack .card.moved")).toContain("position: absolute");
    expect(cssRule(".cardstack .card.moved")).toContain("bottom: auto");
  });

  it("moves the card by the distance of the pointer, and the other card stays where it stands (pinned there)", async () => {
    const wrapper = make();
    drag(wrapper, "OH2ZWB", [400, 500], [460, 440]); // (the second card stood at x = 358 - 10 = 348 of the row, y = 386)
    await wrapper.vm.$nextTick();
    expect(card(wrapper, "OH2ZWB").classes()).toContain("moved");
    expect(style(wrapper, "OH2ZWB")).toEqual({ left: "408px", top: "326px" });
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "0px", top: "386px" });
    expect(wrapper.emitted("update:places")?.at(-1)).toEqual([{ OH2ZWA: { x: 0, y: 386 }, OH2ZWB: { x: 408, y: 326 } }]);
  });

  it("moves with touch and pen the same way, and follows the pointer in steps", async () => {
    const wrapper = make([A]);
    const head = card(wrapper, "OH2ZWA").find(".card-head strong").element;
    pointer("pointerdown", 100, 600, head);
    pointer("pointermove", 120, 590, head);
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "20px", top: "376px" });
    pointer("pointermove", 220, 490, head);
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "120px", top: "276px" });
    pointer("pointerup", 220, 490, head);
  });

  it("does not select text or leave the grabbing cursor: the page is marked while the pointer is down and moving, and the mark goes with the pointer", async () => {
    const wrapper = make([A]);
    const head = card(wrapper, "OH2ZWA").find(".card-head strong").element;
    pointer("pointerdown", 100, 600, head);
    expect(document.body.classList.contains("card-dragging")).toBe(false); // (a click is not a drag)
    const move = new MouseEvent("pointermove", { clientX: 130, clientY: 600, bubbles: true, cancelable: true });
    head.dispatchEvent(move);
    expect(document.body.classList.contains("card-dragging")).toBe(true);
    expect(move.defaultPrevented).toBe(true);
    pointer("pointerup", 130, 600, head);
    expect(document.body.classList.contains("card-dragging")).toBe(false);
    pointer("pointermove", 400, 600, head); // (no more following)
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(1);
    expect(style(wrapper, "OH2ZWA").left).toBe("30px");
  });

  it("is not a drag when the pointer moves less than a few pixels: it is a click on the head", async () => {
    const wrapper = make([A]);
    drag(wrapper, "OH2ZWA", [100, 600], [102, 601]);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
  });

  it("does not drag by the buttons and the links of the head", async () => {
    const wrapper = make([station("OH2ZWA")]);
    const close = card(wrapper, "OH2ZWA").find("button[aria-label='Close']").element;
    drag(wrapper, "OH2ZWA", [100, 600], [200, 500], close);
    const qrz = card(wrapper, "OH2ZWA").find("a.qrz").element;
    drag(wrapper, "OH2ZWA", [100, 600], [200, 500], qrz);
    // (nor by the body or the footer of the card)
    drag(wrapper, "OH2ZWA", [100, 600], [200, 500], card(wrapper, "OH2ZWA").find(".card-fields").element);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
  });

  it("keeps the card inside the map: to its four edges", async () => {
    const wrapper = make([A]);
    drag(wrapper, "OH2ZWA", [100, 600], [-900, -900]);
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "-10px", top: "-84px" }); // (the map's top left corner: the row begins at (10, 84))
    drag(wrapper, "OH2ZWA", [100, 100], [5000, 5000]);
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "850px", top: "416px" }); // (the card's right edge at the map's: 1200 - 340 - 10; the bottom at 800: 800 - 300 - 84)
  });

  it("keeps a moved card inside the map as the map is now: a map that got smaller holds it at its edge", async () => {
    const wrapper = make([A]);
    drag(wrapper, "OH2ZWA", [100, 600], [800, 400]);
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA").left).toBe("700px");
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      if (this.classList.contains("mapwrap")) return rect(0, 0, 800, 800);
      if (this.classList.contains("cardstack")) return rect(10, 84, 780, 686);
      return rect(10 + parseFloat(this.style.left), 84 + parseFloat(this.style.top), CARD.width, CARD.height);
    });
    // (the row's size observer asks for this when the map gets smaller; here the next move does)
    card(wrapper, "OH2ZWA").element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", altKey: true, bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA").left).toBe("450px"); // (800 - 340 - 10)
  });

  it("asks to close the oldest card only when the cards in the row are too wide for the map: cards that stand where they were put take no room in it", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(340);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("cardstack") ? 1180 : 0;
    });
    const D = station("OH2ZWD");
    const full = make([A, B, C, D]);
    await full.vm.$nextTick();
    await full.vm.$nextTick();
    expect(full.emitted("overflow")).toBeDefined(); // (4 cards of 340 and 3 gaps are wider than the 1160 px the row has)
    document.body.replaceChildren();
    const wrapper = make([A, B, C]);
    drag(wrapper, "OH2ZWA", [100, 600], [300, 300]);
    await wrapper.setProps({ rows: [A, B, C, D] });
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("overflow")).toBeUndefined();
    expect(wrapper.findAll(".cardstack > .card:not(.moved)")).toHaveLength(0);
  });
});

describe("StationCards: moving a card never moves another", () => {
  const spot = (wrapper: Wrapper, call: string) => ({ ...style(wrapper, call), moved: card(wrapper, call).classes().includes("moved") });

  it("drag the first (the leftmost) of two cards: the second stays where it was, and the first one's slot is empty", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWA", [100, 600], [700, 300]);
    await wrapper.vm.$nextTick();
    expect(spot(wrapper, "OH2ZWA")).toEqual({ left: "600px", top: "86px", moved: true });
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "348px", top: "386px", moved: true }); // (where it stood in the row: x = 358 - 10)
  });

  it("drag the second: the first stays where it was", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWB", [400, 600], [500, 300]);
    await wrapper.vm.$nextTick();
    expect(spot(wrapper, "OH2ZWA")).toEqual({ left: "0px", top: "386px", moved: true });
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "448px", top: "86px", moved: true });
  });

  it("moves with Alt and an arrow the same way: the others are pinned where they stand", async () => {
    const wrapper = make([A, B, C]);
    card(wrapper, "OH2ZWA")
      .find("button[aria-label='Close']")
      .element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", altKey: true, shiftKey: true, bubbles: true, cancelable: true }));
    await wrapper.vm.$nextTick();
    expect(spot(wrapper, "OH2ZWA").top).toBe("290px");
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "348px", top: "386px", moved: true });
    expect(spot(wrapper, "OH2ZWC")).toEqual({ left: "696px", top: "386px", moved: true });
  });

  it("closing the first of two cards leaves the second where it stood; closing the second leaves the first", async () => {
    const wrapper = make([A, B]);
    await wrapper.setProps({ rows: [B] });
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "348px", top: "386px", moved: true });
    const other = make([A, B]);
    await other.setProps({ rows: [A] });
    expect(spot(other, "OH2ZWA").left).toBe("");
    expect(other.emitted("update:places")).toBeUndefined();
  });

  it("closing a card of the row leaves the cards after it where they stood", async () => {
    const wrapper = make([A, B, C]);
    await wrapper.setProps({ rows: [A, C] });
    expect(spot(wrapper, "OH2ZWC")).toEqual({ left: "696px", top: "386px", moved: true });
    expect(spot(wrapper, "OH2ZWA").moved).toBe(false);
  });

  it("closing a card that was moved moves no one", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWA", [100, 600], [700, 300]);
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ rows: [B] });
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "348px", top: "386px", moved: true });
  });

  it("opens a third card in the slot that the moved card left (the first free one, from the left)", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWA", [100, 600], [700, 300]);
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ rows: [A, B, C] });
    expect(spot(wrapper, "OH2ZWC")).toEqual({ left: "0px", top: "386px", moved: true });
    expect(spot(wrapper, "OH2ZWB")).toEqual({ left: "348px", top: "386px", moved: true });
    expect(spot(wrapper, "OH2ZWA")).toEqual({ left: "600px", top: "86px", moved: true });
  });

  it("opens a third card to the right of the rightmost when the slots are taken, never on top of a card", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWA", [100, 600], [120, 600]); // (a little to the right: the first slot is not free any more)
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ rows: [A, B, C] });
    expect(spot(wrapper, "OH2ZWC")).toEqual({ left: "696px", top: "386px", moved: true });
  });

  it("opens a card in the row above when the row has no room, and in the row when no card was moved or closed", async () => {
    const wrapper = make([A, B, C]);
    drag(wrapper, "OH2ZWA", [100, 600], [120, 600]);
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ rows: [A, B, C, station("OH2ZWD")] });
    expect(spot(wrapper, "OH2ZWD")).toEqual({ left: "0px", top: "78px", moved: true });
    const plain = make([A]);
    await plain.setProps({ rows: [A, B] });
    expect(spot(plain, "OH2ZWB")).toEqual({ left: "", top: "", moved: false });
  });

  it("forgets all the places on Close all, and the cards opened after it are in the row", async () => {
    const wrapper = make([A, B]);
    drag(wrapper, "OH2ZWA", [100, 600], [700, 300]);
    await wrapper.vm.$nextTick();
    await wrapper.setProps({ rows: [] });
    await wrapper.setProps({ rows: [A, B] });
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
    expect(wrapper.emitted("update:places")?.at(-1)).toEqual([{}]);
  });
});

describe("StationCards: moving a card with the keyboard", () => {
  const key = (wrapper: Wrapper, call: string, init: KeyboardEventInit) => {
    const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    card(wrapper, call).find("button[aria-label='Close']").element.dispatchEvent(event);
    return event;
  };

  it("moves the card that has the focus by Alt and an arrow, in steps, a big one with Shift", async () => {
    const wrapper = make([A]);
    const left = key(wrapper, "OH2ZWA", { key: "ArrowLeft", altKey: true });
    await wrapper.vm.$nextTick();
    expect(left.defaultPrevented).toBe(true);
    expect(style(wrapper, "OH2ZWA")).toEqual({ left: "-10px", top: "386px" }); // (the first step is from where the card stands in the row, x = 0, and the map's left edge is 10 px left of the row's)
    key(wrapper, "OH2ZWA", { key: "ArrowUp", altKey: true });
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA").top).toBe("362px");
    key(wrapper, "OH2ZWA", { key: "ArrowRight", altKey: true, shiftKey: true });
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA").left).toBe("86px");
    key(wrapper, "OH2ZWA", { key: "ArrowDown", altKey: true });
    await wrapper.vm.$nextTick();
    expect(style(wrapper, "OH2ZWA").top).toBe("386px");
  });

  it("leaves the arrows alone without Alt (they are for the fields and the buttons)", async () => {
    const wrapper = make([A]);
    const event = key(wrapper, "OH2ZWA", { key: "ArrowLeft" });
    await wrapper.vm.$nextTick();
    expect(event.defaultPrevented).toBe(false);
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
  });
});

describe("StationCards: the bottom sheet of a phone", () => {
  it("cannot be dragged: the head is not a handle, has no hint, and no card is moved", async () => {
    const wrapper = make([A], "phone");
    expect(wrapper.find(".card-head").attributes("title")).toBeUndefined();
    expect(cssRule(".cardstack:not(.sheet) .card-head")).not.toBe(""); // (the handle's style is for the row only: the sheet is excluded by the selector)
    drag(wrapper, "OH2ZWA", [100, 600], [200, 400]);
    card(wrapper, "OH2ZWA").element.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", altKey: true, bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
    expect(card(wrapper, "OH2ZWA").attributes("style")).toBeUndefined();
    expect(wrapper.find(".cardstack").classes()).toContain("sheet");
  });

  it("ignores the places a desktop gave when it is a phone", async () => {
    const wrapper = make([A]);
    drag(wrapper, "OH2ZWA", [100, 600], [200, 400]);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(1);
    await wrapper.setProps({ size: "phone" });
    expect(wrapper.findAll(".card.moved")).toHaveLength(0);
    await wrapper.setProps({ size: "tablet" });
    expect(wrapper.findAll(".card.moved")).toHaveLength(1);
  });

  it("is moved on a tablet", async () => {
    const wrapper = make([A], "tablet");
    drag(wrapper, "OH2ZWA", [100, 600], [200, 400]);
    await wrapper.vm.$nextTick();
    expect(wrapper.findAll(".card.moved")).toHaveLength(1);
  });
});
