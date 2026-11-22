import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import SidePanel from "@/components/SidePanel.vue";
import { TAB_IDS, type SizeClass, type TabId } from "@/lib/layout";
import { t } from "@/i18n";
import { cssRule } from "@/test/css";
import { fakeDaemon, tell, withDaemon, type FakeDaemon } from "@/test/context";
import { configValues, radioRow, radiosTopic } from "@/test/fixtures";
import { stubWidth } from "@/test/width";

// Fake measurements: the width of what the probe holds (the tabs, the More button, and the More
// button with a count; jsdom lays nothing out) and, by stubWidth, the width of the bar. The tabs
// add up to 580 px, the More button is 50 px and 74 with a count; the room is the bar's width less
// the 1 px the page keeps back (and a phone's Map button, whose offsetWidth is 0 here unless a test
// says otherwise).
const TABS: Record<TabId, number> = {
  messages: 80,
  stations: 70,
  nearby: 60,
  email: 50,
  bulletins: 70,
  skeds: 50,
  objects: 50,
  beacon: 50,
  packets: 50,
  settings: 50,
};
const originalRect = Element.prototype.getBoundingClientRect;
const WIDTHS = { ...TABS };
beforeEach(() => {
  Object.assign(TABS, WIDTHS);
  Element.prototype.getBoundingClientRect = function (this: Element): DOMRect {
    const data = (this as HTMLElement).dataset;
    const width = data.tab ? TABS[data.tab as TabId] : "more" in data ? 50 : "moreCount" in data ? 74 : 0;
    return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON: () => ({}) };
  };
});

let width: ReturnType<typeof stubWidth> | undefined;
afterEach(() => {
  Element.prototype.getBoundingClientRect = originalRect;
  width?.restore();
  width = undefined;
  document.body.replaceChildren();
});

type Wrapper = Awaited<ReturnType<typeof make>>;
/** The radios of a station with the HF radio on beside the FM radio. */
const WITH_HF = () => radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"));
const slots = { messages: "<p>messages pane</p>", stations: "<p>stations pane</p>" };
/**
 * The panel of a station with the HF radio on, which has all ten tabs (without one, "the HF tests
 * tab" below).
 */
async function make(room: number, extra: Record<string, unknown> = {}, size: SizeClass = "tablet") {
  width = stubWidth(room);
  const wrapper = mount(SidePanel, {
    props: { tab: "messages" as TabId, collapsed: false, width: 500, size, view: "panel", ...extra },
    slots,
    attachTo: document.body,
    global: withDaemon(fakeDaemon({ radios: WITH_HF() })),
  });
  await nextTick();
  return wrapper;
}
const button = (wrapper: Wrapper) => wrapper.find("button.tabmenu-button");
const items = (wrapper: Wrapper) => wrapper.findAll("[role='menuitem']");
const row = (wrapper: Wrapper) => wrapper.findAll("[role='tab']").map((tab) => tab.attributes("id")?.replace("tab-", ""));
const listed = (wrapper: Wrapper) => items(wrapper).map((item) => item.text().replace(/\s*\d+$/, ""));
const key = async (wrapper: Wrapper, target: string, name: string) => {
  await wrapper.find(target).trigger("keydown", { key: name });
};
const opened = async (wrapper: Wrapper) => {
  await button(wrapper).trigger("click");
  await nextTick();
};

