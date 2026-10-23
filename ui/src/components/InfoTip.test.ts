import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import InfoTip from "@/components/InfoTip.vue";

/** A page `width` wide, the (i) at `left`, and a box `box` wide. */
function layout(width: number, left: number, box: number): void {
  Object.defineProperty(document.documentElement, "clientWidth", { value: width, configurable: true });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    left,
    right: left + 20,
    top: 0,
    bottom: 20,
    width: 20,
    height: 20,
    x: left,
    y: 0,
    toJSON: () => ({}),
  });
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(box);
}

const tip = () => mount(InfoTip, { props: { label: "What it is" }, slots: { default: "A few words." }, attachTo: document.body });
const leftOf = (wrapper: ReturnType<typeof tip>) => wrapper.find<HTMLElement>(".info-text").element.style.left;

async function show(wrapper: ReturnType<typeof tip>): Promise<void> {
  await wrapper.find("button").trigger("click");
  await wrapper.vm.$nextTick();
}

describe("InfoTip", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("is closed until it is pressed, and then shows its words under the (i)", async () => {
    const wrapper = tip();
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await show(wrapper);
    expect(wrapper.find(".info-text").text()).toBe("A few words.");
    expect(wrapper.find("button").attributes("aria-expanded")).toBe("true");
    wrapper.unmount();
  });

  it("is kept inside the page: moved left where it would run off the right edge", async () => {
    layout(390, 300, 280);
    const wrapper = tip();
    await show(wrapper);
    expect(leftOf(wrapper)).toBe("-198px"); // the right edge of the box is at 382 = 390 - 8
    wrapper.unmount();
  });

  it("stays at the (i) when it fits, and never goes past the left margin", async () => {
    layout(1000, 100, 280);
    const roomy = tip();
    await show(roomy);
    expect(leftOf(roomy)).toBe("0px");
    roomy.unmount();
    layout(200, 10, 280);
    const narrow = tip();
    await show(narrow);
    expect(leftOf(narrow)).toBe("-2px"); // the left edge of the box is at 8
    narrow.unmount();
  });

  it("closes with Escape, with the (i) again and with a press anywhere else, but not with one inside", async () => {
    const wrapper = tip();
    await show(wrapper);
    await wrapper.find("button").trigger("keydown", { key: "Escape" });
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await show(wrapper);
    await show(wrapper);
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await show(wrapper);
    await wrapper.find(".info-text").trigger("pointerdown");
    expect(wrapper.find(".info-text").exists()).toBe(true);
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".info-text").exists()).toBe(false);
    wrapper.unmount();
  });
});
