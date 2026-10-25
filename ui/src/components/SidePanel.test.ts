import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import SidePanel from "@/components/SidePanel.vue";
import { cssRule } from "@/test/css";

const slots = {
  stations: "<p>stations pane</p>",
  nearby: "<p>nearby pane</p>",
  packets: "<p>packets pane</p>",
  messages: "<p>messages pane</p>",
  email: "<p>email pane</p>",
  bulletins: "<p>bulletins pane</p>",
  beacon: "<p>beacon pane</p>",
  settings: "<p>settings pane</p>",
};

const innerWidth = window.innerWidth;
afterEach(() => {
  window.innerWidth = innerWidth;
});

describe("SidePanel", () => {
  it("keeps the tab bar to one row that scrolls sideways when the tabs do not fit, and no tab changes its width when it is picked", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    expect(wrapper.find("[role='tablist']").classes()).toContain("tabs");
    expect(cssRule(".tabs")).toMatch(/flex-wrap:\s*nowrap/);
    expect(cssRule(".tabs")).toMatch(/overflow-x:\s*auto/);
    expect(cssRule(".tab")).toMatch(/flex:\s*none/);
    expect(cssRule(".tab")).toMatch(/white-space:\s*nowrap/);
    expect(cssRule(".tab.active")).not.toMatch(/font-weight|padding|width/);
  });

  it("scrolls the tab that was picked into view, also when the page picked it", async () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots, attachTo: document.body });
    const into = vi.fn();
    for (const tab of wrapper.findAll("[role='tab']")) tab.element.scrollIntoView = into;
    await wrapper.setProps({ tab: "settings" });
    await wrapper.vm.$nextTick();
    expect(into).toHaveBeenCalledExactlyOnceWith({ block: "nearest", inline: "nearest" });
    expect(into.mock.contexts[0]).toBe(wrapper.find("#tab-settings").element);
    wrapper.unmount();
  });

  it("turns the wheel of a mouse over the tab bar into a sideways scroll while the tabs do not fit", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    const bar = wrapper.find("[role='tablist']").element;
    Object.defineProperty(bar, "scrollWidth", { value: 700, configurable: true });
    Object.defineProperty(bar, "clientWidth", { value: 400, configurable: true });
    const event = new WheelEvent("wheel", { deltaY: 90, cancelable: true });
    bar.dispatchEvent(event);
    expect(bar.scrollLeft).toBe(90);
    expect(event.defaultPrevented).toBe(true);
    Object.defineProperty(bar, "scrollWidth", { value: 300, configurable: true });
    const spare = new WheelEvent("wheel", { deltaY: 90, cancelable: true });
    bar.dispatchEvent(spare);
    expect(spare.defaultPrevented).toBe(false);
  });

  it("has the nine tabs, the chosen one selected, and shows its pane only", () => {
    const wrapper = mount(SidePanel, { props: { tab: "packets", collapsed: false, width: 400 }, slots });
    expect(wrapper.findAll("[role='tab']").map((t) => t.text())).toEqual([
      "Messages",
      "Stations",
      "Nearby",
      "Email",
      "Bulletins",
      "Objects",
      "Beacon",
      "Packets",
      "Settings",
    ]);
    expect(wrapper.find("[aria-selected='true']").text()).toBe("Packets");
    const visible = wrapper.findAll("[role='tabpanel']").filter((p) => (p.element as HTMLElement).style.display !== "none");
    expect(visible.map((p) => p.text())).toEqual(["packets pane"]);
  });

  it("keeps every pane mounted", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    expect(wrapper.text()).toContain("settings pane");
  });

  it("says which tab was picked", async () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    await wrapper.findAll("[role='tab']")[8]?.trigger("click");
    expect(wrapper.emitted("update:tab")).toEqual([["settings"]]);
  });

  it("shows the count of a tab that has one in a badge, and none for zero or for a tab without", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400, badges: { messages: 3, packets: 0 } }, slots });
    const tabs = wrapper.findAll("[role='tab']");
    expect(tabs.map((t) => t.find(".badge").exists())).toEqual([true, false, false, false, false, false, false, false, false]);
    expect(tabs[0]?.find(".badge").text()).toBe("3");
    expect(tabs[0]?.text()).toBe("Messages 3");
    expect(tabs[0]?.find(".badge").attributes("title")).toBe("3 messages not seen yet");
  });

  it("counts the messages of the Email tab as messages not seen", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400, badges: { email: 1 } }, slots });
    const badge = wrapper.findAll("[role='tab']")[3]?.find(".badge");
    expect([badge?.text(), badge?.attributes("title")]).toEqual(["1", "1 message not seen yet"]);
  });

  it("words the badge of the Bulletins tab as the bulletins that are new", () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400, badges: { bulletins: 2 } }, slots });
    const badge = wrapper.findAll("[role='tab']")[4]?.find(".badge");
    expect([badge?.text(), badge?.attributes("title")]).toEqual(["2", "2 new bulletins"]);
  });

  it("folds away and back", async () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    await wrapper.find(".panel-fold").trigger("click");
    expect(wrapper.emitted("update:collapsed")).toEqual([[true]]);
    await wrapper.setProps({ collapsed: true });
    expect(wrapper.find(".panel").classes()).toContain("collapsed");
    expect(wrapper.find("[role='tab']").exists()).toBe(false);
    await wrapper.find(".panel-fold").trigger("click");
    expect(wrapper.emitted("update:collapsed")?.[1]).toEqual([false]);
  });

  it("has the width it is given, and changes it with the arrow keys", async () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 400 }, slots });
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 400px");
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.emitted("update:width")?.[0]?.[0]).toBeGreaterThan(400);
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.emitted("update:width")?.[1]?.[0]).toBeLessThan(400);
  });

  it("shows the messages not seen on the handle while it is folded (those of the Messages and the Email tab, not the new bulletins), and nothing when they are zero", async () => {
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: true, width: 400, badges: { messages: 3, email: 1, bulletins: 5 } }, slots });
    expect(wrapper.find(".fold-badge").text()).toBe("4");
    expect(wrapper.find(".fold-badge").attributes("title")).toBe("4 messages not seen yet");
    expect(wrapper.find(".panel-fold").text()).toContain("4 messages not seen yet");
    await wrapper.setProps({ badges: { messages: 0, bulletins: 2 } });
    expect(wrapper.find(".fold-badge").exists()).toBe(false);
    await wrapper.setProps({ badges: { messages: 0 } });
    expect(wrapper.find(".fold-badge").exists()).toBe(false);
    await wrapper.setProps({ badges: { messages: 3 }, collapsed: false });
    expect(wrapper.find(".fold-badge").exists()).toBe(false);
  });

  it("shows a remembered width clamped to what the window allows, and the whole width again when the window is wide", async () => {
    window.innerWidth = 1000;
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 900 }, slots });
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 640px");
    window.innerWidth = 700;
    window.dispatchEvent(new Event("resize"));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 340px");
    window.innerWidth = 2000;
    window.dispatchEvent(new Event("resize"));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".panel").attributes("style")).toContain("--panel-width: 900px");
    wrapper.unmount();
  });

  it("does not ask for more than 80 % of the window, nor for less than 360 px of map, with the arrow keys", async () => {
    window.innerWidth = 1000;
    const wrapper = mount(SidePanel, { props: { tab: "stations", collapsed: false, width: 630 }, slots });
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.emitted("update:width")?.[0]).toEqual([640]);
    window.innerWidth = 3000;
    window.dispatchEvent(new Event("resize"));
    await wrapper.setProps({ width: 2390 });
    await wrapper.find("[role='separator']").trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.emitted("update:width")?.[1]).toEqual([2400]);
    wrapper.unmount();
  });
});
