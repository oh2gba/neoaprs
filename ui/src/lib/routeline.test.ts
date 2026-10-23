import { describe, expect, it } from "vitest";
import { routeFeatures, routeHops } from "@/lib/routeline";
import { station, table } from "@/test/fixtures";

const US = { lat: 60.17, lon: 24.94 };
const stations = (extra: Parameters<typeof station>[1] = {}) =>
  table(
    station("OH2GBA", { is_me: true, lat: US.lat, lon: US.lon }),
    station("OH2PU-9", { lat: 60.2, lon: 24.65, last_route: "via OH2RCH-1 → OH2RCH-3", best_route: "via OH2RCH-1 → OH2RCH-3", ...extra }),
    station("OH2RCH-1", { lat: 60.3, lon: 24.5 }),
    station("OH2RCH-3", { lat: 60.25, lon: 24.8 }),
    station("OH2RCH-2", { lat: 60.1, lon: 24.7 }),
  );
const lines = (book: ReturnType<typeof stations>, call = "OH2PU-9") =>
  routeFeatures(book.get(call), book, US).features.flatMap((f) =>
    f.geometry.type === "LineString" ? [{ best: f.properties.best, at: f.geometry.coordinates }] : [],
  );
const dots = (book: ReturnType<typeof stations>, call = "OH2PU-9") =>
  routeFeatures(book.get(call), book, US).features.flatMap((f) => (f.geometry.type === "Point" ? [f.properties.call] : []));

describe("routeHops", () => {
  it("reads the calls of a route as the daemon words it", () => {
    expect(routeHops("via OH2RCH-2")).toEqual({ gate: null, hops: ["OH2RCH-2"] });
    expect(routeHops("via ? → OH2RCH-2")).toEqual({ gate: null, hops: ["?", "OH2RCH-2"] });
    expect(routeHops("via OH7JHF-1 (internet) → OH2RCH-3")).toEqual({ gate: "OH7JHF-1", hops: ["OH2RCH-3"] });
  });

  it("has none for a station heard direct and for no route", () => {
    expect(routeHops("direct")).toBeNull();
    expect(routeHops("")).toBeNull();
  });
});

describe("routeFeatures", () => {
  it("runs from the station through each digipeater to us, with a dot on each digipeater", () => {
    const book = stations();
    expect(lines(book)).toEqual([
      {
        best: 0,
        at: [
          [24.65, 60.2],
          [24.5, 60.3],
          [24.8, 60.25],
          [24.94, 60.17],
        ],
      },
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("goes straight on past a hop with no position, an anonymous one or a station we have not placed", () => {
    const book = stations({ last_route: "via ? → OH2RCH-1 → OH2NOPOS → OH2RCH-3", best_route: "via ? → OH2RCH-1 → OH2NOPOS → OH2RCH-3" });
    book.set("OH2NOPOS", station("OH2NOPOS", { lat: null, lon: null }));
    expect(lines(book)[0]?.at).toEqual([
      [24.65, 60.2],
      [24.5, 60.3],
      [24.8, 60.25],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("is a line straight to us when no hop has a position", () => {
    const book = stations({ last_route: "via ?", best_route: "via ?" });
    expect(lines(book)[0]?.at).toEqual([
      [24.65, 60.2],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual([]);
  });

  it("draws nothing for a station heard direct, for our own station, with no place of ours or no station", () => {
    const direct = stations({ last_route: "direct", best_route: "direct" });
    expect(routeFeatures(direct.get("OH2PU-9"), direct, US).features).toEqual([]);
    const book = stations();
    expect(routeFeatures(book.get("OH2GBA"), book, US).features).toEqual([]);
    expect(routeFeatures(book.get("OH2PU-9"), book, null).features).toEqual([]);
    expect(routeFeatures(undefined, book, US).features).toEqual([]);
  });

  it("draws the best route too, apart, when it is another one than the latest", () => {
    const book = stations({ last_route: "via OH2RCH-1 → OH2RCH-3", best_route: "via OH2RCH-2" });
    const found = lines(book);
    expect(found.map((l) => l.best)).toEqual([0, 1]);
    expect(found[1]?.at).toEqual([
      [24.65, 60.2],
      [24.7, 60.1],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3", "OH2RCH-2"]);
  });

  it("draws the latest route alone when the best one is direct", () => {
    const book = stations({ last_route: "via OH2RCH-2", best_route: "direct" });
    expect(lines(book).map((l) => l.best)).toEqual([0]);
  });

  it("draws the best route alone when the latest packet came direct", () => {
    const book = stations({ last_route: "direct", best_route: "via OH2RCH-2" });
    expect(lines(book).map((l) => l.best)).toEqual([1]);
  });

  it("names a digipeater once when both routes go through it", () => {
    const book = stations({ last_route: "via OH2RCH-1 → OH2RCH-3", best_route: "via OH2RCH-1" });
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("starts a third-party packet at the iGate that put it on the air", () => {
    const book = stations({ last_route: "via OH2RCH-3 (internet) → OH2RCH-1", best_route: "" });
    expect(lines(book)[0]?.at).toEqual([
      [24.8, 60.25],
      [24.5, 60.3],
      [24.94, 60.17],
    ]);
  });
});
