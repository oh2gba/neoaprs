import { describe, expect, it } from "vitest";
import {
  FADE_OPACITY,
  GLIDE_STOP_SEC,
  glidedFeatures,
  inPageClock,
  nextGlides,
  reportOf,
  THING_SHAPES,
  fadeOpacity,
  kindShape,
  liveThings,
  maxAgeSec,
  thingShape,
  trafficCounts,
  trafficFeatures,
  type LayerTables,
} from "@/lib/layers/traffic";
import { LIMITS } from "@/protocol/lists";
import { NOW, ago } from "@/test/fixtures";
import { aircraft, layerThings, ship } from "@/test/layerfixtures";

const ids = (things: { id: string }[]) => things.map((thing) => thing.id);

describe("traffic: what is young enough to be drawn", () => {
  it("gives each layer and source the age the daemon drops its things at", () => {
    expect(maxAgeSec("aircraft", "receiver")).toBe(LIMITS.layers.aircraftReceiverAgeSec);
    expect(maxAgeSec("aircraft", "radarcape")).toBe(LIMITS.layers.aircraftReceiverAgeSec);
    expect(maxAgeSec("aircraft", "adsbfi")).toBe(LIMITS.layers.aircraftServiceAgeSec);
    expect(maxAgeSec("aircraft", "adsblol")).toBe(90);
    expect(maxAgeSec("ships", "fintraffic")).toBe(LIMITS.layers.shipsAgeSec);
    expect(maxAgeSec("ships", "receiver")).toBe(1800);
  });

  it("drops an aircraft of the own receiver at a minute and one of a service at a minute and a half, between two tables", () => {
    const things = [
      aircraft({ id: "a", at: ago(30) }),
      aircraft({ id: "b", at: ago(70) }),
      aircraft({ id: "c", at: ago(100) }),
    ];
    expect(ids(liveThings(layerThings("aircraft", things, { source: "receiver" }), NOW))).toEqual(["a"]);
    expect(ids(liveThings(layerThings("aircraft", things, { source: "adsbfi" }), NOW))).toEqual(["a", "b"]);
  });

  it("keeps a ship for half an hour", () => {
    const things = [ship({ id: "1", at: ago(1700) }), ship({ id: "2", at: ago(1900) })];
    expect(ids(liveThings(layerThings("ships", things, { source: "fintraffic" }), NOW))).toEqual(["1"]);
  });
});

describe("traffic: how faded a thing is", () => {
  it("fades in the four steps of a station's marker over its layer's age", () => {
    expect(FADE_OPACITY).toHaveLength(4);
    expect([0, 14, 15, 30, 45, 59].map((age) => fadeOpacity(age, 60))).toEqual([1, 1, 0.8, 0.6, 0.4, 0.4]);
    expect(fadeOpacity(1799, 1800)).toBe(0.4);
  });
});

