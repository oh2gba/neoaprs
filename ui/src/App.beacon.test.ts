import "@/test/mockmap";
import { describe, expect, it } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { ago, configValues, status } from "@/test/fixtures";
import { open, tabButton, useAppHarness } from "@/test/app";

useAppHarness();

describe("App: the Beacon tab", () => {
  it("sends a beacon from the Beacon tab after two clicks, and shows when the last one went out", async () => {
    const { wrapper, socket } = await open();
    socket.say(status({ beacon_interval_min: 15, beacon_last_sent: ago(60), beacon_next_due: new Date(Date.now() + 840_000).toISOString() }));
    await flushPromises();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .sendrow").text()).toContain("Last beacon1 min ago");
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "beacon_now" });
    await wrapper.find("#pane-beacon .sendrow button").trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "beacon_now" });
  });

  it("sends the status from the Beacon tab after two clicks once there is a status, and not before", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.findAll("#pane-beacon .sendrow button").map((b) => b.text())).toEqual(["Beacon now"]);
    socket.say({
      type: "state",
      topic: "config",
      rev: 1,
      value: configValues({ "status/source": "text", "station/status": "QRV 145.500" }),
    });
    await flushPromises();
    expect(wrapper.findAll("#pane-beacon .sendrow button").map((b) => b.text())).toEqual(["Beacon now", "Send status now"]);
    await wrapper.findAll("#pane-beacon .sendrow button")[1]?.trigger("click");
    expect(socket.sent).not.toContainEqual({ cmd: "status_now" });
    await wrapper.findAll("#pane-beacon .sendrow button")[1]?.trigger("click");
    expect(socket.sent).toContainEqual({ cmd: "status_now" });
    expect(socket.sent).not.toContainEqual({ cmd: "beacon_now" });
  });

  it("previews the beacon packet as it is typed and applies the beacon's settings from the Beacon tab when each field is left", async () => {
    const { wrapper, socket } = await open();
    await tabButton(wrapper, "Beacon")?.trigger("click");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
    await wrapper.find("#pane-beacon #set-station-comment").setValue("hello");
    await wrapper.find("#pane-beacon #set-beacon-path").setValue("");
    expect(wrapper.find("#pane-beacon .beacon-preview code").text()).toBe("OH2GBA>APZNEO:=6010.20N/02456.40E-hello");
    expect(socket.sent.filter((c) => (c as { cmd: string }).cmd === "set_config")).toEqual([]);
    await wrapper.find("#pane-beacon #set-station-comment").trigger("blur");
    expect(socket.sent).toContainEqual({ cmd: "set_config", values: { "station/comment": "hello" } });
    expect(wrapper.find("#pane-settings #set-station-comment").exists()).toBe(false);
  });
});
