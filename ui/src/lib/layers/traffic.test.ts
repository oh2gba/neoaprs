import { describe, expect, it } from "vitest";
import {
  FADE_OPACITY,
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
    const things = [aircraft({ id: "a", at: ago(30) }), aircraft({ id: "b", at: ago(70) }), aircraft({ id: "c", at: ago(100) })];
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
        layerThings("ships", [ship({ id: "s", heading_deg: 182 }), ship({ id: "t", heading_deg: null })], { source: "fintraffic" }),
      ],
      Date.parse("2026-10-21T12:00:00Z"),
    );
    const byId = new Map(data.features.map((feature) => [feature.properties.id, feature.properties]));
    expect(byId.get("a")).toMatchObject({ icon: "traffic-airliner", rotate: 225, layer: "aircraft", key: "aircraft:a", rank: 0 });
    expect(byId.get("b")).toMatchObject({ icon: "traffic-diamond", rotate: 0 });
    expect(byId.get("c")).toMatchObject({ icon: "traffic-airliner-bad", rank: 1 });
    expect(byId.get("s")).toMatchObject({ icon: "traffic-hull", rotate: 182, layer: "ships", key: "ships:s" });
    expect(byId.get("t")).toMatchObject({ icon: "traffic-diamond" });
    expect(data.features.find((feature) => feature.properties.id === "a")?.geometry.coordinates).toEqual([24.9633, 60.3172]);
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
    expect(data.features.map((feature) => [feature.properties.id, feature.properties.icon, feature.properties.rotate])).toEqual([
      ["h", "traffic-helicopter", 90],
      ["g", "traffic-glider", 10],
      ["4", "traffic-heavy4", 300],
      ["u", "traffic-unknown", 45],
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
    expect(data.features.map((feature) => [feature.properties.id, feature.properties.icon, feature.properties.rotate])).toEqual([
      ["b", "traffic-balloon", 0],
      ["still", "traffic-balloon", 0],
      ["h", "traffic-diamond", 0],
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
      [layerThings("aircraft", [aircraft({ id: "new", at: ago(5) }), aircraft({ id: "older", at: ago(40) }), aircraft({ id: "gone", at: ago(61) })])],
      NOW,
    );
    expect(data.features.map((feature) => [feature.properties.id, feature.properties.opacity, feature.properties.name])).toEqual([
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
