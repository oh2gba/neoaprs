import { describe, expect, it } from "vitest";
import { firstDirection, hasPosition, listStations, menuItems, panelItems, talksTo, withOwnSymbol, type Sort } from "@/lib/stations";
import { ago, station, weather } from "@/test/fixtures";

const base: { filter: string; sort: Sort } = { filter: "", sort: { key: "call", dir: 1 } };

describe("hasPosition", () => {
  it("needs both coordinates", () => {
    expect(hasPosition(station("A"))).toBe(true);
    expect(hasPosition(station("A", { lat: null, lon: null }))).toBe(false);
    expect(hasPosition(station("A", { lon: null }))).toBe(false);
  });
});

describe("listStations", () => {
  const rows = [
    station("OH2PU-9", { distance_km: 16, last_heard: ago(30), packets: 5, last_comment: "D-STAR" }),
    station("OH2RDG", { distance_km: 25, last_heard: ago(10), packets: 9, symbol_code: "#" }),
    station("OH2XYZ", { distance_km: null, lat: null, lon: null, last_position_at: null, last_heard: ago(5), packets: 1 }),
    station("OH2GBA", { is_me: true, distance_km: null, last_heard: ago(100) }),
  ];

  it("keeps only the stations heard direct when asked, and ours stays", () => {
    const direct = [station("OH2PU-9", { last_direct_at: ago(60) }), station("OH2RDG", { last_direct_at: null }), station("OH2GBA", { is_me: true })];
    expect(listStations(direct, { ...base, directOnly: true }).map((r) => r.call)).toEqual(["OH2GBA", "OH2PU-9"]);
    expect(listStations(direct, { ...base, directOnly: false }).map((r) => r.call)).toEqual(["OH2GBA", "OH2PU-9", "OH2RDG"]);
  });
  it("keeps only the stations heard on the radio when asked: those known from the internet alone go, an iGate's and ours stay", () => {
    const heard = [
      station("OH2RF", { heard_rf: 2 }),
      station("OH2BOTH", { heard_rf: 1, heard_is: 3 }),
      station("OH2GATED", { heard_rf: 0, heard_rf_gated: 1 }),
      station("OH2NET", { heard_rf: 0, heard_is: 2 }),
      station("OH2GBA", { is_me: true, heard_rf: 0 }),
    ];
    expect(listStations(heard, { ...base, rfOnly: true }).map((r) => r.call)).toEqual(["OH2GBA", "OH2BOTH", "OH2GATED", "OH2RF"]);
    expect(listStations(heard, { ...base, rfOnly: false }).map((r) => r.call)).toEqual(["OH2GBA", "OH2BOTH", "OH2GATED", "OH2NET", "OH2RF"]);
  });
  it("sorts by when the station was last heard direct, the latest first, a station never heard direct last either way", () => {
    const direct = [station("A", { last_direct_at: ago(600) }), station("B", { last_direct_at: null }), station("C", { last_direct_at: ago(60) })];
    expect(firstDirection("last_direct_at")).toBe(-1);
    expect(listStations(direct, { ...base, sort: { key: "last_direct_at", dir: -1 } }).map((r) => r.call)).toEqual(["C", "A", "B"]);
    expect(listStations(direct, { ...base, sort: { key: "last_direct_at", dir: 1 } }).map((r) => r.call)).toEqual(["A", "C", "B"]);
  });
  it("puts our own station on top whatever the order", () => {
    expect(listStations(rows, base).map((r) => r.call)).toEqual(["OH2GBA", "OH2PU-9", "OH2RDG", "OH2XYZ"]);
    expect(listStations(rows, { ...base, sort: { key: "call", dir: -1 } }).map((r) => r.call)).toEqual(["OH2GBA", "OH2XYZ", "OH2RDG", "OH2PU-9"]);
  });
  it("sorts by a number, a missing value last either way", () => {
    expect(listStations(rows, { ...base, sort: { key: "distance_km", dir: 1 } }).map((r) => r.call)).toEqual(["OH2GBA", "OH2PU-9", "OH2RDG", "OH2XYZ"]);
    expect(listStations(rows, { ...base, sort: { key: "distance_km", dir: -1 } }).map((r) => r.call)).toEqual(["OH2GBA", "OH2RDG", "OH2PU-9", "OH2XYZ"]);
  });
  it("sorts by the temperature of the weather stations, the stations with none last either way", () => {
    const wx = [station("A", { weather: weather({ temp_c: -3 }) }), station("B"), station("C", { weather: weather({ temp_c: 12 }) })];
    expect(listStations(wx, { ...base, sort: { key: "temp_c", dir: -1 } }).map((r) => r.call)).toEqual(["C", "A", "B"]);
    expect(listStations(wx, { ...base, sort: { key: "temp_c", dir: 1 } }).map((r) => r.call)).toEqual(["A", "C", "B"]);
    expect(firstDirection("temp_c")).toBe(-1);
  });
  it("sorts by a time, newest first when descending", () => {
    expect(listStations(rows, { ...base, sort: { key: "last_heard", dir: -1 } }).map((r) => r.call)).toEqual(["OH2GBA", "OH2XYZ", "OH2RDG", "OH2PU-9"]);
    expect(listStations(rows, { ...base, sort: { key: "last_position_at", dir: 1 } }).at(-1)?.call).toBe("OH2XYZ");
  });
  it("filters by any part of the call, the symbol name, the comment or the path, in any case", () => {
    expect(listStations(rows, { ...base, filter: "rdg" }).map((r) => r.call)).toEqual(["OH2GBA", "OH2RDG"]);
    expect(listStations(rows, { ...base, filter: "d-star" }).map((r) => r.call)).toContain("OH2PU-9");
    expect(listStations(rows, { ...base, filter: "digipeat" }).map((r) => r.call)).toContain("OH2RDG");
    expect(listStations(rows, { ...base, filter: "rch-2" })).toHaveLength(4);
  });
  it("lists the stations without a position too, and always keeps us", () => {
    expect(listStations(rows, base).map((r) => r.call)).toContain("OH2XYZ");
    expect(listStations(rows, { ...base, filter: "nothing like this" }).map((r) => r.call)).toEqual(["OH2GBA"]);
  });
  it("can leave out the stations that timed out, never ours", () => {
    const timedOut = (row: { call: string }): boolean => row.call === "OH2RDG" || row.call === "OH2GBA";
    const names = (hideTimedOut: boolean): string[] => listStations(rows, { ...base, hideTimedOut, timedOut }).map((r) => r.call);
    expect(names(true)).toEqual(["OH2GBA", "OH2PU-9", "OH2XYZ"]);
    expect(names(false)).toContain("OH2RDG");
    expect(listStations(rows, { ...base, hideTimedOut: true })).toHaveLength(4);
  });
  it("starts a column in the order people read it", () => {
    expect(firstDirection("call")).toBe(1);
    expect(firstDirection("distance_km")).toBe(1);
    expect(firstDirection("last_heard")).toBe(-1);
    expect(firstDirection("packets")).toBe(-1);
  });
});

