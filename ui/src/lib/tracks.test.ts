import { describe, expect, it } from "vitest";
import { TRAIL_OLDEST, trailOpacity, type Aging } from "@/lib/aging";
import { trackLines, trackPoints } from "@/lib/tracks";
import { NOW, ago, station } from "@/test/fixtures";

const aging = (defaultMin: number): Aging => ({ defaultMin });

describe("trackLines", () => {
  const moving = station("OH2PU-9", {
    track: [
      [ago(300), 60.1, 24.5],
      [ago(200), 60.2, 24.6],
      [ago(100), 60.3, 24.7],
    ],
  });

  it("makes a line of [lon, lat] for a station with more than one track point, none for fewer", () => {
    const lines = trackLines([moving, station("A", { track: [[ago(10), 60, 24]] }), station("B")], null, NOW, aging(1440));
    expect(lines.features).toHaveLength(1);
    expect(lines.features[0]?.geometry.coordinates).toEqual([
      [24.5, 60.1],
      [24.6, 60.2],
      [24.7, 60.3],
    ]);
    expect(lines.features[0]?.properties).toMatchObject({ call: "OH2PU-9", selected: 0, opacity: 1 });
  });
  it("marks the selected station's line", () => {
    expect(trackLines([moving], "OH2PU-9", NOW, aging(1440)).features[0]?.properties.selected).toBe(1);
  });

  const long = station("OH2LONG", {
    track: [
      [ago(3000), 60.0, 24.0],
      [ago(2000), 60.1, 24.1],
      [ago(1000), 60.2, 24.2],
      [ago(10), 60.3, 24.3],
    ],
  });

  it("fades along the track: the opacity of a stretch is that of its older point's age against the timeout, the oldest faintest", () => {
    const features = trackLines([long], null, NOW, aging(60)).features;
    const opacities = features.map((f) => f.properties.opacity);
    expect(opacities).toEqual([trailOpacity(3000, 60), trailOpacity(2000, 60), trailOpacity(1000, 60)]);
    expect(opacities).toEqual([...opacities].sort((a, b) => a - b));
    expect(opacities.at(-1)).toBeGreaterThan(opacities[0] ?? 1);
    // the stretches are joined end to end
    expect(features.map((f) => f.geometry.coordinates)).toEqual([
      [
        [24.0, 60.0],
        [24.1, 60.1],
      ],
      [
        [24.1, 60.1],
        [24.2, 60.2],
      ],
      [
        [24.2, 60.2],
        [24.3, 60.3],
      ],
    ]);
  });
  it("is one line where neighbouring stretches have the same opacity", () => {
    expect(trackLines([long], null, NOW, aging(60 * 24 * 7)).features).toHaveLength(1);
  });
  it("fades every stretch to the faintest long after the timeout", () => {
    const own = trackLines([long], null, NOW, aging(5)).features;
    expect(own).toHaveLength(1);
    expect(own[0]?.properties.opacity).toBe(TRAIL_OLDEST);
  });
  it("moves with the time: the same track is fainter later", () => {
    const later = trackLines([long], null, NOW + 1200_000, aging(60)).features;
    const now = trackLines([long], null, NOW, aging(60)).features;
    expect(later.at(-1)?.properties.opacity).toBeLessThan(now.at(-1)?.properties.opacity ?? 0);
  });

  describe("trackPoints", () => {
    it("gives the positions of the selected station's track as points, the oldest first, each with the opacity of its age", () => {
      const points = trackPoints([long, moving], "OH2LONG", NOW, aging(60)).features;
      expect(points.map((f) => f.geometry.coordinates)).toEqual([
        [24.0, 60.0],
        [24.1, 60.1],
        [24.2, 60.2],
        [24.3, 60.3],
      ]);
      expect(points.map((f) => f.properties.opacity)).toEqual([trailOpacity(3000, 60), trailOpacity(2000, 60), trailOpacity(1000, 60), trailOpacity(10, 60)]);
      expect(points.every((f) => f.properties.call === "OH2LONG")).toBe(true);
    });
    it("gives nothing for the stations not selected, for no selection, and for a station with a single position", () => {
      expect(trackPoints([long, moving], null, NOW, aging(60)).features).toEqual([]);
      expect(trackPoints([long, moving], ["OH2PU-9"], NOW, aging(60)).features).toHaveLength(3);
      expect(trackPoints([station("A", { track: [[ago(10), 60, 24]] })], "A", NOW, aging(60)).features).toEqual([]);
    });
  });
});
