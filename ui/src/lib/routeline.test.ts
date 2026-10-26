import { describe, expect, it } from "vitest";
import { routeFeatures, routeHops } from "@/lib/routeline";
import { ago, station, table } from "@/test/fixtures";
import type { StationRow } from "@/protocol/protocol";

type Mark = StationRow["route_marks"][number];

const US = { lat: 60.17, lon: 24.94 };
/** A route the way the daemon tells it; `lat` and `lon` are where the station was when the packet was heard. */
const mark = (kind: Mark["kind"], hops: string[] = [], extra: Partial<Mark> = {}): Mark => ({
  kind,
  hops,
  gate: "",
  at: ago(60),
  lat: null,
  lon: null,
  ...extra,
});
const rf = (...hops: string[]): Mark => mark("rf", hops);
const gated = (gate: string, ...hops: string[]): Mark => mark("gated", hops, { gate });
const heardBy = (gate: string, ...hops: string[]): Mark => mark("igate", hops, { gate });

const stations = (marks: Mark[] = [rf("OH2RCH-1", "OH2RCH-3")], extra: Partial<StationRow> = {}) =>
  table(
    station("OH2GBA", { is_me: true, lat: US.lat, lon: US.lon }),
    station("OH2PU-9", { lat: 60.2, lon: 24.65, route_marks: marks, ...extra }),
    station("OH2RCH-1", { lat: 60.3, lon: 24.5 }),
    station("OH2RCH-3", { lat: 60.25, lon: 24.8 }),
    station("OH2RCH-2", { lat: 60.1, lon: 24.7 }),
    station("OH2GW-10", { lat: 60.05, lon: 24.3 }),
    station("OH2NOPOS", { lat: null, lon: null }),
  );
const features = (book: ReturnType<typeof stations>, call = "OH2PU-9") => routeFeatures(book.get(call), book, US).features;
const lines = (book: ReturnType<typeof stations>, call = "OH2PU-9") =>
  features(book, call).flatMap((f) => (f.geometry.type === "LineString" ? [{ previous: f.properties.previous, at: f.geometry.coordinates }] : []));
const dots = (book: ReturnType<typeof stations>, call = "OH2PU-9") =>
  features(book, call).flatMap((f) => (f.geometry.type === "Point" ? [f.properties.call] : []));

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