describe("withOwnSymbol", () => {
  const settings = { "station/symbol_table": "/", "station/symbol_code": "-" };
  const bare = station("OH2GBA", { is_me: true, symbol_table: "", symbol_code: "", symbol_name: "unknown" });

  it("draws our own station with the symbol of the settings when its row has none", () => {
    const rows = new Map([
      ["OH2GBA", bare],
      ["A", station("A", { symbol_code: ">" })],
    ]);
    const shown = withOwnSymbol(rows, settings);
    expect(shown.get("OH2GBA")).toMatchObject({ symbol_table: "/", symbol_code: "-" });
    expect(shown.get("A")).toBe(rows.get("A"));
    expect(rows.get("OH2GBA")?.symbol_code).toBe("");
  });
  it("leaves the rows alone when our row has a symbol, when the settings have none, or before they are known", () => {
    const own = new Map([["OH2GBA", station("OH2GBA", { is_me: true, symbol_table: "\\", symbol_code: "#" })]]);
    expect(withOwnSymbol(own, settings)).toBe(own);
    const rows = new Map([["OH2GBA", bare]]);
    expect(withOwnSymbol(rows, undefined)).toBe(rows);
    expect(withOwnSymbol(rows, { "station/symbol_table": "/", "station/symbol_code": "" })).toBe(rows);
  });
});

it("sorts the timed-out stations after the live ones, whatever the column", () => {
  const rows = [station("OH2PU-9"), station("OH2RDG"), station("OH2XYZ")];
  const timedOut = (row: { call: string }): boolean => row.call === "OH2RDG";
  expect(listStations(rows, { ...base, hideTimedOut: false, timedOut }).map((r) => r.call)).toEqual(["OH2PU-9", "OH2XYZ", "OH2RDG"]);
  expect(listStations(rows, { ...base, hideTimedOut: false, timedOut, sort: { key: "call", dir: -1 } }).map((r) => r.call)).toEqual([
    "OH2XYZ",
    "OH2PU-9",
    "OH2RDG",
  ]);
});

describe("menuItems and panelItems", () => {
  it("has only Copy call, Show and the QRZ page in the menu of a row: the rest is in the panel", () => {
    expect(menuItems(station("OH2RDG"))).toEqual(["copy", "show", "qrz"]);
    expect(menuItems(station("OH2GBA", { is_me: true }))).toEqual(["copy", "show", "qrz"]);
    expect(menuItems(station("OH2OBJ", { kind: "object", own: true, can_message: false }))).toEqual(["copy", "show"]);
    expect(menuItems(station("Big Storm"))).toEqual(["copy", "show"]);
  });

  it("offers in the panel Message and the queries only where Message is offered, and Forget only where Forget is", () => {
    expect(panelItems(station("OH2RDG"))).toEqual(["message", "ask_position", "ask_status", "ask_heard", "ask_trace", "show", "copy", "qrz", "forget"]);
    expect(panelItems(station("EMAIL-2", { can_message: false }))).toEqual(["show", "copy", "qrz", "forget"]);
    expect(panelItems(station("OH2GBA", { is_me: true }))).toEqual(["show", "copy", "qrz"]);
    expect(panelItems(station("OH2OBJ", { kind: "object", own: true, can_message: false }))).toEqual(["show", "copy"]);
    expect(panelItems(station("FOREIGN", { kind: "object" }))).toEqual(["show", "copy", "forget"]);
  });

  it("asks for the weather only a weather station", () => {
    expect(panelItems(station("OH2MUI", { symbol_code: "_" }))).toContain("ask_weather");
    expect(panelItems(station("OH2RDG"))).not.toContain("ask_weather");
    expect(panelItems(station("OH2MUI", { symbol_code: "_", can_message: false }))).not.toContain("ask_weather");
  });

  it("puts talking to the station in a line of its own", () => {
    expect(panelItems(station("OH2RDG")).map(talksTo)).toEqual([true, true, true, true, true, false, false, false, false]);
  });
});
