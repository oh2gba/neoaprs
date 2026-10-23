import { describe, expect, it } from "vitest";
import { currentEstimate, describeFile, DETAIL_CHOICES, fileLines, filesKey, formatBox, formatBytes, formatDay, isRunning, progressText } from "@/lib/mapfetch";
import { mapFile, mapState } from "@/test/fixtures";

describe("formatBytes", () => {
  it("writes thousands, as the pmtiles program does, with a digit only below ten", () => {
    expect([0, 512, 15_000, 9_500_000, 15_400_000, 493_000_000, 1_240_000_000, 12_300_000_000].map(formatBytes)).toEqual([
      "0 B",
      "512 B",
      "15 kB",
      "9.5 MB",
      "15 MB",
      "493 MB",
      "1.2 GB",
      "12 GB",
    ]);
  });
});

describe("formatBox", () => {
  it("writes the south and the north, the west and the east, with the hemisphere after each", () => {
    expect(formatBox([22.1, 58.8, 27.8, 61.5])).toBe("58.8N to 61.5N, 22.1E to 27.8E");
    expect(formatBox([-70.25, -34.5, -58.5, -30.1])).toBe("34.5S to 30.1S, 70.3W to 58.5W");
    expect(formatBox([])).toBe("");
  });
});

describe("describeFile", () => {
  it("gives the area, the deepest zoom, the size and the day of the detailed map", () => {
    expect(describeFile(mapFile(), true)).toBe("58.8N to 61.5N, 22.1E to 27.8E, zoom 12, 123 MB, 2026-10-22");
  });

  it("leaves the area out of the world's line, and the zoom of a file whose header could not be read", () => {
    expect(describeFile(mapFile({ name: "basemap-world.pmtiles", bytes: 15_100_000, max_zoom: 5 }), false)).toBe("zoom 5, 15 MB, 2026-10-22");
    expect(describeFile(mapFile({ bbox: null, max_zoom: null }), true)).toBe("123 MB, 2026-10-22");
  });

  it("is the line of the current map and then the world's", () => {
    expect(fileLines(mapState())).toEqual([]);
    expect(fileLines(mapState({ detail: mapFile(), world: mapFile({ bytes: 15_000_000, max_zoom: 5 }) }))).toEqual([
      "Detailed map here: 58.8N to 61.5N, 22.1E to 27.8E, zoom 12, 123 MB, 2026-10-22",
      "World map here: zoom 5, 15 MB, 2026-10-22",
    ]);
  });

  it("takes the day of a time stamp", () => {
    expect(formatDay("2026-10-22T23:59:59Z")).toBe("2026-10-22");
  });
});

describe("currentEstimate", () => {
  const estimate = { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" };

  it("is the estimate while the settings are the ones it was made for", () => {
    expect(currentEstimate(mapState({ estimate }))).toEqual(estimate);
  });

  it("is none when the radius or the detail has changed since, or there was none", () => {
    expect(currentEstimate(mapState({ estimate, radius_km: 100 }))).toBeNull();
    expect(currentEstimate(mapState({ estimate, maxzoom: 14 }))).toBeNull();
    expect(currentEstimate(mapState())).toBeNull();
  });
});

describe("the job", () => {
  it("is running while it estimates or downloads", () => {
    expect(["none", "ready", "error"].map((state) => isRunning(mapState({ state: state as "none" })))).toEqual([false, false, false]);
    expect(isRunning(mapState({ state: "estimating" }))).toBe(true);
    expect(isRunning(mapState({ state: "downloading" }))).toBe(true);
  });

  it("says what it is doing, with the percent when there is one", () => {
    expect(progressText(mapState({ state: "downloading", step: "world", percent: 42 }))).toBe("World map 42%");
    expect(progressText(mapState({ state: "downloading", step: "area", percent: 0 }))).toBe("Map of the area 0%");
    expect(progressText(mapState({ state: "downloading", step: "tool", percent: null }))).toBe("Fetching the pmtiles program");
    expect(progressText(mapState({ state: "estimating", step: "build", percent: null }))).toBe("Finding the latest build");
    expect(progressText(mapState({ state: "estimating", step: "", percent: null }))).toBe("Estimating");
  });

  it("shows the size downloaded so far next to the percent, and says when it is trying again", () => {
    expect(progressText(mapState({ state: "downloading", step: "area", percent: 49, downloaded: 340_000_000 }))).toBe("Map of the area 49% · 340 MB");
    expect(progressText(mapState({ state: "downloading", step: "area", percent: 0, downloaded: 0 }))).toBe("Map of the area 0%");
    expect(progressText(mapState({ state: "downloading", step: "world", percent: null, downloaded: 12_300_000 }))).toBe("World map · 12 MB");
    expect(progressText(mapState({ state: "downloading", step: "area", percent: null, note: "no progress: trying again (2 of 3)" }))).toBe(
      "Map of the area · no progress: trying again (2 of 3)",
    );
  });
});

describe("filesKey", () => {
  it("changes when a file is made again, comes or goes, and is null before the daemon has told", () => {
    const none = filesKey(mapState());
    const first = filesKey(mapState({ detail: mapFile() }));
    const again = filesKey(mapState({ detail: mapFile({ modified: "2026-10-23T08:00:00Z" }) }));
    expect(filesKey(null)).toBeNull();
    expect(new Set([none, first, again]).size).toBe(3);
    expect(filesKey(mapState({ detail: mapFile(), state: "ready" }))).toBe(first);
  });
});

describe("DETAIL_CHOICES", () => {
  it("name the three zooms with a word", () => {
    expect(DETAIL_CHOICES.map((c) => c.label)).toEqual(["10 town", "12 streets", "14 houses"]);
    expect(DETAIL_CHOICES.map((c) => c.value)).toEqual(["10", "12", "14"]);
  });
});
