import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import MapFetchPanel from "@/components/MapFetchPanel.vue";
import type { MapState } from "@/protocol/protocol";
import { mapFile, mapState } from "@/test/fixtures";

const ESTIMATE = { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" };

function make(map: MapState, stale = false, early = false) {
  const send = vi.fn(() => true);
  const wrapper = mount(MapFetchPanel, { props: { map, stale, send, early } });
  const button = (label: string) => wrapper.findAll("button").find((b) => b.text() === label);
  return { wrapper, send, button };
}

describe("MapFetchPanel", () => {
  it("has Estimate and Download, both on, and nothing else while no map is made", () => {
    const { wrapper, button } = make(mapState());
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Estimate", "Download"]);
    expect(button("Estimate")?.attributes("disabled")).toBeUndefined();
    expect(button("Download")?.attributes("disabled")).toBeUndefined();
    expect(wrapper.find("progress").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-size").exists()).toBe(false);
    expect(wrapper.find(".mapfetch-file").exists()).toBe(false);
  });

  it("asks the daemon to estimate, and to download", async () => {
    const { send, button } = make(mapState());
    await button("Estimate")?.trigger("click");
    await button("Download")?.trigger("click");
    expect(send.mock.calls).toEqual([[{ cmd: "map_estimate" }], [{ cmd: "map_fetch" }]]);
  });

  it("shows the size beside the button when the estimate is for the area and the detail of the settings", () => {
    expect(
      make(mapState({ estimate: ESTIMATE }))
        .wrapper.find(".mapfetch-size")
        .text(),
    ).toBe("Download size 493 MB");
    expect(
      make(mapState({ estimate: ESTIMATE, radius_km: 200 }))
        .wrapper.find(".mapfetch-size")
        .exists(),
    ).toBe(false);
  });

  it("asks again, with the size on the button, before a download over 200 MB, and sends it on the second press", async () => {
    const { send, button, wrapper } = make(mapState({ estimate: ESTIMATE }));
    await button("Download")?.trigger("click");
    expect(send).not.toHaveBeenCalled();
    expect(button("Download 493 MB?")).toBeDefined();
    await button("Download 493 MB?")?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "map_fetch" });
    expect(wrapper.findAll("button").map((b) => b.text())).toContain("Download");
  });

  it("downloads at once when the estimate is small, and when there is none", async () => {
    const small = make(mapState({ estimate: { ...ESTIMATE, bytes: 60_000_000 } }));
    await small.button("Download")?.trigger("click");
    expect(small.send).toHaveBeenCalledWith({ cmd: "map_fetch" });
  });

  it("shows a bar with the percent and the step while a job runs, and Cancel instead of enabled buttons", async () => {
    const { wrapper, send, button } = make(mapState({ state: "downloading", step: "world", percent: 42, blocked: "a map job is running" }));
    expect(wrapper.find("progress").attributes("value")).toBe("42");
    expect(wrapper.find(".mapfetch-progress").text()).toBe("World map 42%");
    expect(button("Estimate")?.attributes("disabled")).toBeDefined();
    expect(button("Download")?.attributes("disabled")).toBeDefined();
    await button("Cancel")?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "map_cancel" });
  });

  it("has a bar without a value when the step cannot say how far it is, and none of the size while it works", () => {
    const { wrapper } = make(mapState({ state: "estimating", step: "build", percent: null, estimate: ESTIMATE }));
    expect(wrapper.find("progress").attributes("value")).toBeUndefined();
    expect(wrapper.find(".mapfetch-size").exists()).toBe(false);
  });

  it("is off, with the reason as the hover, when the daemon says no job can start", () => {
    const { button } = make(mapState({ blocked: "the station has no position yet: set Latitude and Longitude (the map is cut round them)", box: null }));
    for (const label of ["Estimate", "Download"]) {
      expect(button(label)?.attributes("disabled")).toBeDefined();
      expect(button(label)?.attributes("title")).toContain("no position");
    }
  });

  it("is off, asking to save first, while the form has map settings that are not saved", () => {
    const { button } = make(mapState(), true);
    for (const label of ["Estimate", "Download"]) {
      expect(button(label)?.attributes("disabled")).toBeDefined();
      expect(button(label)?.attributes("title")).toBe("Save first");
    }
  });

  it("shows why the last job failed, and only in the state error", () => {
    expect(
      make(mapState({ state: "error", problem: "no daily build was found" }))
        .wrapper.find(".mapfetch-error")
        .text(),
    ).toBe("no daily build was found");
    expect(
      make(mapState({ state: "none", problem: "" }))
        .wrapper.find(".mapfetch-error")
        .exists(),
    ).toBe(false);
  });

  it("tells the maps that are there: the area, the detail, the size and the day, and the world's", () => {
    const { wrapper } = make(mapState({ state: "ready", detail: mapFile(), world: mapFile({ bytes: 15_100_000, max_zoom: 5 }) }));
    expect(wrapper.findAll(".mapfetch-file").map((p) => p.text())).toEqual([
      "Detailed map here: 58.8N to 61.5N, 22.1E to 27.8E, zoom 12, 123 MB, 2026-10-22",
      "World map here: zoom 5, 15 MB, 2026-10-22",
    ]);
  });

  it("explains nothing in sentences: no hint under the buttons", () => {
    const { wrapper } = make(mapState({ state: "ready", detail: mapFile() }));
    expect(wrapper.find(".hint").exists()).toBe(false);
    expect(wrapper.findAll("p").every((p) => p.classes().some((c) => c === "mapfetch-file" || c === "mapfetch-error"))).toBe(true);
  });

  it("keeps the buttons on for an early form (the first-run guide) when the daemon has no position yet, and off for a job that runs or a form that cannot be saved", () => {
    const blocked = mapState({ blocked: "no position" });
    expect(make(blocked).button("Estimate")?.attributes("disabled")).toBeDefined();
    const early = make(blocked, false, true);
    expect(early.button("Estimate")?.attributes("disabled")).toBeUndefined();
    expect(early.button("Download")?.attributes("title")).toBeUndefined();
    expect(make(blocked, true, true).button("Download")?.attributes("disabled")).toBeDefined();
    expect(make(blocked, true, true).button("Download")?.attributes("title")).toBeUndefined();
    expect(
      make(mapState({ state: "downloading", step: "area", percent: 3 }), false, true)
        .button("Download")
        ?.attributes("disabled"),
    ).toBeDefined();
  });
});