describe("routeFeatures: a route heard on the radio", () => {
  it("runs from the station through each digipeater to us, with a dot on each digipeater", () => {
    const book = stations();
    expect(lines(book)).toEqual([
      {
        previous: 0,
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
    const book = stations([rf("?", "OH2RCH-1", "OH2NOPOS", "OH2RCH-3")]);
    expect(lines(book)[0]?.at).toEqual([
      [24.65, 60.2],
      [24.5, 60.3],
      [24.8, 60.25],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("is a line straight to us when no hop has a position", () => {
    const book = stations([rf("?")]);
    expect(lines(book)[0]?.at).toEqual([
      [24.65, 60.2],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual([]);
  });

  it("draws nothing for a station heard direct, for our own station, with no place of ours, no route or no station", () => {
    const direct = stations([rf()]);
    expect(features(direct)).toEqual([]);
    const book = stations();
    expect(routeFeatures(book.get("OH2GBA"), book, US).features).toEqual([]);
    expect(routeFeatures(book.get("OH2PU-9"), book, null).features).toEqual([]);
    expect(routeFeatures(undefined, book, US).features).toEqual([]);
    expect(features(stations([]))).toEqual([]);
  });

  it("starts a third-party packet at the iGate that put it on the air", () => {
    const book = stations([gated("OH2RCH-3", "OH2RCH-1")]);
    expect(lines(book)[0]?.at).toEqual([
      [24.8, 60.25],
      [24.5, 60.3],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-3", "OH2RCH-1"]);
  });
});

describe("routeFeatures: the latest route and the one before it, and no others", () => {
  it("draws the route before the latest one, greyed, when it came another way", () => {
    const book = stations([rf("OH2RCH-1", "OH2RCH-3"), rf("OH2RCH-2")]);
    const found = lines(book);
    expect(found.map((l) => l.previous)).toEqual([0, 1]);
    expect(found[1]?.at).toEqual([
      [24.65, 60.2],
      [24.7, 60.1],
      [24.94, 60.17],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3", "OH2RCH-2"]);
  });

  it("draws only the two the daemon tells, the latest first, however many it were", () => {
    const book = stations([rf("OH2RCH-1"), rf("OH2RCH-2"), rf("OH2RCH-3")]);
    expect(lines(book).map((l) => l.previous)).toEqual([0, 1]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-2"]);
  });

  it("draws the latest alone when the packet before it came the same way (the daemon tells one)", () => {
    expect(lines(stations([rf("OH2RCH-2")])).map((l) => l.previous)).toEqual([0]);
  });

  it("draws the route before alone, greyed, when the latest packet came direct or from an app (they have no line)", () => {
    expect(lines(stations([rf(), rf("OH2RCH-2")])).map((l) => l.previous)).toEqual([1]);
    expect(lines(stations([mark("app"), rf("OH2RCH-2")])).map((l) => l.previous)).toEqual([1]);
  });

  it("draws the latest alone when the one before it has no line", () => {
    expect(lines(stations([rf("OH2RCH-2"), mark("app")])).map((l) => l.previous)).toEqual([0]);
  });

  it("names a digipeater once when both routes go through it", () => {
    const book = stations([rf("OH2RCH-1", "OH2RCH-3"), rf("OH2RCH-1")]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
  });

  it("starts each route where the moving station was when its packet was heard, else where it is", () => {
    const book = stations();
    book.set("OH2PU-9", {
      ...book.get("OH2PU-9")!,
      route_marks: [
        { ...rf("OH2RCH-1"), lat: 60.4, lon: 25.1 },
        { ...rf("OH2RCH-2"), lat: 60.01, lon: 24.2 },
      ],
    });
    expect(lines(book).map((l) => l.at[0])).toEqual([
      [25.1, 60.4],
      [24.2, 60.01],
    ]);
    book.set("OH2PU-9", { ...book.get("OH2PU-9")!, route_marks: [{ ...rf("OH2RCH-1"), lat: 60.4, lon: 25.1 }, rf("OH2RCH-2")] });
    expect(lines(book).map((l) => l.at[0])).toEqual([
      [25.1, 60.4],
      [24.65, 60.2],
    ]);
  });

  it("draws no route of a station that has no place at all", () => {
    const book = stations([rf("OH2RCH-1")], { lat: null, lon: null });
    expect(features(book)).toEqual([]);
  });
});

describe("routeFeatures: a packet an iGate heard on the radio and put on the internet", () => {
  it("runs from the station through its digipeaters to the iGate, which ends it with its call and the internet mark", () => {
    const book = stations([heardBy("OH2GW-10", "OH2RCH-2")]);
    expect(lines(book)).toEqual([
      {
        previous: 0,
        at: [
          [24.65, 60.2],
          [24.7, 60.1],
          [24.3, 60.05],
        ],
      },
    ]);
    const end = features(book).find((f) => f.geometry.type === "Point" && f.properties.call === "OH2GW-10");
    expect(end?.properties).toMatchObject({ end: 1, previous: 0, label: "OH2GW-10 → internet" });
    expect(dots(book)).toEqual(["OH2RCH-2", "OH2GW-10"]);
  });

  it("runs straight to the iGate when it heard the station direct", () => {
    expect(lines(stations([heardBy("OH2GW-10")]))[0]?.at).toEqual([
      [24.65, 60.2],
      [24.3, 60.05],
    ]);
  });

  it("ends at the last digipeater that has a position when the iGate has none, with no dot for the iGate", () => {
    const book = stations([heardBy("OH2UNKNOWN", "OH2RCH-1", "OH2RCH-3")]);
    expect(lines(book)[0]?.at).toEqual([
      [24.65, 60.2],
      [24.5, 60.3],
      [24.8, 60.25],
    ]);
    expect(dots(book)).toEqual(["OH2RCH-1", "OH2RCH-3"]);
    expect(dots(stations([heardBy("OH2NOPOS", "OH2RCH-1")]))).toEqual(["OH2RCH-1"]);
  });

  it("has no line when the iGate has no position and no digipeater has one either", () => {
    expect(features(stations([heardBy("OH2NOPOS", "?")]))).toEqual([]);
    expect(features(stations([heardBy("OH2NOPOS")]))).toEqual([]);
  });

  it("is never a line to us: the packet reached the internet there", () => {
    const book = stations([heardBy("OH2GW-10", "OH2RCH-2")]);
    expect(lines(book)[0]?.at.some(([lon, lat]) => lon === US.lon && lat === US.lat)).toBe(false);
  });

  it("has no line for a packet that never was on the air", () => {
    expect(features(stations([mark("app")]))).toEqual([]);
  });

  it("is the latest, solid, with the radio route before it greyed, and the other way round", () => {
    const one = stations([heardBy("OH2GW-10", "OH2RCH-2"), rf("OH2RCH-1")]);
    expect(lines(one).map((l) => l.previous)).toEqual([0, 1]);
    expect(lines(one)[1]?.at.at(-1)).toEqual([US.lon, US.lat]);
    const other = stations([rf("OH2RCH-1"), heardBy("OH2GW-10", "OH2RCH-2")]);
    expect(lines(other).map((l) => l.previous)).toEqual([0, 1]);
    expect(lines(other)[1]?.at.at(-1)).toEqual([24.3, 60.05]);
    expect(
      features(other)
        .filter((f) => f.geometry.type === "Point" && "end" in f.properties && f.properties.end === 1)
        .map((f) => f.properties.previous),
    ).toEqual([1]);
  });
});
