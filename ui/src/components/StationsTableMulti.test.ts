import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { cssRule } from "@/test/css";
import { NOW, ago, station, table } from "@/test/fixtures";

const rows = table(
  station("OH2ZWA", { distance_km: 7, last_heard: ago(60) }),
  station("OH2ZWB", { distance_km: 32, last_heard: ago(120) }),
  station("OH2ZWC", { distance_km: 13, last_heard: ago(180) }),
);
const make = (selected: string | null = null, others: string[] = []) =>
  mount(StationsTable, { props: { stations: rows, selected, others, now: NOW, aging: { timeouts: new Map(), defaultMin: 0 } } });
const row = (wrapper: ReturnType<typeof make>, call: string) => wrapper.findAll("tbody tr").find((r) => r.text().includes(call));

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
    expect(wrapper.findAll("tr.selected").map((r) => r.find("td.call").text())).toEqual(["OH2ZWA", "OH2ZWC"]);
    expect(row(wrapper, "OH2ZWB")?.attributes("aria-selected")).toBe("false");
    expect(row(wrapper, "OH2ZWA")?.attributes("aria-selected")).toBe("true");
  });

  it("keeps a station past its timeout in the table, last and marked, unless hide timed out is on; and it can be picked", async () => {
    const old = table(
      station("OH2NEW", { last_heard: ago(60) }),
      station("OH2OLD", { lat: 60.4, lon: 25.1, last_position_at: ago(5 * 3600), last_heard: ago(5 * 3600) }),
    );
    const aging = { timeouts: new Map(), defaultMin: 180 };
    const wrapper = mount(StationsTable, { props: { stations: old, selected: null, others: [], now: NOW, aging } });
    expect(wrapper.findAll("tbody td.call").map((td) => td.text())).toEqual(["OH2NEW", "OH2OLD"]);
    expect(row(wrapper as unknown as ReturnType<typeof make>, "OH2OLD")?.text()).toContain("timed out");
    await row(wrapper as unknown as ReturnType<typeof make>, "OH2OLD")?.trigger("click", { ctrlKey: true });
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
    expect([(box.element as HTMLInputElement).value, first.defaultPrevented, wrapper.findAll("tbody tr").length]).toEqual(["", true, 3]);
    const second = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    box.element.dispatchEvent(second);
    expect(second.defaultPrevented).toBe(false);
  });

  it("reads as one block: at most 640 px wide and in the middle of a wider panel", () => {
    const wrapper = make();
    expect(wrapper.find(".tablepane").classes()).toContain("capped");
    for (const selector of [".tablepane.capped > .toolbar", ".tablepane.capped > .foot", ".tablepane.capped .grid.stations"]) {
      const rule = cssRule(selector);
      expect(rule, selector).toMatch(/max-width:\s*640px/);
      expect(rule, selector).toMatch(/margin-left:\s*auto/);
      expect(rule, selector).toMatch(/margin-right:\s*auto/);
    }
  });

  it("wraps the filter row instead of cutting it off: the box has a width to keep, the three tickboxes are one group that wraps itself, and a phone puts them under the box", () => {
    const wrapper = make();
    expect(wrapper.find(".toolbar").classes()).not.toContain("nowrap");
    expect(cssRule(".toolbar")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".filterbox")).toMatch(/flex:\s*1 1 12em/);
    expect(cssRule(".filterbox")).toMatch(/min-width:\s*min\(12em, 100%\)/);
    expect(wrapper.findAll(".toolbar > .toolbar-checks > label.check")).toHaveLength(3);
    expect(cssRule(".toolbar-checks")).toMatch(/flex-wrap:\s*wrap/);
    expect(cssRule(".size-phone .toolbar .filterbox")).toMatch(/flex:\s*1 1 100%/);
  });

  it("keeps the sticky head from covering a row that is scrolled to, such as the first one", () => {
    expect(cssRule(".scroll")).toMatch(/scroll-padding-top:\s*36px/);
    expect(cssRule(".grid th")).toMatch(/position:\s*sticky/);
  });
});
