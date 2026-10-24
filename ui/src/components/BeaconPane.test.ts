import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BeaconPane from "@/components/BeaconPane.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { ago, configValues, status } from "@/test/fixtures";

type Opts = { connected?: boolean; picking?: boolean; status?: ReturnType<typeof status> | null };

function pane(extra: Record<string, string> = {}, opts: Opts = {}) {
  const daemon = fakeDaemon({
    status: opts.status === undefined ? status({ beacon_last_sent: ago(125) }) : opts.status,
    connected: opts.connected ?? true,
    config: configValues(extra),
  });
  const wrapper = mount(BeaconPane, { props: { picking: opts.picking ?? false }, global: withDaemon(daemon) });
  return { wrapper, send: daemon.send, daemon };
}

type Wrapper = ReturnType<typeof pane>["wrapper"];
const labels = (wrapper: Wrapper) => wrapper.findAll("form .field label").map((l) => l.text());
const group = (wrapper: Wrapper, title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
const rows = (wrapper: Wrapper) => wrapper.findAll(".sendrow");
const buttons = (wrapper: Wrapper) => wrapper.findAll(".sendrow button");

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("BeaconPane", () => {
  it("has no box on top: it opens with the form, and the packet it would make is in the preview", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".beaconbox").exists()).toBe(false);
    expect(wrapper.find(".beaconpane").element.firstElementChild?.tagName).toBe("FORM");
    expect(wrapper.find(".beacon-preview code").text()).toBe("OH2GBA>APZNEO,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
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
    expect(codes).toEqual(["OH2GBA>APZNEO,WIDE2-1:=6010.20N/02456.40E-NeoAPRS", "OH2GBA>APZNEO,WIDE2-1:>211200zQRV 145.500"]);
    await wrapper.find("#set-station-status").setValue("");
    expect(wrapper.findAll(".beacon-preview code")).toHaveLength(1);
  });

  it("has the radio and the template under the choice of the radio, and no preview of a status a radio makes", async () => {
    const { wrapper } = pane();
    await wrapper.find("#set-status-source").setValue("rig");
    expect(wrapper.find("#set-status-rigctld").attributes("placeholder")).toBe("127.0.0.1:4532");
    expect(wrapper.find<HTMLSelectElement>("#set-status-interval_min").element.value).toBe("30");
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

  it("has the Location row, with the Choose on map button, between the call and the symbol", () => {
    const { wrapper } = pane();
    expect(wrapper.find("button.location-pick").text()).toBe("Choose on map");
    expect(
      wrapper
        .findAll("form .field label, form .field .field-label")
        .map((e) => e.text())
        .slice(0, 5),
    ).toEqual(["Call", "Location", "Latitude", "Longitude", "Symbol"]);
  });

  it("lays the Location out as the Call is: the label in the first column, the button, the place and Enter coordinates in the second", () => {
    const { wrapper } = pane();
    const row = wrapper.find(".location-field");
    const call = wrapper.find("#set-station-call").element.closest(".field");
    expect(row.element.classList.contains("field")).toBe(true);
    expect(row.element.previousElementSibling).toBe(call);
    expect([...row.element.children].map((c) => c.className.split(" ")[0])).toEqual(["field-label", "field-control"]);
    expect(row.find(".field-label").text()).toBe("Location");
    expect(row.find(".field-label").element.nextElementSibling).toBe(row.find(".field-control").element);
    expect(call?.querySelector(".field-control")?.tagName).toBe("DIV");
    expect([...row.find(".field-control").element.children].map((c) => c.className.split(" ")[0])).toEqual(["btn", "location-line", "disclosure"]);
    expect(row.find(".disclosure summary").text()).toBe("Enter coordinates");
    expect(wrapper.find("h3.subgroup").exists()).toBe(false);
  });

  describe("Beacon now, in the Beacon group", () => {
    it("is a row at the top of the group: when the last beacon went out, in words, the full time on hover, and the button beside it", () => {
      const { wrapper } = pane();
      const row = group(wrapper, "Beacon")?.find(".sendrow");
      expect(row?.element.previousElementSibling?.tagName).toBe("LEGEND");
      expect(row?.find("dt").text()).toBe("Last beacon");
      expect(row?.find("dd").text()).toBe("2 min ago");
      expect(row?.find("dd").attributes("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d/);
      expect(row?.find("button").text()).toBe("Beacon now");
      expect(row?.find("button").classes()).toEqual(expect.arrayContaining(["btn", "primary"]));
      expect(wrapper.text()).not.toContain("Next due");
      expect(wrapper.text()).not.toContain("every 30 min");
    });

    it("says not yet when no beacon was sent, and before the status has come", () => {
      expect(
        pane({}, { status: status({ beacon_last_sent: null }) })
          .wrapper.find(".sendrow")
          .text(),
      ).toMatch(/Last beacon\s*not yet/);
      expect(pane({}, { status: null }).wrapper.find(".sendrow").text()).toMatch(/Last beacon\s*not yet/);
    });

    it("asks twice, then passes the click on", async () => {
      const { wrapper, send } = pane();
      const button = wrapper.find(".sendrow button");
      await button.trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
      expect(button.text()).toBe("Really send?");
      expect(button.classes()).toContain("danger");
      await button.trigger("click");
      expect(send).toHaveBeenCalledTimes(1);
      expect(send).toHaveBeenCalledWith({ cmd: "beacon_now" });
      expect(button.text()).toBe("Beacon now");
    });

    it("forgets the first click after a few seconds", async () => {
      const { wrapper, send } = pane();
      const button = wrapper.find(".sendrow button");
      await button.trigger("click");
      vi.advanceTimersByTime(5001);
      await wrapper.vm.$nextTick();
      expect(button.text()).toBe("Beacon now");
      await button.trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("is off while the TNC is not connected, and the first click is forgotten when it drops", async () => {
      const { wrapper, send, daemon } = pane();
      await wrapper.find(".sendrow button").trigger("click");
      daemon.connected.value = false;
      await wrapper.vm.$nextTick();
      const button = wrapper.find(".sendrow button");
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.text()).toBe("Beacon now");
      daemon.connected.value = true;
      await wrapper.vm.$nextTick();
      await wrapper.find(".sendrow button").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
      expect(buttons(pane({}, { connected: false }).wrapper)[0]?.attributes("disabled")).toBeDefined();
    });
  });

  describe("Send status now, in the Status group", () => {
    it("is not there while the status is off", () => {
      expect(rows(pane().wrapper)).toHaveLength(1);
      expect(buttons(pane().wrapper).map((b) => b.text())).toEqual(["Beacon now"]);
    });

    it("is a row at the top of the Status group with the status last sent in one line, and the radio's state when a radio makes it", () => {
      const line = (extra: Record<string, string>, st: Partial<ReturnType<typeof status>>) => {
        const { wrapper } = pane(extra, { status: status(st) });
        const row = group(wrapper, "Status")?.find(".sendrow");
        expect(row?.element.previousElementSibling?.tagName).toBe("LEGEND");
        return [row?.find("dt").text(), row?.find("dd").text(), row?.find("button").text()];
      };
      const text = { "status/source": "text" };
      expect(line(text, {})).toEqual(["Status", "-", "Send status now"]);
      expect(line(text, { station_status: "QRV 14.074 MHz USB" })[1]).toBe("QRV 14.074 MHz USB");
      expect(line(text, { station_status: "QRV 14.074 MHz USB", rig_state: "on" })[1]).toBe("QRV 14.074 MHz USB · rigctld on");
      expect(line(text, { station_status: "", rig_state: "off" })[1]).toBe("- · rigctld off");
    });

    it("is there for a text, and for a radio that was set before the choice existed, and asks twice before it passes the click on", async () => {
      for (const extra of [{ "station/status": "QRV 145.500" }, { "status/rigctld": "127.0.0.1:4532" }, { "status/source": "text" }] as Record<
        string,
        string
      >[]) {
        const { wrapper, send } = pane(extra);
        expect(buttons(wrapper).map((b) => b.text())).toEqual(["Beacon now", "Send status now"]);
        const status = buttons(wrapper)[1];
        await status?.trigger("click");
        expect(send).not.toHaveBeenCalledWith({ cmd: "status_now" });
        expect(status?.text()).toBe("Really send?");
        expect(status?.classes()).toContain("danger");
        await status?.trigger("click");
        expect(send).toHaveBeenCalledWith({ cmd: "status_now" });
        expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
        expect(status?.text()).toBe("Send status now");
      }
    });

    it("is armed one at a time: arming the other button forgets the first", async () => {
      const { wrapper } = pane({ "status/source": "text" });
      await buttons(wrapper)[1]?.trigger("click");
      await buttons(wrapper)[0]?.trigger("click");
      expect(buttons(wrapper)[1]?.text()).toBe("Send status now");
      expect(buttons(wrapper)[0]?.text()).toBe("Really send?");
    });

    it("waits for a save: it acts on what is in force, so both buttons are off, saying Saving, while a change is on its way, and not before", async () => {
      const { wrapper, send, daemon } = pane({ "status/source": "text" });
      const disabled = () => buttons(wrapper).map((b) => b.attributes("disabled") !== undefined);
      expect(disabled()).toEqual([false, false]);
      await wrapper.find("#set-station-status").setValue("At the cottage");
      expect(disabled()).toEqual([false, false]); // (typing sends nothing)
      await wrapper.find("#set-station-status").trigger("blur");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/status": "At the cottage" } });
      expect(disabled()).toEqual([true, true]);
      expect(buttons(wrapper).map((b) => b.attributes("title"))).toEqual(["Saving…", "Saving…"]);
      daemon.config.value = configValues({ "status/source": "text", "station/status": "At the cottage" });
      await wrapper.vm.$nextTick();
      expect(disabled()).toEqual([false, false]);
    });

    it("does not follow what is being chosen, only what is saved", async () => {
      const { wrapper } = pane({ "status/source": "text" });
      await wrapper.find("#set-status-source").setValue("off");
      expect(buttons(wrapper)).toHaveLength(2);
    });
  });

  describe("picking a place on the map", () => {
    it("forgets a send that waits for its second press when the pick starts", async () => {
      const { wrapper, send } = pane();
      await buttons(wrapper)[0]?.trigger("click");
      expect(buttons(wrapper)[0]?.text()).toBe("Really send?");
      await wrapper.setProps({ picking: true });
      expect(buttons(wrapper)[0]?.text()).toBe("Beacon now");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("asks the page to end the pick when a send is armed, once, and not when it is sent or nothing is picked", async () => {
      const { wrapper, send } = pane({ "status/source": "text" }, { picking: true });
      await buttons(wrapper)[1]?.trigger("click");
      expect(wrapper.emitted("pickPosition")).toHaveLength(1);
      await buttons(wrapper)[1]?.trigger("click");
      expect(wrapper.emitted("pickPosition")).toHaveLength(1);
      expect(send).toHaveBeenCalledWith({ cmd: "status_now" });
      const idle = pane();
      await buttons(idle.wrapper)[0]?.trigger("click");
      expect(idle.wrapper.emitted("pickPosition")).toBeUndefined();
    });

    it("ends the pick of a place when a send is armed, and the pick forgets a send that waits", async () => {
      const { wrapper } = pane({}, { picking: true });
      await buttons(wrapper)[0]?.trigger("click");
      expect(wrapper.emitted("pickPosition")).toHaveLength(1);
      await wrapper.setProps({ picking: false });
      expect(buttons(wrapper)[0]?.text()).toBe("Really send?");
      await wrapper.setProps({ picking: true });
      expect(buttons(wrapper)[0]?.text()).toBe("Beacon now");
    });
  });
});