describe("the tabs in a row, and the ones that do not fit under More", () => {
  it("has all ten in the row when they fit, to the pixel, and no More button", async () => {
    const wrapper = await make(581);
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    expect(row(wrapper)).toEqual([...TAB_IDS]);
    const fewer = await make(580);
    expect(fewer.find(".tabmenu").exists()).toBe(true);
  });

  it("has the first tabs that fit, in order, and the More button at the end of the row, when they do not", async () => {
    const wrapper = await make(400);
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 5));
    expect(button(wrapper).text()).toBe("More ▾");
    expect(wrapper.find(".tabbar").element.lastElementChild).toBe(wrapper.find(".tabs-probe").element);
    expect(wrapper.find(".tabs").element.nextElementSibling).toBe(wrapper.find(".tabmenu").element);
    expect(button(wrapper).classes()).toEqual(expect.arrayContaining(["tab", "tabmenu-button"]));
    expect(button(wrapper).classes()).not.toContain("active");
  });

  it("keeps a copy of the tabs out of the way to measure, for no one: not read out, not reached, not clicked", async () => {
    const wrapper = await make(400);
    const probe = wrapper.find(".tabs-probe");
    expect(probe.attributes("aria-hidden")).toBe("true");
    expect(probe.attributes("inert")).toBeDefined();
    expect(probe.findAll("[data-tab]")).toHaveLength(TAB_IDS.length);
    expect(probe.find("[role='tab']").exists()).toBe(false);
    expect(probe.find("button").exists()).toBe(false);
    expect(cssRule(".tabs-probe")).toMatch(/visibility:\s*hidden/);
    expect(cssRule(".tabs-probe")).toMatch(/width:\s*max-content/);
    // fixed, not absolute: a row wider than the window must add nothing to the page's width, or the
    // page can be scrolled sideways under its hidden overflow
    expect(cssRule(".tabs-probe")).toMatch(/position:\s*fixed/);
  });

  it("measures the width of the panel and not a breakpoint: the same panel keeps more tabs as it gets wider", async () => {
    const wrapper = await make(300);
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 3));
    width?.set(400);
    await nextTick();
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 5));
    width?.set(700);
    await nextTick();
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    expect(row(wrapper)).toHaveLength(10);
    width?.set(250);
    await nextTick();
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 2));
  });

  it("goes with the badges: more digits in a tab take room, and one tab goes under More", async () => {
    const wrapper = await make(591);
    expect(row(wrapper)).toHaveLength(10);
    TABS.messages = 110;
    await wrapper.setProps({ badges: { messages: 12 } });
    await flushPromises();
    // 610 is more than 590: 540 for the tabs and the More button takes 50
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 8));
  });

  it("has the More button in a bar with the padding of the tabs, so that the bar is as high with it as without", () => {
    expect(cssRule(".tabbar")).toMatch(/padding:\s*4px 38px 0 6px/);
    expect(cssRule(".tabs")).not.toMatch(/padding/);
    expect(cssRule(".tabmenu")).not.toMatch(/padding/);
  });
});

describe("the tab on show", () => {
  it("is in the row in the place of the last tab, when it would be under More, and the menu holds the one it displaced", async () => {
    const wrapper = await make(400, { tab: "packets" });
    expect(row(wrapper)).toEqual(["messages", "stations", "nearby", "email", "packets"]);
    expect(wrapper.find("#tab-packets").attributes("aria-selected")).toBe("true");
    expect(wrapper.find("#tab-packets").classes()).toContain("active");
    expect(button(wrapper).classes()).not.toContain("active");
    await opened(wrapper);
    expect(listed(wrapper)).toEqual(["Bulletins", "HF tests", "Objects", "My station", "Settings"]);
  });

  it("is brought into the row when it is picked from the menu, the row keeping its order otherwise", async () => {
    const wrapper = await make(400);
    await opened(wrapper);
    await items(wrapper)[4]?.trigger("click"); // Settings
    expect(wrapper.emitted("update:tab")).toEqual([["settings"]]);
    await wrapper.setProps({ tab: "settings" });
    expect(row(wrapper)).toEqual(["messages", "stations", "nearby", "email", "settings"]);
    expect(wrapper.find("#tab-settings").attributes("aria-selected")).toBe("true");
    await wrapper.setProps({ tab: "stations" });
    expect(row(wrapper)).toEqual(TAB_IDS.slice(0, 5)); // back in the place it has by its importance
  });

  it("is in the row even where there is room for it alone", async () => {
    const wrapper = await make(120, { tab: "settings" });
    expect(row(wrapper)).toEqual(["settings"]);
  });
});

