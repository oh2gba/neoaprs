import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import BeaconPane from "@/components/BeaconPane.vue";
import type { Command } from "@/protocol/protocol";
import { NOW, configValues, status } from "@/test/fixtures";

function pane(extra: Record<string, string> = {}, connected = true) {
  const send = vi.fn((_command: Command) => true);
  const wrapper = mount(BeaconPane, { props: { status: status(), connected, now: NOW, config: configValues(extra), lastError: null, send } });
  return { wrapper, send };
}

const labels = (wrapper: ReturnType<typeof pane>["wrapper"]) => wrapper.findAll("form .field label").map((l) => l.text());

describe("BeaconPane", () => {
  it("has the beacon box on top, then the form with the packet it would make", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".beaconpane").element.firstElementChild?.classList.contains("beaconbox")).toBe(true);
    expect(wrapper.find(".beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
  });

  it("asks nothing about the destination, the compressed form or the DAO: the program decides", () => {
    const { wrapper } = pane({ "status/source": "text" });
    expect(labels(wrapper)).toEqual(["Call", "Latitude", "Longitude", "Symbol", "Beacon", "Comment", "Power", "Path", "Status", "Text", "Every"]);
    for (const id of ["destination", "compressed", "dao", "symbol_table", "symbol_code"])
      expect(wrapper.find(`#set-beacon-${id}, #set-station-${id}`).exists()).toBe(false);
  });

  it("shows the status report of a text of our own, with the time of the moment", async () => {
    const { wrapper } = pane();
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
    await wrapper.find("#set-status-source").setValue("text");
    await wrapper.find("#set-station-status").setValue("QRV 145.500");
    const codes = wrapper.findAll(".beacon-preview code").map((c) => c.text());
    expect(codes).toEqual(["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"]);
    await wrapper.find("#set-station-status").setValue("");
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
  });

  it("has the radio and the template under the choice of the radio, and no preview of a status a radio makes", async () => {
    const { wrapper } = pane();
    await wrapper.find("#set-status-source").setValue("rig");
    expect(wrapper.find("#set-status-rigctld").attributes("placeholder")).toBe("127.0.0.1:4532");
    expect(wrapper.find("#set-status-interval_min").attributes("placeholder")).toBe("30");
    expect(wrapper.find("#set-status-template").attributes("placeholder")).toBe("QRV {freq} {mode}");
    expect(wrapper.find("#set-station-status").exists()).toBe(false);
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
  });

  it("says so when the values make no packet", async () => {
    const { wrapper } = pane();
    await wrapper.find("#set-station-lat").setValue("95");
    expect(wrapper.find(".beacon-preview code").exists()).toBe(false);
    expect(wrapper.find(".beacon-preview").text()).toContain("make no packet");
  });

  it("passes on the click of Beacon now", async () => {
    const { wrapper } = pane();
    await wrapper.find(".beaconbox button").trigger("click");
    await wrapper.find(".beaconbox button").trigger("click");
    expect(wrapper.emitted("beacon")).toHaveLength(1);
  });

  describe("Send status now", () => {
    const sendNow = (wrapper: ReturnType<typeof pane>["wrapper"]) =>
      wrapper.findAll(".beaconbox button").find((b) => /status|Really/.test(b.text()) && b.text() !== "Beacon now");

    it("is not there while the status is off", () => {
      expect(
        pane()
          .wrapper.findAll(".beaconbox button")
          .map((b) => b.text()),
      ).toEqual(["Beacon now"]);
    });

    it("is there for a text, and for a radio that was set before the choice existed, and asks twice before it passes the click on", async () => {
      for (const extra of [{ "station/status": "QRV 145.500" }, { "status/rigctld": "127.0.0.1:4532" }, { "status/source": "text" }] as Record<
        string,
        string
      >[]) {
        const { wrapper } = pane(extra);
        expect(wrapper.findAll(".beaconbox button").map((b) => b.text())).toEqual(["Beacon now", "Send status now"]);
        await wrapper.findAll(".beaconbox button")[1]?.trigger("click");
        expect(wrapper.emitted("status")).toBeUndefined();
        await sendNow(wrapper)?.trigger("click");
        expect(wrapper.emitted("status")).toHaveLength(1);
        expect(wrapper.emitted("beacon")).toBeUndefined();
      }
    });

    it("waits for a save: it acts on what is in force, so both buttons are off while a change is on its way, and not before", async () => {
      const { wrapper, send } = pane({ "status/source": "text" });
      const disabled = () => wrapper.findAll(".beaconbox button").map((b) => b.attributes("disabled") !== undefined);
      expect(disabled()).toEqual([false, false]);
      await wrapper.find("#set-station-status").setValue("At the cottage");
      expect(disabled()).toEqual([false, false]); // (typing sends nothing)
      await wrapper.find("#set-station-status").trigger("blur");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/status": "At the cottage" } });
      expect(disabled()).toEqual([true, true]);
      await wrapper.setProps({ config: configValues({ "status/source": "text", "station/status": "At the cottage" }) });
      expect(disabled()).toEqual([false, false]);
    });

    it("does not follow what is being chosen, only what is saved", async () => {
      const { wrapper } = pane({ "status/source": "text" });
      await wrapper.find("#set-status-source").setValue("off");
      expect(wrapper.findAll(".beaconbox button")).toHaveLength(2);
    });
  });

  it("ends the pick of a place on the map when a send is armed, and the pick forgets a send that waits", async () => {
    const send = vi.fn((_command: Command) => true);
    const wrapper = mount(BeaconPane, { props: { status: status(), connected: true, now: NOW, config: configValues(), lastError: null, send, picking: true } });
    await wrapper.find(".beaconbox button").trigger("click");
    expect(wrapper.emitted("pickPosition")).toHaveLength(1);
    await wrapper.setProps({ picking: false });
    expect(wrapper.find(".beaconbox button").text()).toBe("Really send?");
    await wrapper.setProps({ picking: true });
    expect(wrapper.find(".beaconbox button").text()).toBe("Beacon now");
  });

  it("has the Location sub-section, with the big Pick on the map button, between the call and the symbol", () => {
    const { wrapper } = pane();
    expect(wrapper.find("button.location-pick").text()).toBe("Pick on the map");
    expect(
      wrapper
        .findAll("form h3, form .field label")
        .map((e) => e.text())
        .slice(0, 5),
    ).toEqual(["Call", "Location", "Latitude", "Longitude", "Symbol"]);
  });
});
