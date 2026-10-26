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
  mount(StationsTable, { props: { selected, others }, global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 } })) });
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
    const wrapper = mount(StationsTable, { props: { selected: null, others: [] }, global: withDaemon(fakeDaemon({ stations: old, aging })) });
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

  it("keeps the sticky head from covering a row that is scrolled to, such as the first one", () => {
    expect(cssRule(".scroll")).toMatch(/scroll-padding-top:\s*36px/);
    expect(cssRule(".grid th")).toMatch(/position:\s*sticky/);
  });

  describe("Message OH2XYZ under an empty result", () => {
    const withFilter = async (text: string, ownCall: string | null = "OH2GBA") => {
      const wrapper = mount(StationsTable, {
        props: { selected: null, others: [] },
        global: withDaemon(fakeDaemon({ stations: rows, aging: { defaultMin: 0 }, call: ownCall })),
      });
      await wrapper.find("input[type='search']").setValue(text);
      return wrapper;
    };
    const button = (wrapper: Awaited<ReturnType<typeof withFilter>>) => wrapper.find("tr.stranger button");

    it("is a button for a call that no station has been heard under, which asks to write to it", async () => {
      const wrapper = await withFilter("oh2xyz");
      expect(wrapper.find("td.empty").text()).toContain("No station matches");
      expect(button(wrapper).text()).toBe("Message OH2XYZ");
      expect(button(wrapper).classes()).toContain("primary");
      await button(wrapper).trigger("click");
      expect(wrapper.emitted("message")).toEqual([["OH2XYZ"]]);
    });

    it("is there although our own row is always listed, and not when only the filter makes the list empty of a station that matches", async () => {
      const withUs = table(station("OH2GBA", { is_me: true }), station("OH2ZWA"));
      const make = (text: string) => {
        const wrapper = mount(StationsTable, {
          props: { selected: null },
          global: withDaemon(fakeDaemon({ stations: withUs, aging: { defaultMin: 0 }, call: "OH2GBA" })),
        });
        return wrapper
          .find("input[type='search']")
          .setValue(text)
          .then(() => wrapper);
      };
      expect((await make("OH9NEW")).find("tr.stranger button").text()).toBe("Message OH9NEW");
      expect((await make("OH2ZWA")).find("tr.stranger").exists()).toBe(false);
      expect((await make("OH2GBA")).find("tr.stranger").exists()).toBe(false);
    });

    it("takes a call with an SSID, and spaces round it", async () => {
      expect(button(await withFilter(" oh2xyz-9 ")).text()).toBe("Message OH2XYZ-9");
    });

    it("is not there for text that is no call: too long, a bad SSID, a word, an empty filter", async () => {
      for (const text of ["OH2XYZABC", "OH2XYZ-16", "hello there", "OH2 XYZ", ""]) expect(button(await withFilter(text)).exists(), text).toBe(false);
    });

    it("is not there when a station matches the filter, even when the text is a whole call", async () => {
      expect(button(await withFilter("OH2ZWA")).exists()).toBe(false);
      expect(button(await withFilter("ZW")).exists()).toBe(false);
    });

    it("is not for the email gateway, whose messages are the Email tab's, and not for our own call", async () => {
      expect(button(await withFilter("EMAIL-2")).exists()).toBe(false);
      expect(button(await withFilter("email-2")).exists()).toBe(false);
      expect(button(await withFilter("oh2gba")).exists()).toBe(false);
      expect(button(await withFilter("OH2GBA", null)).exists()).toBe(true); // (while we do not know our call, nothing is ours)
    });
  });
});
