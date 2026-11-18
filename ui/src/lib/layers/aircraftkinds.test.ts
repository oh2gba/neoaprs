import { describe, expect, it } from "vitest";
import { aircraftShape } from "@/lib/layers/aircraftkinds";
import { AIRCRAFT_SHAPES } from "@/lib/layers/aircraftshapes";

describe("an aircraft's kind", () => {
  it.each([
    ["A1", "light"],
    ["A2", "twin"],
    ["A3", "airliner"],
    ["A4", "airliner"],
    ["A5", "heavy"],
    ["A6", "bizjet"],
    ["A7", "helicopter"],
    ["B1", "glider"],
    ["B2", "balloon"],
    ["B3", "unknown"],
    ["B4", "light"],
    ["B6", "drone"],
  ])("is drawn by its emitter category %s as the %s", (category, shape) => {
    expect(aircraftShape(category, "")).toBe(shape);
  });

  it("is refined by its type designator where the category says only how heavy it is or nothing", () => {
    expect(aircraftShape("A5", "A388")).toBe("heavy4");
    expect(aircraftShape("A5", "B744")).toBe("heavy4");
    expect(aircraftShape("A3", "B789")).toBe("heavy");
    expect(aircraftShape("A2", "C25B")).toBe("bizjet");
    expect(aircraftShape("A2", "AT75")).toBe("twin");
    expect(aircraftShape("A1", "R44")).toBe("helicopter");
    expect(aircraftShape("", "EC35")).toBe("helicopter");
    expect(aircraftShape("", "H160")).toBe("helicopter");
    expect(aircraftShape("", "GLID")).toBe("glider");
    expect(aircraftShape("", "BALL")).toBe("balloon");
    expect(aircraftShape("", "Q9")).toBe("drone");
    expect(aircraftShape("", "A20N")).toBe("airliner");
    expect(aircraftShape("", "C172")).toBe("light");
  });

  it("keeps a category that names a kind whatever the designator says", () => {
    expect(aircraftShape("A7", "A320")).toBe("helicopter");
    expect(aircraftShape("B1", "C172")).toBe("glider");
    expect(aircraftShape("B6", "")).toBe("drone");
  });

  it("takes a business jet named H25B for no helicopter, and a short designator for no longer one", () => {
    expect(aircraftShape("", "H25B")).toBe("bizjet");
    expect(aircraftShape("", "C17")).toBe("heavy4");
    expect(aircraftShape("", "C172")).toBe("light");
  });

  it("is the general aircraft where nothing is known, or what is given is not in the table", () => {
    expect(aircraftShape("", "")).toBe("unknown");
    expect(aircraftShape("", "ZZZZ")).toBe("unknown");
    expect(aircraftShape("A0", "")).toBe("unknown");
    expect(aircraftShape("A3", "ZZZZ")).toBe("airliner");
  });
});

describe("the aircraft's shapes", () => {
  it("are each a path on a box of four numbers, at most 20 px, under a station's 26, and only the balloon is not turned", () => {
    for (const [name, shape] of Object.entries(AIRCRAFT_SHAPES)) {
      expect(shape.viewBox.split(" ").map(Number).every(Number.isFinite), name).toBe(true);
      expect(shape.viewBox.split(" ")).toHaveLength(4);
      expect(shape.d).toMatch(/^[Mm]/);
      expect(shape.size).toBeLessThanOrEqual(20);
      expect(shape.turns, name).toBe(name !== "balloon");
    }
  });
});
