import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
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
});
