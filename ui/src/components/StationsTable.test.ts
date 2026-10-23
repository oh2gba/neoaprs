import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import type { Aging } from "@/lib/aging";
import { cssRule } from "@/test/css";
import { NOW, ago, station, table, weather, weatherStation } from "@/test/fixtures";

const rows = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(500), symbol_code: "-" }),
  station("OH2PU-9", { distance_km: 16, last_heard: ago(180), packets: 20, last_comment: "D-STAR" }),
  station("OH2RDG", { distance_km: 25.4, last_heard: ago(20), packets: 5 }),
  station("OH2NOPOS", { lat: null, lon: null, distance_km: null, bearing_deg: null, last_position_at: null, last_heard: ago(900) }),
);

function calls(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAll("tbody tr td:first-child").map((td) => td.text());
}

const never: Aging = { timeouts: new Map(), defaultMin: 0 };

function make(selected: string | null = null, aging: Aging = never, stations = rows) {
  return mount(StationsTable, { props: { stations, selected, now: NOW, aging } });
}

beforeEach(() => localStorage.clear());

describe("StationsTable", () => {
  it("lists our station first and the others by how recently they were heard", () => {
    expect(calls(make())).toEqual(["OH2GBA", "OH2RDG", "OH2PU-9", "OH2NOPOS"]);
  });

  it("keeps a call with an SSID on one line: the call cell has the class whose rule forbids wrapping", () => {
    const cells = make().findAll("tbody tr td:first-child");
    expect(cells.length).toBeGreaterThan(0);
    for (const cell of cells) expect(cell.classes()).toContain("call");
    expect(cssRule(".grid .call")).toMatch(/white-space:\s*nowrap/);
  });

  it("writes the distance, the bearing, the ages, the packets and the path", () => {
    const text = make().findAll("tbody tr")[2]?.text() ?? "";
    expect(text).toContain("OH2PU-9");
    expect(text).toContain("16");
    expect(text).toContain("45° NE");
    expect(text).toContain("3 min");
    expect(text).toContain("20");
    expect(text).toContain("OH2RCH-2*");
  });

  it("has a wx column with the temperature of a weather station and a dash for any other, sorted by a click", async () => {
    const stations = table(
      station("OH2GBA", { is_me: true }),
      weatherStation("OH2MUI", { weather: weather({ temp_c: 10 }) }),
      weatherStation("OH2NJR", { weather: weather({ temp_c: -3.25 }) }),
      station("OH2CAR"),
    );
    const wrapper = make(null, never, stations);
    const cells = (): string[] => wrapper.findAll("tbody tr").map((tr) => tr.findAll("td")[7]?.text() ?? "");
    const head = wrapper.findAll("th button").find((b) => b.text().startsWith("wx"));
    expect(head).toBeDefined();
    await head?.trigger("click");
    expect(wrapper.findAll("tbody tr td:first-child").map((td) => td.text())).toEqual(["OH2GBA", "OH2MUI", "OH2NJR", "OH2CAR"]);
    expect(cells()).toEqual(["-", "10.0°", "-3.3°", "-"]);
    await head?.trigger("click");
    expect(wrapper.findAll("tbody tr td:first-child").map((td) => td.text())).toEqual(["OH2GBA", "OH2NJR", "OH2MUI", "OH2CAR"]);
    expect(wrapper.findAll("tbody tr")[1]?.findAll("td")[7]?.attributes("title")).toBe("10 min ago");
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

  it("can show only the stations with a position", async () => {
    const wrapper = make();
    await wrapper.findAll("input[type='checkbox']")[0]?.setValue(true);
    expect(calls(wrapper)).not.toContain("OH2NOPOS");
    expect(wrapper.find(".foot").text()).toBe("3 of 4 stations");
  });

  describe("a station past its timeout", () => {
    const old = table(
      station("OH2GBA", { is_me: true, last_position_at: ago(86400 * 3) }),
      station("OH2FRESH", { last_heard: ago(30), last_position_at: ago(60) }),
      station("OH2OLD", { last_heard: ago(60), last_position_at: ago(3 * 3600) }),
    );
    const aging: Aging = { timeouts: new Map([["OH2FRESH", 0]]), defaultMin: 60 };
    const lines = (wrapper: ReturnType<typeof make>) => wrapper.findAll("tbody tr");

    it("stays in the table, dim, with the word timed out in the Position column; ours and a fresh one do not have it", () => {
      const wrapper = make(null, aging, old);
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2FRESH", "OH2OLD"]);
      const [mine, fresh, gone] = lines(wrapper);
      expect(gone?.classes()).toContain("timedout");
      expect(gone?.findAll("td")[5]?.text()).toBe("3 h timed out");
      expect(mine?.classes()).not.toContain("timedout");
      expect(fresh?.text()).not.toContain("timed out");
    });

    it("can be hidden by the toggle, which is remembered", async () => {
      const wrapper = make(null, aging, old);
      const toggle = wrapper.findAll("input[type='checkbox']")[1];
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
    const cells = (wrapper: ReturnType<typeof make>) =>
      Object.fromEntries(wrapper.findAll("tbody tr").map((tr) => [tr.find("td").text(), tr.findAll("td")[6]?.text()]));

    it("has a Direct column: when the station was last heard direct and the share of its packets that came direct", () => {
      const wrapper = make(null, never, heard);
      expect(wrapper.findAll("th").map((th) => th.text())).toContain("Direct");
      expect(cells(wrapper)).toEqual({ OH2GBA: "-", OH2NEAR: "5 min, 40 %", OH2ONCE: "2 h, 25 %", OH2FAR: "-" });
    });

    it("sorts by when it was last heard direct, the latest first, and a station never heard direct last", async () => {
      const wrapper = make(null, never, heard);
      await wrapper
        .findAll("th button")
        .find((b) => b.text().startsWith("Direct"))
        ?.trigger("click");
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2NEAR", "OH2ONCE", "OH2FAR"]);
      await wrapper
        .findAll("th button")
        .find((b) => b.text().startsWith("Direct"))
        ?.trigger("click");
      expect(calls(wrapper)).toEqual(["OH2GBA", "OH2ONCE", "OH2NEAR", "OH2FAR"]);
    });

    it("can be narrowed to them by a toggle, which is remembered; our own station stays", async () => {
      const wrapper = make(null, never, heard);
      const toggle = wrapper.findAll("input[type='checkbox']")[2];
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
    expect(wrapper.emitted("select")).toEqual([["OH2RDG"]]);
  });

  it("says so when there is no station", () => {
    const wrapper = mount(StationsTable, { props: { stations: new Map(), selected: null, now: NOW, aging: never } });
    expect(wrapper.text()).toContain("No station heard yet.");
  });
});
