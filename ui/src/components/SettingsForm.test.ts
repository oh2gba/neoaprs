import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import type { Scope } from "@/lib/settings";
import { CONFIG_KEYS } from "@/protocol/lists";
import type { PortsMessage } from "@/protocol/protocol";
import { cssRule } from "@/test/css";
import { fakeDaemon, tell, withDaemon, type Given } from "@/test/context";
import { configValues, mapFile, mapState, toastOf } from "@/test/fixtures";

/** The form in a page whose settings are the fixtures' with `extra` over them; `more` is what else the context has. */
function make(extra: Record<string, string> = {}, scope: Scope = "settings", more: Given = {}) {
  const daemon = fakeDaemon({ config: configValues(extra), ...more });
  const wrapper = mount(SettingsForm, { props: { scope }, global: withDaemon(daemon) });
  return { wrapper, send: daemon.send, daemon };
}

/** This browser alerts with the sound and a pop-up, so that the page shows both tests (a page on the loopback starts at off, which shows none). */
const alertWithBoth = () => localStorage.setItem("NeoAPRS.alert.mode", "both");
afterEach(() => localStorage.clear());

const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
const portList = (extra: Partial<PortsMessage> = {}): PortsMessage => ({
  type: "ports",
  search: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyS0", "n/a")],
  ...extra,
});

