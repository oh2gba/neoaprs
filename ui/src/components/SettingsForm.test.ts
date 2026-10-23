import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import SettingsForm from "@/components/SettingsForm.vue";
import type { Scope } from "@/lib/settings";
import { CONFIG_KEYS } from "@/protocol/lists";
import type { Command, PortsMessage } from "@/protocol/protocol";
import { configValues, mapState } from "@/test/fixtures";

function make(extra: Record<string, string> = {}, scope: Scope = "settings") {
  const send = vi.fn((_command: Command) => true);
  const wrapper = mount(SettingsForm, { props: { config: configValues(extra), lastError: null, send, scope } });
  return { wrapper, send };
}

const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
const portList = (extra: Partial<PortsMessage> = {}): PortsMessage => ({
  type: "ports",
  search: true,
  ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyS0", "n/a")],
  ...extra,
});

describe("SettingsForm", () => {
  it("has a field for every key of the Settings tab, in groups, and none of the beacon's", () => {
    const { wrapper } = make();
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).toEqual(["TNC", "Digipeater", "Web page", "Notifications", "Map", "Update check"]);
    expect(wrapper.findAll(".field")).toHaveLength(
      CONFIG_KEYS.filter(
        (k) =>
          !k.startsWith("beacon/") &&
          !k.startsWith("station/") &&
          !k.startsWith("status/") &&
          !k.startsWith("tcp/") &&
          k !== "web/key" &&
          k !== "web/https" &&
          k !== "serial/last_port" &&
          k !== "update/url" &&
          k !== "serial/pattern" &&
          k !== "serial/skip" &&
          k !== "web/port" &&
          k !== "web/allowed_hosts",
      ).length + 1, // (the New version row of the Update check group, which is no setting)
    );
    expect(wrapper.find("#set-station-lat").exists()).toBe(false);
  });

  it("has no field for what is fixed or left to the shell: the log time, the daily update check, the page's port and host names", () => {
    const { wrapper } = make();
    for (const id of ["set-log-keep_days", "set-update-check", "set-web-port", "set-web-allowed_hosts", "set-update-url"])
      expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
    expect(wrapper.text()).not.toContain("Allowed hosts");
    expect(CONFIG_KEYS).not.toContain("log/keep_days");
    expect(CONFIG_KEYS).not.toContain("update/check");
  });

  it("has no group called Other, and no raw key as a label, whatever the daemon lists", () => {
    const { wrapper } = make();
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).not.toContain("Other");
    for (const label of wrapper.findAll("label")) expect(label.text()).not.toMatch(/\//);
  });

  it("has our station's keys, then the beacon's, in the Beacon scope, and a place for the preview", () => {
    const wrapper = mount(SettingsForm, {
      props: { config: configValues(), lastError: null, send: vi.fn(() => true), scope: "beacon" },
      slots: { preview: "<p class='sample'>preview</p>" },
    });
    expect(wrapper.findAll("fieldset legend").map((l) => l.text())).toEqual(["Station", "Beacon", "Status"]);
    expect(wrapper.findAll(".field label").map((l) => l.text())).toEqual([
      "Call",
      "Latitude",
      "Longitude",
      "Symbol",
      "Comment",
      "Power",
      "Interval",
      "Path",
      "Status",
    ]);
    expect(wrapper.find(".sample").exists()).toBe(true);
  });

  it("has a link at the top of the Settings tab, outside the Save bar, which asks for the first-run guide, and none on the Beacon tab", async () => {
    const { wrapper } = make();
    const setup = wrapper.find("button.setup-open");
    expect(setup.text()).toBe("Run the setup guide again");
    expect(setup.attributes("type")).toBe("button");
    expect(setup.element.closest(".settings-actions")).toBeNull();
    expect(wrapper.find(".settings-actions").text()).not.toContain("Setup");
    await setup.trigger("click");
    expect(wrapper.emitted("setup")).toHaveLength(1);
    expect(make({}, "beacon").wrapper.find(".setup-open").exists()).toBe(false);
  });

  it("shows the default as the placeholder of a field that is empty", () => {
    const config = configValues();
    config.defaults["map/radius_km"] = "45";
    const wrapper = mount(SettingsForm, { props: { config, lastError: null, send: vi.fn(() => true) } });
    expect(wrapper.find<HTMLInputElement>("#set-map-radius_km").attributes("placeholder")).toBe("45");
  });

  it("explains no field in words: no hint renders, only labels, placeholders, units, titles and the daemon's errors", () => {
    for (const scope of ["settings", "beacon"] as const) {
      const { wrapper } = make({}, scope);
      expect(wrapper.find(".hint").exists()).toBe(false);
      expect(wrapper.findAll(".field p")).toHaveLength(0);
      expect(wrapper.find("[id$='-hint']").exists()).toBe(false);
      for (const field of wrapper.findAll(".field")) {
        const text = field.find("select").exists() ? field.find("label").text() : field.text(); // (the options of a select are its choices, not words about it; the (i) is closed and says "i")
        expect(text.length, text).toBeLessThan(42);
      }
    }
  });

  it("puts a unit after the field where one applies, and the word for 0 in its place", async () => {
    const { wrapper } = make();
    const unit = (id: string) => wrapper.find(`#${id}`).element.closest(".field")?.querySelector(".unit")?.textContent;
    expect(unit("set-tnc-check_sec")).toBe("s");
    expect(unit("set-serial-baud")).toBe("baud");
    expect(unit("set-map-hide_after_min")).toBe("min");
    await wrapper.find("#set-map-hide_after_min").setValue("0");
    expect(unit("set-map-hide_after_min")).toBe("never");
    await wrapper.find("#set-tnc-check_sec").setValue("0");
    expect(unit("set-tnc-check_sec")).toBe("off");
  });

  it("shows what an empty value means as the placeholder, else the default", () => {
    const { wrapper } = make();
    expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
    const beacon = make({ "status/source": "text" }, "beacon").wrapper;
    expect(beacon.find("#set-beacon-path").attributes("placeholder")).toBe("direct");
    expect(beacon.find("#set-beacon-power_w").attributes("placeholder")).toBe("none");
    expect(beacon.find("#set-station-status").attributes("placeholder")).toBe("none");
  });

  it("has the antenna in the Station group with its units, and a choice for the direction, once there is a power", async () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.find("#set-beacon-antenna_height_m").exists()).toBe(false);
    await wrapper.find("#set-beacon-power_w").setValue("5");
    const station = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Station");
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

    it("shows the port, the speed and the keep-alive of a TNC that has a command mode", () => {
      const { wrapper } = make();
      expect(fieldIds(wrapper)).toEqual(["set-tnc-profile", "set-serial-port", "set-serial-baud", "set-tnc-check_sec"]);
    });

    it("leaves the keep-alive out for a KISS TNC, which cannot be asked if it is there", async () => {
      const { wrapper } = make();
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
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "tnc/profile": "kiss-tcp", "serial/port": "" } });
      const kept = make({ "serial/port": "tcp://10.0.0.5:8100" });
      await kept.wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      await kept.wrapper.find("form").trigger("submit");
      expect(kept.send).toHaveBeenCalledWith({ cmd: "set_config", values: { "tnc/profile": "kiss-tcp" } });
    });

    it("shows the speed of the profile as the placeholder of an empty speed", async () => {
      const { wrapper } = make({ "serial/baud": "" });
      expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
      await wrapper.find("#set-tnc-profile").setValue("kantronics");
      expect(wrapper.find("#set-serial-baud").attributes("placeholder")).toBe("9600");
    });

    it("shows the refusal of the daemon under the profile", async () => {
      const { wrapper } = make();
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
      await wrapper.find("form").trigger("submit");
      await wrapper.setProps({
        lastError: { text: "set_config: tnc/profile: KISS over TCP connects over TCP (tcp/host and tcp/port), not to the serial port COM3", n: 1 },
      });
      expect(wrapper.find("#set-tnc-profile").element.closest(".field")?.querySelector(".field-error")?.textContent).toContain("not to the serial port COM3");
    });
  });

  describe("the TNC port", () => {
    const OWNER = { "serial/port": "/dev/brainbox_3", "serial/pattern": "/dev/brainbox_*", "serial/last_port": "/dev/brainbox_3", "serial/baud": "9600" };
    const withPorts = (extra: Record<string, string> = {}, ports: PortsMessage | null = portList()) => {
      const send = vi.fn((_command: Command) => true);
      const wrapper = mount(SettingsForm, { props: { config: configValues(extra), lastError: null, send, ports } });
      return { wrapper, send };
    };
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
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed", "Keep-alive"]);
      expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
      expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
      expect(headings(wrapper)).toHaveLength(0);
    });

    it("says 'none chosen' for the empty port where the daemon does not search", () => {
      expect(labels(withPorts().wrapper)).toEqual(["Radio type", "Port", "Speed", "Keep-alive"]);
      const { wrapper } = withPorts({}, portList({ search: false }));
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed", "Keep-alive"]);
      expect(headings(wrapper)).toHaveLength(0);
      expect(options(wrapper)[0]).toBe("none chosen");
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
      expect(wrapper.text()).toContain("1 changed");
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "" } });
    });

    it("saves only the port that was picked from the list", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      await select(wrapper).setValue("/dev/ttyUSB0");
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "/dev/ttyUSB0" } });
    });

    it("types a path or an address after Other, and saves it", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      expect(wrapper.find("#set-serial-port-typed").exists()).toBe(false);
      await select(wrapper).setValue("\u0000other");
      expect(wrapper.find("#set-serial-port-typed").attributes("placeholder")).toBe("/dev/ttyUSB0");
      expect(wrapper.text()).not.toContain("changed");
      await wrapper.find("#set-serial-port-typed").setValue("socket://10.0.0.5:8100");
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/port": "socket://10.0.0.5:8100" } });
    });

    it("leaves a stored installation as it is: opening the page and saving unchanged sends nothing", async () => {
      const { wrapper, send } = withPorts(OWNER);
      expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeDefined();
      await wrapper.find("form").trigger("submit");
      expect(send.mock.calls.filter(([c]) => c.cmd === "set_config")).toHaveLength(0);
    });

    it("never sends the port found, whatever else is changed", async () => {
      const { wrapper, send } = withPorts({ "serial/port": "" });
      await wrapper.find("#set-serial-baud").setValue("19200");
      await wrapper.find("#set-tnc-check_sec").setValue("90");
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "serial/baud": "19200", "tnc/check_sec": "90" } });
    });

    it("follows the daemon when it finds the radio on another port", async () => {
      const { wrapper } = withPorts({ "serial/port": "", "serial/last_port": "/dev/ttyUSB0" });
      await wrapper.setProps({ config: configValues({ "serial/port": "", "serial/last_port": "/dev/ttyACM0" }) });
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

    it("puts the units and the hover titles on the speed, the keep-alive and the port", () => {
      const { wrapper } = withPorts();
      const field = (id: string) => wrapper.find(`#${id}`).element.closest(".field");
      expect(field("set-serial-baud")?.querySelector(".unit")?.textContent).toBe("baud");
      expect(field("set-tnc-check_sec")?.querySelector(".unit")?.textContent).toBe("s");
      expect(field("set-tnc-check_sec")?.querySelector(".info-toggle")).not.toBeNull();
      expect(field("set-serial-port")?.querySelector(".info-toggle")).not.toBeNull();
    });
  });

  it("saves only what was changed", async () => {
    const { wrapper, send } = make({}, "beacon");
    expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeDefined();
    await wrapper.find("#set-station-lat").setValue("61.5");
    await wrapper.find("#set-beacon-path").setValue("WIDE2-2");
    await wrapper.find("#set-beacon-power_w").setValue("5");
    expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).toContain("3 changed");
    await wrapper.find("form").trigger("submit");
    expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "station/lat": "61.5", "beacon/path": "WIDE2-2", "beacon/power_w": "5" } });
  });

  it("shows the error of the daemon under the field it names", async () => {
    const { wrapper } = make({}, "beacon");
    await wrapper.find("#set-station-lat").setValue("95");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ lastError: { text: "set_config: station/lat: 95 is not between -90 and 90", n: 1 } });
    const field = wrapper.find("#set-station-lat").element.closest(".field");
    expect(field?.querySelector(".field-error")?.textContent).toBe("95 is not between -90 and 90");
    expect(wrapper.find("#set-station-lon").element.closest(".field")?.querySelector(".field-error")).toBeNull();
  });

  it("says Saved when the settings come back", async () => {
    const { wrapper } = make({}, "beacon");
    await wrapper.find("#set-station-lat").setValue("61.5");
    await wrapper.find("form").trigger("submit");
    await wrapper.setProps({ config: configValues({ "station/lat": "61.5" }) });
    expect(wrapper.find("[role='status']").text()).toBe("Saved.");
  });

  describe("the Notifications group", () => {
    it("has the daemon's own alert under a heading of its own, with no Messaging group beside it, and the slot for the browser's fields after it", () => {
      const wrapper = mount(SettingsForm, {
        props: { config: configValues(), lastError: null, send: vi.fn(() => true) },
        slots: { notifications: '<p id="from-slot">browser</p>' },
      });
      const groups = wrapper.findAll("fieldset");
      const titles = groups.map((g) => g.find("legend").text());
      expect(titles).toContain("Notifications");
      const group = groups[titles.indexOf("Notifications")];
      expect(group?.findAll("label").map((l) => l.text())).toEqual(["Alert", "Command"]);
      expect(group?.find("h3").text()).toBe("On the NeoAPRS computer i");
      expect(group?.find("h3").attributes("title")).toBeTruthy();
      expect(group?.find("#from-slot").exists()).toBe(true);
      expect(titles).not.toContain("Messaging");
      expect(wrapper.findAll("#from-slot")).toHaveLength(1);
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
      await wrapper.find("form").trigger("submit");
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

    it("sends update_check, waits for the answer and says up to date with the version", async () => {
      const { wrapper, send } = make();
      await check(wrapper)?.trigger("click");
      expect(send).toHaveBeenCalledWith({ cmd: "update_check" });
      expect(check(wrapper)?.attributes("disabled")).toBeDefined();
      await check(wrapper)?.trigger("click");
      expect(send).toHaveBeenCalledTimes(1);
      await wrapper.setProps({ updateResult: answer({}) });
      expect(check(wrapper)?.attributes("disabled")).toBeUndefined();
      expect(wrapper.find(".updatecheck-result").text()).toBe("up to date (0.3.0)");
      expect(wrapper.find("button.updatecheck-result").exists()).toBe(false);
    });

    it("says which version is available, as a button that asks for the panel with the steps", async () => {
      const { wrapper } = make();
      await check(wrapper)?.trigger("click");
      await wrapper.setProps({ updateResult: answer({ outcome: "newer", version: "0.4.0" }) });
      const result = wrapper.find("button.updatecheck-result");
      expect(result.text()).toBe("0.4.0 available");
      await result.trigger("click");
      expect(wrapper.emitted("update")).toHaveLength(1);
    });

    it("says no answer, with the reason when the daemon gave one", async () => {
      const { wrapper } = make();
      await check(wrapper)?.trigger("click");
      await wrapper.setProps({ updateResult: answer({ outcome: "no_answer", version: "", text: "the version page could not be reached" }) });
      expect(wrapper.find(".updatecheck-result").text()).toBe("the version page could not be reached");
    });
  });

  describe("the Test button of the alert", () => {
    const button = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper.find("#set-messages-alert_command").element.closest(".field")?.querySelector("button");
    const result = (wrapper: ReturnType<typeof make>["wrapper"]) =>
      wrapper.find("#set-messages-alert_command").element.closest(".field")?.querySelector(".field-result");

    it("is right of the alert command, and of no other field but the update check's and the (i) of the digipeater, and not in the Beacon tab", () => {
      const { wrapper } = make();
      expect(button(wrapper)?.textContent?.trim()).toBe("Test");
      expect(wrapper.findAll(".field button:not(.info-toggle)").map((b) => b.text())).toEqual(["Refresh", "Test", "Check now"]);
      expect(
        make({}, "beacon")
          .wrapper.findAll(".field button:not(.info-toggle)")
          .map((b) => b.text()),
      ).toEqual(["Change"]);
    });

    it("sends alert_test, waits while it runs, and shows ran in green under the field", async () => {
      const { wrapper, send } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send).toHaveBeenCalledWith({ cmd: "alert_test" });
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(true);
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send.mock.calls.filter(([c]) => c.cmd === "alert_test")).toHaveLength(1);
      await wrapper.setProps({ alertResult: { type: "alert_result", ok: true, text: "ran" } });
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(false);
      expect(result(wrapper)?.textContent).toBe("ran");
      expect(result(wrapper)?.classList.contains("ok")).toBe(true);
    });

    it("shows a failure in red, and the result goes with the next edit", async () => {
      const { wrapper } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      await wrapper.setProps({ alertResult: { type: "alert_result", ok: false, text: "exit code 3: no display" } });
      expect(result(wrapper)?.textContent).toBe("exit code 3: no display");
      expect(result(wrapper)?.classList.contains("ok")).toBe(false);
      await wrapper.find("#set-messages-alert_command").setValue("true");
      expect(result(wrapper)).toBeNull();
    });

    it("shows the error of an empty command as the result", async () => {
      const { wrapper } = make();
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      await wrapper.setProps({ lastError: { text: "alert_test: no alert command", n: 1 } });
      expect(result(wrapper)?.textContent).toBe("no alert command");
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(false);
    });

    it("is disabled with the title Save first while the field differs from the saved command", async () => {
      const { wrapper, send } = make();
      expect(button(wrapper)?.getAttribute("title")).toBeNull();
      await wrapper.find("#set-messages-alert_command").setValue("notify-send changed");
      expect(button(wrapper)?.hasAttribute("disabled")).toBe(true);
      expect(button(wrapper)?.getAttribute("title")).toBe("Save first");
      await wrapper.find("#set-messages-alert_command + button").trigger("click");
      expect(send).not.toHaveBeenCalledWith({ cmd: "alert_test" });
    });
  });

  it("says there is no word before the daemon has spoken", () => {
    const wrapper = mount(SettingsForm, { props: { config: null, lastError: null, send: vi.fn(() => true) } });
    expect(wrapper.text()).toContain("No word from the daemon yet.");
  });

  describe("the Map group", () => {
    const mount_ = (map = mapState(), extra: Record<string, string> = {}, scope: Scope = "settings") => {
      const send = vi.fn(() => true);
      const wrapper = mount(SettingsForm, { props: { config: configValues(extra), lastError: null, send, scope, map } });
      return { wrapper, send };
    };

    it("ends with the buttons that make the map, in the Map group and nowhere else", () => {
      const { wrapper } = mount_();
      const group = wrapper.findAll("fieldset").find((f) => f.find("legend").text() === "Map");
      expect(group?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Estimate", "Download"]);
      expect(wrapper.findAll(".mapfetch")).toHaveLength(1);
      expect(mount_(mapState(), {}, "beacon").wrapper.find(".mapfetch").exists()).toBe(false);
    });

    it("has no buttons until the daemon has told the state of the map", () => {
      const wrapper = mount(SettingsForm, { props: { config: configValues(), lastError: null, send: vi.fn(() => true) } });
      expect(wrapper.find(".mapfetch").exists()).toBe(false);
    });

    it("has the radius in km and the detail as a choice with a word for each zoom", () => {
      const { wrapper } = mount_();
      expect(wrapper.find<HTMLInputElement>("#set-map-radius_km").element.value).toBe("150");
      expect(wrapper.find("#set-map-radius_km").element.closest(".field")?.querySelector(".unit")?.textContent).toBe("km");
      const detail = wrapper.find<HTMLSelectElement>("#set-map-maxzoom");
      expect(detail.findAll("option").map((o) => o.text())).toEqual(["10 town", "12 streets", "14 houses"]);
      expect(detail.element.value).toBe("12");
    });

    it("keeps a detail that is none of the three in the choice, as the number", () => {
      const { wrapper } = mount_(mapState({ maxzoom: 11 }), { "map/maxzoom": "11" });
      const detail = wrapper.find<HTMLSelectElement>("#set-map-maxzoom");
      expect(detail.findAll("option").map((o) => o.text())).toEqual(["10 town", "12 streets", "14 houses", "11"]);
      expect(detail.element.value).toBe("11");
    });

    it("turns the buttons off while a map setting is changed and not saved, and on again when it is put back", async () => {
      const { wrapper } = mount_();
      const buttons = () => wrapper.findAll(".mapfetch button");
      await wrapper.find("#set-map-radius_km").setValue("60");
      expect(buttons().every((b) => b.attributes("disabled") !== undefined && b.attributes("title") === "Save first")).toBe(true);
      await wrapper.find("#set-map-radius_km").setValue("150");
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true);
      await wrapper.find("#set-tnc-check_sec").setValue("30");
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true);
    });

    it("sends the detail as the number the daemon keeps", async () => {
      const { wrapper, send } = mount_();
      await wrapper.find("#set-map-maxzoom").setValue("14");
      await wrapper.find("form").trigger("submit");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "map/maxzoom": "14" } });
    });
  });
});