describe("traffic: the map's features", () => {
  it("draws an aircraft as the shape of its kind turned to its heading, a ship as a hull, a thing without a direction as a diamond, and an emergency in the bad colour", () => {
    const data = trafficFeatures(
      [
        layerThings("aircraft", [
          aircraft({ id: "a", heading_deg: 225 }),
          aircraft({ id: "b", heading_deg: null }),
          aircraft({ id: "c", emergency: true, at: ago(0) }),
        ]),
        layerThings("ships", [ship({ id: "s", heading_deg: 182 }), ship({ id: "t", heading_deg: null })], {
          source: "fintraffic",
        }),
      ],
      Date.parse("2026-10-21T12:00:00Z"),
    );
    const byId = new Map(data.features.map((feature) => [feature.properties.id, feature.properties]));
    expect(byId.get("a")).toMatchObject({
      icon: "traffic-aircraft-airliner",
      rotate: 225,
      layer: "aircraft",
      key: "aircraft:a",
      rank: 0,
    });
    expect(byId.get("b")).toMatchObject({ icon: "traffic-aircraft-diamond", rotate: 0 });
    expect(byId.get("c")).toMatchObject({ icon: "traffic-aircraft-airliner-bad", rank: 1 });
    expect(byId.get("s")).toMatchObject({ icon: "traffic-ships-hull", rotate: 182, layer: "ships", key: "ships:s" });
    expect(byId.get("t")).toMatchObject({ icon: "traffic-ships-diamond" });
    expect([...byId.values()].map((one) => one.side)).toEqual([26, 16, 26, 16, 16]);
    expect(data.features.find((feature) => feature.properties.id === "a")?.geometry.coordinates).toEqual([
      24.9633, 60.3172,
    ]);
  });

  it("draws each aircraft by its kind: a helicopter, a glider, a heavy with four engines, one of which nothing is known", () => {
    const data = trafficFeatures(
      [
        layerThings("aircraft", [
          aircraft({ id: "h", category: "A7", designator: "EC35", heading_deg: 90 }),
          aircraft({ id: "g", category: "B1", designator: "", heading_deg: 10 }),
          aircraft({ id: "4", category: "A5", designator: "A388", heading_deg: 300 }),
          aircraft({ id: "u", category: "", designator: "", heading_deg: 45 }),
        ]),
      ],
      NOW,
    );
    expect(
      data.features.map((feature) => [feature.properties.id, feature.properties.icon, feature.properties.rotate]),
    ).toEqual([
      ["h", "traffic-aircraft-helicopter", 90],
      ["g", "traffic-aircraft-glider", 10],
      ["4", "traffic-aircraft-heavy4", 300],
      ["u", "traffic-aircraft-unknown", 45],
    ]);
  });

  it("never turns a balloon, and draws it as a balloon where it gives no direction; any other aircraft without one is the diamond", () => {
    const data = trafficFeatures(
      [
        layerThings("aircraft", [
          aircraft({ id: "b", category: "B2", designator: "", heading_deg: 130 }),
          aircraft({ id: "still", category: "B2", designator: "", heading_deg: null }),
          aircraft({ id: "h", category: "A7", designator: "", heading_deg: null }),
        ]),
      ],
      NOW,
    );
    expect(
      data.features.map((feature) => [feature.properties.id, feature.properties.icon, feature.properties.rotate]),
    ).toEqual([
      ["b", "traffic-aircraft-balloon", 0],
      ["still", "traffic-aircraft-balloon", 0],
      ["h", "traffic-aircraft-diamond", 0],
    ]);
  });

  it("says a thing's kind for its card and hover box whether or not it gives a direction, and has an image for every shape the map draws", () => {
    expect(kindShape("aircraft", aircraft({ category: "A7", designator: "", heading_deg: null }))).toBe("helicopter");
    expect(thingShape("aircraft", aircraft({ category: "A7", designator: "", heading_deg: null }))).toBe("diamond");
    expect(kindShape("ships", ship({ heading_deg: null }))).toBe("hull");
    expect(new Set(THING_SHAPES).size).toBe(THING_SHAPES.length);
    expect(THING_SHAPES).toEqual(
      expect.arrayContaining([
        "airliner",
        "heavy",
        "heavy4",
        "bizjet",
        "twin",
        "light",
        "helicopter",
        "glider",
        "balloon",
        "drone",
        "unknown",
        "hull",
        "diamond",
      ]),
    );
  });

  it("gives each thing its name and the opacity of its age, and leaves out what is too old", () => {
    const data = trafficFeatures(
      [
        layerThings("aircraft", [
          aircraft({ id: "new", at: ago(5) }),
          aircraft({ id: "older", at: ago(40) }),
          aircraft({ id: "gone", at: ago(61) }),
        ]),
      ],
      NOW,
    );
    expect(
      data.features.map((feature) => [feature.properties.id, feature.properties.opacity, feature.properties.name]),
    ).toEqual([
      ["new", 1, "FIN7AB"],
      ["older", 0.6, "FIN7AB"],
    ]);
  });
});

describe("traffic: the count of the Layers box", () => {
  it("counts the things drawn now, gives a dash while the source is away, and nothing for a layer without a table", () => {
    const tables: LayerTables = new Map([
      ["aircraft", layerThings("aircraft", [aircraft({ id: "a" }), aircraft({ id: "b", at: ago(120) })])],
      ["ships", layerThings("ships", [ship()], { away: true })],
    ]);
    expect(trafficCounts(tables, NOW)).toEqual({ aircraft: 1, ships: null });
    expect(trafficCounts(new Map([["ships", layerThings("ships", [])]]), NOW)).toEqual({ ships: 0 });
    expect(trafficCounts(new Map(), NOW)).toEqual({});
  });
});

