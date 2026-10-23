import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MapPickBar from "@/components/MapPickBar.vue";
import SidePanel from "@/components/SidePanel.vue";
import type { SizeClass } from "@/lib/layout";
import { cssRule, mediaRule } from "@/test/css";

const slots = { stations: "<p>stations pane</p>", packets: "<p>packets pane</p>", messages: "<p>messages pane</p>", settings: "<p>settings pane</p>" };
function make(size: SizeClass, extra: Record<string, unknown> = {}) {
  return mount(SidePanel, { props: { tab: "packets", collapsed: false, width: 500, size, view: "panel", ...extra }, slots });
}
const visible = (wrapper: ReturnType<typeof make>) =>
  wrapper.findAll("[role='tabpanel']").filter((p) => p.attributes("style") === undefined || !p.attributes("style")?.includes("none"));

describe("SidePanel on a phone", () => {
  it("begins the tab bar with a Map button, which asks for the map and has no tab's place", async () => {
    const wrapper = make("phone");
    const map = wrapper.find(".tab-map");
    expect(map.text()).toBe("Map");
    expect(wrapper.find(".tabs .tab-map").exists()).toBe(false); // (outside the tab list: it is not one of its tabs)
    expect(map.attributes("aria-pressed")).toBe("false");
    await map.trigger("click");
    expect(wrapper.emitted("update:view")).toEqual([["map"]]);
  });

  it("shows the open tab alone in its turn, and none while the map has the turn, the Map button marked", async () => {
    const wrapper = make("phone");
    expect(visible(wrapper).map((p) => p.attributes("id"))).toEqual(["pane-packets"]);
    expect(wrapper.find("#tab-packets").classes()).toContain("active");
    await wrapper.setProps({ view: "map" });
    expect(visible(wrapper)).toHaveLength(0);
    expect(wrapper.find(".tab-map").classes()).toContain("active");
    expect(wrapper.find(".tab-map").attributes("aria-pressed")).toBe("true");
    expect(wrapper.find("#tab-packets").classes()).not.toContain("active");
    expect(wrapper.find("#tab-packets").attributes("aria-selected")).toBe("false");
    expect(wrapper.find(".panel").classes()).toContain("bar-only");
  });

  it("brings the panel when a tab is picked, also the tab that is the open one while the map shows", async () => {
    const wrapper = make("phone", { view: "map" });
    await wrapper.find("#tab-packets").trigger("click");
    await wrapper.find("#tab-messages").trigger("click");
    expect(wrapper.emitted("update:tab")).toEqual([["packets"], ["messages"]]);
    expect(wrapper.emitted("update:view")).toEqual([["panel"], ["panel"]]);
  });

  it("has no handle to drag, no fold button, and no folded state, whatever was remembered", () => {
    const wrapper = make("phone", { collapsed: true });
    expect(wrapper.find("[role='separator']").exists()).toBe(false);
    expect(wrapper.find(".panel-fold").exists()).toBe(false);
    expect(wrapper.find(".panel").classes()).not.toContain("collapsed");
    expect(wrapper.find(".tabs").exists()).toBe(true);
    expect(wrapper.find(".panel").attributes("style")).toBeUndefined();
  });

  it("fills the screen under the bar with the open tab, the map under no condition beside it", () => {
    expect(cssRule(".size-phone .panel")).toMatch(/flex:\s*1 1 auto/);
    expect(cssRule(".size-phone .panel")).toMatch(/width:\s*auto/);
    expect(cssRule(".size-phone .panel")).toMatch(/order:\s*-1/);
    expect(cssRule(".size-phone .main")).toMatch(/flex-direction:\s*column/);
    expect(cssRule(".size-phone.view-map .panel")).toMatch(/flex:\s*none/);
    expect(cssRule(".size-phone.view-panel .mapwrap")).toMatch(/display:\s*none/);
  });
});

describe("SidePanel on a tablet and a desktop", () => {
  it("has no Map button, and shows the open tab whatever the view says", () => {
    for (const size of ["tablet", "desktop"] as const) {
      const wrapper = make(size, { view: "map" });
      expect(wrapper.find(".tab-map").exists()).toBe(false);
      expect(visible(wrapper).map((p) => p.attributes("id"))).toEqual(["pane-packets"]);
      expect(wrapper.find(".panel-fold").exists()).toBe(true);
    }
  });

  it("gives a desktop the handle and the user's width, and a tablet neither: its width is the style's, between 380 and 420 px", () => {
    const desktop = make("desktop");
    expect(desktop.find("[role='separator']").exists()).toBe(true);
    expect(desktop.find(".panel").attributes("style")).toContain("--panel-width: 500px");
    const tablet = make("tablet");
    expect(tablet.find("[role='separator']").exists()).toBe(false);
    expect(tablet.find(".panel").attributes("style")).toBeUndefined();
    expect(cssRule(".size-tablet .panel")).toMatch(/width:\s*clamp\(380px, 40%, 420px\)/);
  });

  it("can be folded on a tablet, like on a desktop", async () => {
    const wrapper = make("tablet", { collapsed: true });
    expect(wrapper.find(".panel").classes()).toContain("collapsed");
    await wrapper.find(".panel-fold").trigger("click");
    expect(wrapper.emitted("update:collapsed")).toEqual([[false]]);
  });
});

describe("the style for a finger", () => {
  it("makes every control at least 40 px high on a touch screen, and the symbols 40 px wide", () => {
    expect(mediaRule("(pointer: coarse)", ".btn")).toMatch(/min-height:\s*40px/);
    expect(mediaRule("(pointer: coarse)", ".tab")).toMatch(/min-height:\s*40px/);
    expect(mediaRule("(pointer: coarse)", ".input")).toMatch(/min-height:\s*40px/);
    expect(mediaRule("(pointer: coarse)", ".xbtn")).toMatch(/min-width:\s*40px/);
    expect(mediaRule("(pointer: coarse)", ".grid.stations td")).toMatch(/height:\s*40px/);
    expect(mediaRule("(pointer: coarse)", ".input")).toMatch(/font-size:\s*16px/);
  });

  it("keeps the notch and the home bar clear, and the page the height of the window that moves with the toolbars of a phone", () => {
    expect(cssRule(".app")).toMatch(/height:\s*100dvh/);
    expect(cssRule(".app")).toMatch(/padding-left:\s*env\(safe-area-inset-left\)/);
    expect(cssRule(".app")).toMatch(/padding-right:\s*env\(safe-area-inset-right\)/);
    expect(cssRule(".appheader")).toMatch(/env\(safe-area-inset-top\)/);
    expect(cssRule(".size-phone .cardstack")).toMatch(/env\(safe-area-inset-bottom\)/);
    expect(cssRule("html, body") || cssRule("html")).toMatch(/overflow:\s*hidden/);
  });
});

describe("MapPickBar", () => {
  it("says what to do and cancels", async () => {
    const wrapper = mount(MapPickBar);
    expect(wrapper.text()).toContain("Tap the place on the map");
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("cancel")).toHaveLength(1);
  });
});
