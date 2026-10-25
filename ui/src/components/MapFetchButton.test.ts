import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import MapFetchButton from "@/components/MapFetchButton.vue";
import MapFetchNotes from "@/components/MapFetchNotes.vue";
import type { MapState } from "@/protocol/protocol";
import { cssRule } from "@/test/css";
import { mapFile, mapState } from "@/test/fixtures";

const ESTIMATE = { bytes: 493_000_000, tiles: 41233, radius_km: 150, maxzoom: 12, box: [22.1, 58.8, 27.8, 61.5], build: "20261022" };

function make(map: MapState, stale = false, early = false) {
  const send = vi.fn(() => true);
  const wrapper = mount(MapFetchButton, { props: { map, stale, send, early } });
  const notes = mount(MapFetchNotes, { props: { map } });
  const button = () => wrapper.find<HTMLButtonElement>("button.mapfetch-button");
  return { wrapper, notes, send, button };
}

describe("MapFetchButton", () => {
  it("is one plain button, Download map, on, and nothing else while no map is made (the blue is for the one main action of a form)", () => {
    const { wrapper, notes, button } = make(mapState());
    expect(wrapper.findAll("button").map((b) => b.text())).toEqual(["Download map"]);
    expect(button().classes()).not.toContain("primary");
    expect(button().attributes("disabled")).toBeUndefined();
    expect(notes.find("progress").exists()).toBe(false);
    expect(notes.find(".mapfetch-file").exists()).toBe(false);
    expect(notes.html()).toBe("<!--v-if-->");
  });

  it("runs the estimate on the first press, and says Checking size… until the size is known", async () => {
    const { wrapper, notes, send, button } = make(mapState());
    await button().trigger("click");
    expect(send.mock.calls).toEqual([[{ cmd: "map_estimate" }]]);
    expect(button().text()).toBe("Checking size…");
    expect(button().attributes("disabled")).toBeDefined();
    await wrapper.setProps({ map: mapState({ state: "estimating", step: "build", percent: null }) });
    expect(button().text()).toBe("Checking size…");
    await notes.setProps({ map: mapState({ state: "estimating", step: "build", percent: null }) });
    expect(notes.find(".mapfetch-progress").exists()).toBe(true);
  });

  it("then asks Download 493 MB? whatever the size, and sends the download on the second press", async () => {
    const { wrapper, send, button } = make(mapState());
    await button().trigger("click");
    await wrapper.setProps({ map: mapState({ state: "none", estimate: ESTIMATE }) });
    expect(button().text()).toBe("Download 493 MB?");
    expect(button().classes()).toContain("danger");
    expect(send).toHaveBeenCalledTimes(1);
    await button().trigger("click");
    expect(send.mock.calls).toEqual([[{ cmd: "map_estimate" }], [{ cmd: "map_fetch" }]]);
    await wrapper.setProps({ map: mapState({ state: "downloading", step: "world", percent: 1 }) });
    expect(button().classes()).not.toContain("danger");
  });

  it("asks with the size of a small map too", async () => {
    const { wrapper, button } = make(mapState());
    await button().trigger("click");
    await wrapper.setProps({ map: mapState({ estimate: { ...ESTIMATE, bytes: 60_000_000 } }) });
    expect(button().text()).toBe("Download 60 MB?");
  });

  it("takes the question back when the radius changes", async () => {
    const { wrapper, button } = make(mapState());
    await button().trigger("click");
    await wrapper.setProps({ map: mapState({ estimate: ESTIMATE }) });
    expect(button().text()).toBe("Download 493 MB?");
    await wrapper.setProps({ map: mapState({ estimate: ESTIMATE, radius_km: 200 }) });
    expect(button().text()).toBe("Download map");
  });

  it("takes the question back, and shows why, when the check fails", async () => {
    const { wrapper, notes, button } = make(mapState());
    await button().trigger("click");
    await wrapper.setProps({ map: mapState({ state: "error", problem: "no daily build was found" }) });
    expect(button().text()).toBe("Download map");
    await notes.setProps({ map: mapState({ state: "error", problem: "no daily build was found" }) });
    expect(notes.find(".mapfetch-error").text()).toBe("no daily build was found");
  });

  it("does not wait for a size when the command could not be sent", async () => {
    const send = vi.fn(() => false);
    const wrapper = mount(MapFetchButton, { props: { map: mapState(), stale: false, send } });
    await wrapper.find("button").trigger("click");
    expect(wrapper.find("button").text()).toBe("Download map");
  });

  it("is off while a job runs, says Downloading…, and has Cancel beside it (the bar and the step are under the row)", async () => {
    const { wrapper, notes, send, button } = make(mapState({ state: "downloading", step: "world", percent: 42, blocked: "a map job is running" }));
    expect(notes.find("progress").attributes("value")).toBe("42");
    expect(notes.find(".mapfetch-progress").text()).toBe("World map 42%");
    expect(button().attributes("disabled")).toBeDefined();
    expect(button().text()).toBe("Downloading…");
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "Cancel")
      ?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "map_cancel" });
  });

  it("has a bar without a value when the step cannot say how far it is", () => {
    const { notes } = make(mapState({ state: "estimating", step: "build", percent: null, estimate: ESTIMATE }));
    expect(notes.find("progress").attributes("value")).toBeUndefined();
  });

  it("is off, with the reason as the hover, when the daemon says no job can start", () => {
    const { button } = make(mapState({ blocked: "the station has no position yet: set Latitude and Longitude (the map is cut round them)", box: null }));
    expect(button().attributes("disabled")).toBeDefined();
    expect(button().attributes("title")).toContain("no position");
  });

  it("is off, saying Saving, while a map setting is being saved", () => {
    const { button } = make(mapState(), true);
    expect(button().attributes("disabled")).toBeDefined();
    expect(button().attributes("title")).toBe("Saving…");
  });

  it("shows why the last job failed, and only in the state error", () => {
    expect(
      make(mapState({ state: "error", problem: "no daily build was found" }))
        .notes.find(".mapfetch-error")
        .text(),
    ).toBe("no daily build was found");
    expect(
      make(mapState({ state: "none", problem: "" }))
        .notes.find(".mapfetch-error")
        .exists(),
    ).toBe(false);
  });

  it("says one quiet line when there is a detailed map, and then offers Download again; nothing of the world map or of the details", () => {
    const { wrapper, notes, button } = make(mapState({ state: "ready", detail: mapFile(), world: mapFile({ bytes: 15_100_000, max_zoom: 5 }) }));
    expect(notes.findAll(".mapfetch-file").map((p) => p.text())).toEqual(["Map downloaded 22 Oct"]);
    expect(notes.find(".mapfetch-file").classes()).toContain("muted");
    expect(wrapper.text() + notes.text()).not.toContain("World map");
    expect(wrapper.text() + notes.text()).not.toContain("zoom");
    expect(button().text()).toBe("Download again");
    expect(button().classes()).not.toContain("primary");
  });

  it("says nothing of the maps for a world map only", () => {
    expect(
      make(mapState({ state: "none", world: mapFile({ max_zoom: 5 }) }))
        .notes.find(".mapfetch-file")
        .exists(),
    ).toBe(false);
  });

  it("explains nothing in sentences: no hint under the button", () => {
    const { wrapper, notes } = make(mapState({ state: "ready", detail: mapFile() }));
    expect(wrapper.find(".hint").exists()).toBe(false);
    expect(notes.findAll("p").every((p) => p.classes().some((c) => c === "mapfetch-file" || c === "mapfetch-error"))).toBe(true);
  });

  it("keeps the notes under the row, in the grid of the label column, and the button wrapping under the field when the row is narrow", () => {
    expect(cssRule(".mapfetch-notes")).toMatch(/display:\s*grid/);
    expect(cssRule(".mapfetch-notes")).toContain("minmax(7em, 36%) 1fr");
    expect(cssRule(".mapfetch-notes > *")).toMatch(/grid-column:\s*2/);
    expect(cssRule(".field-control:has(.mapfetch-button)")).toMatch(/flex-wrap:\s*wrap/);
  });

  it("keeps the button on for an early form (the first-run guide) when the daemon has no position yet, and off for a job that runs or a form that cannot be saved", () => {
    const blocked = mapState({ blocked: "no position" });
    expect(make(blocked).button().attributes("disabled")).toBeDefined();
    const early = make(blocked, false, true);
    expect(early.button().attributes("disabled")).toBeUndefined();
    expect(early.button().attributes("title")).toBeUndefined();
    expect(make(blocked, true, true).button().attributes("disabled")).toBeDefined();
    expect(make(blocked, true, true).button().attributes("title")).toBeUndefined();
    expect(
      make(mapState({ state: "downloading", step: "area", percent: 3 }), false, true)
        .button()
        .attributes("disabled"),
    ).toBeDefined();
  });
});