describe("SettingsForm", () => {
  it("has a field for every key of the Settings tab, in groups, and none of the beacon's", () => {
    alertWithBoth();
    const { wrapper } = make();
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).toEqual([
      "TNC",
      "iGate",
      "Digipeater",
      "Web page",
      "Notifications",
      "On the NeoAPRS computer i",
      "In this browser",
      "Map",
      "Update check",
      "Help",
      "About",
    ]);
    expect(wrapper.findAll("form > fieldset").map((f) => f.find("legend").text())).toEqual([
      "TNC",
      "iGate",
      "Digipeater",
      "Web page",
      "Notifications",
      "Map",
      "Update check",
      "Help",
      "About",
    ]);
    const beacons = ["beacon/", "station/", "status/", "gps/"]; // (the Beacon tab's)
    const elsewhere = [
      "tcp/host", // (only for a TNC reached over TCP)
      "tcp/port",
      "web/key",
      "web/https",
      "serial/last_port",
      "update/url",
      "serial/pattern",
      "serial/skip",
      "web/port",
      "web/allowed_hosts",
      "igate/server", // (left to the shell: the default suits everyone)
      "map/maxzoom",
      "map/source",
      "map/station_hours", // (the Stations tab has it)
    ];
    expect(wrapper.findAll(".field")).toHaveLength(
      CONFIG_KEYS.filter((k) => !beacons.some((prefix) => k.startsWith(prefix)) && !elsewhere.includes(k)).length +
        1 + // (the New version row of the Update check group, which is no setting)
        3 + // (the browser's own: Alert for a new message, Sound, Pop-up)
        1, // (Language)
    );
    expect(wrapper.find("#set-station-lat").exists()).toBe(false);
  });

  it("has no field for what is fixed or left to the shell: the log time, the daily update check, the page's port and host names", () => {
    const { wrapper } = make();
    for (const id of ["set-log-keep_days", "set-update-check", "set-web-port", "set-web-allowed_hosts", "set-update-url"])
      expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
    expect(wrapper.text()).not.toContain("Allowed hosts");
  });

  it("has no group called Other, and no raw key as a label, whatever the daemon lists", () => {
    const { wrapper } = make();
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).not.toContain("Other");
    for (const label of wrapper.findAll("label")) expect(label.text()).not.toMatch(/\//);
  });

  it("has our station's keys, then the beacon's, in the Beacon scope", () => {
    const wrapper = mount(SettingsForm, {
      props: { scope: "beacon" },
      global: withDaemon(),
    });
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).toEqual(["Station", "Beacon", "Status"]);
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual(["Call", "Position", "Symbol", "Beacon", "Comment", "Power", "Path", "Status"]);
  });

  describe("the position choice of the Station group of the Beacon tab", () => {
    const group = (wrapper: ReturnType<typeof make>["wrapper"], title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
    const labels = (wrapper: ReturnType<typeof make>["wrapper"], title = "Station") =>
      group(wrapper, title)
        ?.findAll(".field > label")
        .map((l) => l.text());

    it("is one choice under the call: Fixed, a GPS via gpsd or a GPS on a serial port, and there is no Mobile group, GPS source or Mobile switch", () => {
      const { wrapper } = make({}, "beacon");
      expect(labels(wrapper)).toEqual(["Call", "Position", "Symbol"]);
      expect(wrapper.find<HTMLSelectElement>("#set-gps-source").element.value).toBe("off");
      expect(wrapper.findAll("#set-gps-source option").map((o) => [o.attributes("value"), o.text()])).toEqual([
        ["off", "Fixed"],
        ["gpsd", "A GPS via gpsd"],
        ["serial", "A GPS on a serial port"],
      ]);
      expect(group(wrapper, "Mobile")).toBeUndefined();
      expect(wrapper.text()).not.toContain("GPS source");
      expect(wrapper.find("#set-beacon-mobile").exists()).toBe(false);
      expect(wrapper.find(".settings details.disclosure summary").text()).not.toBe("SmartBeaconing");
    });

    it("has the (i) of the choice, which says what each answer makes the station", async () => {
      const { wrapper } = make({}, "beacon");
      const field = wrapper.find("#set-gps-source").element.closest(".field");
      expect(field?.querySelector(".info-toggle")).not.toBeNull();
      (field?.querySelector(".info-toggle") as HTMLElement).click();
      await wrapper.vm.$nextTick();
      expect(field?.querySelector(".info-text")?.textContent).toContain("Fixed: the station stays at the location below");
      expect(field?.querySelector(".info-text")?.textContent).toContain("A GPS: the position, course and speed come from the receiver");
    });

    it("asks for the address of gpsd for gpsd, with the default as the placeholder, and no place to give while a GPS is chosen", () => {
      const { wrapper } = make({ "gps/source": "gpsd" }, "beacon");
      expect(labels(wrapper)).toEqual(["Call", "Position", "gpsd address", "Symbol"]);
      expect(wrapper.find("#set-gps-host").attributes("placeholder")).toBe("127.0.0.1:2947");
    });

    it("asks for the port and the speed of the receiver for a serial one", () => {
      const { wrapper } = make({ "gps/source": "serial", "gps/baud": "9600" }, "beacon");
      expect(labels(wrapper)).toEqual(["Call", "Position", "GPS port", "GPS speed", "Symbol"]);
      expect(wrapper.find("#set-gps-device").element.tagName).toBe("SELECT");
      expect(wrapper.find<HTMLInputElement>("#set-gps-baud").element.value).toBe("9600");
      expect(wrapper.find("#set-gps-baud").element.parentElement?.textContent).toContain("baud");
    });

    describe("the port of a serial receiver", () => {
      const options = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.findAll("#set-gps-device option").map((o) => [o.attributes("value"), o.text()]);

      it("is picked from the ports of the system, with not set first and Other... last, and never says find automatically or found", () => {
        const { wrapper } = make({ "gps/source": "serial" }, "beacon", { ports: portList() });
        expect(options(wrapper)).toEqual([
          ["", "not set"],
          ["/dev/ttyUSB0", "/dev/ttyUSB0 - FT232R USB UART"],
          ["/dev/ttyS0", "/dev/ttyS0"],
          ["\u0000other", "Other..."],
        ]);
        expect(wrapper.find<HTMLSelectElement>("#set-gps-device").element.value).toBe("");
        expect(group(wrapper, "Station")?.find(".port-found").exists()).toBe(false);
        expect(group(wrapper, "Station")?.text()).not.toContain("find automatically");
      });

      it("is not set where the daemon does not search for the radio either", () => {
        const { wrapper } = make({ "gps/source": "serial" }, "beacon", { ports: portList({ search: false }) });
        expect(options(wrapper)[0]).toEqual(["", "not set"]);
      });

      it("keeps a port that is set and the system does not list among the options", () => {
        const { wrapper } = make({ "gps/source": "serial", "gps/device": "socket://10.0.0.5:4001" }, "beacon", { ports: portList() });
        expect(options(wrapper).map(([value]) => value)).toContain("socket://10.0.0.5:4001");
        expect(wrapper.find<HTMLSelectElement>("#set-gps-device").element.value).toBe("socket://10.0.0.5:4001");
      });

      it("applies a port picked at once", async () => {
        const { wrapper, send } = make({ "gps/source": "serial" }, "beacon", { ports: portList() });
        await wrapper.find("#set-gps-device").setValue("/dev/ttyUSB0");
        expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "gps/device": "/dev/ttyUSB0" } });
      });

      it("lets a path or a socket address be typed under Other..., sent when the field is left", async () => {
        const { wrapper, send } = make({ "gps/source": "serial" }, "beacon", { ports: portList() });
        await wrapper.find("#set-gps-device").setValue("\u0000other");
        const typed = wrapper.find<HTMLInputElement>("#set-gps-device-typed");
        expect(typed.attributes("placeholder")).toBe("/dev/ttyUSB1");
        expect(send).not.toHaveBeenCalled();
        await typed.setValue("socket://10.0.0.5:4001");
        await typed.trigger("keydown.enter");
        expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "gps/device": "socket://10.0.0.5:4001" } });
      });

      it("asks the system for its ports again on Refresh", async () => {
        const { wrapper, send } = make({ "gps/source": "serial" }, "beacon", { ports: portList() });
        await wrapper
          .findAll("button")
          .find((b) => b.text() === "Refresh")
          ?.trigger("click");
        expect(send).toHaveBeenCalledWith({ cmd: "list_ports" });
      });

      it("appears when A GPS on a serial port is chosen, though the port is still empty", async () => {
        const { wrapper, send } = make({}, "beacon", { ports: portList() });
        expect(wrapper.find("#set-gps-device").exists()).toBe(false);
        await wrapper.find("#set-gps-source").setValue("serial");
        expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "gps/source": "serial" } });
        expect(wrapper.find("#set-gps-device").exists()).toBe(true);
      });

      it("is not there for gpsd or for no source", () => {
        expect(make({ "gps/source": "gpsd" }, "beacon").wrapper.find("#set-gps-device").exists()).toBe(false);
        expect(make({}, "beacon").wrapper.find("#set-gps-device").exists()).toBe(false);
      });
    });

    it("applies the choice at once, and the port and speed when they are left", async () => {
      const { wrapper, send } = make({ "gps/source": "serial" }, "beacon");
      await wrapper.find("#set-gps-source").setValue("gpsd");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "gps/source": "gpsd" } });
      const baud = wrapper.find<HTMLInputElement>("#set-gps-baud");
      expect(baud.exists()).toBe(false);
    });

    it("sends the speed of a serial receiver when it is finished", async () => {
      const { wrapper, send } = make({ "gps/source": "serial" }, "beacon");
      const baud = wrapper.find<HTMLInputElement>("#set-gps-baud");
      await baud.setValue("9600");
      await baud.trigger("keydown", { key: "Enter" });
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "gps/baud": "9600" } });
    });

    it("shows the Location (Choose on map, the place, the coordinates and the locator behind it) for Fixed and hides it while a GPS is chosen, in both directions", async () => {
      const { wrapper } = make({ "station/lat": "60.17", "station/lon": "24.94" }, "beacon");
      const location = () =>
        ["button.location-pick", ".location-place", "#set-station-lat", "#set-station-lon", "#set-station-locator"].map((css) => wrapper.find(css).exists());
      expect(wrapper.find(".location-field .field-label").text()).toBe("Location");
      expect(location()).toEqual([true, true, false, false, false]);
      await wrapper.find(".location-place").trigger("click");
      expect(location()).toEqual([true, true, true, true, true]);
      await wrapper.find("#set-gps-source").setValue("gpsd");
      expect(wrapper.find(".location-field").exists()).toBe(false);
      expect(location()).toEqual([false, false, false, false, false]);
      expect(wrapper.text()).not.toContain("Home position");
      await wrapper.find("#set-gps-source").setValue("serial");
      expect(wrapper.find(".location-field").exists()).toBe(false);
      await wrapper.find("#set-gps-source").setValue("off");
      expect(location()[0] && location()[1]).toBe(true);
    });

    it("hides the Location of a GPS station without touching the stored place", () => {
      const { wrapper, send } = make({ "gps/source": "gpsd", "station/lat": "60.17", "station/lon": "24.94" }, "beacon");
      expect(wrapper.find(".location-field").exists()).toBe(false);
      expect(send).not.toHaveBeenCalled();
    });

    describe("the Beacon group", () => {
      const beaconLabels = (wrapper: ReturnType<typeof make>["wrapper"]) => labels(wrapper, "Beacon");
      const folds = (wrapper: ReturnType<typeof make>["wrapper"]) =>
        group(wrapper, "Beacon")
          ?.findAll("details > summary")
          .map((f) => f.text());

      it("has the interval, the comment, the antenna and the path of a fixed station, and no Travelling", () => {
        const { wrapper } = make({ "beacon/power_w": "5" }, "beacon");
        expect(beaconLabels(wrapper)).toEqual(["Beacon", "Comment", "Power", "Antenna height", "Antenna gain", "Antenna direction", "Path"]);
        expect(folds(wrapper)).toEqual(["Antenna", "Advanced"]);
        expect(wrapper.find("#set-beacon-travel").exists()).toBe(false);
      });

      it("has the Beacon choice and Travelling, and no antenna, for a moving station, whichever GPS", () => {
        for (const source of ["gpsd", "serial"]) {
          const { wrapper } = make({ "gps/source": source, "beacon/power_w": "5" }, "beacon");
          expect(beaconLabels(wrapper), source).toEqual(["Beacon", "Travelling", "Comment", "Path"]);
          expect(folds(wrapper), source).toEqual(["Advanced"]);
          for (const id of ["beacon-power_w", "beacon-antenna_height_m", "beacon-antenna_gain_db", "beacon-antenna_direction"])
            expect(wrapper.find(`#set-${id}`).exists(), id).toBe(false);
        }
      });

      it("offers a moving station Off and On (SmartBeaconing), and a fixed one Off and the three intervals", () => {
        const options = (wrapper: ReturnType<typeof make>["wrapper"]) =>
          wrapper.findAll("#set-beacon-interval_min option").map((o) => [o.attributes("value"), o.text()]);
        expect(options(make({}, "beacon").wrapper)).toEqual([
          ["0", "Off"],
          ["30", "Every 30 min"],
          ["60", "Every 60 min"],
          ["180", "Every 3 hours"],
        ]);
        for (const source of ["gpsd", "serial"]) {
          expect(options(make({ "gps/source": source }, "beacon").wrapper), source).toEqual([
            ["0", "Off"],
            ["30", "On (SmartBeaconing)"],
          ]);
        }
      });

      it("shows a moving station's stored interval as On, and stores the default interval when On is chosen from Off", async () => {
        const stored = make({ "gps/source": "gpsd", "beacon/interval_min": "180" }, "beacon");
        expect(stored.wrapper.find<HTMLSelectElement>("#set-beacon-interval_min").element.value).toBe("30");
        const { wrapper, send } = make({ "gps/source": "gpsd", "beacon/interval_min": "0" }, "beacon");
        expect(wrapper.find<HTMLSelectElement>("#set-beacon-interval_min").element.value).toBe("0");
        await wrapper.find("#set-beacon-interval_min").setValue("30");
        expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "30" } });
        await stored.wrapper.find("#set-beacon-interval_min").setValue("0");
        expect(stored.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "0" } });
      });

      it("follows the choice as it is made, in both directions, with the antenna back as it was", async () => {
        const { wrapper } = make({ "beacon/power_w": "5" }, "beacon");
        await wrapper.find("#set-gps-source").setValue("gpsd");
        expect(beaconLabels(wrapper)).toEqual(["Beacon", "Travelling", "Comment", "Path"]);
        await wrapper.find("#set-gps-source").setValue("off");
        expect(beaconLabels(wrapper)).toEqual(["Beacon", "Comment", "Power", "Antenna height", "Antenna gain", "Antenna direction", "Path"]);
      });

      it("offers the four ways of travelling, By car first, with a one-line (i) that says what it changes", async () => {
        const { wrapper } = make({ "gps/source": "gpsd" }, "beacon");
        const select = wrapper.find<HTMLSelectElement>("#set-beacon-travel");
        expect(select.element.value).toBe("car");
        expect(select.findAll("option").map((o) => [o.attributes("value"), o.text()])).toEqual([
          ["car", "By car"],
          ["bicycle", "By bicycle"],
          ["foot", "On foot"],
          ["boat", "By boat"],
        ]);
        const field = select.element.closest(".field");
        (field?.querySelector(".info-toggle") as HTMLElement).click();
        await wrapper.vm.$nextTick();
        expect(field?.querySelectorAll(".info-text .info-line")).toHaveLength(1);
        expect(field?.querySelector(".info-text")?.textContent).toMatch(/how often the beacon goes and at which turns/);
      });

      it("applies the way of moving at once, and shows the one in force", async () => {
        const { wrapper, send } = make({ "gps/source": "gpsd", "beacon/travel": "foot" }, "beacon");
        expect(wrapper.find<HTMLSelectElement>("#set-beacon-travel").element.value).toBe("foot");
        await wrapper.find("#set-beacon-travel").setValue("boat");
        expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/travel": "boat" } });
      });
    });

    it("has none of the old Mobile switch or SmartBeaconing numbers, nor the names of the daemon's old keys in the page", () => {
      const { wrapper } = make({ "gps/source": "gpsd" }, "beacon");
      expect((CONFIG_KEYS as readonly string[]).filter((k) => k === "beacon/mobile" || k.startsWith("smart/"))).toEqual([]);
      expect(wrapper.find("#set-beacon-mobile").exists()).toBe(false);
      expect(wrapper.find("#set-smart-fast_kmh").exists()).toBe(false);
      expect(wrapper.text().replace("On (SmartBeaconing)", "")).not.toContain("SmartBeaconing");
      expect(wrapper.text()).not.toContain("Fast speed");
    });
  });

  describe("the Beacon group of the Beacon tab", () => {
    const group = (wrapper: ReturnType<typeof make>["wrapper"], title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
    const folds = (wrapper: ReturnType<typeof make>["wrapper"]) => group(wrapper, "Beacon")?.findAll("details.disclosure") ?? [];

    it("has Call, Location and Symbol in the Station group, and the comment with the beacon", () => {
      const { wrapper } = make({}, "beacon");
      expect(
        group(wrapper, "Station")
          ?.findAll(".field label, .field .field-label, h3")
          .map((e) => e.text()),
      ).toEqual(["Call", "Position", "Location", "Symbol"]);
      expect(group(wrapper, "Station")?.find("#set-station-comment").exists()).toBe(false);
      expect(group(wrapper, "Beacon")?.find("#set-station-comment").exists()).toBe(true);
    });

    it("is one choice for how often: off, every 30 or 60 minutes or every 3 hours, then the comment", () => {
      const { wrapper } = make({ "beacon/interval_min": "30" }, "beacon");
      const select = wrapper.find<HTMLSelectElement>("#set-beacon-interval_min");
      expect(wrapper.find("label[for=set-beacon-interval_min]").text()).toBe("Beacon");
      expect(select.element.tagName).toBe("SELECT");
      expect(select.findAll("option").map((o) => [o.attributes("value"), o.text()])).toEqual([
        ["0", "Off"],
        ["30", "Every 30 min"],
        ["60", "Every 60 min"],
        ["180", "Every 3 hours"],
      ]);
      expect(select.element.value).toBe("30");
      expect(
        group(wrapper, "Beacon")
          ?.findAll(".field > label")
          .map((l) => l.text())
          .slice(0, 2),
      ).toEqual(["Beacon", "Comment"]);
    });

    it("shows a stored interval that is none of the choices as one more, so that nothing changes until another is picked", async () => {
      const { wrapper, send } = make({ "beacon/interval_min": "20" }, "beacon");
      const select = wrapper.find<HTMLSelectElement>("#set-beacon-interval_min");
      expect(select.findAll("option").map((o) => o.text())).toEqual(["Off", "Every 30 min", "Every 60 min", "Every 3 hours", "Every 20 min"]);
      expect(select.element.value).toBe("20");
      expect(send).not.toHaveBeenCalled();
      await select.setValue("60");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "60" } });
    });

    it("applies the interval at once", async () => {
      const { wrapper, send } = make({}, "beacon");
      await wrapper.find("#set-beacon-interval_min").setValue("180");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "180" } });
    });

    it("keeps the antenna behind a closed Antenna heading and the path behind a closed Advanced heading, each with its (i)", () => {
      const { wrapper } = make({ "beacon/power_w": "5" }, "beacon");
      expect(folds(wrapper).map((f) => [f.find("summary").text(), (f.element as HTMLDetailsElement).open])).toEqual([
        ["Antenna", false],
        ["Advanced", false],
      ]);
      const antenna = folds(wrapper)[0];
      expect(antenna?.findAll(".field > label").map((l) => l.text())).toEqual(["Power", "Antenna height", "Antenna gain", "Antenna direction"]);
      expect(antenna?.findAll(".info-toggle")).toHaveLength(4);
      const advanced = folds(wrapper)[1];
      expect(advanced?.findAll(".field > label").map((l) => l.text())).toEqual(["Path"]);
      expect(advanced?.find(".info-toggle").exists()).toBe(true);
      expect(advanced?.find<HTMLSelectElement>("#set-beacon-path").element.value).toBe("recommended");
      expect(advanced?.findAll("#set-beacon-path option").map((o) => o.text())).toEqual(["Recommended (WIDE2-1)", "Direct only (no digipeaters)", "Custom…"]);
      expect(advanced?.find("#set-beacon-path-typed").exists()).toBe(false);
    });

    it("names the recommended path of the symbol in the Path choice, and follows a change of the symbol", async () => {
      const { wrapper, daemon } = make({ "beacon/power_w": "5", "station/symbol_table": "/", "station/symbol_code": ">" }, "beacon");
      const options = () => wrapper.findAll("#set-beacon-path option").map((o) => o.text());
      expect(options()[0]).toBe("Recommended (WIDE1-1,WIDE2-1)");
      await tell(daemon, { config: configValues({ "beacon/power_w": "5", "station/symbol_table": "/", "station/symbol_code": "-" }) });
      expect(options()[0]).toBe("Recommended (WIDE2-1)");
      await tell(daemon, { config: configValues({ "beacon/power_w": "5", "station/symbol_table": "E", "station/symbol_code": "s" }) });
      expect(options()[0]).toBe("Recommended (WIDE1-1,WIDE2-1)");
      expect(wrapper.find<HTMLSelectElement>("#set-beacon-path").element.value).toBe("recommended");
    });

    it("works the fields in the folds like the others: a typed one when it is left, a choice at once", async () => {
      const { wrapper, send, daemon } = make({ "beacon/power_w": "5" }, "beacon");
      await wrapper.find("#set-beacon-path").setValue("custom");
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-beacon-path-typed").setValue("WIDE2-2");
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-beacon-path-typed").trigger("blur");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
      await wrapper.find("#set-beacon-antenna_direction").setValue("N");
      expect(send).toHaveBeenCalledTimes(1); // (waits for the answer to the first)
      await tell(daemon, { config: configValues({ "beacon/power_w": "5", "beacon/path": "WIDE2-2" }) });
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "beacon/antenna_direction": "N" } });
    });

    it("is not in the Settings tab", () => {
      expect(make().wrapper.find("details.settings-fold").exists()).toBe(false);
    });
  });

  it("has a link at the top of the Settings tab which asks for the first-run guide, and none on the Beacon tab", async () => {
    const { wrapper } = make();
    const setup = wrapper.find("button.setup-open");
    expect(setup.text()).toBe("Run the setup guide again");
    expect(setup.attributes("type")).toBe("button");
    await setup.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(make({}, "beacon").wrapper.find(".setup-open").exists()).toBe(false);
  });

  it("shows the default as the placeholder of a field that is empty", () => {
    const config = configValues();
    config.defaults["map/radius_km"] = "45";
    const wrapper = mount(SettingsForm, { global: withDaemon(fakeDaemon({ config })) });
    expect(wrapper.find<HTMLInputElement>("#set-map-radius_km").attributes("placeholder")).toBe("45");
  });

  it("explains no field in words: no hint renders, only labels, placeholders, units, titles and the daemon's errors", () => {
    for (const scope of ["settings", "beacon"] as const) {
      const { wrapper } = make({}, scope);
      expect(wrapper.find(".hint").exists()).toBe(false);
      expect(wrapper.findAll(".field p")).toHaveLength(0);
      expect(wrapper.find("[id$='-hint']").exists()).toBe(false);
      for (const field of wrapper.findAll(".field")) {
        if (field.classes().includes("location-field")) continue; // (the row Location: a button, the place, a closed heading; its coordinate fields are checked on their own)
        const text = field.find("select").exists() ? field.find("label").text() : field.text(); // (the options of a select are its choices, not words about it; the (i) is closed and says "i")
        expect(text.length, text).toBeLessThan(42);
      }
    }
  });

  it("puts a unit after the field where one applies", () => {
    const { wrapper } = make();
    const unit = (id: string) => wrapper.find(`#${id}`).element.closest(".field")?.querySelector(".unit")?.textContent;
    expect(unit("set-serial-baud")).toBe("baud");
    expect(unit("set-map-radius_km")).toBe("km");
  });

  it("shows what an empty value means as the placeholder, else the default", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
    const beacon = make({ "status/source": "text" }, "beacon").wrapper;
    expect(beacon.find("#set-beacon-power_w").attributes("placeholder")).toBe("none");
    expect(beacon.find("#set-station-status").attributes("placeholder")).toBe("none");
  });

  it("has the antenna in the Antenna fold with its units, and a choice for the direction, once there is a power", async () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.find("#set-beacon-antenna_height_m").exists()).toBe(false);
    await wrapper.find("#set-beacon-power_w").setValue("5");
    const station = wrapper.find("details.settings-fold");
    expect(station?.find("#set-beacon-power_w").exists()).toBe(true);
    const units = ["power_w", "antenna_height_m", "antenna_gain_db"].map(
      (k) => station?.find(`#set-beacon-${k}`).element.closest(".field")?.querySelector(".unit")?.textContent,
    );
    expect(units).toEqual(["W", "m", "dB"]);
    const direction = station?.find("#set-beacon-antenna_direction");
    expect(direction?.element.tagName).toBe("SELECT");
    expect(direction?.findAll("option").map((o) => o.text())).toEqual(["omni", "N", "NE", "E", "SE", "S", "SW", "W", "NW"]);
    expect(wrapper.find("#set-beacon-dao").exists()).toBe(false);
    expect(wrapper.find("#set-beacon-compressed").exists()).toBe(false);
    expect(wrapper.find("#set-beacon-destination").exists()).toBe(false);
  });

  it("offers a choice for the TNC, and the port the daemon found is no field", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-tnc-profile").element.tagName).toBe("SELECT");
    expect(wrapper.find("#set-serial-last_port").exists()).toBe(false);
  });

  describe("the TNC profile", () => {
    const fieldIds = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper
        .findAll("fieldset")
        .find((f) => f.find("legend").text() === "TNC")
        ?.findAll("[id^='set-']")
        .map((e) => e.attributes("id"));

    it("is a select of the profiles by their names, the daemon's value chosen", () => {
      const { wrapper } = make();
      const select = wrapper.find<HTMLSelectElement>("#set-tnc-profile");
      expect(wrapper.find("label[for=set-tnc-profile]").text()).toBe("Radio type");
      expect(select.findAll("option").map((o) => o.text())).toEqual([
        "Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2",
        "Kenwood TM-D710 / TH-D72",
        "Kantronics KPC-3+",
        "KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)",
        "KISS over TCP (Direwolf, soundmodem)",
      ]);
      expect(select.element.value).toBe("kenwood-tnc2");
    });

    it("shows the port and the speed of a serial TNC", async () => {
      const { wrapper } = make();
      expect(fieldIds(wrapper)).toEqual(["set-tnc-profile", "set-serial-port", "set-serial-baud"]);
      await wrapper.find("#set-tnc-profile").setValue("kiss");
      expect(fieldIds(wrapper)).toEqual(["set-tnc-profile", "set-serial-port", "set-serial-baud"]);
    });

    it("shows the host and the port of the TCP server for KISS over TCP, and no serial port", async () => {
      const { wrapper } = make({ "serial/port": "/dev/ttyUSB0" });
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      expect(fieldIds(wrapper)).toEqual(["set-tnc-profile", "set-tcp-host", "set-tcp-port"]);
      expect(wrapper.find("#set-tcp-port").attributes("placeholder")).toBe("8001");
    });

    it("clears a serial device when a TCP profile is chosen, so that the daemon does not refuse the save, and keeps an address", async () => {
      const { wrapper, send } = make({ "serial/port": "/dev/ttyUSB0" });
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "tnc/profile": "kiss-tcp", "serial/port": "" } });
      const kept = make({ "serial/port": "tcp://10.0.0.5:8100" });
      await kept.wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      expect(kept.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "tnc/profile": "kiss-tcp" } });
    });

    it("shows the speed of the profile as the placeholder of an empty speed", async () => {
      const { wrapper } = make({ "serial/baud": "" });
      expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
      await wrapper.find("#set-tnc-profile").setValue("kantronics");
      expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
    });

    it("shows the refusal of the daemon under the profile", async () => {
      const { wrapper, daemon } = make();
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      await tell(daemon, {
        lastError: toastOf("set_config: tnc/profile: KISS over TCP connects over TCP (tcp/host and tcp/port), not to the serial port COM3"),
      });
      expect(wrapper.find("#set-tnc-profile").element.closest(".field")?.querySelector(".field-error")?.textContent).toContain("not to the serial port COM3");
    });
  });

  describe("the TNC port", () => {
    const OWNER = { "serial/port": "/dev/brainbox_3", "serial/pattern": "/dev/brainbox_*", "serial/last_port": "/dev/brainbox_3", "serial/baud": "9600" };
    const withPorts = (extra: Record<string, string> = {}, ports: PortsMessage | null = portList()) => make(extra, "settings", { ports });
    type Wrapper = ReturnType<typeof make>["wrapper"];
    const select = (wrapper: Wrapper) => wrapper.find<HTMLSelectElement>("#set-serial-port");
    const options = (wrapper: Wrapper) =>
      select(wrapper)
        .findAll("option")
        .map((o) => o.text());
    const headings = (wrapper: Wrapper) =>
      wrapper
        .findAll("fieldset")
        .find((f) => f.find("legend").text() === "TNC")
        ?.findAll(".subgroup");
    const found = (wrapper: Wrapper) => wrapper.find(".port-found");
    const labels = (wrapper: Wrapper) =>
      wrapper
        .findAll("fieldset")
        .find((f) => f.find("legend").text() === "TNC")
        ?.findAll("label")
        .map((l) => l.text());

    it("is one choice: find automatically, the ports the system lists, and Other", () => {
      const { wrapper } = withPorts();
      expect(wrapper.find("label[for=set-serial-port]").text()).toBe("Port");
      expect(select(wrapper).element.tagName).toBe("SELECT");
      expect(options(wrapper)).toEqual(["find automatically", "/dev/ttyUSB0 - FT232R USB UART", "/dev/ttyS0", "/dev/brainbox_3", "Other..."]);
      expect(select(wrapper).element.value).toBe("");
    });

    it("tells the port found last beside an automatic port, as a note and not a field", () => {
      const { wrapper } = withPorts({ "serial/port": "", "serial/last_port": "/dev/brainbox_3" });
      expect(found(wrapper).text()).toBe("found: /dev/brainbox_3");
      expect(wrapper.find("#set-serial-last_port").exists()).toBe(false);
      expect(wrapper.findAll("input[readonly]")).toHaveLength(0);
      expect(labels(wrapper)).not.toContain("Last port found");
    });

    it("says nothing of it before the radio was found, or while a port is named", () => {
      expect(found(withPorts({ "serial/port": "", "serial/last_port": "" }).wrapper).exists()).toBe(false);
      expect(found(withPorts(OWNER).wrapper).exists()).toBe(false);
    });

    it("shows a named port that the system does not list as chosen, once", () => {
      const { wrapper } = withPorts(OWNER);
      expect(select(wrapper).element.value).toBe("/dev/brainbox_3");
      expect(options(wrapper).filter((o) => o === "/dev/brainbox_3")).toHaveLength(1);
    });

    it("shows the port of the owner's station once, and not which ports the search looks at or skips (those stay in the daemon)", () => {
      const { wrapper } = withPorts(OWNER);
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed"]);
      expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
      expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
      expect(headings(wrapper)).toHaveLength(0);
    });

    it("says not set for the empty port where the daemon does not search", () => {
      expect(labels(withPorts().wrapper)).toEqual(["Radio type", "Port", "Speed"]);
      const { wrapper } = withPorts({}, portList({ search: false }));
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed"]);
      expect(headings(wrapper)).toHaveLength(0);
      expect(options(wrapper)[0]).toBe("not set");
    });

    it("shows no search and no port for KISS over TCP", async () => {
      const { wrapper } = withPorts(OWNER);
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      expect(labels(wrapper)).toEqual(["Radio type", "TCP host", "TCP port"]);
      expect(wrapper.find("#set-serial-port").exists()).toBe(false);
      expect(headings(wrapper)).toHaveLength(0);
      expect(wrapper.find(".port-found").exists()).toBe(false);
    });

    it("saves only the port when find automatically is chosen: the port is cleared and nothing else", async () => {
      const { wrapper, send } = withPorts(OWNER);
      await select(wrapper).setValue("");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "" } });
    });

    it("saves only the port that was picked from the list", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      await select(wrapper).setValue("/dev/ttyUSB0");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "/dev/ttyUSB0" } });
    });

    it("types a path or an address after Other, and saves it", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      expect(wrapper.find("#set-serial-port-typed").exists()).toBe(false);
      await select(wrapper).setValue("\u0000other");
      expect(wrapper.find("#set-serial-port-typed").attributes("placeholder")).toBe("/dev/ttyUSB0");
      await wrapper.find("#set-serial-port-typed").setValue("socket://10.0.0.5:8100");
      expect(send).not.toHaveBeenCalled(); // (not while it is typed)
      await wrapper.find("#set-serial-port-typed").trigger("blur");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "socket://10.0.0.5:8100" } });
    });

    it("sends a typed path on Enter, and Esc puts the port in force back", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      await select(wrapper).setValue("\u0000other");
      await wrapper.find("#set-serial-port-typed").setValue("/dev/ttyACM1");
      await wrapper.find("#set-serial-port-typed").trigger("keydown", { key: "Enter" });
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "/dev/ttyACM1" } });
      const other = withPorts({ "serial/port": "" });
      await select(other.wrapper).setValue("\u0000other");
      await other.wrapper.find("#set-serial-port-typed").setValue("/dev/nope");
      await other.wrapper.find("#set-serial-port-typed").trigger("keydown", { key: "Escape" });
      expect(select(other.wrapper).element.value).toBe("");
      expect(other.send).not.toHaveBeenCalled();
    });

    it("leaves a stored installation as it is: opening the page and leaving every field sends nothing", async () => {
      const { wrapper, send } = withPorts(OWNER);
      for (const input of wrapper.findAll("input[type=text]:not([readonly])")) await input.trigger("blur");
      expect(send.mock.calls.filter(([c]) => c.cmd === "set_config")).toHaveLength(0);
    });

    it("never sends the port found, whatever else is changed, and sends the changes one at a time", async () => {
      const { wrapper, send, daemon } = withPorts({ "serial/port": "" });
      await wrapper.find("#set-serial-baud").setValue("19200");
      await wrapper.find("#set-serial-baud").trigger("blur");
      await wrapper.find("#set-map-radius_km").setValue("200");
      await wrapper.find("#set-map-radius_km").trigger("blur");
      expect(send.mock.calls.filter(([c]) => c.cmd === "set_config")).toEqual([[{ cmd: "set_config", values: { "serial/baud": "19200" } }]]);
      await tell(daemon, { config: configValues({ "serial/port": "", "serial/baud": "19200" }) });
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/radius_km": "200" } });
    });

    it("follows the daemon when it finds the radio on another port", async () => {
      const { wrapper, daemon } = withPorts({ "serial/port": "", "serial/last_port": "/dev/ttyUSB0" });
      await tell(daemon, { config: configValues({ "serial/port": "", "serial/last_port": "/dev/ttyACM0" }) });
      expect(found(wrapper).text()).toBe("found: /dev/ttyACM0");
    });

    it("does not ask the daemon for the ports by itself (the page does, once connected), only with Refresh", async () => {
      const { wrapper, send } = withPorts();
      expect(send).not.toHaveBeenCalled();
      await wrapper
        .findAll("button")
        .find((b) => b.text() === "Refresh")
        ?.trigger("click");
      expect(send.mock.calls.filter(([c]) => c.cmd === "list_ports")).toHaveLength(1);
    });

    it("puts the unit and the (i) on the speed and the port", () => {
      const { wrapper } = withPorts();
      const field = (id: string) => wrapper.find(`#${id}`).element.closest(".field");
      expect(field("set-serial-baud")?.querySelector(".unit")?.textContent).toBe("baud");
      expect(field("set-serial-port")?.querySelector(".info-toggle")).not.toBeNull();
    });
  });

  describe("typed fields", () => {
    const type = async (wrapper: ReturnType<typeof make>["wrapper"], id: string, text: string) => {
      if (id.startsWith("set-station-l") && !wrapper.find(`#${id}`).exists()) await wrapper.find(".location-place").trigger("click"); // (the coordinates are behind the place)
      await wrapper.find(`#${id}`).setValue(text);
    };

    it("are sent when the field is left, and not while they are typed", async () => {
      const { wrapper, send } = make({}, "beacon");
      await type(wrapper, "set-beacon-path", "custom");
      await type(wrapper, "set-beacon-path-typed", "WIDE2-2");
      await type(wrapper, "set-station-comment", "Hello");
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-beacon-path-typed").trigger("blur");
      expect(send).toHaveBeenCalledTimes(1);
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
    });

    it("are sent on Enter, and not again when the field is left after", async () => {
      const { wrapper, send } = make({}, "beacon");
      await type(wrapper, "set-station-comment", "Hello");
      await wrapper.find("#set-station-comment").trigger("keydown", { key: "Enter" });
      await wrapper.find("#set-station-comment").trigger("blur");
      expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/comment": "Hello" } }]]);
    });

    it("are never sent when the page finds them wrong: the reason is under the field and the text stays", async () => {
      const { wrapper, send } = make({}, "beacon");
      await type(wrapper, "set-station-call", "OH2 GBA");
      await wrapper.find("#set-station-call").trigger("blur");
      await type(wrapper, "set-station-lat", "95");
      await wrapper.find("#set-station-lat").trigger("blur");
      expect(send).not.toHaveBeenCalled();
      expect(wrapper.find("#set-station-call").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Not a call");
      expect(wrapper.find("#set-station-lat").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Between -90 and 90");
      expect(wrapper.find<HTMLInputElement>("#set-station-lat").element.value).toBe("95");
    });

    it("go back to what is in force on Esc, with the reason gone", async () => {
      const { wrapper, send } = make({}, "beacon");
      await type(wrapper, "set-station-lat", "95");
      await wrapper.find("#set-station-lat").trigger("blur");
      await wrapper.find("#set-station-lat").trigger("keydown", { key: "Escape" });
      expect(wrapper.find<HTMLInputElement>("#set-station-lat").element.value).toBe("60.17");
      expect(wrapper.find(".field-error").exists()).toBe(false);
      await type(wrapper, "set-station-comment", "typing");
      await wrapper.find("#set-station-comment").trigger("keydown", { key: "Escape" });
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("NeoAPRS");
      await wrapper.find("#set-station-comment").trigger("blur");
      expect(send).not.toHaveBeenCalled();
    });

    it("show the field as changed while they are typed and not yet sent", async () => {
      const { wrapper } = make({}, "beacon");
      await type(wrapper, "set-station-comment", "Hello");
      expect(wrapper.find("#set-station-comment").element.closest(".field")?.classList.contains("changed")).toBe(true);
      await wrapper.find("#set-station-comment").trigger("blur");
      expect(wrapper.find("#set-station-comment").element.closest(".field")?.classList.contains("changed")).toBe(false);
    });
  });

  describe("fields that belong together", () => {
    it("send the latitude and the longitude in one set_config when focus leaves the pair, not when it moves from one to the other", async () => {
      const { wrapper, send } = make({}, "beacon");
      await wrapper.find(".location-place").trigger("click");
      await wrapper.find("#set-station-lat").setValue("61.5");
      await wrapper.find("#set-station-lat").trigger("blur", { relatedTarget: wrapper.find("#set-station-lon").element });
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-station-lon").setValue("25.5");
      await wrapper.find("#set-station-lon").trigger("blur");
      expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "61.5", "station/lon": "25.5" } }]]);
    });

    it("send the TCP host and the TCP port in one set_config, so that the TNC restarts once", async () => {
      const { wrapper, send } = make({ "tnc/profile": "kiss-tcp" });
      await wrapper.find("#set-tcp-host").setValue("10.0.0.5");
      await wrapper.find("#set-tcp-host").trigger("blur", { relatedTarget: wrapper.find("#set-tcp-port").element });
      await wrapper.find("#set-tcp-port").setValue("8100");
      await wrapper.find("#set-tcp-port").trigger("keydown", { key: "Enter" });
      expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "tcp/host": "10.0.0.5", "tcp/port": "8100" } }]]);
    });

    it("send a place picked on the map as latitude and longitude together", async () => {
      const { wrapper, send } = make({}, "beacon");
      await wrapper.setProps({ picked: { lat: 60.429449, lon: 24.1452399, n: 1 } });
      await wrapper.find(".location-place").trigger("click");
      expect(wrapper.find<HTMLInputElement>("#set-station-lat").element.value).toBe("60.42945");
      expect(wrapper.find<HTMLInputElement>("#set-station-lon").element.value).toBe("24.14524");
      expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.42945", "station/lon": "24.14524" } }]]);
    });
  });

  describe("choices", () => {
    it("apply at once: a list and a switch", async () => {
      const { wrapper, send } = make({ "beacon/power_w": "5" }, "beacon");
      await wrapper.find("#set-beacon-antenna_direction").setValue("N");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "beacon/antenna_direction": "N" } });
      const settings = make();
      await settings.wrapper.find("#set-digi-enabled").setValue(true);
      expect(settings.send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "digi/enabled": "true" } });
    });
  });

  describe("what the daemon answers", () => {
    it("shows the error of the daemon under the field it names, with the typed text kept and the value in force unchanged", async () => {
      const { wrapper, daemon } = make({}, "beacon");
      await wrapper.find("#set-station-comment").setValue("é is not ascii");
      await wrapper.find("#set-station-comment").trigger("blur");
      await tell(daemon, { lastError: toastOf("set_config: station/comment: 'é' is not ASCII") });
      const field = wrapper.find("#set-station-comment").element.closest(".field");
      expect(field?.querySelector(".field-error")?.textContent).toBe("'é' is not ASCII");
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("é is not ascii");
      expect(wrapper.find(".location-entry").exists()).toBe(false);
    });

    it("shows nothing beside the field while a change is on its way or when it is saved, so that nothing moves; a screen reader is told", async () => {
      const { wrapper, daemon } = make({}, "beacon");
      const field = () => wrapper.find("#set-station-comment").element.closest(".field");
      const shape = () => [...(field()?.querySelectorAll("*") ?? [])].map((e) => e.tagName).join(" ");
      const before = shape();
      await wrapper.find("#set-station-comment").setValue("Hello");
      await wrapper.find("#set-station-comment").trigger("blur");
      expect(wrapper.find("[role='status'][aria-live]").text()).toBe("");
      await tell(daemon, { config: configValues({ "station/comment": "Hello" }) });
      expect(wrapper.find("[role='status'][aria-live]").text()).toBe("Saved");
      expect(wrapper.find(".field-state").exists()).toBe(false);
      expect(wrapper.text()).not.toContain("Saved ✓");
      expect(wrapper.text()).not.toContain("Saving");
      expect(shape()).toBe(before);
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("Hello");
    });

    it("shows a refused choice as it was, with the reason under it", async () => {
      const { wrapper, daemon } = make();
      await wrapper.find("#set-tnc-profile").setValue("kiss");
      await tell(daemon, { lastError: toastOf("set_config: tnc/profile: KISS TNC is too much") });
      expect(wrapper.find<HTMLSelectElement>("#set-tnc-profile").element.value).toBe("kenwood-tnc2");
      expect(wrapper.find("#set-tnc-profile").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("KISS TNC is too much");
    });

    it("leaves a field that is being edited alone when the daemon tells other settings, and follows it in a field that is not", async () => {
      const { wrapper, daemon } = make({}, "beacon");
      await wrapper.find("#set-station-comment").setValue("mine");
      await tell(daemon, { config: configValues({ "station/comment": "theirs", "beacon/path": "WIDE2-2" }) });
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("mine");
      expect(wrapper.find<HTMLSelectElement>("#set-beacon-path").element.value).toBe("custom");
      expect(wrapper.find<HTMLInputElement>("#set-beacon-path-typed").element.value).toBe("WIDE2-2");
    });
  });

  describe("linked settings", () => {
    it("fills in the usual rigctld with the radio as the status, so that the choice is valid at once", async () => {
      const { wrapper, send } = make({}, "beacon");
      await wrapper.find("#set-status-source").setValue("rig");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "status/source": "rig", "status/rigctld": "127.0.0.1:4532" } });
      expect(wrapper.find<HTMLInputElement>("#set-status-rigctld").element.value).toBe("127.0.0.1:4532");
    });

    it("says on the power that the comment must be shorter first", async () => {
      const { wrapper, daemon } = make({ "station/comment": "x".repeat(40) }, "beacon");
      await wrapper.find("#set-beacon-power_w").setValue("5");
      await wrapper.find("#set-beacon-power_w").trigger("blur");
      await tell(daemon, {
        lastError: toastOf(
          "set_config: station/comment: 40 characters is more than the 36 allowed with the PHG extension (clear beacon/power_w to send none)",
          "setting.comment_too_long",
          { length: 40, limit: 36 },
        ),
      });
      expect(wrapper.find("#set-beacon-power_w").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Shorten the comment to 36 first");
      expect(wrapper.find<HTMLInputElement>("#set-beacon-power_w").element.value).toBe("5");
    });
  });

  describe("the Notifications group", () => {
    it("has the daemon's own alert in a box of its own (a fieldset with its legend, in the style of the group's), with no Messaging group beside it, and the browser's fields in a box after it", () => {
      alertWithBoth();
      const wrapper = mount(SettingsForm, { global: withDaemon() });
      const groups = wrapper.findAll("form > fieldset");
      const titles = groups.map((g) => g.find("legend").text());
      expect(titles).toContain("Notifications");
      const group = groups[titles.indexOf("Notifications")];
      const boxes = group?.findAll("fieldset") ?? [];
      expect(boxes).toHaveLength(2);
      expect(boxes.map((b) => b.classes())).toEqual([["subbox"], ["subbox"]]);
      expect(boxes.map((b) => b.element.parentElement)).toEqual([group?.element, group?.element]);
      expect(boxes[0]?.find("legend").text()).toBe("On the NeoAPRS computer i");
      expect(boxes[0]?.find("legend").attributes("title")).toBeTruthy();
      expect(boxes[0]?.findAll("label").map((l) => l.text())).toEqual(["Alert", "Command"]);
      expect(boxes[0]?.find("legend .info-toggle").exists()).toBe(true);
      expect(boxes[1]?.find("legend").text()).toBe("In this browser");
      expect(boxes[1]?.findAll("label").map((l) => l.text())).toEqual(["Alert for a new message", "Sound", "Pop-up"]);
      expect(boxes[1]?.find("#alert-mode").exists()).toBe(true);
      expect(group?.findAll(":scope > .field")).toHaveLength(0); // (every field of the group is in one of the two boxes)
      expect(group?.find("h3").exists()).toBe(false);
      expect(titles).not.toContain("Messaging");
      expect(wrapper.findAll("#alert-mode")).toHaveLength(1);
    });
    it("keeps the Test button of the command and the tests of the browser, with the fields and the tips, each in its box", () => {
      alertWithBoth();
      const wrapper = mount(SettingsForm, { global: withDaemon() });
      const [computer, browser] = wrapper.findAll("fieldset.subbox");
      expect(computer?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Test"]);
      expect(browser?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(expect.arrayContaining(["Test sound", "Test pop-up"]));
      expect(computer?.find("#set-messages-alert_command").exists()).toBe(true);
      expect(browser?.find("#set-messages-alert_command").exists()).toBe(false);
    });
    it("hides the Command and its Test button while the Alert is off, and shows them the moment it is ticked", async () => {
      const { wrapper } = make({ "messages/alert": "false" });
      const box = () => wrapper.findAll("fieldset.subbox")[0];
      expect(box()?.find("legend").text()).toBe("On the NeoAPRS computer i");
      expect(
        box()
          ?.findAll("label")
          .map((l) => l.text()),
      ).toEqual(["Alert"]);
      expect(box()?.find("legend .info-toggle").exists()).toBe(true);
      expect(wrapper.find("#set-messages-alert_command").exists()).toBe(false);
      expect(box()?.findAll("button:not(.info-toggle)")).toHaveLength(0);
      await wrapper.find("#set-messages-alert").setValue(true);
      expect(
        box()
          ?.findAll("label")
          .map((l) => l.text()),
      ).toEqual(["Alert", "Command"]);
      expect(
        box()
          ?.findAll("button:not(.info-toggle)")
          .map((b) => b.text()),
      ).toEqual(["Test"]);
      await wrapper.find("#set-messages-alert").setValue(false);
      expect(wrapper.find("#set-messages-alert_command").exists()).toBe(false);
    });
    it("shows the Command and its Test button while the Alert is on", () => {
      const { wrapper } = make({ "messages/alert": "true" });
      expect(wrapper.find("#set-messages-alert_command").exists()).toBe(true);
      expect(
        wrapper
          .findAll("fieldset.subbox")[0]
          ?.findAll("button:not(.info-toggle)")
          .map((b) => b.text()),
      ).toEqual(["Test"]);
    });
    it("has the style of the group boxes for the boxes in it", () => {
      expect(cssRule(".settings fieldset")).toMatch(/border:\s*1px solid var\(--border\)/);
      expect(cssRule(".settings legend")).toMatch(/font-weight:\s*600/);
      expect(cssRule(".settings fieldset.subbox")).toMatch(/margin:/);
    });
    it("is not in the Beacon tab", () => {
      expect(make({}, "beacon").wrapper.text()).not.toContain("On the NeoAPRS computer");
    });
  });

  describe("the Digipeater group", () => {
    const group = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Digipeater");

    it("is one switch, off by default, with an (i) that says what it does", async () => {
      const { wrapper } = make();
      expect(group(wrapper)?.findAll(".field")).toHaveLength(1);
      const switch_ = wrapper.find<HTMLInputElement>("#set-digi-enabled");
      expect(wrapper.find("label[for='set-digi-enabled']").text()).toBe("Digipeater");
      expect(switch_.attributes("type")).toBe("checkbox");
      expect(switch_.element.checked).toBe(false);
      expect(group(wrapper)?.find(".info-text").exists()).toBe(false);
      await group(wrapper)?.find(".info-toggle").trigger("click");
      expect(group(wrapper)?.find(".info-text").text()).toContain("WIDE1-1");
    });

    it("saves digi/enabled when it is switched on", async () => {
      const { wrapper, send } = make();
      await wrapper.find("#set-digi-enabled").setValue(true);
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "digi/enabled": "true" } });
    });
  });

  describe("the Check now button of the update check", () => {
    const check = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.findAll(".field button").find((b) => b.text() === "Check now");
    const answer = (extra: object) => ({ type: "update_result" as const, outcome: "current" as const, version: "0.3.0", text: "", ...extra });

    it("is the group's only field: the daily check has no switch and the address is not on the page", () => {
      const { wrapper } = make();
      const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Update check");
      expect(group?.findAll(".field")).toHaveLength(1);
      expect(group?.find("label").text()).toBe("New version");
      expect(group?.find("select, input[type=checkbox]").exists()).toBe(false);
      expect(wrapper.find("#set-update-url").exists()).toBe(false);
    });

    it("sends update_check, waits for the answer and says up to date with the version in the toast", async () => {
      const { wrapper, send, daemon } = make();
      await check(wrapper)?.trigger("click");
      expect(send).toHaveBeenCalledWith({ cmd: "update_check" });
      expect(check(wrapper)?.attributes("disabled")).toBeDefined();
      await check(wrapper)?.trigger("click");
      expect(send).toHaveBeenCalledTimes(1);
      await tell(daemon, { updateResult: answer({}) });
      expect(check(wrapper)?.attributes("disabled")).toBeUndefined();
      expect(daemon.say).toHaveBeenCalledExactlyOnceWith("up to date (0.3.0)");
      expect(wrapper.find(".field-control").text()).not.toContain("up to date");
      expect(wrapper.emitted("update")).toBeUndefined();
    });

    it("asks for the panel with the steps, and says nothing, when a newer version is available", async () => {
      const { wrapper, daemon } = make();
      await check(wrapper)?.trigger("click");
      await tell(daemon, { updateResult: answer({ outcome: "newer", version: "0.4.0" }) });
      expect(wrapper.emitted("update")).toHaveLength(1);
      expect(daemon.say).not.toHaveBeenCalled();
    });

    it("says no answer, with the reason when the daemon gave one", async () => {
      const { wrapper, daemon } = make();
      await check(wrapper)?.trigger("click");
      await tell(daemon, { updateResult: answer({ outcome: "no_answer", version: "", text: "the version page could not be reached" }) });
      expect(daemon.say).toHaveBeenCalledExactlyOnceWith("the version page could not be reached");
    });
  });

  describe("the Test button of the alert", () => {
    const button = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper.find("#set-messages-alert_command").element.closest(".field")?.querySelector("button");
    const beside = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper.find("#set-messages-alert_command").element.closest(".field")?.querySelector("[role='status']");

    it("is right of the alert command, and of no other field but the update check's and the (i) of the digipeater, and not in the Beacon tab", () => {
      alertWithBoth();
      const { wrapper } = make();
      expect(button(wrapper)?.textContent?.trim()).toBe("Test");
      expect(wrapper.findAll(".field button:not(.info-toggle)").map((b) => b.text())).toEqual([
        "Refresh",
        "Test",
        "Enable pop-ups…",
        "Test sound",
        "Test pop-up",
        "Check now",
      ]);
      expect(
        make({}, "beacon")
          .wrapper.findAll(".field button:not(.info-toggle):not(.location-pick):not(.location-place):not(.symbolbtn)")
          .map((b) => b.text()),
      ).toEqual([]);
    });

    it("sends alert_test, waits while it runs, and says ran in the toast", async () => {
      const { wrapper, send, daemon } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send).toHaveBeenCalledWith({ cmd: "alert_test" });
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(true);
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send.mock.calls.filter(([c]) => c.cmd === "alert_test")).toHaveLength(1);
      await tell(daemon, { alertResult: { type: "alert_result", ok: true, text: "ran" } });
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(false);
      expect(daemon.say).toHaveBeenCalledExactlyOnceWith("ran");
      expect(beside(wrapper)).toBeNull();
    });

    it("says a failure in the toast", async () => {
      const { wrapper, daemon } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      await tell(daemon, { alertResult: { type: "alert_result", ok: false, text: "exit code 3: no display" } });
      expect(daemon.say).toHaveBeenCalledExactlyOnceWith("exit code 3: no display");
      expect(beside(wrapper)).toBeNull();
    });

    it("says the error of an empty command in the toast", async () => {
      const { wrapper, daemon } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      await tell(daemon, { lastError: toastOf("alert_test: no alert command") });
      expect(daemon.say).toHaveBeenCalledExactlyOnceWith("no alert command");
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(false);
    });

    it("is disabled while the field differs from the command in force (it is being saved)", async () => {
      const { wrapper, send } = make();
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(false);
      await wrapper.find("#set-messages-alert_command").setValue("notify-send changed");
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(true);
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "alert_test" });
    });
  });

  it("says there is no word before the daemon has spoken", () => {
    const wrapper = mount(SettingsForm, { global: withDaemon(fakeDaemon({ config: null })) });
    expect(wrapper.text()).toContain("No word from the daemon yet.");
  });

  describe("the Map group", () => {
    const mount_ = (map = mapState(), extra: Record<string, string> = {}, scope: Scope = "settings") => make(extra, scope, { map });

    it("is one row, Radius with its field and unit and then a plain Download map at the right end of the same row, in the Map group and nowhere else", () => {
      const { wrapper } = mount_();
      const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Map");
      expect(group?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Download map"]);
      expect(wrapper.findAll(".mapfetch-button")).toHaveLength(1);
      const row = wrapper.find("#set-map-radius_km").element.closest(".field");
      expect([...(row?.querySelector(".field-control")?.children ?? [])].map((c) => c.tagName + "." + (c.className.split(" ")[0] || "")).slice(0, 3)).toEqual([
        "INPUT.input",
        "SPAN.unit",
        "BUTTON.btn",
      ]);
      expect(row?.contains(wrapper.find(".mapfetch-button").element)).toBe(true);
      expect(wrapper.find(".mapfetch-button").classes()).not.toContain("primary");
      expect(group?.findAll(".primary")).toHaveLength(0);
      expect(mount_(mapState(), {}, "beacon").wrapper.find(".mapfetch-button").exists()).toBe(false);
    });

    it("says the quiet line Map downloaded under the row, in the grid of the label column, and the button reads Download again", () => {
      const { wrapper } = mount_(mapState({ state: "ready", detail: mapFile() }));
      const row = wrapper.find("#set-map-radius_km").element.closest(".field");
      expect(row?.nextElementSibling?.classList.contains("mapfetch-notes")).toBe(true);
      expect(wrapper.find(".mapfetch-notes .mapfetch-file").text()).toBe("Map downloaded 22 Oct");
      expect(wrapper.find(".mapfetch-notes .mapfetch-file").classes()).toContain("muted");
      expect(wrapper.find(".mapfetch-button").text()).toBe("Download again");
      expect(row?.contains(wrapper.find(".mapfetch-notes").element)).toBe(false);
    });

    it("has no buttons until the daemon has told the state of the map", () => {
      const wrapper = mount(SettingsForm, { global: withDaemon() });
      expect(wrapper.find(".mapfetch-button").exists()).toBe(false);
      expect(wrapper.find("#set-map-radius_km").exists()).toBe(true); // (the row is the radius alone)
    });

    it("has the radius in km, and no detail, no map source and no time for stations to leave the map: those are not on the page", () => {
      const { wrapper } = mount_();
      expect(wrapper.find<HTMLInputElement>("#set-map-radius_km").element.value).toBe("150");
      expect(wrapper.find("#set-map-radius_km").element.closest(".field")?.querySelector(".unit")?.textContent).toBe("km");
      for (const id of ["set-map-maxzoom", "set-map-source", "set-map-hide_after_min", "set-map-station_hours"])
        expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
      expect(
        wrapper
          .find("fieldset:has(#set-map-radius_km)")
          .findAll(".field label")
          .map((l) => l.text()),
      ).toEqual(["Radius"]);
    });

    it("turns the buttons off while a map setting is being saved, and on again when it is, and takes the radius when the field is left", async () => {
      const { wrapper, send, daemon } = mount_();
      const buttons = () => wrapper.findAll(".mapfetch-button");
      await wrapper.find("#set-map-radius_km").setValue("60");
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true); // (typing sends nothing)
      await wrapper.find("#set-map-radius_km").trigger("blur");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "map/radius_km": "60" } });
      expect(buttons().every((b) => b.attributes("disabled") !== undefined && b.attributes("title") === "Saving…")).toBe(true);
      await tell(daemon, { config: configValues({ "map/radius_km": "60" }) });
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true);
    });
  });
});