describe("the More button", () => {
  it("has the badges of the tabs under it added up, and none when they have none", async () => {
    const quiet = await make(400, { badges: { messages: 3, email: 1, bulletins: 2 } });
    expect(button(quiet).find(".badge").exists()).toBe(false); // the three are in the row
    quiet.unmount();
    const wrapper = await make(300, { badges: { messages: 3, email: 1, bulletins: 2 } });
    expect(row(wrapper)).toEqual(["messages", "stations", "nearby"]);
    expect(button(wrapper).find(".badge").text()).toBe("3");
    expect(button(wrapper).find(".sr-only").text()).toBe(", 3 new");
  });

  it("opens a menu of the tabs that are not in the row, in their order, each with its badge, and nothing before", async () => {
    const wrapper = await make(300, { badges: { messages: 3, bulletins: 2 } });
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(button(wrapper).attributes("aria-haspopup")).toBe("menu");
    expect(button(wrapper).attributes("aria-expanded")).toBe("false");
    await opened(wrapper);
    expect(button(wrapper).attributes("aria-expanded")).toBe("true");
    expect(wrapper.find("[role='menu']").attributes("id")).toBe(button(wrapper).attributes("aria-controls"));
    expect(items(wrapper).map((i) => i.text())).toEqual(["Email", "Bulletins 2", "HF tests", "Objects", "My station", "Packets", "Settings"]);
    expect(items(wrapper)[1]?.find(".badge").attributes("title")).toBe("2 new bulletins");
    expect(items(wrapper).some((i) => i.attributes("aria-current"))).toBe(false);
  });

  it("picks a tab from the menu, which closes and gives the focus back to the button, and brings the panel on a phone", async () => {
    const wrapper = await make(360, {}, "phone");
    await opened(wrapper);
    await items(wrapper).at(-2)?.trigger("click");
    expect(wrapper.emitted("update:tab")).toEqual([["packets"]]);
    expect(wrapper.emitted("update:view")).toEqual([["panel"]]);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(document.activeElement).toBe(button(wrapper).element);
  });

  it("closes with Esc and gives the focus back to the button", async () => {
    const wrapper = await make(400);
    await opened(wrapper);
    await key(wrapper, "[role='menu']", "Escape");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(document.activeElement).toBe(button(wrapper).element);
  });

  it("closes with Esc also when it was opened with the mouse, the focus on the button or on the page, and leaves the Esc to nothing else", async () => {
    const wrapper = await make(400);
    const after = vi.fn();
    document.addEventListener("keydown", after);
    await button(wrapper).trigger("click");
    expect(wrapper.find("[role='menu']").exists()).toBe(true);
    await button(wrapper).trigger("keydown", { key: "Escape" });
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(document.activeElement).toBe(button(wrapper).element);
    await button(wrapper).trigger("click");
    (document.activeElement as HTMLElement).blur();
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    await nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
    expect(event.defaultPrevented).toBe(true);
    expect(after).not.toHaveBeenCalled();
    document.removeEventListener("keydown", after);
  });

  it("closes with a click outside, and not with one inside", async () => {
    const wrapper = await make(400);
    await opened(wrapper);
    wrapper.find("[role='menu']").element.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(true);
    document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    await nextTick();
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("closes with a second click on the button", async () => {
    const wrapper = await make(400);
    await opened(wrapper);
    await button(wrapper).trigger("click");
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });

  it("opens from the keyboard on its first item with Down and on its last with Up, and moves with the arrows, round at the ends, and with Home and End", async () => {
    const wrapper = await make(400);
    const focused = () => items(wrapper).findIndex((i) => i.element === document.activeElement);
    await button(wrapper).trigger("keydown", { key: "ArrowDown" });
    await nextTick();
    expect(items(wrapper)).toHaveLength(5);
    expect(focused()).toBe(0);
    await key(wrapper, "[role='menu']", "ArrowDown");
    expect(focused()).toBe(1);
    await key(wrapper, "[role='menu']", "ArrowUp");
    await key(wrapper, "[role='menu']", "ArrowUp");
    expect(focused()).toBe(4);
    await key(wrapper, "[role='menu']", "ArrowDown");
    expect(focused()).toBe(0);
    await key(wrapper, "[role='menu']", "End");
    expect(focused()).toBe(4);
    await key(wrapper, "[role='menu']", "Home");
    expect(focused()).toBe(0);
    await key(wrapper, "[role='menu']", "Escape");
    await button(wrapper).trigger("keydown", { key: "ArrowUp" });
    await nextTick();
    expect(focused()).toBe(4);
  });

  it("picks the focused item with Enter, as a button does", async () => {
    const wrapper = await make(400);
    await button(wrapper).trigger("keydown", { key: "ArrowDown" });
    await nextTick();
    (document.activeElement as HTMLElement).click(); // (a browser clicks the focused button on Enter)
    expect(wrapper.emitted("update:tab")).toEqual([["skeds"]]);
  });

  it("is gone, with its menu, when the tabs fit again", async () => {
    const wrapper = await make(400);
    await opened(wrapper);
    width?.set(700);
    await nextTick();
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    expect(wrapper.find("[role='menu']").exists()).toBe(false);
  });
});

describe("on a phone", () => {
  it("has the Map button first, then the tabs that fit in what it leaves, then More, the same split as everywhere", async () => {
    const wrapper = await make(300, {}, "phone");
    const bar = wrapper.find(".tabbar").element;
    expect(bar.firstElementChild).toBe(wrapper.find(".tab-map").element);
    expect(wrapper.find(".tab-map").element.nextElementSibling).toBe(wrapper.find(".tabs").element);
    expect(row(wrapper)).toEqual(["messages", "stations", "nearby"]);
    expect(wrapper.find(".tabs").element.nextElementSibling).toBe(wrapper.find(".tabmenu").element);
    await wrapper.find(".tab-map").trigger("click");
    expect(wrapper.emitted("update:view")).toEqual([["map"]]);
  });

  it("has the room of the Map button taken from the bar", async () => {
    const wrapper = await make(587, {}, "phone"); // (581 and the 6 px of margin of the Map button)
    expect(wrapper.find(".tabmenu").exists()).toBe(false);
    wrapper.unmount();
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetWidth");
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 40 });
    try {
      const narrow = await make(587, {}, "phone");
      expect(narrow.find(".tabmenu").exists()).toBe(true); // 587 - 40 - 6 - 1 = 540 < 580
      // 540 - 50 = 490: 80 + 70 + 60 + 50 + 70 + 50 + 50 + 50 = 480, the packets make 530
      expect(row(narrow)).toEqual(TAB_IDS.slice(0, 8));
    } finally {
      if (original) Object.defineProperty(HTMLElement.prototype, "offsetWidth", original);
    }
  });

  it("has no tab on show while the map has the turn, and the Map button is the one that is active; the tab is still kept in the row", async () => {
    const wrapper = await make(300, { view: "map", tab: "packets" }, "phone");
    expect(wrapper.find(".tab-map").classes()).toContain("active");
    expect(wrapper.findAll("[role='tab'][aria-selected='true']")).toHaveLength(0);
    expect(row(wrapper)).toContain("packets");
    expect(button(wrapper).classes()).not.toContain("active");
  });

  it("keeps the bar's padding the same on the right as on the left, there being no fold button", () => {
    expect(cssRule(".size-phone .tabbar")).toMatch(/padding-right:\s*6px/);
  });
});

