import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import { cssRule } from "@/test/css";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, station, table } from "@/test/fixtures";

const me = station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(900), heard_rf: 0 });
const rf = station("OH2RF", { last_heard: ago(30), heard_rf: 4 });
const gated = station("OH2GATED", { last_heard: ago(60), heard_rf: 0, heard_rf_gated: 2, last_rf_at: null, last_rf_gated_at: ago(60) });
const net = station("OH2NET", {
  last_heard: ago(90),
  heard_rf: 0,
  heard_is: 3,
  last_rf_at: null,
  last_is_at: ago(90),
  position_via: "is",
  last_route: "",
  can_message: false,
});
const both = station("OH2BOTH", { last_heard: ago(20), heard_rf: 2, heard_is: 1, last_is_at: ago(20), last_rf_at: ago(100) });
const object = station("LEADER", { kind: "object", own: true, last_heard: ago(200), heard_rf: 0 });

const make = (...rows: ReturnType<typeof station>[]) =>
  mount(StationsTable, { props: { selected: null }, global: withDaemon(fakeDaemon({ stations: table(...rows) })) });
const labels = (wrapper: ReturnType<typeof make>): [string, string][] =>
  wrapper.findAll("tbody tr[data-call]").map((tr): [string, string] => [tr.find(".callname").text(), tr.find(".via").exists() ? tr.find(".via").text() : ""]);

beforeEach(() => localStorage.clear());

describe("how a station was heard, in the Stations table", () => {
  it("is a small label under the call of every row: RF, iGate, Internet or two joined; none for our own station and our objects", () => {
    expect(labels(make(me, rf, gated, net, both, object))).toEqual([
      ["OH2GBA", ""],
      ["OH2BOTH", "RF · Internet"],
      ["OH2RF", "RF"],
      ["OH2GATED", "iGate"],
      ["OH2NET", "Internet"],
      ["LEADER", ""],
    ]);
  });

  it("says in a title what the label means", () => {
    const wrapper = make(rf, net, both);
    const titles: Record<string, string | undefined> = {};
    for (const tr of wrapper.findAll("tbody tr[data-call]")) titles[tr.attributes("data-call") ?? ""] = tr.find(".via").attributes("title");
    expect(titles).toEqual({
      OH2RF: "Heard on the radio",
      OH2NET: "Received over the internet (APRS-IS), not on the radio",
      OH2BOTH: "Heard on the radio; Received over the internet (APRS-IS), not on the radio",
    });
  });

  it("marks the row of a station known from the internet alone, and no other", () => {
    const wrapper = make(rf, net, both, gated);
    expect(wrapper.findAll("tbody tr.internetonly").map((tr) => tr.attributes("data-call"))).toEqual(["OH2NET"]);
  });

  it("keeps a row one line high: the label is a quiet tag after the call on the call's line, in italics for a station of the internet alone", () => {
    const wrapper = make(rf, net, both);
    for (const tr of wrapper.findAll("tbody tr[data-call]")) {
      const cell = tr.get("td.call").element;
      expect([...cell.children].map((c) => c.className.split(" ")[0])).toEqual(["callname", "tag"]);
      expect(tr.get(".via").classes()).toContain("tag-quiet");
    }
    expect(cssRule(".grid.stations td")).toMatch(/height:\s*30px/);
    expect(cssRule(".grid.stations td.call")).toMatch(/white-space:\s*nowrap/);
    expect(cssRule(".grid.stations td.call .via")).not.toMatch(/display:\s*block/);
    expect(cssRule(".grid.stations tr.internetonly td.call .via")).toMatch(/font-style:\s*italic/);
  });
});

describe("the tickbox heard on RF only", () => {
  const boxes = (wrapper: ReturnType<typeof make>): string[] =>
    wrapper.findAll("input[type='checkbox']").map((c) => c.element.parentElement?.textContent?.trim() ?? "");

  it("is not there while no station has been received over the internet", () => {
    expect(boxes(make(me, rf, gated))).toEqual(["hide timed out", "direct only"]);
  });

  it("is there from the first station received over the internet, next to the other two, and unticked", () => {
    const wrapper = make(me, rf, both);
    expect(boxes(wrapper)).toEqual(["hide timed out", "direct only", "heard on RF only"]);
    expect(wrapper.findAll<HTMLInputElement>("input[type='checkbox']")[2]?.element.checked).toBe(false);
    expect(wrapper.findAll("tbody tr[data-call]")).toHaveLength(3);
  });

  it("leaves out the stations known from the internet alone, not those also heard on the radio, an iGate's, ours or our objects", async () => {
    const wrapper = make(me, rf, gated, net, both, object);
    await wrapper.findAll("input[type='checkbox']")[2]?.setValue(true);
    expect(labels(wrapper).map(([call]) => call)).toEqual(["OH2GBA", "OH2BOTH", "OH2RF", "OH2GATED", "LEADER"]);
    expect(wrapper.find(".foot").text()).toBe("5 of 6 stations");
    await wrapper.findAll("input[type='checkbox']")[2]?.setValue(false);
    expect(labels(wrapper)).toHaveLength(6);
  });

  it("is remembered in this browser, like the others", async () => {
    const first = make(me, net, both);
    await first.findAll("input[type='checkbox']")[2]?.setValue(true);
    first.unmount();
    const again = make(me, net, both);
    expect(again.findAll<HTMLInputElement>("input[type='checkbox']")[2]?.element.checked).toBe(true);
    expect(labels(again).map(([call]) => call)).toEqual(["OH2GBA", "OH2BOTH"]);
  });

  it("has a title that says what it leaves out", () => {
    expect(make(net).find("label[title]").attributes("title")).toBe("Leave out the stations known only from the internet");
  });
});