describe("SettingsForm: the Location of our station (Beacon tab)", () => {
  type Wrapper = ReturnType<typeof make>["wrapper"];
  const pick = (wrapper: Wrapper) => wrapper.find<HTMLButtonElement>("button.location-pick");
  const place = (wrapper: Wrapper) => wrapper.find<HTMLButtonElement>("button.location-place");
  const open = (wrapper: Wrapper) => place(wrapper).trigger("click");
  const lat = (wrapper: Wrapper) => wrapper.find<HTMLInputElement>("#set-station-lat");
  const lon = (wrapper: Wrapper) => wrapper.find<HTMLInputElement>("#set-station-lon");
  const locator = (wrapper: Wrapper) => wrapper.find<HTMLInputElement>("#set-station-locator");

  it("is a row after the call: Location in the label column, a plain Choose on map, Cancel while the map waits, and the place in force as text beside it", async () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.find(".location-field > .field-label").text()).toBe("Location");
    expect(wrapper.find(".location-field > .field-control button.location-pick").exists()).toBe(true);
    expect(pick(wrapper).classes()).not.toContain("primary");
    expect(pick(wrapper).text()).toBe("Choose on map");
    expect(place(wrapper).text()).toBe("60.17 N, 24.94 E · KP20le");
    expect(place(wrapper).element.previousElementSibling).toBe(pick(wrapper).element);
    await pick(wrapper).trigger("click");
    expect(wrapper.emitted("pickPosition")).toHaveLength(1);
    await wrapper.setProps({ picking: true });
    expect(pick(wrapper).text()).toBe("Cancel");
    const order = wrapper.findAll(".field label, .field .field-label").map((e) => e.text());
    expect(order.slice(0, 4)).toEqual(["Call", "Position", "Location", "Symbol"]);
  });

  it("is only on the Beacon tab", () => {
    expect(make().wrapper.find(".location-field").exists()).toBe(false);
  });

  it("writes south and west as S and W, and says Not set while there is no place", () => {
    expect(make({ "station/lat": "-33.8568", "station/lon": "-70.1" }, "beacon").wrapper.find(".location-place").text()).toMatch(/^33\.8568 S, 70\.1 W · /);
    expect(make({ "station/lat": "", "station/lon": "" }, "beacon").wrapper.find(".location-place").text()).toBe("Not set");
  });

  it("keeps the coordinates and the locator behind the place: closed while there is a place, opened by a click on the place, closed too while there is none", async () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.find(".location-entry").exists()).toBe(false);
    expect(place(wrapper).attributes("aria-expanded")).toBe("false");
    await open(wrapper);
    expect(place(wrapper).attributes("aria-expanded")).toBe("true");
    expect(wrapper.findAll(".location-entry label").map((l) => l.text())).toEqual(["Latitude", "Longitude", "Locator"]);
    expect([lat(wrapper).element.value, lon(wrapper).element.value, locator(wrapper).element.value]).toEqual(["60.17", "24.94", "KP20le"]);
    await open(wrapper);
    expect(wrapper.find(".location-entry").exists()).toBe(false);
    const unset = make({ "station/lat": "", "station/lon": "" }, "beacon").wrapper;
    expect(unset.find(".location-entry").exists()).toBe(false);
    expect(place(unset).text()).toBe("Not set");
  });

  it("opens the entry by itself when the daemon refuses a coordinate, with the reason under it", async () => {
    const { wrapper, daemon } = make({}, "beacon");
    expect(wrapper.find(".location-entry").exists()).toBe(false);
    await wrapper.setProps({ picked: { lat: 60.4, lon: 24.1, n: 1 } });
    await tell(daemon, { lastError: toastOf("set_config: station/lat: 'x' is not a number") });
    expect(wrapper.find(".location-entry").exists()).toBe(true);
    expect(lat(wrapper).element.closest(".field")?.querySelector(".field-error")?.textContent).toContain("not a number");
  });

  it("has no Enter coordinates heading and no disclosure in the row", () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.text()).not.toContain("Enter coordinates");
    expect(wrapper.find(".location-field details").exists()).toBe(false);
  });

  it("applies a place picked on the map at once, latitude and longitude in one set_config", async () => {
    const { wrapper, send, daemon } = make({}, "beacon");
    await wrapper.setProps({ picked: { lat: 60.429449, lon: 24.1452399, n: 1 } });
    expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.42945", "station/lon": "24.14524" } }]]);
    await tell(daemon, { config: configValues({ "station/lat": "60.42945", "station/lon": "24.14524" }) });
    expect(place(wrapper).text()).toContain("60.42945 N, 24.14524 E");
  });

  it("applies typed coordinates together when focus leaves the pair and both are right, and not before", async () => {
    const { wrapper, send } = make({ "station/lat": "", "station/lon": "" }, "beacon");
    await open(wrapper);
    await lat(wrapper).setValue("60.5");
    await lat(wrapper).trigger("blur", { relatedTarget: lon(wrapper).element });
    expect(send).not.toHaveBeenCalled();
    await lon(wrapper).setValue("24,5");
    await lon(wrapper).trigger("blur");
    expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.5", "station/lon": "24,5" } }]]);
  });

  it("applies a locator as the centre of its square, latitude and longitude in one set_config, when its field is left or Enter is pressed", async () => {
    const { wrapper, send } = make({}, "beacon");
    await open(wrapper);
    await locator(wrapper).setValue("KP20ie");
    expect([lat(wrapper).element.value, lon(wrapper).element.value]).toEqual(["60.1875", "24.7083"]);
    expect(send).not.toHaveBeenCalled(); // (typing sends nothing)
    await locator(wrapper).trigger("keydown", { key: "Enter" });
    expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.1875", "station/lon": "24.7083" } }]]);
    await locator(wrapper).trigger("blur");
    expect(send).toHaveBeenCalledTimes(1); // (leaving it afterwards sends nothing more: the pair is what it was sent as)
  });

  it("puts the place back on Esc in the locator, both coordinates, with the reason gone", async () => {
    const { wrapper, send } = make({}, "beacon");
    await open(wrapper);
    await locator(wrapper).setValue("KP20ie");
    expect(lat(wrapper).element.closest(".field")?.classList.contains("changed")).toBe(true);
    await locator(wrapper).trigger("keydown", { key: "Escape" });
    expect([lat(wrapper).element.value, lon(wrapper).element.value, locator(wrapper).element.value]).toEqual(["60.17", "24.94", "KP20le"]);
    expect(send).not.toHaveBeenCalled();
    await locator(wrapper).setValue("SS00aa");
    expect(locator(wrapper).element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Not a locator");
    await locator(wrapper).trigger("keydown", { key: "Escape" });
    expect(locator(wrapper).element.closest(".field")?.querySelector(".field-error")).toBeNull();
    expect(locator(wrapper).element.value).toBe("KP20le");
  });

  it("writes the locator of the coordinates as they are typed", async () => {
    const { wrapper } = make({}, "beacon");
    await open(wrapper);
    await lat(wrapper).setValue("61.5");
    await lon(wrapper).setValue("25.5");
    expect(locator(wrapper).element.value).toBe("KP21sm");
  });

  it("sends nothing while only one of the two is given, and says which is missing", async () => {
    const { wrapper, send } = make({ "station/lat": "", "station/lon": "" }, "beacon");
    await open(wrapper);
    await lat(wrapper).setValue("60.5");
    await lat(wrapper).trigger("blur");
    expect(send).not.toHaveBeenCalled();
    expect(lon(wrapper).element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Needed with the latitude");
  });
});

