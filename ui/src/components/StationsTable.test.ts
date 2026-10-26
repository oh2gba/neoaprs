import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import type { Aging } from "@/lib/aging";
import { cssRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(500), symbol_code: "-" }),
  station("OH2PU-9", { distance_km: 16, last_heard: ago(180), packets: 20, last_comment: "D-STAR" }),
  station("OH2RDG", { distance_km: 25.4, last_heard: ago(20), packets: 5 }),
  station("OH2NOPOS", { lat: null, lon: null, distance_km: null, bearing_deg: null, last_position_at: null, last_heard: ago(900) }),
);

function calls(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll("tbody tr td.call").map((td) => td.text());
}

const never: Aging = { defaultMin: 0 };

function make(selected: string | null = null, aging: Aging = never, stations = rows) {
  return mount(StationsTable, { props: { selected }, global: withDaemon(fakeDaemon({ stations, aging })) });
}

beforeEach(() => localStorage.clear());

describe("StationsTable", () => {
  it("has the (i) of the tab at the top, which says what the list is and what the tick means", async () => {
    const wrapper = make();
    expect(wrapper.find(".tablepane").element.firstElementChild?.className).toBe("tab-help");
    await wrapper.find(".tab-help .info-toggle").trigger("click");
    expect(wrapper.find(".tab-help .info-text").text()).toContain("Every station heard, with its distance and direction from you.");
    expect(wrapper.find(".tab-help .info-text").text()).toContain("heard direct, with no digipeater");
  });

  it("lists our station first and the others by how recently they were heard", () => {
    expect(calls(make())).toEqual(["OH2GBA", "OH2RDG", "OH2PU-9", "OH2NOPOS"]);
  });

  it("keeps a call with an SSID on one line: the call cell has the class whose rule forbids wrapping", () => {
    const cells = make().findAll("tbody tr td.call");
    expect(cells.length).toBeGreaterThan(0);
    expect(cssRule(".grid .call")).toMatch(/white-space:\s*nowrap/);
  });

  it("has the columns symbol, Call, a check mark, km, the bearing as an arrow and Last heard, and nothing else: the rest is on the card", () => {
    const wrapper = make();
    expect(wrapper.findAll("thead th").map((th) => th.text())).toEqual(["", "Call", "heard direct", "km", "bearing", "Last heard ▼", ""]);
    for (const tr of wrapper.findAll("tbody tr")) expect(tr.findAll("td")).toHaveLength(7);
    const text = wrapper.findAll("tbody tr")[2]?.text() ?? "";
    expect(text).toContain("OH2PU-9");
    expect(text).toContain("16");
    expect(text).toContain("3 min");
    expect(text).not.toContain("OH2RCH-2*");
    expect(text).not.toContain("Brg");
    expect(text).not.toContain("20");
  });

  it("shows the bearing as a small arrow turned to it, north up, the compass point and the degrees only as its hover title; none for a station with no bearing", () => {
    const rowsOf = make().findAll("tbody tr");
    const pu = rowsOf[2]?.find("td.bearing");
    expect(pu?.attributes("title")).toBe("NE, 45°");
    expect(pu?.find(".arrow").attributes("style")).toContain("rotate(45deg)");
    expect(pu?.find(".arrow").attributes("aria-hidden")).toBe("true");
    expect(pu?.text()).toContain("NE, 45°"); // for a screen reader
    const mine = rowsOf[0]?.find("td.bearing");
    expect(mine?.find(".arrow").exists()).toBe(false);
    expect(mine?.attributes("title")).toBe("-");
  });

  it("is sorted by the other columns, not by the arrow", () => {
    const heads = make().findAll("thead th");
    expect(heads[4]?.find("button").exists()).toBe(false);
    expect(heads[3]?.find("button").exists()).toBe(true);
  });

  it("says when a station was last heard, anything it sent, with the full time as the hover title", () => {
    const cell = make().findAll("tbody tr")[2]?.findAll("td")[5];
    expect(cell?.text()).toBe("3 min");
    expect(cell?.attributes("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
  });

  it("has a green check mark after the call of a station heard direct, named for a screen reader, and nothing for the others", () => {
    const stations = table(
      station("OH2GBA", { is_me: true, last_direct_at: ago(60) }),
      station("OH2NEAR", { last_direct_at: ago(300) }),
      station("OH2FAR", { last_direct_at: null }),
    );
    const wrapper = make(null, never, stations);
    const marks = Object.fromEntries(wrapper.findAll("tbody tr").map((tr) => [tr.find("td.call").text(), tr.find("td.direct .direct-mark")]));
    expect(marks.OH2NEAR?.exists()).toBe(true);
    expect(marks.OH2NEAR?.attributes("aria-label")).toBe("Heard direct");
    expect(marks.OH2NEAR?.attributes("title")).toBe("Heard direct");
    expect(marks.OH2GBA?.exists()).toBe(false);
    expect(marks.OH2FAR?.exists()).toBe(false);
    expect(wrapper.text()).not.toMatch(/\d+ %/);
  });

  it("shows the symbol first, as a picture with its name for a hover", () => {
    const first = make().findAll("tbody tr")[1]?.findAll("td")[0];
    expect(first?.find(".symicon").exists()).toBe(true);
    expect(first?.attributes("title")).toBe("Car");
  });

  it("makes every row one line, the same height, in a table that fits a narrow panel", () => {
    const wrapper = make();
    expect(wrapper.find("table").classes()).toContain("stations");
    expect(cssRule(".grid.stations td")).toMatch(/white-space:\s*nowrap/);
    expect(cssRule(".grid.stations td")).toMatch(/height:\s*30px/);
  });

  it("sorts by a column on a click, and the other way on the next", async () => {
    const wrapper = make();
    const distance = wrapper.findAll("th button").find((b) => b.text().startsWith("km"));
    await distance?.trigger("click");
    expect(calls(wrapper)).toEqual(["OH2GBA", "OH2PU-9", "OH2RDG", "OH2NOPOS"]);
    expect(wrapper.find("th[aria-sort='ascending']").exists()).toBe(true);
    await distance?.trigger("click");
    expect(calls(wrapper)).toEqual(["OH2GBA", "OH2RDG", "OH2PU-9", "OH2NOPOS"]);
    expect(wrapper.find("th[aria-sort='descending']").exists()).toBe(true);
  });

  it("filters by the text of the box", async () => {
    const wrapper = make();
    await wrapper.find("input[type='search']").setValue("d-star");
    expect(calls(wrapper)).toEqual(["OH2GBA", "OH2PU-9"]);
    await wrapper.find("input[type='search']").setValue("zzz");
    expect(calls(wrapper)).toEqual(["OH2GBA"]);
  });

  it("has no tickbox for a position, and lists the stations without one", () => {
    const wrapper = make();
    expect(wrapper.findAll("input[type='checkbox']").map((c) => c.element.parentElement?.textContent?.trim())).toEqual(["hide timed out", "direct only"]);
    expect(calls(wrapper)).toContain("OH2NOPOS");
  });

  describe("a station past its timeout", () => {
    const old = table(
      station("OH2GBA", { is_me: true, last_position_at: ago(86400 * 3) }),
      station("OH2FRESH", { last_heard: ago(30), last_position_at: ago(60) }),
      station("OH2OLD", { last_heard: ago(60), last_position_at: ago(3 * 3600) }),
    );
    const aging: Aging = { defaultMin: 60 };
    const lines = (wrapper: ReturnType<typeof make>) => wrapper.findAll("tbody tr");

    it("stays in the table, dim, with the word timed out after the time it was heard; ours and a fresh one do not have it", () => {
      const wrapper = make(null, aging, old);
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2FRESH", "OH2OLD"]);
      const [mine, fresh, gone] = lines(wrapper);
      expect(gone?.classes()).toContain("timedout");
      expect(gone?.findAll("td")[5]?.text()).toBe("1 min timed out");
      expect(mine?.classes()).not.toContain("timedout");
      expect(fresh?.text()).not.toContain("timed out");
    });

    it("can be hidden by the toggle, which is remembered", async () => {
      const wrapper = make(null, aging, old);
      const toggle = wrapper.findAll("input[type='checkbox']")[0];
      expect(toggle?.element.parentElement?.textContent).toContain("hide timed out");
      await toggle?.setValue(true);
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2FRESH"]);
      expect(wrapper.find(".foot").text()).toBe("2 of 3 stations");
      expect(localStorage.getItem("NeoAPRS.hidetimedout")).toBe("on");
      expect(make(null, aging, old).findAll("tbody tr")).toHaveLength(2);
      await toggle?.setValue(false);
      expect(calls(wrapper)).toContain("OH2OLD");
    });

    it("is not marked when there is no timeout", () => {
      expect(make(null, never, old).find("tr.timedout").exists()).toBe(false);
    });
  });

  describe("the stations heard direct", () => {
    const heard = table(
      station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null }),
      station("OH2NEAR", { last_heard: ago(30), last_direct_at: ago(300), heard_direct: 2, heard_via: [["OH2RCH-2", 3]], packets: 5 }),
      station("OH2ONCE", { last_heard: ago(60), last_direct_at: ago(7200), heard_direct: 1, heard_via: [["OH2RCH-2", 3]], packets: 4 }),
      station("OH2FAR", { last_heard: ago(90), last_direct_at: null, heard_direct: 0, heard_via: [["OH2RCH-2", 3]], packets: 3 }),
    );
    it("can be narrowed to them by a toggle, which is remembered; our own station stays", async () => {
      const wrapper = make(null, never, heard);
      const toggle = wrapper.findAll("input[type='checkbox']")[1];
      expect(toggle?.element.parentElement?.textContent).toContain("direct only");
      await toggle?.setValue(true);
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2NEAR", "OH2ONCE"]);
      expect(wrapper.find(".foot").text()).toBe("3 of 4 stations");
      expect(localStorage.getItem("NeoAPRS.directonly")).toBe("on");
      expect(calls(make(null, never, heard))).toEqual(["OH2GBA", "OH2NEAR", "OH2ONCE"]);
      await toggle?.setValue(false);
      expect(calls(wrapper)).toContain("OH2FAR");
    });
  });

  it("marks the selected row and says which station was picked", async () => {
    const wrapper = make("OH2PU-9");
    expect(wrapper.findAll("tr.selected")).toHaveLength(1);
    expect(wrapper.find("tr.selected").text()).toContain("OH2PU-9");
    await wrapper.findAll("tbody tr")[1]?.trigger("click");
    expect(wrapper.emitted("select")).toEqual([["OH2RDG", false]]);
  });

  it("says so when there is no station", () => {
    const wrapper = mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ aging: never })) });
    expect(wrapper.text()).toContain("No station heard yet.");
  });
});
