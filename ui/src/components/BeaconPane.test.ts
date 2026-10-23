import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import BeaconPane from "@/components/BeaconPane.vue";
import { NOW, configValues, status } from "@/test/fixtures";

function pane() {
  return mount(BeaconPane, { props: { status: status(), connected: true, now: NOW, config: configValues(), lastError: null, send: vi.fn(() => true) } });
}

describe("BeaconPane", () => {
  it("has the beacon box on top, then the form with the packet it would make", () => {
    const wrapper = pane();
    expect(wrapper.find(".beaconpane").element.firstElementChild?.classList.contains("beaconbox")).toBe(true);
    expect(wrapper.find(".beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
  });

  it("shows the static status report once there is a status, with the time of the moment", async () => {
    const wrapper = pane();
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
    await wrapper.find("#set-station-status").setValue("QRV 145.500");
    const codes = wrapper.findAll(".beacon-preview code").map((c) => c.text());
    expect(codes).toEqual(["OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS", "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 145.500"]);
    await wrapper.find("#set-station-status").setValue("");
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
  });

  it("has the status group with the radio, the interval and the template, and no preview of a status a radio makes", async () => {
    const wrapper = pane();
    expect(wrapper.find("#set-status-rigctld").attributes("placeholder")).toBe("off");
    expect(wrapper.find("#set-status-interval_min").attributes("placeholder")).toBe("30");
    expect(wrapper.find("#set-status-template").attributes("placeholder")).toBe("QRV {freq} {mode}");
    await wrapper.find("#set-station-status").setValue("QRV 145.500");
    await wrapper.find("#set-status-rigctld").setValue("127.0.0.1:4532");
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
  });

  it("says so when the values make no packet", async () => {
    const wrapper = pane();
    await wrapper.find("#set-station-lat").setValue("95");
    expect(wrapper.find(".beacon-preview code").exists()).toBe(false);
    expect(wrapper.find(".beacon-preview").text()).toContain("make no packet");
  });

  it("passes on the click of Beacon now", async () => {
    const wrapper = pane();
    await wrapper.find(".beaconbox button").trigger("click");
    await wrapper.find(".beaconbox button").trigger("click");
    expect(wrapper.emitted("beacon")).toHaveLength(1);
  });
});