describe("SettingsForm: the beacon Off (Beacon tab)", () => {
  const GREYED = [
    "set-beacon-travel",
    "set-station-comment",
    "set-beacon-power_w",
    "set-beacon-antenna_height_m",
    "set-beacon-antenna_gain_db",
    "set-beacon-antenna_direction",
    "set-beacon-path",
    "set-status-source",
    "set-status-rigctld",
    "set-status-template",
    "set-status-interval_min",
    "set-station-status",
  ];
  const STATION = [
    "set-station-call",
    "set-gps-source",
    "set-gps-host",
    "set-gps-device",
    "set-gps-baud",
    "set-station-lat",
    "set-station-lon",
    "set-beacon-interval_min",
  ];
  const off = (extra: Record<string, string> = {}) =>
    make(
      { "beacon/interval_min": "0", "beacon/power_w": "5", "status/source": "rig", "status/rigctld": "127.0.0.1:4532", "beacon/path": "WIDE2-2", ...extra },
      "beacon",
    );
  const control = (wrapper: ReturnType<typeof make>["wrapper"], id: string) => wrapper.find<HTMLInputElement | HTMLSelectElement>(`#${id}`);

  it("greys the comment, the antenna, the path and every field of the Status group for a fixed station, and keeps their values", () => {
    const { wrapper } = off({ "status/source": "text", "station/status": "QRV" });
    const ids = GREYED.filter((id) => !["set-beacon-travel", "set-status-rigctld", "set-status-template"].includes(id));
    for (const id of ids) {
      expect(control(wrapper, id).exists(), id).toBe(true);
      expect(control(wrapper, id).element.disabled, id).toBe(true);
      expect(control(wrapper, id).element.closest(".field")?.classList.contains("disabled"), id).toBe(true);
    }
    expect(control(wrapper, "set-station-comment").element.value).toBe("NeoAPRS");
    expect(control(wrapper, "set-beacon-power_w").element.value).toBe("5");
    expect(control(wrapper, "set-station-status").element.value).toBe("QRV");
    expect(control(wrapper, "set-status-interval_min").element.value).toBe("30");
  });

  it("greys the rigctld fields too when the status comes from the radio", () => {
    const { wrapper } = off();
    for (const id of ["set-status-rigctld", "set-status-template"]) expect(control(wrapper, id).element.disabled, id).toBe(true);
    expect(control(wrapper, "set-status-rigctld").element.value).toBe("127.0.0.1:4532");
  });

  it("greys Travelling, the comment and the path for a moving station, and shows no antenna", () => {
    const { wrapper } = off({ "gps/source": "gpsd" });
    for (const id of ["set-beacon-travel", "set-station-comment", "set-beacon-path", "set-status-source"])
      expect(control(wrapper, id).element.disabled, id).toBe(true);
    expect(control(wrapper, "set-beacon-power_w").exists()).toBe(false);
    expect(control(wrapper, "set-beacon-travel").element.value).toBe("car");
  });

  it("never greys the Station group or the Beacon choice", () => {
    for (const source of ["off", "gpsd", "serial"]) {
      const { wrapper } = off({ "gps/source": source });
      const present = STATION.filter((id) => control(wrapper, id).exists());
      expect(present.length, source).toBeGreaterThanOrEqual(3);
      expect(
        present.filter((id) => control(wrapper, id).element.disabled),
        source,
      ).toEqual([]);
      expect(wrapper.find<HTMLButtonElement>("#set-station-symbol-change").element.disabled, source).toBe(false);
      expect(wrapper.find("#set-station-symbol-change").element.closest(".field")?.classList.contains("disabled"), source).toBe(false);
    }
  });

  it("leaves the folds openable, with their fields greyed inside", async () => {
    const { wrapper } = off();
    const antenna = wrapper.findAll("details.disclosure").find((d) => d.find("summary").text() === "Antenna");
    expect(antenna).toBeDefined();
    await antenna?.find("summary").trigger("click");
    (antenna?.element as HTMLDetailsElement).open = true;
    expect(antenna?.find<HTMLInputElement>("#set-beacon-power_w").element.disabled).toBe(true);
  });

  it("greys nothing while the beacon is on, for any interval and for a moving station", () => {
    for (const extra of [{ "beacon/interval_min": "30" }, { "beacon/interval_min": "180" }, { "beacon/interval_min": "30", "gps/source": "serial" }] as Record<
      string,
      string
    >[]) {
      const { wrapper } = off(extra);
      expect(wrapper.findAll(".field.disabled"), JSON.stringify(extra)).toHaveLength(0);
      expect(wrapper.findAll("input:disabled, select:disabled"), JSON.stringify(extra)).toHaveLength(0);
    }
  });

  it("greys at once when Off is chosen and ungreys when an interval is chosen, and applies the choice", async () => {
    const { wrapper, send } = make({}, "beacon");
    expect(wrapper.findAll(".field.disabled")).toHaveLength(0);
    await wrapper.find("#set-beacon-interval_min").setValue("0");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "0" } });
    expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.disabled).toBe(true);
    await wrapper.find("#set-beacon-interval_min").setValue("60");
    expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.disabled).toBe(false);
  });

  it("keeps the (i) of a greyed field working", () => {
    const { wrapper } = off();
    const field = control(wrapper, "set-station-comment").element.closest(".field");
    expect(field?.querySelector(".info-toggle")).not.toBeNull();
    expect((field?.querySelector(".info-toggle") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("SettingsForm: the Transmit switch is gone", () => {
  it("is on neither tab, and station/transmit is no field whatever its value", () => {
    for (const scope of ["beacon", "settings"] as const) {
      for (const value of ["true", "false"]) {
        const { wrapper } = make({ "station/transmit": value }, scope);
        expect(wrapper.find("#set-station-transmit").exists(), `${scope} ${value}`).toBe(false);
        expect(wrapper.text()).not.toMatch(/Receive only(?!:)/); // (the iGate group says "Receive only:" in its quiet line; the badge is not on the page)
        expect(wrapper.findAll(".field label").map((l) => l.text())).not.toContain("Transmit");
      }
    }
  });
});
