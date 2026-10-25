import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { nextTick } from "vue";
import SidePanel from "@/components/SidePanel.vue";
import { TAB_IDS, type SizeClass, type TabId } from "@/lib/layout";
import { cssRule } from "@/test/css";
import { stubWidth } from "@/test/width";

// The tabs fit when the row's scroll width (what the tabs want) is not more than the width of the bar (stubWidth: every element is that wide; the Map button's width is 0 here).
let want = 300;
Object.defineProperty(HTMLElement.prototype, "scrollWidth", { configurable: true, get: () => want });

let width: ReturnType<typeof stubWidth> | undefined;
afterEach(() => {
  width?.restore();
  width = undefined;
  document.body.replaceChildren();
});

const slots = { messages: "<p>messages pane</p>", stations: "<p>stations pane</p>" };
async function make(room: number, extra: Record<string, unknown> = {}, size: SizeClass = "tablet") {
  width = stubWidth(room);
  const wrapper = mount(SidePanel, {
    props: { tab: "messages" as TabId, collapsed: false, width: 500, size, view: "panel", ...extra },
    slots,
    attachTo: document.body,
  });
  await nextTick();
  return wrapper;
}
const button = (wrapper: Awaited<ReturnType<typeof make>>) => wrapper.find("button.tabmenu-button");
const items = (wrapper: Awaited<ReturnType<typeof make>>) => wrapper.findAll("[role='menuitem']");
const key = async (wrapper: Awaited<ReturnType<typeof make>>, target: string, name: string) => {
  await wrapper.find(target).trigger("keydown", { key: name });
};

