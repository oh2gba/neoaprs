import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMarker } from "@/test/fakemap";
import { configValues } from "@/test/fixtures";
import { open, stations, useAppHarness } from "@/test/app";

useAppHarness();

// How long a station stays on the map is one setting of the daemon (map/station_hours), chosen in the Stations tab: the map, the dimming of the table and the trails follow it.
describe("App: the time a station stays on the map", () => {
  const before = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString();
  const shown = () => FakeMarker.live().map((m) => m.element.textContent);
  const sets = (socket: { sent: unknown[] }) => socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config");

  it("is 3 hours until the setting says otherwise: a station heard 4 hours ago is off the map and dim in the table, until the daemon says 6 hours", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [{ op: "set", key: "OH2RDG", value: { ...stations.OH2RDG, last_position_at: before(4 * 3600) } }],
    });
    await flushPromises();
    const row = () => wrapper.findAll("#pane-stations tbody tr").find((r) => r.text().includes("OH2RDG"));
    expect(shown()).not.toContain("OH2RDG");
    expect(row()?.classes()).toContain("timedout");
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "map/station_hours": "6" }) });
    await flushPromises();
    expect(shown()).toContain("OH2RDG");
    expect(row()?.classes()).not.toContain("timedout");
    socket.say({ type: "state", topic: "config", rev: 2, value: configValues({ "map/station_hours": "1" }) });
    await flushPromises();
    expect(shown()).not.toContain("OH2RDG");
    expect(row()?.classes()).toContain("timedout");
  });

  it("is chosen in the select of the Stations tab: it sends the setting at once, the map follows the daemon's answer, with no toast", async () => {
    const { wrapper, socket } = await open();
    socket.say({
      type: "patch",
      topic: "stations",
      rev: 1,
      ops: [{ op: "set", key: "OH2RDG", value: { ...stations.OH2RDG, last_position_at: before(5 * 3600) } }],
    });
    await flushPromises();
    const select = wrapper.find<HTMLSelectElement>("#pane-stations #stations-on-map");
    expect(select.element.value).toBe("3");
    expect(shown()).not.toContain("OH2RDG");
    await select.setValue("6");
    expect(sets(socket)).toEqual([{ cmd: "set_config", values: { "map/station_hours": "6" } }]);
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "map/station_hours": "6" }) });
    await flushPromises();
    expect(shown()).toContain("OH2RDG");
    expect(wrapper.find<HTMLSelectElement>("#pane-stations #stations-on-map").element.value).toBe("6");
    expect(wrapper.find(".toast").exists()).toBe(false);
  });

  it("shows what another device chose, and is not on the Settings tab", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "state", topic: "config", rev: 1, value: configValues({ "map/station_hours": "24" }) });
    await flushPromises();
    expect(wrapper.find<HTMLSelectElement>("#pane-stations #stations-on-map").element.value).toBe("24");
    expect(wrapper.find("#pane-settings #set-map-station_hours").exists()).toBe(false);
  });
});
