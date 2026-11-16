import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BeaconPane from "@/components/BeaconPane.vue";
import { t } from "@/i18n";
import type { RadioRow } from "@/protocol/protocol";
import { fakeDaemon, tell, withDaemon } from "@/test/context";
import { cssRule } from "@/test/css";
import { NOW, ago, configValues, gpsOff, gpsState, radioRow, radiosTopic, status } from "@/test/fixtures";

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
const labels = (wrapper: Wrapper) => wrapper.findAll("form .field:not(.action-row) label").map((l) => l.text());
const group = (wrapper: Wrapper, title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
const rows = (wrapper: Wrapper) => wrapper.findAll("#status-now");
/** The buttons that send now, in the order of the page: Beacon now under the Beacon choice, then Send status now. */
const buttons = (wrapper: Wrapper) => wrapper.findAll("#beacon-now, #status-now");
/** The state of the beacon: the row under the Beacon choice. */
const block = (wrapper: Wrapper) => group(wrapper, "Beacon")?.find(".beaconstatus") ?? wrapper.find(".beaconstatus");

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("BeaconPane", () => {
  it("has the (i) of the tab at the top, which says what the beacon is, with its picture", async () => {
    const { wrapper } = pane();
    await wrapper.find(".tab-help .info-toggle").trigger("click");
    expect(wrapper.find(".tab-help .info-text").text()).toContain("The beacon is your position, sent every so often");
    expect(wrapper.find(".tab-help svg[data-picture='beacon']").exists()).toBe(true);
  });

  it("opens with the form, which has the state of the beacon directly under the Beacon choice and Beacon now under it", () => {
    const { wrapper } = pane();
    expect(wrapper.find(".beaconbox").exists()).toBe(false);
    expect(wrapper.find(".beaconpane").element.firstElementChild?.className).toBe("tab-help");
    expect(wrapper.find(".beaconpane").element.children[1]?.tagName).toBe("FORM");
    const choice = wrapper.find("#set-beacon-interval_min").element.closest(".field");
    expect(choice?.nextElementSibling).toBe(block(wrapper).element);
    expect(block(wrapper).element.nextElementSibling).toBe(wrapper.find("#beacon-now").element.closest(".action-row"));
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
        ?.findAll(".field:not(.action-row) > label")
        .map((l) => l.text());
    const sendRow = () => wrapper.findAll("#status-now").length;
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
        .findAll("form .field:not(.action-row) label, form .field:not(.action-row) .field-label")
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
    it("is the radio's status row: the state, one line, and behind the arrow the full time of the last beacon; Beacon now is a row of its own", () => {
      const { wrapper } = pane(
        {},
        { status: status({ beacon_interval_min: 60, beacon_last_sent: ago(240), beacon_next_due: new Date(NOW + 56 * 60_000).toISOString() }) },
      );
      expect(block(wrapper).element.tagName).toBe("DETAILS");
      expect(block(wrapper).find(".statetext").text()).toBe("on");
      expect(block(wrapper).find(".statetext").classes()).toContain("beacon-on");
      expect(block(wrapper).find(".tncstatus").text()).toBe("Last beacon 4 min ago · next in 56 min (every 60 min)");
      expect(block(wrapper).find(".tncstatus").attributes("role")).toBe("status");
      expect(block(wrapper).find(".tncstatus").attributes("title")).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d/);
      expect(block(wrapper).find("button").exists()).toBe(false);
      const row = wrapper.find("#beacon-now").element.closest(".action-row");
      expect(row?.querySelector("label")?.textContent).toBe("Send now");
      expect(row?.querySelector(".infotip")).not.toBeNull();
      expect(wrapper.find("#beacon-now").text()).toBe("Beacon now");
      expect(wrapper.find("#beacon-now").classes()).toEqual(["btn"]);
      expect(wrapper.find("#status-now").exists()).toBe(false);
    });

    it("says off, and in the detail what that means without the word again, while the interval is 0", () => {
      const { wrapper } = pane({ "beacon/interval_min": "0" }, { status: status({ beacon_last_sent: ago(125) }) });
      expect(block(wrapper).find(".statetext").text()).toBe("off");
      expect(block(wrapper).find(".tncstatus").text()).toBe("No automatic beacon · Beacon now still sends");
    });

    it("says off in the warn colour and that nothing is sent in RX only, and has the buttons that send secondary", () => {
      const { wrapper } = pane(
        { "station/transmit": "false", "status/source": "text" },
        { status: status({ beacon_interval_min: 60, beacon_last_sent: ago(240) }) },
      );
      expect(block(wrapper).find(".statetext").text()).toBe("off");
      expect(block(wrapper).find(".statetext").classes()).toContain("tnc-waiting");
      expect(block(wrapper).find(".tncstatus").text()).toBe("RX only: nothing is sent");
      const report = group(wrapper, "Status")?.find(".beaconstatus");
      expect([report?.find(".statetext").text(), report?.find(".statetext").classes(), report?.find(".tncstatus").text()]).toEqual([
        "off",
        expect.arrayContaining(["tnc-waiting"]),
        "RX only: nothing is sent",
      ]);
      expect(wrapper.findAll(".tncstatus").every((l) => l.text() !== "-" && l.text() !== "")).toBe(true);
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

    it("shows no row before the status has come", () => {
      const { wrapper } = pane({}, { status: null });
      expect(wrapper.find(".beaconstatus").exists()).toBe(false);
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
      const button = wrapper.find("#beacon-now");
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
      const button = wrapper.find("#beacon-now");
      await button.trigger("click");
      vi.advanceTimersByTime(5001);
      await wrapper.vm.$nextTick();
      expect(button.text()).toBe("Beacon now");
      await button.trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("is off while the TNC is not connected, and the first click is forgotten when it drops", async () => {
      const { wrapper, send, daemon } = pane();
      await wrapper.find("#beacon-now").trigger("click");
      daemon.connected.value = false;
      await wrapper.vm.$nextTick();
      const button = wrapper.find("#beacon-now");
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.text()).toBe("Beacon now");
      daemon.connected.value = true;
      await wrapper.vm.$nextTick();
      await wrapper.find("#beacon-now").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
      expect(buttons(pane({}, { connected: false }).wrapper)[0]?.attributes("disabled")).toBeDefined();
    });
  });

  describe("Send status now, in the Status group", () => {
    it("is not there while the status is off", () => {
      expect(rows(pane().wrapper)).toHaveLength(0);
      expect(buttons(pane().wrapper).map((b) => b.text())).toEqual(["Beacon now"]);
    });

    it("is the status report as a row under the Status choice with when it last went and when it may next, and the radio's state behind the arrow when a radio makes it", () => {
      const line = (extra: Record<string, string>, st: Partial<ReturnType<typeof status>>) => {
        const { wrapper } = pane(extra, { status: status(st) });
        const row = group(wrapper, "Status")?.find(".beaconstatus");
        expect(wrapper.find("#set-status-source").element.closest(".field")?.nextElementSibling).toBe(row?.element);
        return [
          row?.find(".statetext").text(),
          row?.find(".tncstatus").text(),
          row?.findAll(".igatefold").map((p) => p.text()),
          wrapper.find("#status-now").text(),
        ];
      };
      const text = { "status/source": "text", "station/status": "QRV 144.800 MHz FM" };
      expect(line(text, {})).toEqual(["on", "Not sent yet", ["Every 30 min"], "Send status now"]);
      expect(line(text, { station_status: "QRV 144.800 MHz FM", station_status_last_sent: ago(240) })).toEqual([
        "on",
        "Last sent 4 min ago · next in 26 min (every 30 min)",
        ["Every 30 min"],
        "Send status now",
      ]);
      expect(line(text, { station_status_last_sent: ago(31 * 60) })[1]).toBe("Last sent 31 min ago · next now (every 30 min)");
      expect(line({ ...text, "beacon/interval_min": "0" }, { station_status_last_sent: ago(240) })[1]).toBe("Last sent 4 min ago · no timed status");
      expect(line(text, { station_status: "QRV 14.074 MHz USB", rig_state: "on" })[2]).toEqual(["QRV 14.074 MHz USB", "Every 30 min", "rigctld on"]);
      expect(line(text, { station_status: "", rig_state: "off" })).toEqual(["on", "Not sent yet", ["Every 30 min", "rigctld off"], "Send status now"]);
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

  it("is the GPS and not the timer: the state of the GPS, the fix, and Beacon now as a row, with no Mobile group", () => {
    const { wrapper } = pane(moving, { gps: gpsState({ next_beacon_at: later(42) }) });
    expect(block(wrapper).find(".statetext").text()).toBe("fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-fix");
    expect(block(wrapper).find(".tncstatus").text()).toBe("Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago");
    expect(wrapper.find("#beacon-now").text()).toBe("Beacon now");
    expect(group(wrapper, "Mobile")).toBeUndefined();
    expect(wrapper.text()).not.toContain("Last beacon");
  });

  it("says under the fix when SmartBeaconing sends next, and why the last one went", () => {
    const { wrapper } = pane(moving, { gps: gpsState({ next_beacon_at: later(42), last_beacon_at: ago(12), last_beacon_reason: "turn" }) });
    expect(block(wrapper).find(".igatefold").text()).toBe("SmartBeaconing: next timed beacon in 42 s, last sent 12 s ago (turn)");
    expect(block(wrapper).find(".problem").exists()).toBe(false);
  });

  it("says there is no beacon without a fix, why there is none, and keeps Beacon now as it is", async () => {
    const { wrapper, send } = pane(moving, {
      gps: gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "the receiver has no position fix yet" }),
    });
    expect(block(wrapper).find(".statetext").text()).toBe("no fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-no_fix");
    expect(block(wrapper).find(".tncstatus").text()).toBe("No fix yet");
    expect(block(wrapper).find(".igatefold").text()).toBe("No beacon: no GPS fix");
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
    expect(wrapper.find(".beaconstatus").exists()).toBe(false);
    daemon.gps.value = gpsOff();
    await wrapper.vm.$nextTick();
    expect(block(wrapper).find(".tncstatus").text()).toMatch(/^(Last beacon|No beacon)/);
    expect(
      block(pane({}, { gps: gpsState() }).wrapper)
        .find(".tncstatus")
        .text(),
    ).toMatch(/^Fix: /);
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
        ?.findAll(".field:not(.action-row) > label")
        .map((l) => l.text());
    const beaconLabels = (wrapper: Wrapper) =>
      group(wrapper, "Beacon")
        ?.findAll(".field:not(.action-row) > label")
        .map((l) => l.text());
    const fixed = pane({ "beacon/power_w": "5" }).wrapper;
    expect(stationLabels(fixed)).toEqual(["Call", "Position", "Symbol"]);
    expect(beaconLabels(fixed)).toEqual(["Beacon", "Comment", "Power", "Antenna height", "Antenna gain", "Antenna direction", "Path"]);
    expect(
      group(fixed, "Beacon")
        ?.findAll("details:not(.statusfold) > summary")
        .map((l) => l.text()),
    ).toEqual(["Antenna", "Advanced"]);
    const car = pane({ "gps/source": "serial", "beacon/power_w": "5" }, { gps: gpsState({ source: "serial" }) }).wrapper;
    expect(stationLabels(car)).toEqual(["Call", "Position", "GPS port", "GPS speed", "Symbol"]);
    expect(beaconLabels(car)).toEqual(["Beacon", "Travelling", "Comment", "Path"]);
    expect(
      group(car, "Beacon")
        ?.findAll("details:not(.statusfold) > summary")
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
    expect(block(wrapper).find(".statetext").text()).toBe("fix");
    expect(block(wrapper).find(".statetext").classes()).toContain("gps-fix");
    expect(block(wrapper).find(".tncstatus").text()).toMatch(/^Fix: 60\.4295 N 24\.1452 E/);
    expect(
      block(wrapper)
        .findAll("p")
        .map((p) => p.text()),
    ).toEqual(["No automatic beacon · Beacon now still sends"]);
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
    ).toEqual(["No automatic beacon · Beacon now still sends", "the receiver has no position fix yet"]);
    const fixed = off();
    expect(block(fixed.wrapper).find(".statetext").text()).toBe("off");
    expect(block(fixed.wrapper).find(".tncstatus").text()).toBe("No automatic beacon · Beacon now still sends");
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

describe("BeaconPane with several radios", () => {
  // the radios as the daemon tells them, and their own settings in radio_values (as the daemon sends them beside the settings of before)
  const later = (seconds: number) => new Date(NOW + seconds * 1000).toISOString();
  const FM = (extra: Partial<RadioRow> = {}) => radioRow(1, "kenwood-tnc2", extra);
  const HF = (extra: Partial<RadioRow> = {}) => radioRow(2, "mercury", extra);
  const FM3 = (extra: Partial<RadioRow> = {}) => radioRow(3, "kiss", { number: 2, ...extra });
  const SIX = () => [
    FM({ name: "Shack" }),
    HF({ name: "20 m" }),
    FM3({ name: "Mobile12" }),
    radioRow(4, "kiss", { number: 3, name: "Kitchen" }),
    radioRow(5, "dummy-hf", { number: 2, name: "Dummy" }),
    radioRow(6, "kiss-tcp", { number: 4, name: "Direwolf" }),
  ];
  const valuesOf = (rows: RadioRow[]): Record<string, string> =>
    Object.fromEntries(
      rows.flatMap((row): [string, string][] => [
        [`radio/${row.id}/beacon`, String(row.choices.beacon)],
        ...(row.choices.path === null ? [] : [[`radio/${row.id}/path`, row.choices.path] as [string, string]]),
      ]),
    );
  function radiosPane(
    rows: RadioRow[] | null,
    extra: Record<string, string> = {},
    opts: { status?: ReturnType<typeof status>; attach?: boolean; gps?: ReturnType<typeof gpsState>; values?: RadioRow[] } = {},
  ) {
    const told = rows ?? opts.values ?? [];
    const base = configValues(extra);
    const daemon = fakeDaemon({
      status: opts.status ?? status({ beacon_interval_min: 20, beacon_last_sent: ago(240), beacon_next_due: later(16 * 60) }),
      config: { ...base, radio_values: { ...base.radio_values, ...valuesOf(told) } },
      radios: rows === null ? null : radiosTopic(...rows),
      gps: opts.gps ?? null,
    });
    const wrapper = mount(BeaconPane, { global: withDaemon(daemon), attachTo: opts.attach ? document.body : undefined });
    return { wrapper, send: daemon.send, daemon };
  }
  const sendOn = (wrapper: Wrapper) => wrapper.find("#beacon-send-on").element.closest(".field");
  const ticks = (wrapper: Wrapper) => wrapper.findAll<HTMLInputElement>("#beacon-send-on ~ .field-control input[type=checkbox]");
  const tickNames = (wrapper: Wrapper) => wrapper.findAll("#beacon-send-on ~ .field-control label.check").map((l) => l.text());
  const fold = (wrapper: Wrapper) =>
    block(wrapper)
      .findAll(".igatefold")
      .map((p) => p.text());
  const configs = (send: ReturnType<typeof pane>["send"]) => send.mock.calls.map(([command]) => command).filter((command) => command.cmd === "set_config");

  describe("Send on", () => {
    it("is not there with one radio on: the tab is as it was (the FM radio alone, the HF radio alone, a radio that is off or removed beside it)", () => {
      for (const rows of [[FM()], [FM({ enabled: false }), HF()], [FM(), HF({ enabled: false })], [FM(), HF({ removed: true, enabled: false })]]) {
        const { wrapper } = radiosPane(rows);
        expect(wrapper.find("#beacon-send-on").exists()).toBe(false);
        expect(fold(wrapper).filter((line) => /^(FM|HF)( \d)?: /.test(line))).toEqual([]);
      }
      expect(pane().wrapper.find("#beacon-send-on").exists()).toBe(false);
    });

    it("is a tick for each radio that is on, by its name, under the Beacon choice and before the state of the beacon, each ticked as the daemon has it", () => {
      const { wrapper } = radiosPane([FM(), HF({ choices: { beacon: false, path: null, digipeat: null } }), FM3({ enabled: false })]);
      const row = sendOn(wrapper);
      expect(row?.querySelector(".field-label")?.textContent).toBe("Send on");
      expect(row?.getAttribute("role")).toBe("group");
      expect(wrapper.find("#set-beacon-interval_min").element.closest(".field")?.nextElementSibling).toBe(row);
      expect(row?.nextElementSibling).toBe(block(wrapper).element);
      expect(tickNames(wrapper)).toEqual(["FM", "HF"]);
      expect(ticks(wrapper).map((tick) => [tick.attributes("id"), tick.element.checked])).toEqual([
        ["set-radio-1-beacon", true],
        ["set-radio-2-beacon", false],
      ]);
      expect(wrapper.find("#set-radio-3-beacon").exists()).toBe(false);
    });

    it("greys the last tick that is ticked, so that the beacon is switched off by the interval alone, and only that one", () => {
      const { wrapper } = radiosPane([FM(), HF({ choices: { beacon: false, path: null, digipeat: null } })]);
      expect(ticks(wrapper).map((tick) => tick.attributes("disabled") !== undefined)).toEqual([true, false]);
      const all = radiosPane([FM(), HF()]).wrapper;
      expect(ticks(all).map((tick) => tick.attributes("disabled") !== undefined)).toEqual([false, false]);
    });

    it("applies a tick at once as the radio's own setting, and the other is greyed while it is on its way", async () => {
      const { wrapper, send, daemon } = radiosPane([FM(), HF(), FM3()]);
      await ticks(wrapper)[1]?.setValue(false);
      expect(configs(send)).toEqual([{ cmd: "set_config", values: { "radio/2/beacon": "false" } }]);
      expect(ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined])).toEqual([
        [true, false],
        [false, false],
        [true, false],
      ]);
      await ticks(wrapper)[2]?.setValue(false);
      expect(ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined])).toEqual([
        [true, true],
        [false, false],
        [false, false],
      ]);
      // the daemon takes both: the ticks are what it says from then on, also when another page changes them again
      const base = daemon.config.value;
      if (base === null) throw new Error("no config");
      await tell(daemon, { config: { ...base, radio_values: { ...base.radio_values, "radio/2/beacon": "false", "radio/3/beacon": "false" } } });
      await tell(daemon, { config: { ...base, radio_values: { ...base.radio_values, "radio/2/beacon": "false", "radio/3/beacon": "false" } } });
      expect(ticks(wrapper).map((tick) => tick.element.checked)).toEqual([true, false, false]);
      await tell(daemon, { config: { ...base, radio_values: { ...base.radio_values, "radio/2/beacon": "true", "radio/3/beacon": "false" } } });
      expect(ticks(wrapper).map((tick) => tick.element.checked)).toEqual([true, true, false]);
      expect(configs(send)).toHaveLength(2);
    });

    it("shows the daemon's refusal of a tick under the row, in its coded words, and the tick as it is in force", async () => {
      const { wrapper, daemon } = radiosPane([FM(), HF()]);
      await ticks(wrapper)[1]?.setValue(false);
      await tell(daemon, {
        lastError: {
          cmd: "set_config",
          key: "radio/2/beacon",
          code: "radio.unknown",
          params: { radio: 2 },
          text: "set_config: radio/2/beacon: there is no radio 2",
          n: 1,
        },
      });
      expect(sendOn(wrapper)?.querySelector(".field-error")?.textContent).toBe("there is no radio 2");
      expect(sendOn(wrapper)?.classList.contains("invalid")).toBe(true);
      expect(ticks(wrapper).map((tick) => tick.element.checked)).toEqual([true, true]);
    });

    it("takes a refusal away when another tick is pressed: the row's one line is about the latest press", async () => {
      const { wrapper, daemon } = radiosPane([FM(), HF(), FM3()]);
      await ticks(wrapper)[1]?.setValue(false);
      await tell(daemon, {
        lastError: {
          cmd: "set_config",
          key: "radio/2/beacon",
          code: "radio.unknown",
          params: { radio: 2 },
          text: "set_config: radio/2/beacon: there is no radio 2",
          n: 1,
        },
      });
      expect(sendOn(wrapper)?.querySelector(".field-error")?.textContent).toBe("there is no radio 2");
      await ticks(wrapper)[2]?.setValue(false);
      expect(sendOn(wrapper)?.querySelector(".field-error")).toBeNull();
      expect(sendOn(wrapper)?.classList.contains("invalid")).toBe(false);
    });

    it("shows the main radio's tick ticked and greyed while no radio that is on is ticked, and a tick of another keeps it ticked (plan rule 3.1)", async () => {
      const none = { choices: { beacon: false, path: "", digipeat: false } };
      const hfNone = { choices: { beacon: false, path: null, digipeat: null } };
      const { wrapper, send, daemon } = radiosPane([FM(), HF(hfNone), FM3(none)], {}, { status: status({ main_radio: 1, beacon_interval_min: 20 }) });
      expect(ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined])).toEqual([
        [true, true],
        [false, false],
        [false, false],
      ]);
      // FM is switched off: the beacon goes out on the main radio, now HF, and its tick says so
      await tell(daemon, {
        radios: radiosTopic(FM({ enabled: false }), HF(hfNone), FM3(none)),
        status: status({ main_radio: 2, beacon_interval_min: 20 }),
      });
      expect(tickNames(wrapper)).toEqual(["HF", "FM 2"]);
      expect(ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined])).toEqual([
        [true, true],
        [false, false],
      ]);
      expect(fold(wrapper).map((line) => line.split(":")[0])).toEqual(["HF"]);
      await ticks(wrapper)[1]?.setValue(true);
      expect(configs(send)).toEqual([{ cmd: "set_config", values: { "radio/2/beacon": "true", "radio/3/beacon": "true" } }]);
      expect(ticks(wrapper).map((tick) => [tick.element.checked, tick.attributes("disabled") !== undefined])).toEqual([
        [true, false],
        [true, false],
      ]);
    });

    it("has six ticks that wrap onto more lines, each tick and its name together, a name of 8 characters whole, each with its own id (the width of 375 px is the browser's to show)", () => {
      const { wrapper } = radiosPane(SIX());
      expect(tickNames(wrapper)).toEqual(["Shack", "20 m", "Mobile12", "Kitchen", "Dummy", "Direwolf"]);
      expect(sendOn(wrapper)?.querySelector(".field-control")?.classList.contains("toolbar-checks")).toBe(true);
      expect(cssRule(".toolbar-checks")).toMatch(/flex-wrap:\s*wrap/);
      expect(cssRule(".check")).toMatch(/white-space:\s*nowrap/);
      expect(cssRule(".field-control")).toMatch(/min-width:\s*0/);
      expect(new Set(ticks(wrapper).map((tick) => tick.attributes("id"))).size).toBe(6);
      expect(fold(wrapper)).toHaveLength(6);
    });
  });

  describe("the state of the beacon", () => {
    it("says each radio's beacon behind the arrow, by its name, with its own interval: FM 20 while HF keeps 30", () => {
      const { wrapper } = radiosPane([
        FM({ beacon: { last_sent: ago(240), next_due: later(16 * 60), interval_min: 20, problem: null } }),
        HF({ beacon: { last_sent: ago(120), next_due: later(29 * 60), interval_min: 30, problem: null } }),
      ]);
      expect(block(wrapper).find(".tncstatus").text()).toBe("Last beacon 2 min ago · next in 16 min (every 20 min)");
      expect(fold(wrapper)).toEqual(["FM: last beacon 4 min ago · next in 16 min (every 20 min)", "HF: last beacon 2 min ago · next in 29 min (every 30 min)"]);
    });

    it("lists the radios the beacon goes out on: not one whose Send on is unticked, nor one that is off", () => {
      const { wrapper } = radiosPane([
        FM(),
        HF({ choices: { beacon: false, path: null, digipeat: null } }),
        FM3({ name: "Mobile12" }),
        radioRow(4, "kiss", { enabled: false }),
      ]);
      expect(fold(wrapper).map((line) => line.split(":")[0])).toEqual(["FM", "Mobile12"]);
    });

    it("has no Beacon choice before the daemon has told the radios (it tells them before the settings, so the form comes with them), and each radio's beacon once they come", async () => {
      const told = [
        FM({ beacon: { last_sent: ago(240), next_due: later(16 * 60), interval_min: 20, problem: null } }),
        HF({ beacon: { last_sent: null, next_due: null, interval_min: 30, problem: null } }),
      ];
      const { wrapper, daemon } = radiosPane(null, {}, { values: told });
      expect([ticks(wrapper).length, wrapper.find("#set-beacon-interval_min").exists(), wrapper.find(".beaconstatus").exists()]).toEqual([0, false, false]);
      await tell(daemon, { radios: radiosTopic(...told) });
      expect(ticks(wrapper)).toHaveLength(2);
      expect(block(wrapper).find(".tncstatus").text()).toBe("Last beacon 4 min ago · next in 16 min (every 20 min)");
      expect(fold(wrapper)).toEqual(["FM: last beacon 4 min ago · next in 16 min (every 20 min)", "HF: no beacon sent yet · no timed beacon"]);
    });

    it("says each radio's beacon of a moving station too: FM by SmartBeaconing, HF by its own interval", () => {
      const { wrapper } = radiosPane(
        [
          FM({ beacon: { last_sent: ago(240), next_due: later(60), interval_min: 20, problem: null } }),
          HF({ beacon: { last_sent: ago(120), next_due: later(29 * 60), interval_min: 30, problem: null } }),
        ],
        { "gps/source": "gpsd" },
        { gps: gpsState() },
      );
      expect(fold(wrapper).filter((line) => /^(FM|HF): /.test(line))).toEqual([
        "FM: last beacon 4 min ago · next in 1 min",
        "HF: last beacon 2 min ago · next in 29 min (every 30 min)",
      ]);
    });
  });

  describe("Beacon now and Send status now", () => {
    const waiting = { state: "waiting" as const };

    it("send while one radio the beacon goes on is connected, and Send status now while the main radio is", async () => {
      const { wrapper, send } = radiosPane([FM(waiting), HF()], { "status/source": "text" });
      expect(buttons(wrapper).map((button) => button.attributes("disabled") === undefined)).toEqual([true, false]);
      expect(wrapper.find("#status-now").attributes("title")).toBe("FM: not connected");
      await wrapper.find("#beacon-now").trigger("click");
      await wrapper.find("#beacon-now").trigger("click");
      expect(send).toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("is off while none of the radios it goes on is connected, with those radios as its title; an unticked radio's link does not count", () => {
      const { wrapper } = radiosPane([FM(waiting), HF({ state: "connecting", name: "20 m" }), FM3({ choices: { beacon: false, path: "", digipeat: false } })], {
        "status/source": "text",
      });
      const button = wrapper.find("#beacon-now");
      expect(button.attributes("disabled")).toBeDefined();
      expect(button.attributes("title")).toBe("FM: not connected\n20 m: not connected");
    });

    it("goes on the main radio when no radio is ticked, and waits for it", () => {
      const none = { choices: { beacon: false, path: "", digipeat: false } };
      const { wrapper } = radiosPane([FM({ ...none, ...waiting }), FM3(none)], {}, { status: status({ main_radio: 1 }) });
      expect(wrapper.find("#beacon-now").attributes("disabled")).toBeDefined();
      expect(
        radiosPane([FM(none), FM3({ ...none, ...waiting })], {}, { status: status({ main_radio: 1 }) })
          .wrapper.find("#beacon-now")
          .attributes("disabled"),
      ).toBeUndefined();
    });

    it("forgets the first press when the radios it would go on drop, as it does when the link drops", async () => {
      const { wrapper, send, daemon } = radiosPane([FM(), HF({ choices: { beacon: false, path: null, digipeat: null } })], { "status/source": "text" });
      await wrapper.find("#beacon-now").trigger("click");
      expect(wrapper.find("#beacon-now").text()).toBe("Really send?");
      await tell(daemon, { radios: radiosTopic(FM(waiting), HF({ choices: { beacon: false, path: null, digipeat: null } })) });
      expect(wrapper.find("#beacon-now").attributes("disabled")).toBeDefined();
      await tell(daemon, { radios: radiosTopic(FM(), HF({ choices: { beacon: false, path: null, digipeat: null } })) });
      expect(wrapper.find("#beacon-now").text()).toBe("Beacon now");
      await wrapper.find("#beacon-now").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "beacon_now" });
    });

    it("with one radio, is off without the link and says so as Send does", () => {
      const { wrapper } = pane({ "status/source": "text" }, { connected: false });
      expect(buttons(wrapper).map((button) => button.attributes("title"))).toEqual(["The radio is not connected", "The radio is not connected"]);
      expect(buttons(pane({ "status/source": "text" }).wrapper).map((button) => button.attributes("title"))).toEqual([undefined, undefined]);
    });

    it("with one radio that sends beside one that only listens, is off while the one that sends is not connected, whatever the other is", async () => {
      const text = (extra: Partial<RadioRow> = {}) => radioRow(3, "tnc-text", { number: 2, ...extra });
      const { wrapper, daemon } = radiosPane([FM({ state: "waiting" }), text()], { "status/source": "text" });
      const words = t("compose.tnc_not_connected"); // (the words of Send's title with one radio)
      expect(buttons(wrapper).map((button) => [button.attributes("disabled") !== undefined, button.attributes("title")])).toEqual([
        [true, words],
        [true, words],
      ]);
      await tell(daemon, { radios: radiosTopic(FM(), text({ state: "waiting" })) });
      expect(buttons(wrapper).map((button) => [button.attributes("disabled") !== undefined, button.attributes("title")])).toEqual([
        [false, undefined],
        [false, undefined],
      ]);
    });
  });

  describe("the Path rows of Advanced", () => {
    const pathLabels = (wrapper: Wrapper) =>
      group(wrapper, "Beacon")
        ?.findAll(".settings-fold .field > label")
        .map((l) => l.text())
        .filter((text) => /path/i.test(text));

    it("is one row, Path, with one radio, and none for the HF radio alone", () => {
      expect(pathLabels(pane().wrapper)).toEqual(["Path"]);
      expect(pathLabels(radiosPane([FM({ enabled: false }), HF()]).wrapper)).toEqual([]);
    });

    it("is a row for each radio that may carry a path, named while several radios are on: none for HF", () => {
      const { wrapper } = radiosPane([FM(), HF(), FM3({ choices: { beacon: true, path: "WIDE2-2", digipeat: false } })]);
      expect(pathLabels(wrapper)).toEqual(["FM: path", "FM 2: path"]);
      expect(wrapper.find("#set-radio-1-path").exists()).toBe(true);
      expect(wrapper.find<HTMLSelectElement>("#set-radio-3-path").element.value).toBe("custom");
      expect(wrapper.find<HTMLInputElement>("#set-radio-3-path-typed").element.value).toBe("WIDE2-2");
      expect(pathLabels(radiosPane([FM(), HF()]).wrapper)).toEqual(["FM: path"]);
    });

    it("sends each row as its radio's own setting: Direct only at once, a typed path when it is left, checked first as the beacon's path is", async () => {
      const { wrapper, send, daemon } = radiosPane([FM(), HF(), FM3()], {}, { attach: true });
      const answer = async (values: Record<string, string>) => {
        const base = daemon.config.value;
        if (base === null) throw new Error("no config");
        const flat = Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith("radio/")));
        await tell(daemon, { config: { ...base, values: { ...base.values, ...flat }, radio_values: { ...base.radio_values, ...values } } });
      };
      await wrapper.find("#set-radio-3-path").setValue("direct");
      await answer({ "radio/3/path": "DIRECT" });
      expect(wrapper.find<HTMLSelectElement>("#set-radio-3-path").element.value).toBe("direct");
      await wrapper.find("#set-radio-1-path").setValue("direct");
      await answer({ "radio/1/path": "DIRECT" });
      expect(configs(send)).toEqual([
        { cmd: "set_config", values: { "radio/3/path": "DIRECT" } },
        { cmd: "set_config", values: { "radio/1/path": "DIRECT" } },
      ]);
      await wrapper.find("#set-radio-3-path").setValue("custom");
      const typed = wrapper.find<HTMLInputElement>("#set-radio-3-path-typed");
      await typed.setValue("OH2RDK-7,NOT A CALL");
      await typed.trigger("blur");
      expect(configs(send)).toHaveLength(2);
      expect(wrapper.find("#set-radio-3-path").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe(
        "Calls separated by commas, 8 at the most",
      );
      await typed.setValue("OH2RDK-7");
      await typed.trigger("blur");
      expect(configs(send)[2]).toEqual({ cmd: "set_config", values: { "radio/3/path": "OH2RDK-7" } });
      wrapper.unmount();
    });

    it("is the one row, Path, of the one radio that is on when it is not radio 1, and sends that radio's own setting", async () => {
      const { wrapper, send } = radiosPane([FM({ removed: true, enabled: false }), FM3()]);
      expect(pathLabels(wrapper)).toEqual(["Path"]);
      expect(wrapper.find("#set-beacon-path").exists()).toBe(false);
      await wrapper.find("#set-radio-3-path").setValue("direct");
      expect(configs(send)).toEqual([{ cmd: "set_config", values: { "radio/3/path": "DIRECT" } }]);
    });

    it("has Travelling while a radio that is on does SmartBeaconing, and not for the HF radio alone", () => {
      const moving = { "gps/source": "gpsd" };
      const travelling = (wrapper: Wrapper) => wrapper.find("#set-beacon-travel").exists();
      expect(travelling(radiosPane([FM({ removed: true, enabled: false }), FM3()], moving).wrapper)).toBe(true);
      expect(travelling(radiosPane([FM({ enabled: false }), HF()], moving).wrapper)).toBe(false);
      expect(travelling(radiosPane([FM(), HF()], moving).wrapper)).toBe(true);
    });

    it("sends Recommended for a radio's own path, chosen or by emptying its Custom field", async () => {
      const custom = { choices: { beacon: true, path: "WIDE2-2", digipeat: false } };
      const { wrapper, send, daemon } = radiosPane([FM(), HF(), FM3(custom)], {}, { attach: true });
      const answer = async (path: string) => {
        const base = daemon.config.value;
        if (base === null) throw new Error("no config");
        await tell(daemon, { config: { ...base, radio_values: { ...base.radio_values, "radio/3/path": path } } });
      };
      await wrapper.find("#set-radio-3-path").setValue("recommended");
      expect(configs(send)).toEqual([{ cmd: "set_config", values: { "radio/3/path": "" } }]);
      await answer("");
      expect(wrapper.find<HTMLSelectElement>("#set-radio-3-path").element.value).toBe("recommended");
      await answer("WIDE2-2"); // (another page sets it again)
      expect(wrapper.find<HTMLSelectElement>("#set-radio-3-path").element.value).toBe("custom");
      const typed = wrapper.find<HTMLInputElement>("#set-radio-3-path-typed");
      await typed.setValue("");
      await typed.trigger("blur");
      expect(configs(send)[1]).toEqual({ cmd: "set_config", values: { "radio/3/path": "" } });
      wrapper.unmount();
    });

    it("greys every row in RX only, as it greys the one", () => {
      const { wrapper } = radiosPane([FM(), HF(), FM3()], { "station/transmit": "false" });
      expect(["#set-radio-1-path", "#set-radio-3-path"].map((id) => wrapper.find(id).attributes("disabled"))).toEqual(["", ""]);
    });
  });
});

