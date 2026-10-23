import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap, FakeMarker, fakeState } from "@/test/fakemap";
import { mapFile, mapState, packet } from "@/test/fixtures";
import { open, stations, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: stations and the map", () => {
  it("shows the four stations on the map and in the table", async () => {
    const { wrapper } = await open();
    expect(FakeMarker.live()).toHaveLength(3); // the fourth has no position
    expect(wrapper.findAll("#pane-stations tbody tr")).toHaveLength(4);
    expect(wrapper.find("#pane-stations tbody tr").text()).toContain("OH2GBA");
    expect(FakeMap.last().jumps).toEqual([{ center: [24.94, 60.17], zoom: 9 }]); // the map opened on the world before the daemon said where we are
  });

  it("keeps a timed out station off the map but in the table, and shows it while it is selected", async () => {
    const { wrapper, socket } = await open();
    const before = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [
        { op: "set", key: "OH2RDG", value: { ...stations.OH2RDG, last_position_at: before(4 * 3600) } },
        { op: "set", key: "OH2PU-9", value: { ...stations["OH2PU-9"], last_position_at: before(60) } },
      ],
    });
    await flushPromises();
    const shown = () => FakeMarker.live().map((m) => m.element.textContent);
    expect(shown()).not.toContain("OH2RDG");
    expect(shown()).toContain("OH2PU-9");
    const row = () => wrapper.findAll("#pane-stations tbody tr").find((r) => r.text().includes("OH2RDG"));
    expect(row()?.text()).toContain("timed out");
    await row()?.trigger("click");
    await flushPromises();
    expect(FakeMap.last().flights).toHaveLength(1);
    expect(shown()).toContain("OH2RDG");
    expect(wrapper.find(".card").text()).toContain("timed out");
    await wrapper.find(".card button[aria-label='Close']").trigger("click");
    await flushPromises();
    expect(shown()).not.toContain("OH2RDG");
  });

  it("draws our own station with the symbol of the settings, the daemon having heard none", async () => {
    await open();
    const ours = FakeMarker.live().find((m) => m.element.textContent === "OH2GBA");
    expect(ours?.element.querySelectorAll(".stn-layer")).toHaveLength(1);
  });

  it("shows the packets as they arrive, newest first", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Packets")?.trigger("click");
    expect(wrapper.find("#pane-packets tbody tr").text()).toContain("second");
    socket.say({ type: "patch", topic: "packets", rev: 1, ops: [{ op: "set", key: "3", value: packet(3, { summary: "third" }) }] });
    await flushPromises();
    expect(wrapper.find("#pane-packets tbody tr").text()).toContain("third");
  });

  it("selects a station by a marker, shows its card, and forgets it", async () => {
    const { wrapper, socket } = await open();
    FakeMarker.live()
      .find((m) => m.element.textContent === "OH2PU-9")
      ?.element.click();
    await flushPromises();
    expect(wrapper.find(".card").text()).toContain("OH2PU-9");
    expect(wrapper.find("#pane-stations tr.selected").text()).toContain("OH2PU-9");
    await wrapper.find(".card-foot .forget").trigger("click");
    await wrapper.find(".card-foot .forget").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "forget_station", call: "OH2PU-9" });
    expect(wrapper.find(".card").exists()).toBe(false);
  });

  it("flies the map to a station picked in the table", async () => {
    const { wrapper } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2RDG"))
      ?.trigger("click");
    await flushPromises();
    expect(FakeMap.last().flights).toHaveLength(1);
    expect(wrapper.find(".card").text()).toContain("OH2RDG");
  });

  it("lets go of a station the daemon no longer has", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2RDG"))
      ?.trigger("click");
    socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "del", key: "OH2RDG" }] });
    await flushPromises();
    expect(wrapper.find(".card").exists()).toBe(false);
  });

  it("sets and clears the timeout of a station from its card, takes it from the daemon, and keeps it out of the conversation", async () => {
    const { wrapper, socket } = await open();
    await wrapper
      .findAll("#pane-stations tbody tr")
      .find((r) => r.text().includes("OH2PU-9"))
      ?.trigger("click");
    const field = () => wrapper.find<HTMLInputElement>(".card .timeout-input");
    await field().setValue("45");
    expect(socket.sent).toContainEqual({ cmd: "set_station_timeout", call: "OH2PU-9", minutes: 45 });
    socket.say({
      type: "patch",
      topic: "station_prefs",
      rev: 1,
      ops: [{ op: "set", key: "OH2PU-9", value: { path: null, hide_after_min: 45, rf_only: false } }],
    });
    await flushPromises();
    expect(field().element.value).toBe("45");
    await wrapper.find(".card .timeoutbox .use-default").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "clear_station_timeout", call: "OH2PU-9" });
    await tabButton(wrapper, "Messages")?.trigger("click");
    await wrapper.find("#pane-messages .conv").trigger("click");
    expect(wrapper.find("#pane-messages .timeout-input").exists()).toBe(false); // the map timeout is the station's, not the conversation's
  });

  it("offers the download on the map when there is no base map, and the button opens the Settings tab", async () => {
    fakeState.archive = false;
    const { wrapper } = await open();
    expect(wrapper.find(".mapnote span").text()).toBe("No base map");
    await wrapper.find(".mapnote button").trigger("click");
    expect(tabButton(wrapper, "Settings")?.attributes("aria-selected")).toBe("true");
  });

  it("sets the map's style again when the daemon has made the files", async () => {
    const { socket } = await open();
    socket.say({ type: "state", topic: "map", rev: 0, value: mapState({ state: "downloading", step: "area", percent: 50 }) });
    await flushPromises();
    expect(FakeMap.last().styles).toHaveLength(1);
    socket.say({
      type: "patch",
      topic: "map",
      rev: 1,
      ops: [{ op: "replace", value: mapState({ state: "ready", detail: mapFile(), world: mapFile({ name: "basemap-world.pmtiles" }) }) }],
    });
    await flushPromises();
    expect(FakeMap.last().styles).toHaveLength(2);
  });
});