describe("the HF tests tab, only while a radio of the kind Mercury is on", () => {
  async function within(daemon: FakeDaemon, room: number, extra: Record<string, unknown> = {}) {
    width = stubWidth(room);
    const wrapper = mount(SidePanel, {
      props: { tab: "messages" as TabId, collapsed: false, width: 500, size: "tablet" as SizeClass, view: "panel", ...extra },
      slots,
      attachTo: document.body,
      global: withDaemon(daemon),
    });
    await nextTick();
    return wrapper;
  }
  const fmAlone = () => fakeDaemon();
  const withHf = () => fakeDaemon({ radios: WITH_HF() });
  const NINE = TAB_IDS.filter((id) => id !== "skeds");

  it("is not there for a station without a Mercury radio: one tab less, in the row and under More", async () => {
    const wide = await within(fmAlone(), 1000);
    expect(row(wide)).toEqual(NINE);
    const narrow = await within(fmAlone(), 300);
    await opened(narrow);
    expect([...row(narrow), ...listed(narrow).map((name) => TAB_IDS.find((id) => t(`tab.${id}`) === name))]).toEqual(NINE);
  });

  it("is there while the Mercury radio is on, and while a third radio of the kind Mercury is on with the Mercury radio of before off", async () => {
    expect(row(await within(withHf(), 1000))).toEqual([...TAB_IDS]);
    const third = fakeDaemon({
      radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" }), radioRow(4, "dummy-hf", { number: 2 })),
    });
    expect(row(await within(third, 1000))).toEqual([...TAB_IDS]);
  });

  it("is not offered until the daemon has told its radios, so that the row of a station without Mercury does not lose a tab when they come", async () => {
    const early = fakeDaemon({ radios: null, config: null });
    const wrapper = await within(early, 1000);
    expect(row(wrapper)).toEqual(NINE);
    await tell(early, { config: configValues() });
    await tell(early, { radios: radiosTopic(radioRow(1, "kenwood-tnc2")) });
    expect(row(wrapper)).toEqual(NINE);
    const hf = fakeDaemon({ radios: null });
    const later = await within(hf, 1000);
    expect(row(later)).toEqual(NINE);
    await tell(hf, { radios: WITH_HF() });
    expect(row(later)).toEqual([...TAB_IDS]);
  });

  it("keeps a remembered HF tests tab in its place until the daemon has told its radios, and gives way then if no Mercury radio is on", async () => {
    const early = fakeDaemon({ radios: null, config: null });
    const wrapper = await within(early, 1000, { tab: "skeds" });
    expect([row(wrapper), wrapper.emitted("update:tab")]).toEqual([[...TAB_IDS], undefined]);
    await tell(early, { radios: radiosTopic(radioRow(1, "kenwood-tnc2")), config: configValues() });
    expect(wrapper.emitted("update:tab")).toEqual([["messages"]]);
    const hf = fakeDaemon({ radios: null, config: null });
    const kept = await within(hf, 1000, { tab: "skeds" });
    await tell(hf, { radios: WITH_HF(), config: configValues() });
    expect([row(kept), kept.emitted("update:tab")]).toEqual([[...TAB_IDS], undefined]);
  });

  it("is measured out of the split as before: nine tabs that fit need no More button where ten did", async () => {
    // (the ten add up to 580 px, the nine to 530: in 540 px the ten need More, the nine fit,
    // Settings stays in the row)
    expect(button(await within(withHf(), 541)).exists()).toBe(true);
    const nine = await within(fmAlone(), 541);
    expect(button(nine).exists()).toBe(false);
    expect(row(nine)).toEqual(NINE);
  });

  it("gives way to the first tab when it was the tab remembered, and when the Mercury radio is switched off while it is open", async () => {
    const remembered = await within(fmAlone(), 1000, { tab: "skeds" });
    expect(remembered.emitted("update:tab")).toEqual([["messages"]]);
    const daemon = withHf();
    const open = await within(daemon, 1000, { tab: "skeds" });
    expect(open.emitted("update:tab")).toBeUndefined();
    await tell(daemon, { radios: radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" })) });
    expect(open.emitted("update:tab")).toEqual([["messages"]]);
    expect(row(open)).not.toContain("skeds");
  });

  it("counts on the More button only the badges of the tabs offered", async () => {
    const wrapper = await within(fmAlone(), 300, { badges: { skeds: 123, messages: 2 } });
    expect(wrapper.find("[data-more-count] .badge").text()).toBe("8");
  });
});