describe("SettingsForm: our position picked on the map (Beacon tab)", () => {
  it("has Pick on the map on a row of its own under the longitude in the Beacon tab only, Cancel while the map waits, and asks the page to wait for a click", async () => {
    const { wrapper } = make({}, "beacon");
    const row = wrapper.find(".pick-row");
    expect(row.element.previousElementSibling?.querySelector("#set-station-lon")).not.toBeNull();
    expect(row.element.closest(".field")).toBeNull();
    const pick = () => wrapper.findAll("button").find((b) => b.text() === "Pick on the map" || b.text() === "Cancel");
    expect(pick()?.text()).toBe("Pick on the map");
    await pick()?.trigger("click");
    expect(wrapper.emitted("pickPosition")).toHaveLength(1);
    await wrapper.setProps({ picking: true });
    expect(pick()?.text()).toBe("Cancel");
    expect(
      make()
        .wrapper.findAll("button")
        .some((b) => b.text() === "Pick on the map"),
    ).toBe(false);
  });

  it("fills the latitude and the longitude with the place picked, to be saved like any change", async () => {
    const { wrapper, send } = make({}, "beacon");
    await wrapper.setProps({ picked: { lat: 60.429449, lon: 24.1452399, n: 1 } });
    expect(wrapper.find<HTMLInputElement>("#set-station-lat").element.value).toBe("60.42945");
    expect(wrapper.find<HTMLInputElement>("#set-station-lon").element.value).toBe("24.14524");
    await wrapper.find("form").trigger("submit");
    const saved = send.mock.calls.at(-1)?.[0] as { cmd: string; values: Record<string, string> } | undefined;
    expect(saved?.cmd).toBe("set_config");
    expect([saved?.values["station/lat"], saved?.values["station/lon"]]).toEqual(["60.42945", "24.14524"]);
  });
});