describe("BeaconPane: the comment and the status count what is left, as a message does", () => {
  const counterOf = (wrapper: Wrapper, id: string) => wrapper.find(id).element.closest(".field")?.querySelector(".compose-left");
  const typeInto = async (wrapper: Wrapper, id: string, text: string) => {
    const input = wrapper.find<HTMLInputElement>(id);
    input.element.value = text;
    await input.trigger("input");
    return input.element.value;
  };

  it("has the counter of a message right of the Comment, of the 43 characters a comment may have, and of 36 with a power (the PHG extension)", async () => {
    const { wrapper } = pane();
    expect(counterOf(wrapper, "#set-station-comment")?.textContent).toBe("36 left");
    expect(counterOf(wrapper, "#set-station-comment")?.getAttribute("title")).toBe("36 of 43 characters left");
    expect(counterOf(wrapper, "#set-station-comment")?.className).toBe("compose-left mono");
    await typeInto(wrapper, "#set-beacon-power_w", "5");
    expect(counterOf(wrapper, "#set-station-comment")?.textContent).toBe("29 left");
    expect(counterOf(wrapper, "#set-station-comment")?.getAttribute("title")).toBe("29 of 36 characters left");
  });

  it("takes no more than the comment may have: a paste is cut at the limit", async () => {
    const { wrapper } = pane({ "beacon/power_w": "5" });
    expect(await typeInto(wrapper, "#set-station-comment", "z".repeat(50))).toBe("z".repeat(36));
    expect(counterOf(wrapper, "#set-station-comment")?.textContent).toBe("0 left");
  });

  it("shows a comment that became too long (a power was set after it) as it is, with how many are over, and lets it only be shortened", async () => {
    const long = "w".repeat(40);
    const { wrapper } = pane({ "beacon/power_w": "5", "station/comment": long });
    expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe(long);
    expect(counterOf(wrapper, "#set-station-comment")?.textContent).toBe("4 over");
    expect(await typeInto(wrapper, "#set-station-comment", long + "w")).toBe(long);
    expect(await typeInto(wrapper, "#set-station-comment", long.slice(0, 39))).toBe(long.slice(0, 39));
  });

  it("counts the 55 characters of the status text and takes no more", async () => {
    const { wrapper } = pane({ "status/source": "text", "station/status": "QRV 145.500" });
    expect(counterOf(wrapper, "#set-station-status")?.textContent).toBe("44 left");
    expect(await typeInto(wrapper, "#set-station-status", "s".repeat(60))).toBe("s".repeat(55));
    expect(counterOf(wrapper, "#set-station-status")?.textContent).toBe("0 left");
  });

  it("counts a status made from the radio as the daemon checks it, the frequency and the mode at their widest", async () => {
    const { wrapper } = pane({ "status/source": "rig", "status/rigctld": "127.0.0.1:4532" });
    expect(counterOf(wrapper, "#set-status-template")?.textContent).toBe("32 left"); // (QRV {freq} {mode}: 4 + 12 + 1 + 6)
    expect(await typeInto(wrapper, "#set-status-template", "QRV {freq} {mode} " + "x".repeat(40))).toBe("QRV {freq} {mode} " + "x".repeat(31));
    expect(counterOf(wrapper, "#set-status-template")?.textContent).toBe("0 left");
  });
});
