import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { FakeMap } from "@/test/fakemap";
import { station } from "@/test/fixtures";
import { open, stations, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

const withPhg = {
  ...stations.OH2RDG,
  extensions: {
    phg: { power_w: 25, height_m: 12.2, gain_db: 5, direction_deg: null, range_km: 21.4 },
    range_km: null,
    dfs: null,
    df_bearing: null,
    area: null,
  },
};

describe("App: the Nearby tab", () => {
  it("comes after Stations and lists the digipeaters heard, the one with the symbol and the one only heard repeating", async () => {
    const { wrapper } = await open();
    expect(wrapper.findAll("[role='tab']").map((t) => t.text())).toContain("Nearby");
    const names = wrapper.findAll("[role='tab']").map((t) => t.text());
    expect(names.indexOf("Nearby")).toBe(names.indexOf("Stations") + 1);
    await tabButton(wrapper, "Nearby")?.trigger("click");
    const section = wrapper.findAll("#pane-nearby section")[0];
    expect(section?.findAll("td .call").map((c) => c.text())).toEqual(["OH2RDG", "OH2RCH-2"]);
  });

  it("selects a station when its row is clicked: the card opens and the map flies to it", async () => {
    const { wrapper } = await open();
    await tabButton(wrapper, "Nearby")?.trigger("click");
    await wrapper.find("#pane-nearby tr[data-call='OH2RDG']").trigger("click");
    await flushPromises();
    expect(wrapper.find(".card").text()).toContain("OH2RDG");
    expect(FakeMap.last().flights).toHaveLength(1);
    expect(wrapper.find("#pane-nearby tr.selected").exists()).toBe(true);
    expect(wrapper.find("#pane-stations tr.selected").text()).toContain("OH2RDG");
  });

  it("draws the range circles on the map when Show range is ticked, remembers it, and takes them off when it is not", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "set", key: "OH2RDG", value: withPhg }] });
    await flushPromises();
    FakeMap.last().fire("style.load");
    await tabButton(wrapper, "Nearby")?.trigger("click");
    const ranges = () =>
      FakeMap.last().getSource("digipeater-ranges")?.setData.mock.calls.at(-1)?.[0] as { features: { properties: { call: string } }[] } | undefined;
    expect(ranges()).toBeUndefined();
    await wrapper.find("#pane-nearby input[type='checkbox']").setValue(true);
    await flushPromises();
    expect(ranges()?.features.map((f) => f.properties.call)).toEqual(["OH2RDG"]);
    expect(localStorage.getItem("NeoAPRS.ranges")).toBe("on");
    await wrapper.find("#pane-nearby input[type='checkbox']").setValue(false);
    await flushPromises();
    expect(ranges()?.features).toEqual([]);
    expect(localStorage.getItem("NeoAPRS.ranges")).toBe("off");
  });

  it("lists an iGate that put third-party packets on the air", async () => {
    const { wrapper, socket } = await open();
    socket.say({ type: "patch", topic: "stations", rev: 1, ops: [{ op: "set", key: "OH7JHF-1", value: station("OH7JHF-1", { gated: 5, heard_via: [] }) }] });
    await flushPromises();
    await tabButton(wrapper, "Nearby")?.trigger("click");
    const gates = wrapper.findAll("#pane-nearby section")[2];
    expect(gates?.text()).toContain("OH7JHF-1");
    expect(gates?.text()).toContain("5 third-party packets put on the air");
  });
});