describe("traffic: the things glide between their reports", () => {
  const at = new Date(NOW).toISOString();
  const coordinates = (
    tables: Parameters<typeof trafficFeatures>[0],
    glides: ReturnType<typeof nextGlides>,
    ms: number,
  ) => glidedFeatures(trafficFeatures(tables, NOW), glides, ms).features.map((one) => one.geometry.coordinates);

  const course = (layer: "aircraft" | "ships", thing: ReturnType<typeof aircraft>) =>
    reportOf(layer, thing, layerThings(layer, [thing]), 0).courseDeg;

  it("moves an aircraft along its track and a ship along its course over ground, never its heading", () => {
    expect(course("aircraft", aircraft({ heading_deg: 225, course_deg: 231 }))).toBe(231);
    expect(course("aircraft", aircraft({ heading_deg: 225, course_deg: null }))).toBeNull();
    expect(course("ships", ship({ heading_deg: 182, course_deg: 170 }))).toBe(170);
    expect(course("ships", ship({ course_deg: null }))).toBeNull();
  });

  it("tells a thing's age by the daemon's clock, and goes on by the motion's own clock", () => {
    const thing = aircraft({ at: new Date(NOW - 5000).toISOString(), course_deg: 0, speed_kmh: 360 });
    const table = layerThings("aircraft", [thing], { at: new Date(NOW).toISOString() });
    const glides = nextGlides(new Map(), [table], 1000, () => 1000);
    const [atReceipt] = coordinates([table], glides, 1000);
    const [later] = coordinates([table], glides, 3000);
    expect(atReceipt[1] - thing.lat).toBeCloseTo(0.5 / 111.195, 4);
    expect(later[1] - thing.lat).toBeCloseTo(0.7 / 111.195, 4);
  });

  it("does not move a thing whose time or whose table's time is no time, or is well after the table's", () => {
    const iso = (ms: number) => new Date(ms).toISOString();
    const report = (at: string, tableAt: string) => {
      const thing = aircraft({ at, course_deg: 0, speed_kmh: 360 });
      return reportOf("aircraft", thing, layerThings("aircraft", [thing], { at: tableAt }), 1000);
    };
    expect(report(iso(NOW - 3000), iso(NOW))).toMatchObject({ atMs: -2000, courseDeg: 0 });
    expect(report("not a time", iso(NOW))).toMatchObject({ atMs: 1000, courseDeg: null });
    expect(report(iso(NOW), "not a time")).toMatchObject({ atMs: 1000, courseDeg: null });
    expect(report(iso(NOW + 3_600_000), iso(NOW))).toMatchObject({ atMs: 1000, courseDeg: null });
  });

  it("puts a table's times on the page's clock when the page's clock is a minute ahead", () => {
    const table = layerThings("aircraft", [aircraft({ at: new Date(NOW - 5000).toISOString() })], {
      at: new Date(NOW).toISOString(),
      trails: [{ id: "461f2a", points: [[24.9, 60.3, new Date(NOW - 65_000).toISOString()]] }],
    });
    const ahead = NOW + 60_000;
    const held = inPageClock(table, ahead);
    expect(held.at).toBe(new Date(ahead).toISOString());
    expect(held.things[0].at).toBe(new Date(ahead - 5000).toISOString());
    expect(held.trails[0].points[0][2]).toBe(new Date(ahead - 65_000).toISOString());
    expect(liveThings(held, ahead)).toHaveLength(1);
    expect(inPageClock({ ...table, at: "not a time" }, ahead)).toEqual({ ...table, at: "not a time" });
  });

  it("carries an aircraft on from its report and stops it after a few report intervals", () => {
    const tables = [layerThings("aircraft", [aircraft({ at, course_deg: 0, speed_kmh: 360 })])];
    const glides = nextGlides(new Map(), tables, NOW);
    const [start] = coordinates(tables, glides, NOW);
    const [later] = coordinates(tables, glides, NOW + 10_000);
    expect(later[1] - start[1]).toBeCloseTo(1 / 111.195, 4);
    const stop = GLIDE_STOP_SEC.aircraft * 1000;
    expect(coordinates(tables, glides, NOW + stop + 60_000)).toEqual(coordinates(tables, glides, NOW + stop));
  });

  it("does not move a ship that reports no course", () => {
    const tables = [layerThings("ships", [ship({ at, course_deg: null })])];
    const glides = nextGlides(new Map(), tables, NOW);
    expect(coordinates(tables, glides, NOW + 30_000)).toEqual([[24.9601, 60.1512]]);
  });

  it("goes on from where it is drawn when the next report comes, and forgets a thing that left", () => {
    const first = [layerThings("aircraft", [aircraft({ at, course_deg: 90, speed_kmh: 720 })])];
    const glides = nextGlides(new Map(), first, NOW);
    const [before] = coordinates(first, glides, NOW + 5000);
    const next = [
      layerThings(
        "aircraft",
        [aircraft({ at: new Date(NOW + 4000).toISOString(), lon: 24.99, course_deg: 90, speed_kmh: 720 })],
        { at: new Date(NOW + 5000).toISOString() },
      ),
    ];
    const after = nextGlides(glides, next, NOW + 5000);
    const [now] = coordinates(next, after, NOW + 5000);
    expect(now[0]).toBeCloseTo(before[0], 9);
    expect(now[1]).toBeCloseTo(before[1], 9);
    expect(nextGlides(after, [layerThings("aircraft", [])], NOW + 6000).size).toBe(0);
  });

  it("starts from the newest report when the tab comes back, the tables having been emptied while it was hidden", () => {
    const old = [layerThings("aircraft", [aircraft({ at, lon: 24.9, course_deg: 90, speed_kmh: 720 })])];
    const hidden = nextGlides(nextGlides(new Map(), old, NOW), [], NOW + 1000);
    expect(hidden.size).toBe(0);
    const later = NOW + 600_000;
    const back = [
      layerThings(
        "aircraft",
        [aircraft({ at: new Date(later).toISOString(), lon: 25.4, course_deg: 90, speed_kmh: 720 })],
        { at: new Date(later).toISOString() },
      ),
    ];
    const [drawn] = coordinates(back, nextGlides(hidden, back, later), later);
    expect(drawn[0]).toBeCloseTo(25.4, 9);
  });
});
