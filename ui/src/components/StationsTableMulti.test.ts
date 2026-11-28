import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { cssRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const rows = table(
  station("OH2ZWA", { distance_km: 7, last_heard: ago(60) }),
  station("OH2ZWB", { distance_km: 32, last_heard: ago(120) }),
  station("OH2ZWC", { distance_km: 13, last_heard: ago(180) }),
);
const make = (selected: string | null = null, others: string[] = []) =>
  mount(StationsTable, {
    props: { selected, others },
    global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 } })),
  });
const row = (wrapper: ReturnType<typeof make>, call: string) =>
  wrapper.findAll("tbody tr").find((r) => r.text().includes(call));

beforeEach(() => localStorage.clear());

describe("StationsTable with several cards", () => {
  it("says whether Ctrl (or Cmd on a Mac) was held when a row was clicked, or Enter pressed on it", async () => {
    const wrapper = make();
    await row(wrapper, "OH2ZWA")?.trigger("click");
    await row(wrapper, "OH2ZWB")?.trigger("click", { ctrlKey: true });
    await row(wrapper, "OH2ZWC")?.trigger("click", { metaKey: true });
    await row(wrapper, "OH2ZWA")?.trigger("keydown.enter", { ctrlKey: true });
    await row(wrapper, "OH2ZWA")?.trigger("keydown.enter");
    expect(wrapper.emitted("select")).toEqual([
      ["OH2ZWA", false],
      ["OH2ZWB", true],
      ["OH2ZWC", true],
      ["OH2ZWA", true],
      ["OH2ZWA", false],
    ]);
  });

  it("marks the rows of all the open cards", () => {
    const wrapper = make("OH2ZWC", ["OH2ZWA"]);
    expect(wrapper.findAll("tr.selected").map((r) => r.find("td.call .callname").text())).toEqual(["OH2ZWA", "OH2ZWC"]);
    expect(row(wrapper, "OH2ZWB")?.attributes("aria-selected")).toBe("false");
    expect(row(wrapper, "OH2ZWA")?.attributes("aria-selected")).toBe("true");
  });

  it("keeps a station past its timeout in the table, last and marked, unless hide timed out is on; and it can be picked", async () => {
    const old = table(
      station("OH2NEW", { last_heard: ago(60) }),
      station("OH2OLD", { lat: 60.4, lon: 25.1, last_position_at: ago(5 * 3600), last_heard: ago(5 * 3600) }),
    );
    const aging = { defaultMin: 180 };
    const wrapper = mount(StationsTable, {
      props: { selected: null, others: [] },
      global: withDaemon(fakeDaemon({ stations: old, aging })),
    });
    expect(wrapper.findAll("tbody td.call .callname").map((td) => td.text())).toEqual(["OH2NEW", "OH2OLD"]);
    expect(row(wrapper, "OH2OLD")?.text()).toContain("timed out");
    await row(wrapper, "OH2OLD")?.trigger("click", { ctrlKey: true });
    expect(wrapper.emitted("select")).toEqual([["OH2OLD", true]]);
  });

  it("clears the filter on the first Esc, and does not take the second one, which is for the page (it closes the newest card)", async () => {
    const wrapper = make();
    const box = wrapper.find("input[type='search']");
    await box.setValue("ZWA");
    expect(wrapper.findAll("tbody tr")).toHaveLength(1);
    const first = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    box.element.dispatchEvent(first);
    await wrapper.vm.$nextTick();
    expect([
      (box.element as HTMLInputElement).value,
      first.defaultPrevented,
      wrapper.findAll("tbody tr").length,
    ]).toEqual(["", true, 3]);
    const second = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    box.element.dispatchEvent(second);
    expect(second.defaultPrevented).toBe(false);
  });

  it("fills the panel as the Email tab does: no cap and no centring, the tags column takes the free width and the other columns fit their content", () => {
    const wrapper = make();
    expect(wrapper.find(".tablepane").classes()).not.toContain("capped");
    for (const selector of [".tablepane > .toolbar", ".grid.stations", ".nearby-section"])
      expect(cssRule(selector), selector).not.toMatch(/max-width|margin-left:\s*auto/);
    expect(cssRule(".grid.stations td")).toMatch(/width:\s*1%/);
    expect(cssRule(".grid.stations td.heard")).toMatch(/width:\s*auto/);
  });

  it("wraps the filter row instead of cutting it off: the box has a width to keep, the tickboxes and the select of the hours are one group that wraps itself, and a phone puts them under the box", () => {
    const wrapper = make();
    expect(wrapper.find(".toolbar").classes()).not.toContain("nowrap");
    expect(cssRule(".toolbar")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".filterbox")).toMatch(/flex:\s*1 1 12em/);
    expect(cssRule(".filterbox")).toMatch(/min-width:\s*min\(12em, 100%\)/);
    expect(wrapper.findAll(".toolbar > .toolbar-checks > label.check")).toHaveLength(3);
    expect(cssRule(".toolbar-checks")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".size-phone .toolbar .filterbox")).toMatch(/flex:\s*1 1 100%/);
  });

  it("has the filters in a group box of their own, as the other tabs have their fields: a legend, and the filter field, the tickboxes and the hours inside it", () => {
    const wrapper = make();
    const box = wrapper.find(".tablepane > fieldset.filters");
    expect(box.exists()).toBe(true);
    expect(box.find("legend").text()).toBe("Filter");
    expect(box.find("input.filterbox").attributes("placeholder")).toBe("Call, symbol, comment, path");
    expect(box.findAll("label.check")).toHaveLength(3);
    expect(wrapper.find(".tablepane").element.children[1]).toBe(box.element);
  });

  it("keeps the sticky head from covering a row that is scrolled to, such as the first one", () => {
    expect(cssRule(".scroll")).toMatch(/scroll-padding-top:\s*36px/);
    expect(cssRule(".grid th")).toMatch(/position:\s*sticky/);
  });

  describe("a button to write to the filter's call under an empty result", () => {
    const withFilter = async (text: string, ownCall: string | null = "OH2GBA") => {
      const wrapper = mount(StationsTable, {
        props: { selected: null, others: [] },
        global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 }, call: ownCall })),
      });
      await wrapper.find("input[type='search']").setValue(text);
      return wrapper;
    };

    it("is not there: a call no station was heard under is written to by the + of Messages alone", async () => {
      for (const text of ["oh2xyz", " oh2xyz-9 ", "OH2GBA"]) {
        const wrapper = await withFilter(text, text === "OH2GBA" ? null : "OH2GBA");
        expect(wrapper.find("td.empty").text(), text).toContain("No station matches");
        expect(wrapper.findAll("tbody button").length, text).toBe(0);
        expect(wrapper.text(), text).not.toContain("Message ");
      }
    });

    it("leaves the Message button of a station that is in the list", async () => {
      const wrapper = await withFilter("OH2ZWA");
      await wrapper.find("button[aria-label='Message OH2ZWA']").trigger("click");
      expect(wrapper.emitted("message")).toEqual([["OH2ZWA"]]);
    });
  });
});
