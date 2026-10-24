import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it } from "vitest";
import StationsTable from "@/components/StationsTable.vue";
import type { Aging } from "@/lib/aging";
import { fakeDaemon, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { ago, station, table } from "@/test/fixtures";

// Rows drawn over each other (Chromium kept stale copies of the cells of a dimmed row, painted over other rows, when the rows moved or changed): a row of the table has no opacity of its own, and nothing but the head is sticky.
const stations = table(
  station("OH2GBA", { is_me: true, distance_km: null, bearing_deg: null, last_heard: ago(500) }),
  station("OH2FRESH", { bearing_deg: 90, last_heard: ago(30), last_position_at: ago(60) }),
  station("OH2OLD", { bearing_deg: 200, last_heard: ago(60), last_position_at: ago(3 * 3600) }),
  station("OH2GONE", { bearing_deg: 10, last_heard: ago(120), last_position_at: ago(5 * 3600) }),
);
const aging: Aging = { timeouts: new Map(), defaultMin: 60 };
const make = () => mount(StationsTable, { props: { selected: "OH2OLD" }, global: withDaemon(fakeDaemon({ stations, aging })) });
const sheet = readFileSync(resolve(__dirname, "../styles/tables.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

beforeEach(() => localStorage.clear());

describe("the rows of the Stations table", () => {
  it("are one row for each call, none twice, and a timed-out row is a row like the others (no extra element, no position of its own)", () => {
    const wrapper = make();
    const calls = wrapper.findAll("tbody tr td.call").map((td) => td.text());
    expect(calls).toEqual(["OH2GBA", "OH2FRESH", "OH2OLD", "OH2GONE"]);
    expect(new Set(calls).size).toBe(calls.length);
    const timedOut = wrapper.findAll("tbody tr.timedout");
    expect(timedOut.map((r) => r.find("td.call").text())).toEqual(["OH2OLD", "OH2GONE"]);
    for (const tr of wrapper.findAll("tbody tr")) expect(tr.element.getAttribute("style")).toBeNull();
  });

  it("have no opacity on the row: a timed-out row is dimmed in its cells, and the bearing's arrow (turned by a transform) is dimmed itself, not through its cell", () => {
    expect(cssRule(".grid tr.timedout")).not.toMatch(/opacity/);
    expect(cssRule(".grid tr.timedout.selected")).not.toMatch(/opacity/);
    expect(cssRule(".grid tr.timedout td:not(.bearing)")).toMatch(/opacity:\s*0\.55/);
    expect(cssRule(".grid tr.timedout .arrow")).toMatch(/opacity:\s*0\.55/);
    expect(cssRule(".grid tr.timedout.selected td")).toMatch(/opacity:\s*1\b/);
    expect(cssRule(".grid tr.timedout.selected .arrow")).toMatch(/opacity:\s*1\b/);
    // no rule of the sheet puts an opacity on a row or on the bearing cell
    for (const match of sheet.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!/opacity/.test(match[2] ?? "")) continue;
      for (const selector of (match[1] ?? "").split(",").map((part) => part.trim())) {
        expect(selector, "an opacity on a row").not.toMatch(/\btr(\.[\w-]+)*$/);
        expect(selector, "an opacity on the bearing cell").not.toMatch(/td\.bearing$/);
      }
    }
  });

  it("have the arrow in the bearing cell that the dimming rules leave out, and not in another cell", () => {
    const wrapper = make();
    const cells = wrapper.findAll("tbody tr.timedout td");
    expect(cells.filter((td) => td.find("svg.arrow").exists()).every((td) => td.classes().includes("bearing"))).toBe(true);
    for (const tr of wrapper.findAll("tbody tr.timedout")) expect(tr.find("td.bearing svg.arrow").exists()).toBe(true);
  });

  it("are not sticky or positioned: only the head cells are, and a selected timed-out row is still a row of the table", () => {
    const wrapper = make();
    for (const match of sheet.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (!/position:\s*(sticky|fixed|absolute)/.test(match[2] ?? "")) continue;
      for (const selector of (match[1] ?? "").split(",").map((part) => part.trim())) expect(selector).toMatch(/^\.grid th$/);
    }
    const selected = wrapper.find("tbody tr.timedout.selected");
    expect(selected.find("td.call").text()).toBe("OH2OLD");
  });
});
