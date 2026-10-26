import "@/test/mockmap";
import { flushPromises } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BASE_SOURCE, WORLD_SOURCE } from "@/lib/basemapstyle";
import { FakeMap, fakeState, resetFakes } from "@/test/fakemap";
import { tell } from "@/test/context";
import { mapFile, mapState } from "@/test/fixtures";
import { mountStationMap } from "@/test/stationmap";

// What stands over the map when it cannot be drawn well, and where: the daemon always has a world map, so the notes are for a file that is gone or cannot be read, and for the detailed map that is not there yet.
const props = { stations: new Map(), selected: null, focus: null, home: { lat: 60.17, lon: 24.94 }, now: 0, dark: false, aging: { defaultMin: 0 } };

async function mounted(files: { archive: boolean; world: boolean }) {
  fakeState.archive = files.archive;
  fakeState.world = files.world;
  const made = mountStationMap(props);
  await flushPromises();
  return made;
}

beforeEach(() => resetFakes());
afterEach(() => document.body.replaceChildren());

describe("the note over the map", () => {
  it("is above the first-run guide when there is no base map at all: a layer beside the map, not inside it, and the guide gives way to it", async () => {
    const { wrapper, daemon } = await mounted({ archive: false, world: false });
    daemon.guide.show();
    await flushPromises();
    expect(wrapper.find(".mapnote span").text()).toBe("No base map");
    expect(wrapper.find(".stationmap .mapnote").exists()).toBe(false); // (the map is a layer of its own, under the guide; the note is not in it)
    expect(wrapper.find(".mapnote button").exists()).toBe(false); // (the guide makes the map itself)
  });

  it("is not hidden by a rule of the style sheets: the first-run guide neither hides it nor sits over it", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const css = (name: string): string => readFileSync(resolve(__dirname, "../styles", name), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css("setup.css")).not.toMatch(/\.mapnote\s*\{[^}]*display:\s*none/);
    expect(css("map.css")).toMatch(/\.mapnote\s*\{[^}]*z-index:\s*5/); // the guide is z-index 4
    expect(css("setup.css")).toMatch(/\.setup\s*\{[^}]*z-index:\s*4/);
  });

  it("says nothing of the detailed map while the first-run guide is open (it makes the map itself), and says it when it is closed", async () => {
    const { wrapper, daemon } = await mounted({ archive: false, world: true });
    expect(wrapper.find(".mapnote span").text()).toBe("No detailed map");
    expect(wrapper.find(".mapnote button").exists()).toBe(true);
    daemon.guide.show();
    await flushPromises();
    expect(wrapper.find(".mapnote").exists()).toBe(false);
    daemon.guide.close();
    await flushPromises();
    expect(wrapper.find(".mapnote").exists()).toBe(true);
  });

  it("says nothing of the detailed map while it is being downloaded", async () => {
    const { wrapper, daemon } = await mounted({ archive: false, world: true });
    expect(wrapper.find(".mapnote").exists()).toBe(true);
    await tell(daemon, { map: mapState({ state: "downloading", step: "area", percent: 10, world: mapFile() }) });
    expect(wrapper.find(".mapnote").exists()).toBe(false);
  });

  it("says the files cannot be read when the engine cannot open their archives, and takes it back when the files are made again", async () => {
    const { wrapper } = await mounted({ archive: false, world: true });
    FakeMap.last().fire("error", { sourceId: WORLD_SOURCE, error: new Error("Wrong magic number for PMTiles archive") });
    await flushPromises();
    expect(wrapper.find(".mapnote span").text()).toBe("The map file cannot be read");
    expect(wrapper.find(".mapnote button").exists()).toBe(false); // (a detailed map would not mend the world's file)
  });

  it("does not take a missing tile for a file that cannot be read, nor an error of a source that is not drawn", async () => {
    const { wrapper } = await mounted({ archive: true, world: true });
    FakeMap.last().fire("error", { sourceId: WORLD_SOURCE, tile: { tileID: 1 }, error: new Error("tile") });
    FakeMap.last().fire("error", { sourceId: "tracks", error: new Error("x") });
    await flushPromises();
    expect(wrapper.find(".mapnote").exists()).toBe(false);
  });

  it("keeps drawing with the other file when only one cannot be read", async () => {
    const { wrapper } = await mounted({ archive: true, world: true });
    FakeMap.last().fire("error", { sourceId: BASE_SOURCE, error: new Error("Bad response code: 500") });
    await flushPromises();
    expect(wrapper.find(".mapnote").exists()).toBe(false);
    FakeMap.last().fire("error", { sourceId: WORLD_SOURCE, error: new Error("Bad response code: 500") });
    await flushPromises();
    expect(wrapper.find(".mapnote span").text()).toBe("The map file cannot be read");
    expect(wrapper.find(".mapnote button").exists()).toBe(true); // (the detailed map is there to be made again)
  });
});
