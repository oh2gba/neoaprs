import { cssRule } from "@/test/css";
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import InfoTip from "@/components/InfoTip.vue";
import { openTip } from "@/lib/infotip";

const mounted: ReturnType<typeof mount>[] = [];

function tip(props: { label?: string } = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const wrapper = mount(InfoTip, {
    props: { label: "About DAO", ...props },
    slots: { default: '<span class="info-line">One more digit of the position.</span><span class="info-line">Example: !W41!</span>' },
    attachTo: host,
  });
  mounted.push(wrapper);
  return wrapper;
}

/** A page `width` wide in which the (i) has its left edge at `left` and the open note is `box` wide. */
function layout(width: number, left: number, box: number): void {
  Object.defineProperty(document.documentElement, "clientWidth", { value: width, configurable: true });
  Object.defineProperty(document.documentElement, "clientHeight", { value: 800, configurable: true });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const note = this.classList.contains("info-text");
    const at = note ? 0 : left;
    const w = note ? box : 20;
    return { left: at, right: at + w, top: 100, bottom: 120, width: w, height: 20, x: at, y: 100, toJSON: () => ({}) };
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
  openTip.value = null;
});

describe("InfoTip", () => {
  it("is a small (i) button that names the field it is about, with its note closed", () => {
    const wrapper = tip();
    const button = wrapper.find("button");
    expect(button.text()).toBe("i");
    expect(button.attributes("aria-label")).toBe("About DAO");
    expect(button.attributes("aria-expanded")).toBe("false");
    expect(button.attributes("type")).toBe("button");
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("opens the note on a click or a tap, with its lines, and closes it on the next", async () => {
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    expect(wrapper.find("button").attributes("aria-expanded")).toBe("true");
    const note = wrapper.find(".info-text");
    expect(note.findAll(".info-line").map((l) => l.text())).toEqual(["One more digit of the position.", "Example: !W41!"]);
    expect(wrapper.find("button").attributes("aria-controls")).toBe(note.attributes("id"));
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("shows any markup put in its slot, so that master's bulletin note and the settings' notes are one thing", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const wrapper = mount(InfoTip, { props: { label: "What the kinds are" }, slots: { default: "A bulletin is <b>for everyone</b>." }, attachTo: host });
    mounted.push(wrapper);
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".info-text").text()).toBe("A bulletin is for everyone.");
    expect(wrapper.find("b").exists()).toBe(true);
  });

  it("shows a picture under the text when it is given one, with its description for a screen reader, in a wider note", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const wrapper = mount(InfoTip, {
      props: { label: "About the path", picture: "path" },
      slots: { default: '<span class="info-line">Two hops.</span>' },
      attachTo: host,
    });
    mounted.push(wrapper);
    await wrapper.find("button").trigger("click");
    const note = wrapper.find(".info-text");
    expect(note.classes()).toContain("with-picture");
    expect(note.find(".info-line").text()).toBe("Two hops.");
    const picture = note.find("svg[role='img']");
    expect(picture.attributes("data-picture")).toBe("path");
    expect(picture.attributes("aria-label")).toMatch(/WIDE1-1/);
    expect(note.element.lastElementChild).toBe(picture.element);
  });

  it("has no picture and the plain width without one", async () => {
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    expect(wrapper.find(".info-text").classes()).not.toContain("with-picture");
    expect(wrapper.find("svg").exists()).toBe(false);
  });

  it("closes on Esc and gives the focus back to the button", async () => {
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").exists()).toBe(false);
    expect(document.activeElement).toBe(wrapper.find("button").element);
  });

  it("stays open for other keys and for a click inside the note, and closes on a click or tap outside", async () => {
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    wrapper.find(".info-text").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").exists()).toBe(true);
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("closes when the focus moves to something else, as Tab does", async () => {
    const wrapper = tip();
    const other = document.createElement("button");
    document.body.appendChild(other);
    await wrapper.find("button").trigger("click");
    other.dispatchEvent(new Event("focusin", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").exists()).toBe(false);
  });

  it("is the only note open: opening another closes the first", async () => {
    const first = tip({ label: "About Path" });
    const second = tip({ label: "DAO" });
    await first.find("button").trigger("click");
    await second.find("button").trigger("click");
    expect(first.find(".info-text").exists()).toBe(false);
    expect(second.find(".info-text").exists()).toBe(true);
  });

  it("lets go of the page's listeners when it goes away", async () => {
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    wrapper.unmount();
    mounted.length = 0;
    expect(openTip.value).toBeNull();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });

  it("opens under the (i), fixed in the window, with its right edge at the (i)'s, moved left where that runs off the right edge", async () => {
    layout(390, 370, 280);
    const wrapper = tip();
    await wrapper.find("button").trigger("click");
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    const style = wrapper.find<HTMLElement>(".info-text").element.style;
    expect([style.left, style.top, style.width]).toEqual(["102px", "124px", "280px"]); // its right edge at 382 = 390 - 8
    expect(cssRule(".info-text")).toMatch(/position:\s*fixed/);
    expect(Number(/z-index:\s*(\d+)/.exec(cssRule(".info-text"))?.[1])).toBeGreaterThan(10);
  });

  it("stays by the (i) when it fits, and never goes past the left margin, for an (i) in the left column of the panel", async () => {
    layout(1000, 500, 280);
    const roomy = tip();
    await roomy.find("button").trigger("click");
    await roomy.vm.$nextTick();
    await roomy.vm.$nextTick();
    expect(roomy.find<HTMLElement>(".info-text").element.style.left).toBe("240px");
    await roomy.find("button").trigger("click");
    layout(1000, 0, 280);
    await roomy.find("button").trigger("click");
    await roomy.vm.$nextTick();
    await roomy.vm.$nextTick();
    expect(roomy.find<HTMLElement>(".info-text").element.style.left).toBe("8px");
  });
});