describe("the tabs as one button when they do not fit", () => {
  it("has the row of tabs when they fit in the width of the bar, and no menu", async () => {
    want = 400;
    const wrapper = await make(400);
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    expect(wrapper.find(".tabs").classes()).not.toContain("measuring");
    expect(wrapper.find(".tabs").attributes("aria-hidden")).toBeUndefined();
    expect(wrapper.findAll("[role='tab']")).toHaveLength(9);
  });

  it("has one button with the name of the open tab when they do not, and the row is out of the way and not for a screen reader", async () => {
    want = 401;
    const wrapper = await make(400);
    expect(button(wrapper).text()).toBe("☰ Messages");
    expect(button(wrapper).classes()).toEqual(expect.arrayContaining(["tab", "active"]));
    expect(wrapper.find(".tabs").classes()).toContain("measuring");
    expect(wrapper.find(".tabs").attributes("aria-hidden")).toBe("true");
    expect(cssRule(".tabs.measuring")).toMatch(/visibility:\s*hidden/);
    expect(cssRule(".tabs.measuring")).toMatch(/width:\s*max-content/);
  });

  it("measures the width of the panel and not a breakpoint: the same panel gets either form as its width changes", async () => {
    want = 500;
    const wrapper = await make(600);
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    width?.set(480);
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".tabmenu").exists()).toBe(true);
    width?.set(520);
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
  });

  it("goes with the badges: more digits in a tab can make the row too wide", async () => {
    want = 400;
    const wrapper = await make(400);
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    want = 430;
    await wrapper.setProps({ badges: { messages: 12 } });
    await flushPromises();
    expect(wrapper.find(".tabmenu").exists()).toBe(true);
  });

  it("is as high as the row of tabs: it is a tab in a bar with the same padding", async () => {
    expect(cssRule(".tabmenu")).toMatch(/padding:\s*4px 0 0 6px/);
    expect(cssRule(".tabs")).toMatch(/padding:\s*4px 38px 0 6px/);
    want = 700;
    expect(button(await make(400)).classes()).toContain("tab");
  });

  it("shows the total of the badges on the button, and none when there is none", async () => {
    want = 700;
    const quiet = await make(400);
    expect(button(quiet).find(".badge").exists()).toBe(false);
    quiet.unmount();
    const wrapper = await make(400, { badges: { messages: 3, email: 1, bulletins: 2 } });
    expect(button(wrapper).find(".badge").text()).toBe("6");
    expect(button(wrapper).find(".sr-only").text()).toBe(", 6 new");
  });

  it("opens a menu with all the tabs in their order, each with its badge, the open one marked, and nothing before", async () => {
    want = 700;
    const wrapper = await make(400, { tab: "email", badges: { messages: 3, bulletins: 2 } });
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(button(wrapper).attributes("aria-haspopup")).toBe("menu");
    expect(button(wrapper).attributes("aria-expanded")).toBe("false");
    await button(wrapper).trigger("click");
    expect(button(wrapper).attributes("aria-expanded")).toBe("true");
    const menu = wrapper.find("[role='menu']");
    expect(menu.attributes("id")).toBe(button(wrapper).attributes("aria-controls"));
    expect(items(wrapper).map((i) => i.text())).toEqual([
      "Messages 3",
      "Stations",
      "Nearby",
      "Email",
      "Bulletins 2",
      "Objects",
      "Beacon",
      "Packets",
      "Settings",
    ]);
    expect(items(wrapper).map((i) => i.attributes("aria-current"))).toEqual([
      undefined,
      undefined,
      undefined,
      "page",
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ]);
    expect(items(wrapper)[0]?.find(".badge").attributes("title")).toBe("3 messages not seen yet");
    expect(items(wrapper)[4]?.find(".badge").attributes("title")).toBe("2 new bulletins");
  });

  it("picks a tab from the menu, which closes, and brings the panel on a phone", async () => {
    want = 700;
    const wrapper = await make(360, {}, "phone");
    await button(wrapper).trigger("click");
    await items(wrapper)[7]?.trigger("click");
    expect(wrapper.emitted("update:tab")).toEqual([["packets"]]);
    expect(wrapper.emitted("update:view")).toEqual([["panel"]]);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(document.activeElement).toBe(button(wrapper).element);
  });

  it("closes with Esc and gives the focus back to the button", async () => {
    want = 700;
    const wrapper = await make(400);
    await button(wrapper).trigger("click");
    await wrapper.vm.$nextTick();
    await key(wrapper, "[role='menu']", "Escape");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(document.activeElement).toBe(button(wrapper).element);
  });

  it("closes with a click outside, and not with one inside", async () => {
    want = 700;
    const wrapper = await make(400);
    await button(wrapper).trigger("click");
    wrapper.find("[role='menu']").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(true);
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("closes with a second click on the button", async () => {
    want = 700;
    const wrapper = await make(400);
    await button(wrapper).trigger("click");
    await button(wrapper).trigger("click");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("moves with the arrow keys, round at the ends, and with Home and End; the open tab has the focus first", async () => {
    want = 700;
    const wrapper = await make(400, { tab: "stations" });
    await button(wrapper).trigger("click");
    await wrapper.vm.$nextTick();
    await button(wrapper).trigger("keydown", { key: "ArrowDown" });
    await wrapper.vm.$nextTick();
    const focused = () => items(wrapper).findIndex((i) => i.element === document.activeElement);
    expect(focused()).toBe(1);
    await key(wrapper, "[role='menu']", "ArrowDown");
    expect(focused()).toBe(2);
    await key(wrapper, "[role='menu']", "ArrowUp");
    await key(wrapper, "[role='menu']", "ArrowUp");
    expect(focused()).toBe(0);
    await key(wrapper, "[role='menu']", "ArrowUp");
    expect(focused()).toBe(8);
    await key(wrapper, "[role='menu']", "ArrowDown");
    expect(focused()).toBe(0);
    await key(wrapper, "[role='menu']", "End");
    expect(focused()).toBe(8);
    await key(wrapper, "[role='menu']", "Home");
    expect(focused()).toBe(0);
  });

  it("opens from the keyboard on the last tab with Up, and on the open one with Down", async () => {
    want = 700;
    const wrapper = await make(400, { tab: "email" });
    await button(wrapper).trigger("keydown", { key: "ArrowUp" });
    await wrapper.vm.$nextTick();
    expect(items(wrapper).findIndex((i) => i.element === document.activeElement)).toBe(8);
  });

  it("keeps the Map button of a phone beside the menu button, and it asks for the map", async () => {
    want = 700;
    const wrapper = await make(360, {}, "phone");
    expect(wrapper.find(".tab-map").exists()).toBe(true);
    expect(wrapper.find(".tab-map").element.nextElementSibling).toBe(wrapper.find(".tabmenu").element);
    await wrapper.find(".tab-map").trigger("click");
    expect(wrapper.emitted("update:view")).toEqual([["map"]]);
  });

  it("leaves the menu button without the active mark while the map has the turn on a phone", async () => {
    want = 700;
    const wrapper = await make(360, { view: "map" }, "phone");
    expect(button(wrapper).classes()).not.toContain("active");
    expect(wrapper.find(".tab-map").classes()).toContain("active");
  });

  it("has the room of the Map button taken from the bar", async () => {
    want = 360;
    const wrapper = await make(380, {}, "phone");
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    wrapper.unmount();
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 40 });
    try {
      const narrow = await make(380, {}, "phone");
      expect(narrow.find(".tabmenu").exists()).toBe(true); // 380 - 40 - 6 = 334 < 360
    } finally {
      Reflect.deleteProperty(HTMLElement.prototype, "offsetWidth");
    }
  });

  it("closes the menu when the tabs fit again", async () => {
    want = 500;
    const wrapper = await make(400);
    await button(wrapper).trigger("click");
    width?.set(600);
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("lists every tab the panel has", async () => {
    want = 700;
    const wrapper = await make(400);
    await button(wrapper).trigger("click");
    expect(items(wrapper)).toHaveLength(TAB_IDS.length);
  });
});
