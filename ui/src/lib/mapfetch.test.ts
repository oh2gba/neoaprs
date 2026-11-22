import { describe, expect, it } from "vitest";
import { bytesText } from "@/lib/format";
import { blockedText, currentEstimate, downloadedLine, filesKey, isRunning, problemText, progressText, setupMapLine } from "@/lib/mapfetch";
import type { MapState } from "@/protocol/protocol";
import { mapFile, mapState } from "@/test/fixtures";

describe("bytesText", () => {
  it("writes thousands, with a digit only below ten", () => {
    expect([0, 512, 15_000, 9_500_000, 15_400_000, 493_000_000, 1_240_000_000, 12_300_000_000].map(bytesText)).toEqual([
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
  it("chooses the unit after rounding", () => {
    expect([999_600, 999_999, 9_960, 1_048_575, 1_048_000].map(bytesText)).toEqual(["1.0 MB", "1.0 MB", "10 kB", "1.0 MB", "1.0 MB"]);
  });
});

describe("downloadedLine", () => {
  it("is one plain line with the day of the detailed map, and nothing without one (the world map ships with NeoAPRS)", () => {
    expect(downloadedLine(mapState({ detail: mapFile() }))).toBe("Map downloaded 22 Oct");
    expect(downloadedLine(mapState({ detail: mapFile({ modified: "2026-01-03T00:00:00Z" }) }))).toBe("Map downloaded 3 Jan");
    expect(downloadedLine(mapState({ detail: mapFile({ modified: "" }) }))).toBe("Map downloaded");
    expect(downloadedLine(mapState({ world: mapFile({ max_zoom: 5 }) }))).toBe("");
    expect(downloadedLine(mapState())).toBe("");
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
    expect(progressText(mapState({ state: "estimating", step: "build", percent: null }))).toBe("Finding the latest build");
    expect(progressText(mapState({ state: "estimating", step: "", percent: null }))).toBe("Estimating");
  });

  it("shows the size downloaded so far next to the percent, and says when it is trying again", () => {
    expect(progressText(mapState({ state: "downloading", step: "area", percent: 49, downloaded: 340_000_000 }))).toBe("Map of the area 49% · 340 MB");
    expect(progressText(mapState({ state: "downloading", step: "area", percent: 0, downloaded: 0 }))).toBe("Map of the area 0%");
    expect(progressText(mapState({ state: "downloading", step: "world", percent: null, downloaded: 12_300_000 }))).toBe("World map · 12 MB");
    expect(progressText(mapState({ state: "downloading", step: "area", percent: null, retry: { attempt: 2, tries: 3 } }))).toBe(
      "Map of the area · no progress: trying again (2 of 3)",
    );
  });
});

describe("the problem and the block", () => {
  it("say the daemon's code in the page's words, with its values", () => {
    expect(problemText(mapState({ problem: { code: "no_build", params: { days: 7 } } }))).toBe(
      "no daily build of the map was found in the last 7 days (is there a connection?)",
    );
    expect(blockedText(mapState({ blocked: "busy" }))).toBe("a map job is running");
    expect([problemText(mapState()), blockedText(mapState())]).toEqual(["", ""]);
  });

  it("do not throw on what a daemon of another build sends (an English sentence, a code the page does not know)", () => {
    const other = mapState({ blocked: "a map job is running" as MapState["blocked"], problem: "the map could not be made" as unknown as MapState["problem"] });
    expect(blockedText(other)).toBe("");
    expect(problemText(other)).toBe("the map could not be made; the log says why");
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

describe("setupMapLine", () => {
  it("is the quiet line of the guide while the detailed map is being made", () => {
    expect(setupMapLine(mapState({ state: "downloading", step: "area", percent: 12 }))).toBe("setup.map_auto");
    expect(setupMapLine(mapState({ state: "ready", detail: mapFile() }))).toBe("");
  });

  it("says the detailed map will come when online, when the daemon could not fetch it yet (and no job runs)", () => {
    expect(setupMapLine(mapState({ state: "error", problem: { code: "no_build", params: { days: 10 } }, later: true }))).toBe("setup.map_later");
    expect(setupMapLine(mapState({ state: "downloading", later: true }))).toBe("setup.map_auto");
  });

  it("is none without a map state, with a detailed map, or when all is quiet", () => {
    expect(setupMapLine(null)).toBe("");
    expect(setupMapLine(mapState({ state: "ready", detail: mapFile(), later: true }))).toBe("");
    expect(setupMapLine(mapState())).toBe("");
  });
});
