import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BeaconPane from "@/components/BeaconPane.vue";
import { fakeDaemon, withDaemon } from "@/test/context";
import { NOW, ago, configValues, gpsOff, gpsState, status } from "@/test/fixtures";

type Opts = { connected?: boolean; picking?: boolean; status?: ReturnType<typeof status> | null; gps?: ReturnType<typeof gpsState> | null };

function pane(extra: Record<string, string> = {}, opts: Opts = {}) {
  const daemon = fakeDaemon({
    status: opts.status === undefined ? status({ beacon_last_sent: ago(125) }) : opts.status,
    connected: opts.connected ?? true,
    config: configValues(extra),
    gps: opts.gps ?? null,
  });
  const wrapper = mount(BeaconPane, { props: { picking: opts.picking ?? false }, global: withDaemon(daemon) });
  return { wrapper, send: daemon.send, daemon };
}

type Wrapper = ReturnType<typeof pane>["wrapper"];
const labels = (wrapper: Wrapper) => wrapper.findAll("form .field label").map((l) => l.text());
const group = (wrapper: Wrapper, title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
const rows = (wrapper: Wrapper) => wrapper.findAll(".sendrow");
/** The buttons that send now, in the order of the page: Beacon now in the beacon status, then Send status now. */
const buttons = (wrapper: Wrapper) => wrapper.findAll(".beaconstatus button, .sendrow button");
const block = (wrapper: Wrapper) => wrapper.find(".beaconstatus");

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("BeaconPane", () => {
  it("has the (i) of the tab at the top, which says what the beacon is, with its picture", async () => {
    const { wrapper } = pane();
    await wrapper.find(".tab-help .info-toggle").trigger("click");
    expect(wrapper.find(".tab-help .info-text").text()).toContain("The beacon is your position, sent every so often");
    expect(wrapper.find(".tab-help svg[data-picture='beacon']").exists()).toBe(true);
  });

  it("opens with the form, which starts with the beacon status", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".beaconbox").exists()).toBe(false);
    expect(wrapper.find(".beaconpane").element.firstElementChild?.className).toBe("tab-help");
    expect(wrapper.find(".beaconpane").element.children[1]?.tagName).toBe("FORM");
    expect(block(wrapper).element.parentElement?.tagName).toBe("FORM");
    expect(block(wrapper).element.nextElementSibling?.tagName).toBe("FIELDSET");
    expect(block(wrapper).element.nextElementSibling?.querySelector("legend")?.textContent).toBe("Station");
    expect(wrapper.find(".beacon-preview").exists()).toBe(false);
  });

  it("asks nothing about the destination, the compressed form or the DAO: the program decides", () => {
    const { wrapper } = pane({ "status/source": "text" });
    expect(labels(wrapper)).toEqual(["Call", "Position", "Symbol", "Beacon", "Comment", "Power", "Path", "Status", "Every", "Text"]);
    for (const id of ["destination", "compressed", "dao", "symbol_table", "symbol_code"])
      expect(wrapper.find(`#set-beacon-${id}, #set-station-${id}`).exists()).toBe(false);
  });

  it("has Every directly under the Status choice, then what the source needs, and only the choice while Status is off", async () => {
    const { wrapper } = pane();
    const fields = () =>
      group(wrapper, "Status")
        ?.findAll(".field > label")
        .map((l) => l.text());
    const sendRow = () => wrapper.findAll(".sendrow").length;
    expect(fields()).toEqual(["Status"]);
    expect(sendRow()).toBe(0);
    await wrapper.find("#set-status-source").setValue("text");
    expect(fields()).toEqual(["Status", "Every", "Text"]);
    expect(sendRow()).toBe(1);
    await wrapper.find("#set-status-source").setValue("rig");
    expect(fields()).toEqual(["Status", "Every", "Rigctld", "Text"]);
    expect(wrapper.find("#set-status-rigctld").attributes("placeholder")).toBe("127.0.0.1:4532");
    expect(wrapper.find<HTMLSelectElement>("#set-status-interval_min").element.value).toBe("30");
    expect(wrapper.find("#set-status-template").attributes("placeholder")).toBe("QRV {freq} {mode}");
    expect(wrapper.find("#set-station-status").exists()).toBe(false);
    expect(sendRow()).toBe(1);
    await wrapper.find("#set-status-source").setValue("off");
    expect(fields()).toEqual(["Status"]);
    expect(sendRow()).toBe(0);
    expect(wrapper.find("#set-status-interval_min").exists()).toBe(false);
  });

  it("has the Location row, with the Choose on map button, under the choice of the position", () => {
    const { wrapper } = pane();
    expect(wrapper.find("button.location-pick").text()).toBe("Choose on map");
    expect(
      wrapper
        .findAll("form .field label, form .field .field-label")
        .map((e) => e.text())
        .slice(0, 6),
    ).toEqual(["Call", "Position", "Location", "Symbol", "Beacon", "Comment"]);
  });

  it("lays the Location out as the Call is: the label in the first column, the plain button and the place as text on one line in the second", () => {
    const { wrapper } = pane();
    const row = wrapper.find(".location-field");
    const call = wrapper.find("#set-station-call").element.closest(".field");
    expect(row.element.classList.contains("field")).toBe(true);
    expect(row.element.previousElementSibling).toBe(wrapper.find("#set-gps-source").element.closest(".field"));
    expect([...row.element.children].map((c) => (c.classList.contains("statetext") ? "statetext" : (c.className.split(" ")[0] ?? "")))).toEqual([
      "field-label",
      "field-control",
    ]);
    expect(row.find(".field-label").text()).toBe("Location");
    expect(row.find(".field-label").element.nextElementSibling).toBe(row.find(".field-control").element);
    expect(call?.querySelector(".field-control")?.tagName).toBe("DIV");
    expect(
      [...row.find(".field-control").element.children].map((c) => (c.classList.contains("statetext") ? "statetext" : (c.className.split(" ")[0] ?? ""))),
    ).toEqual(["btn", "location-place"]);
    expect(row.find(".btn").classes()).not.toContain("primary");
    expect(row.find(".location-place").text()).toBe("60.17 N, 24.94 E · KP20le");
    expect(row.find("details").exists()).toBe(false);
    expect(wrapper.find("h3.subgroup").exists()).toBe(false);
  });

  describe("the beacon status of a fixed station, at the top of the tab, with Beacon now", () => {
    it("is a label, a pill and one line, with the full time of the last beacon on hover and Beacon now at its end", () => {
      const { wrapper } = pane(
        {},
        { status: status({ beacon_interval_min: 60, beacon_last_sent: ago(240), beacon_next_due: new Date(NOW + 56 * 60_000).toISOString() }) },
      );
      expect(
        [...block(wrapper).find(".beaconhead").element.children].map((c) =>
          c.classList.contains("statetext") ? "statetext" : (c.className.split(" ")[0] ?? ""),
        ),
      ).toEqual(["beaconlabel", "statetext", "tncstatus", "btn"]);
      expect(block(wrapper).find(".beaconlabel").text()).toBe("Beacon");
      expect(block(wrapper).find(".statetext").text()).toBe("on");
      expect(block(wrapper).find(".statetext").classes()).toContain("beacon-on");
      expect(block(wrapper).find(".tncstatus").text()).toBe("Last beacon 4 min ago · next in 56 min (every 60 min)");
      expect(block(wrapper).find(".tncstatus").attributes("role")).toBe("status");
      expect(block(wrapper).find(".tncstatus").attributes("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d/);
      expect(block(wrapper).find("button").text()).toBe("Beacon now");
      expect(block(wrapper).find("button").classes()).toEqual(expect.arrayContaining(["btn", "primary"]));
      expect(block(wrapper).findAll("p")).toHaveLength(0);
      expect(group(wrapper, "Beacon")?.find(".sendrow").exists()).toBe(false);
    });

    it("says Beacon off, with the pill off, while the interval is 0", () => {
      const { wrapper } = pane({ "beacon/interval_min": "0" }, { status: status({ beacon_last_sent: ago(125) }) });
      expect(block(wrapper).find(".beaconlabel").text()).toBe("Beacon");
      expect(block(wrapper).find(".statetext").text()).toBe("off");
      expect(block(wrapper).find(".statetext").classes()).toContain("beacon-off");
      expect(block(wrapper).find(".tncstatus").text()).toBe("Beacon off");
    });

    it("says that none was sent yet, with or without a timer", () => {
      const timed = status({ beacon_interval_min: 30, beacon_next_due: new Date(NOW + 5 * 60_000).toISOString() });
      expect(
        block(pane({}, { status: timed }).wrapper)
          .find(".tncstatus")
          .text(),
      ).toBe("No beacon sent yet · next in 5 min (every 30 min)");
      expect(
        block(pane({}, { status: status() }).wrapper)
          .find(".tncstatus")
          .text(),
      ).toBe("No beacon sent yet · no timed beacon");
    });

    it("says nothing is known before the status has come, with no pill", () => {
      const { wrapper } = pane({}, { status: null });
      expect(block(wrapper).find(".statetext").exists()).toBe(false);
      expect(block(wrapper).find(".tncstatus").text()).toBe("No word from the daemon yet.");
    });

    it("follows the clock", async () => {
      const { wrapper, daemon } = pane(
        {},
        { status: status({ beacon_interval_min: 60, beacon_last_sent: ago(240), beacon_next_due: new Date(NOW + 56 * 60_000).toISOString() }) },
      );
      daemon.now.value = NOW + 60_000;
      await wrapper.vm.$nextTick();
      expect(block(wrapper).find(".tncstatus").text()).toBe("Last beacon 5 min ago · next in 55 min (every 60 min)");
    });

    it("asks twice, then passes the click on", async () => {
      const { wrapper, send } = pane();
      const button = wrapper.find(".beaconstatus button");
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
      const button = wrapper.find(".beaconstatus button");
      await button.trigger("click");
      vi.advanceTimersByTime(5001);
      await wrapper.vm.$nextTick();
      expect(button.text()).toBe("Beacon now");
      await button.trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("is off while the TNC is not connected, and the first click is forgotten when it drops", async () => {
      const { wrapper, send, daemon } = pane();
      await wrapper.find(".beaconstatus button").trigger("click");
      daemon.connected.value = false;
      await wrapper.vm.$nextTick();
      const button = wrapper.find(".beaconstatus button");
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.text()).toBe("Beacon now");
      daemon.connected.value = true;
      await wrapper.vm.$nextTick();
      await wrapper.find(".beaconstatus button").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
      expect(buttons(pane({}, { connected: false }).wrapper)[0]?.attributes("disabled")).toBeDefined();
    });
  });

  describe("Send status now, in the Status group", () => {
    it("is not there while the status is off", () => {
      expect(rows(pane().wrapper)).toHaveLength(0);
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

    it("follows what is being chosen: it goes when Status is chosen Off and comes back with another choice", async () => {
      const { wrapper } = pane({ "status/source": "text" });
      await wrapper.find("#set-status-source").setValue("off");
      expect(buttons(wrapper)).toHaveLength(1);
      await wrapper.find("#set-status-source").setValue("rig");
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

describe("the beacon status of a moving station", () => {
  const later = (seconds: number) => new Date(NOW + seconds * 1000).toISOString();
  const moving = { "gps/source": "gpsd" };

  it("is the GPS and not the timer: the label, the state of the GPS on the pill, the fix, and Beacon now, with no Mobile group", () => {
    const { wrapper } = pane(moving, { gps: gpsState({ next_beacon_at: later(42) }) });
    expect(block(wrapper).classes()).toContain("moving");
    expect(block(wrapper).find(".beaconlabel").text()).toBe("GPS");
    expect(block(wrapper).find(".statetext").text()).toBe("fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-fix");
    expect(block(wrapper).find(".tncstatus").text()).toBe("Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago");
    expect(block(wrapper).find("button").text()).toBe("Beacon now");
    expect(group(wrapper, "Mobile")).toBeUndefined();
    expect(wrapper.text()).not.toContain("Last beacon");
  });

  it("says under the fix when SmartBeaconing sends next, and why the last one went", () => {
    const { wrapper } = pane(moving, { gps: gpsState({ next_beacon_at: later(42), last_beacon_at: ago(12), last_beacon_reason: "turn" }) });
    expect(block(wrapper).find(".mobileline").text()).toBe("SmartBeaconing: next timed beacon in 42 s, last sent 12 s ago (turn)");
    expect(block(wrapper).find(".tncstatus + button + .mobileline, .beaconhead + .mobileline").exists()).toBe(true);
    expect(block(wrapper).find(".problem").exists()).toBe(false);
  });

  it("says there is no beacon without a fix, why there is none, and keeps Beacon now as it is", async () => {
    const { wrapper, send } = pane(moving, {
      gps: gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "the receiver has no position fix yet" }),
    });
    expect(block(wrapper).find(".statetext").text()).toBe("no fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-no_fix");
    expect(block(wrapper).find(".tncstatus").text()).toBe("No fix yet");
    expect(block(wrapper).find(".mobileline").text()).toBe("No beacon: no GPS fix");
    expect(block(wrapper).find(".problem").text()).toBe("the receiver has no position fix yet");
    const button = buttons(wrapper)[0];
    expect(button?.text()).toBe("Beacon now");
    await button?.trigger("click");
    await button?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "beacon_now" });
  });

  it("says what it is connecting to, from the settings, and follows the GPS", async () => {
    const { wrapper, daemon } = pane(moving, { gps: gpsState({ state: "connecting", lat: null, lon: null, fix_at: null, problem: "Connection refused" }) });
    expect(block(wrapper).find(".tncstatus").text()).toBe("Connecting to gpsd at 127.0.0.1:2947");
    expect(block(wrapper).find(".problem").text()).toBe("Connection refused");
    daemon.gps.value = gpsState();
    await wrapper.vm.$nextTick();
    expect(block(wrapper).find(".statetext").text()).toBe("fix");
    expect(block(wrapper).find(".problem").exists()).toBe(false);
  });

  it("is a moving station's from what the daemon says, and from the setting before it has said", async () => {
    const { wrapper, daemon } = pane(moving, { gps: null });
    expect(block(wrapper).find(".beaconlabel").text()).toBe("GPS");
    expect(block(wrapper).find(".statetext").exists()).toBe(false);
    expect(block(wrapper).find(".tncstatus").text()).toBe("No word from the daemon yet.");
    daemon.gps.value = gpsOff();
    await wrapper.vm.$nextTick();
    expect(block(wrapper).find(".beaconlabel").text()).toBe("Beacon");
    expect(
      block(pane({}, { gps: gpsState() }).wrapper)
        .find(".beaconlabel")
        .text(),
    ).toBe("GPS");
  });

  it("has no place in the Station group while a GPS is chosen: the stored place is kept out of sight", () => {
    expect(group(pane().wrapper, "Station")?.find(".location-field .field-label").text()).toBe("Location");
    for (const source of ["gpsd", "serial"] as const) {
      const { wrapper } = pane({ "gps/source": source }, { gps: gpsState({ source }) });
      expect(group(wrapper, "Station")?.find(".location-field").exists(), source).toBe(false);
      expect(group(wrapper, "Station")?.find("button.location-pick").exists(), source).toBe(false);
      expect(group(wrapper, "Station")?.find("#set-station-lat").exists(), source).toBe(false);
      expect(group(wrapper, "Station")?.find("#set-station-lon").exists(), source).toBe(false);
    }
  });

  it("shows what a moving station has, and not what a fixed one has: Travelling and no antenna", () => {
    const stationLabels = (wrapper: Wrapper) =>
      group(wrapper, "Station")
        ?.findAll(".field > label")
        .map((l) => l.text());
    const beaconLabels = (wrapper: Wrapper) =>
      group(wrapper, "Beacon")
        ?.findAll(".field > label")
        .map((l) => l.text());
    const fixed = pane({ "beacon/power_w": "5" }).wrapper;
    expect(stationLabels(fixed)).toEqual(["Call", "Position", "Symbol"]);
    expect(beaconLabels(fixed)).toEqual(["Beacon", "Comment", "Power", "Antenna height", "Antenna gain", "Antenna direction", "Path"]);
    expect(
      group(fixed, "Beacon")
        ?.findAll("details > summary")
        .map((l) => l.text()),
    ).toEqual(["Antenna", "Advanced"]);
    const car = pane({ "gps/source": "serial", "beacon/power_w": "5" }, { gps: gpsState({ source: "serial" }) }).wrapper;
    expect(stationLabels(car)).toEqual(["Call", "Position", "GPS port", "GPS speed", "Symbol"]);
    expect(beaconLabels(car)).toEqual(["Beacon", "Travelling", "Comment", "Path"]);
    expect(
      group(car, "Beacon")
        ?.findAll("details > summary")
        .map((l) => l.text()),
    ).toEqual(["Advanced"]);
    expect(car.find("#set-beacon-interval_min").exists()).toBe(true);
    expect(car.find("#set-beacon-power_w").exists()).toBe(false);
  });
});

describe("BeaconPane with the beacon Off", () => {
  const off = (extra: Record<string, string> = {}, opts: Opts = {}) => pane({ "beacon/interval_min": "0", "status/source": "text", ...extra }, opts);

  it("keeps Beacon now and Send status now on: Off is no automatic beacon, and a press sends", async () => {
    const { wrapper, send } = off();
    expect(buttons(wrapper).map((b) => [b.text(), b.attributes("disabled") !== undefined, b.attributes("title")])).toEqual([
      ["Beacon now", false, undefined],
      ["Send status now", false, undefined],
    ]);
    await buttons(wrapper)[0]?.trigger("click");
    await buttons(wrapper)[0]?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "beacon_now" });
    await buttons(wrapper)[1]?.trigger("click");
    await buttons(wrapper)[1]?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "status_now" });
  });

  it("does the same for a moving station", () => {
    const { wrapper } = off({ "gps/source": "gpsd" }, { gps: gpsState() });
    expect(buttons(wrapper).map((b) => [b.attributes("disabled") !== undefined, b.attributes("title")])).toEqual([
      [false, undefined],
      [false, undefined],
    ]);
    expect(block(wrapper).find(".beaconlabel").text()).toBe("GPS");
    expect(block(wrapper).find(".statetext").text()).toBe("fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-fix");
    expect(block(wrapper).find(".tncstatus").text()).toMatch(/^Fix: 60\.4295 N 24\.1452 E/);
    expect(
      block(wrapper)
        .findAll("p")
        .map((p) => p.text()),
    ).toEqual(["Beacon off"]);
    expect(block(wrapper).find(".beaconhead + .mobileline").exists()).toBe(true);
  });

  it("shows a moving station's missing fix and its reason while the beacon is Off, and the fixed station's block as it was", () => {
    const { wrapper } = off(
      { "gps/source": "gpsd" },
      { gps: gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "the receiver has no position fix yet" }) },
    );
    expect(block(wrapper).find(".statetext").text()).toBe("no fix");
    expect(block(wrapper).find(".tncstatus").text()).toBe("No fix yet");
    expect(
      block(wrapper)
        .findAll("p")
        .map((p) => p.text()),
    ).toEqual(["Beacon off", "the receiver has no position fix yet"]);
    const fixed = off();
    expect(block(fixed.wrapper).find(".beaconlabel").text()).toBe("Beacon");
    expect(block(fixed.wrapper).find(".statetext").text()).toBe("off");
    expect(block(fixed.wrapper).find(".tncstatus").text()).toBe("Beacon off");
    expect(block(fixed.wrapper).findAll("p")).toHaveLength(0);
  });

  it("keeps the status row in view, and greys only the timing: the status's Every, and what is sent stays editable", () => {
    const { wrapper } = off();
    expect(rows(wrapper)).toHaveLength(1);
    const greyed = group(wrapper, "Status")
      ?.findAll(".field.disabled label")
      .map((l) => l.text());
    expect(greyed).toEqual(["Every"]);
    expect(group(wrapper, "Beacon")?.findAll(".field.disabled")).toHaveLength(0);
  });

  it("turns both buttons on again with the first interval, and they work", async () => {
    const { wrapper, send, daemon } = off();
    daemon.config.value = configValues({ "beacon/interval_min": "60", "status/source": "text" });
    await wrapper.vm.$nextTick();
    expect(buttons(wrapper).map((b) => [b.attributes("disabled") !== undefined, b.attributes("title")])).toEqual([
      [false, undefined],
      [false, undefined],
    ]);
    await buttons(wrapper)[0]?.trigger("click");
    await buttons(wrapper)[0]?.trigger("click");
    expect(send).toHaveBeenCalledWith({ cmd: "beacon_now" });
  });

  it("keeps the buttons on when the daemon has taken Off, and turns them off with the title RX only when transmitting is off", async () => {
    const { wrapper, daemon } = pane({ "status/source": "text" });
    await wrapper.find("#set-beacon-interval_min").setValue("0");
    daemon.config.value = configValues({ "beacon/interval_min": "0", "status/source": "text" });
    await wrapper.vm.$nextTick();
    expect(buttons(wrapper).map((b) => b.attributes("title"))).toEqual([undefined, undefined]);
    daemon.config.value = configValues({ "beacon/interval_min": "0", "status/source": "text", "station/transmit": "false" });
    await wrapper.vm.$nextTick();
    expect(buttons(wrapper).map((b) => [b.attributes("disabled") !== undefined, b.attributes("title")])).toEqual([
      [true, "RX only: nothing is sent"],
      [true, "RX only: nothing is sent"],
    ]);
  });
});
