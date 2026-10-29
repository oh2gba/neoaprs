import { describe, expect, it } from "vitest";
import { choicesFor, firstHops, hopsOf, nextHops, pathOf, reversedRoute, typedHops } from "@/lib/pathbuilder";
import type { StationRow } from "@/protocol/protocol";
import { ago, station } from "@/test/fixtures";

/** A station of which no route is known, but what a test gives. */
const quiet = (call: string, extra: Partial<StationRow> = {}): StationRow =>
  station(call, { heard_via: [], last_route: "", best_route: "", route_marks: [], suggested_path: null, ...extra });
const digi = (call: string, extra: Partial<StationRow> = {}): StationRow => quiet(call, { symbol_table: "/", symbol_code: "#", ...extra });
const mark = (hops: string[]): StationRow["route_marks"][number] => ({ kind: "rf", hops, gate: "", at: ago(60), lat: null, lon: null });

describe("a path as the builder holds it", () => {
  it("is its hops, and none for DIRECT and for an empty field", () => {
    expect(hopsOf("oh2rdk-7, OH2RCH-2")).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(hopsOf("DIRECT")).toEqual([]);
    expect(hopsOf("")).toEqual([]);
  });

  it("goes to the field as calls separated by commas, DIRECT for none", () => {
    expect(pathOf(["OH2RDK-7", "OH2RCH-2"])).toBe("OH2RDK-7,OH2RCH-2");
    expect(pathOf([])).toBe("DIRECT");
  });

  it("takes a typed hop that is a call with an SSID or an alias, one or several, and nothing else", () => {
    expect(typedHops(" oh2rdk-7 ")).toEqual(["OH2RDK-7"]);
    expect(typedHops("WIDE2-2,OH2RCH-2")).toEqual(["WIDE2-2", "OH2RCH-2"]);
    expect(typedHops("")).toBeNull();
    expect(typedHops("DIRECT")).toBeNull();
    expect(typedHops("OH2RDK-16")).toBeNull();
    expect(typedHops("OH2 RDK")).toBeNull();
  });
});

describe("the first hop", () => {
  it("is a digipeater we hear direct, the one that repeated the most for us first, then the one heard direct last", () => {
    const rows = [
      quiet("OH2A", { heard_via: [["OH2RCH-2", 30]] }),
      quiet("OH2B", {
        heard_via: [
          ["OH2RDK-7", 4],
          ["?", 9],
        ],
      }),
      digi("OH2RDG", { heard_direct: 2, last_direct_at: ago(60), distance_km: 16 }),
      digi("OH2RCH-2", { heard_direct: 5, last_direct_at: ago(600), distance_km: 14 }),
      digi("OH2FAR", { heard_direct: 0, last_direct_at: null }),
    ];
    expect(firstHops(rows)).toEqual([
      { call: "OH2RCH-2", count: 30, at: ago(600), km: 14 },
      { call: "OH2RDK-7", count: 4, at: null, km: null },
      { call: "OH2RDG", count: 0, at: ago(60), km: 16 },
    ]);
  });
});

describe("a hop after another", () => {
  const rows = [
    quiet("OH2A", { best_route: "via OH2RDK-7 → OH2RCH-2", last_route: "via OH2RDK-7 → OH2RCH-2" }),
    quiet("OH2B", { route_marks: [mark(["OH2RCH-2", "OH2RDK-7"]), mark(["OH2RCH-3", "OH2RDK-7"])] }),
    quiet("OH2C", { best_route: "via OH7JHF-1 (internet) → OH2RCH-3 → OH2RDK-7" }),
    quiet("OH2D", { last_route: "via ? → OH2RDK-7" }),
    digi("OH2RCH-2", { distance_km: 14 }),
    quiet("OH2GBA", { is_me: true, best_route: "via OH2GBA → OH2RDK-7" }),
  ];

  it("is a digipeater seen next to it in the routes, either way round, counted once for each station", () => {
    expect(nextHops(rows, "OH2RDK-7", ["OH2RDK-7"])).toEqual([
      { call: "OH2RCH-2", count: 2, at: null, km: 14 },
      { call: "OH2RCH-3", count: 2, at: null, km: null },
    ]);
  });

  it("leaves out the hops already in the path", () => {
    expect(nextHops(rows, "OH2RCH-2", ["OH2RDK-7", "OH2RCH-2"])).toEqual([]);
  });

  it("is offered for the first three hops, and not after an alias", () => {
    expect(choicesFor(rows, [])?.after).toBeNull();
    expect(choicesFor(rows, ["OH2RDK-7"])?.choices.map((c) => c.call)).toEqual(["OH2RCH-2", "OH2RCH-3"]);
    expect(choicesFor(rows, ["WIDE1-1"])).toBeNull();
    expect(choicesFor(rows, ["OH2RDK-7", "OH2RCH-2", "OH2RCH-3"])).toBeNull();
  });
});

describe("as its packets come", () => {
  it("is the station's best route turned round, none for one heard direct, and nothing for one with no route", () => {
    const rows = new Map([
      ["OH2DPN", quiet("OH2DPN", { suggested_path: "OH2RDK-7,OH2RCH-2" })],
      ["OH2NEAR", quiet("OH2NEAR", { suggested_path: "" })],
      ["OH2NONE", quiet("OH2NONE")],
    ]);
    expect(reversedRoute(rows, "OH2DPN")).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(reversedRoute(rows, "OH2NEAR")).toEqual([]);
    expect(reversedRoute(rows, "OH2NONE")).toBeNull();
    expect(reversedRoute(rows, "OH2GONE")).toBeNull();
  });
});
