import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { agingOf } from "@/lib/aging";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, configValues, station, table } from "@/test/fixtures";

const stations = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(500) }),
  station("OH2FRESH", { last_heard: ago(30), last_position_at: ago(60) }),
  station("OH2TWO", { last_heard: ago(60), last_position_at: ago(2 * 3600) }),
  station("OH2FIVE", { last_heard: ago(120), last_position_at: ago(5 * 3600) }),
);

beforeEach(() => localStorage.clear());

describe("the select 'On map for' of the Stations tab", () => {
  const make = (hours = "3") => {
    const daemon = fakeDaemon({ stations, config: configValues({ "map/station_hours": hours }), aging: agingOf({ "map/station_hours": hours }) });
    return { daemon, wrapper: mount(StationsTable, { props: { selected: null }, global: withDaemon(daemon) }) };
  };

  it("offers 1, 3, 6, 12 and 24 hours, and shows the hours in force", () => {
    const { wrapper } = make("12");
    const select = wrapper.find<HTMLSelectElement>("select#stations-on-map");
    expect(select.findAll("option").map((o) => [o.element.value, o.text()])).toEqual([
      ["1", "1 h"],
      ["3", "3 h"],
      ["6", "6 h"],
      ["12", "12 h"],
      ["24", "24 h"],
    ]);
    expect(select.element.value).toBe("12");
    expect(wrapper.find(".onmap").text()).toContain("On map for");
  });

  it("sends the setting when another is picked, and nothing else", async () => {
    const { wrapper, daemon } = make();
    await wrapper.find("select#stations-on-map").setValue("24");
    expect(daemon.send.mock.calls.map((c) => c[0])).toEqual([{ cmd: "set_config", values: { "map/station_hours": "24" } }]);
  });

  it("dims the rows that are past the hours: 1 h dims the one heard 2 h ago, 3 h only the one heard 5 h ago, 6 h none", () => {
    const dim = (hours: string) =>
      make(hours)
        .wrapper.findAll("tbody tr.timedout td.call")
        .map((td) => td.text());
    expect(dim("1")).toEqual(["OH2TWO", "OH2FIVE"]);
    expect(dim("3")).toEqual(["OH2FIVE"]);
    expect(dim("6")).toEqual([]);
  });
});
