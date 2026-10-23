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
          k !== "web/allowed_hosts" &&
          k !== "map/maxzoom" &&
          k !== "map/source",
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
      "Beacon",
      "Comment",
      "Power",
      "Path",
      "Status",
    ]);
    expect(wrapper.find(".sample").exists()).toBe(true);
  });

  describe("the Beacon group of the Beacon tab", () => {
    const group = (wrapper: ReturnType<typeof make>["wrapper"], title: string) => wrapper.findAll("fieldset").find((f) => f.find("legend").text() === title);
    const folds = (wrapper: ReturnType<typeof make>["wrapper"]) => group(wrapper, "Beacon")?.findAll("details.disclosure") ?? [];

    it("has Call, Location and Symbol in the Station group, and the comment with the beacon", () => {
      const { wrapper } = make({}, "beacon");
      expect(
        group(wrapper, "Station")
          ?.findAll(".field label, h3")
          .map((e) => e.text()),
      ).toEqual(["Call", "Location", "Latitude", "Longitude", "Symbol"]);
      expect(group(wrapper, "Station")?.find("#set-station-comment").exists()).toBe(false);
      expect(group(wrapper, "Beacon")?.find("#set-station-comment").exists()).toBe(true);
    });

    it("is one choice for how often: off, every 15, 30 or 60 minutes, then the comment", () => {
      const { wrapper } = make({ "beacon/interval_min": "30" }, "beacon");
      const select = wrapper.find<HTMLSelectElement>("#set-beacon-interval_min");
      expect(wrapper.find("label[for=set-beacon-interval_min]").text()).toBe("Beacon");
      expect(select.element.tagName).toBe("SELECT");
      expect(select.findAll("option").map((o) => [o.attributes("value"), o.text()])).toEqual([
        ["0", "Off"],
        ["15", "Every 15 min"],
        ["30", "Every 30 min"],
        ["60", "Every 60 min"],
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
      expect(select.findAll("option").map((o) => o.text())).toEqual(["Off", "Every 15 min", "Every 30 min", "Every 60 min", "Every 20 min"]);
      expect(select.element.value).toBe("20");
      expect(send).not.toHaveBeenCalled();
      await select.setValue("60");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "60" } });
    });

    it("applies the interval at once", async () => {
      const { wrapper, send } = make({}, "beacon");
      await wrapper.find("#set-beacon-interval_min").setValue("15");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "beacon/interval_min": "15" } });
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
      expect(advanced?.find<HTMLInputElement>("#set-beacon-path").element.value).toBe("WIDE1-1,WIDE2-1");
    });

    it("works the fields in the folds like the others: a typed one when it is left, a choice at once", async () => {
      const { wrapper, send } = make({ "beacon/power_w": "5" }, "beacon");
      await wrapper.find("#set-beacon-path").setValue("WIDE2-2");
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-beacon-path").trigger("blur");
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "beacon/path": "WIDE2-2" } });
      await wrapper.find("#set-beacon-antenna_direction").setValue("N");
      expect(send).toHaveBeenCalledTimes(1); // (waits for the answer to the first)
      await wrapper.setProps({ config: configValues({ "beacon/power_w": "5", "beacon/path": "WIDE2-2" }) });
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
    expect(beacon.find("#set-beacon-path").attributes("placeholder")).toBe("direct");
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

    it("shows the port and the speed of a serial TNC, and no keep-alive: that is fixed at 60 seconds and is no setting", async () => {
      const { wrapper } = make();
      expect(fieldIds(wrapper)).toEqual(["set-tnc-profile", "set-serial-port", "set-serial-baud"]);
      expect(wrapper.find("#set-tnc-check_sec").exists()).toBe(false);
      expect(wrapper.text()).not.toContain("Keep-alive");
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
      const { wrapper } = make();
      await wrapper.find("#set-tnc-profile").setValue("kiss-tcp");
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
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed"]);
      expect(wrapper.find("#set-serial-pattern").exists()).toBe(false);
      expect(wrapper.find("#set-serial-skip").exists()).toBe(false);
      expect(headings(wrapper)).toHaveLength(0);
    });

    it("says 'none chosen' for the empty port where the daemon does not search", () => {
      expect(labels(withPorts().wrapper)).toEqual(["Radio type", "Port", "Speed"]);
      const { wrapper } = withPorts({}, portList({ search: false }));
      expect(labels(wrapper)).toEqual(["Radio type", "Port", "Speed"]);
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
      const { wrapper, send } = withPorts({ "serial/port": "" });
      await wrapper.find("#set-serial-baud").setValue("19200");
      await wrapper.find("#set-serial-baud").trigger("blur");
      await wrapper.find("#set-map-radius_km").setValue("200");
      await wrapper.find("#set-map-radius_km").trigger("blur");
      expect(send.mock.calls.filter(([c]) => c.cmd === "set_config")).toEqual([[{ cmd: "set_config", values: { "serial/baud": "19200" } }]]);
      await wrapper.setProps({ config: configValues({ "serial/port": "", "serial/baud": "19200" }) });
      expect(send).toHaveBeenLastCalledWith({ cmd: "set_config", values: { "map/radius_km": "200" } });
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

    it("puts the unit and the (i) on the speed and the port", () => {
      const { wrapper } = withPorts();
      const field = (id: string) => wrapper.find(`#${id}`).element.closest(".field");
      expect(field("set-serial-baud")?.querySelector(".unit")?.textContent).toBe("baud");
      expect(field("set-serial-port")?.querySelector(".info-toggle")).not.toBeNull();
    });
  });

  describe("typed fields", () => {
    const type = async (wrapper: ReturnType<typeof make>["wrapper"], id: string, text: string) => {
      await wrapper.find(`#${id}`).setValue(text);
    };

    it("are sent when the field is left, and not while they are typed", async () => {
      const { wrapper, send } = make({}, "beacon");
      await type(wrapper, "set-beacon-path", "WIDE2-2");
      await type(wrapper, "set-station-comment", "Hello");
      expect(send).not.toHaveBeenCalled();
      await wrapper.find("#set-beacon-path").trigger("blur");
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
      const { wrapper } = make({}, "beacon");
      await wrapper.find("#set-station-comment").setValue("é is not ascii");
      await wrapper.find("#set-station-comment").trigger("blur");
      await wrapper.setProps({ lastError: { text: "set_config: station/comment: 'é' is not ASCII", n: 1 } });
      const field = wrapper.find("#set-station-comment").element.closest(".field");
      expect(field?.querySelector(".field-error")?.textContent).toBe("'é' is not ASCII");
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("é is not ascii");
      expect(wrapper.find("#set-station-lon").element.closest(".field")?.querySelector(".field-error")).toBeNull();
    });

    it("shows nothing beside the field while a change is on its way or when it is saved, so that nothing moves; a screen reader is told", async () => {
      const { wrapper } = make({}, "beacon");
      const field = () => wrapper.find("#set-station-comment").element.closest(".field");
      const shape = () => [...(field()?.querySelectorAll("*") ?? [])].map((e) => e.tagName).join(" ");
      const before = shape();
      await wrapper.find("#set-station-comment").setValue("Hello");
      await wrapper.find("#set-station-comment").trigger("blur");
      expect(wrapper.find("[role='status'][aria-live]").text()).toBe("");
      await wrapper.setProps({ config: configValues({ "station/comment": "Hello" }) });
      expect(wrapper.find("[role='status'][aria-live]").text()).toBe("Saved");
      expect(wrapper.find(".field-state").exists()).toBe(false);
      expect(wrapper.text()).not.toContain("Saved ✓");
      expect(wrapper.text()).not.toContain("Saving");
      expect(shape()).toBe(before);
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("Hello");
    });

    it("shows a refused choice as it was, with the reason under it", async () => {
      const { wrapper } = make();
      await wrapper.find("#set-tnc-profile").setValue("kiss");
      await wrapper.setProps({ lastError: { text: "set_config: tnc/profile: KISS TNC is too much", n: 1 } });
      expect(wrapper.find<HTMLSelectElement>("#set-tnc-profile").element.value).toBe("kenwood-tnc2");
      expect(wrapper.find("#set-tnc-profile").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("KISS TNC is too much");
    });

    it("leaves a field that is being edited alone when the daemon tells other settings, and follows it in a field that is not", async () => {
      const { wrapper } = make({}, "beacon");
      await wrapper.find("#set-station-comment").setValue("mine");
      await wrapper.setProps({ config: configValues({ "station/comment": "theirs", "beacon/path": "WIDE2-2" }) });
      expect(wrapper.find<HTMLInputElement>("#set-station-comment").element.value).toBe("mine");
      expect(wrapper.find<HTMLInputElement>("#set-beacon-path").element.value).toBe("WIDE2-2");
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
      const { wrapper } = make({ "station/comment": "x".repeat(40) }, "beacon");
      await wrapper.find("#set-beacon-power_w").setValue("5");
      await wrapper.find("#set-beacon-power_w").trigger("blur");
      await wrapper.setProps({
        lastError: {
          text: "set_config: station/comment: 40 characters is more than the 36 allowed with the PHG extension (clear beacon/power_w to send none)",
          n: 1,
        },
      });
      expect(wrapper.find("#set-beacon-power_w").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Shorten the comment to 36 first");
      expect(wrapper.find<HTMLInputElement>("#set-beacon-power_w").element.value).toBe("5");
    });
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
      expect(group?.findAll("button:not(.info-toggle)").map((b) => b.text())).toEqual(["Download map"]);
      expect(wrapper.findAll(".mapfetch")).toHaveLength(1);
      expect(mount_(mapState(), {}, "beacon").wrapper.find(".mapfetch").exists()).toBe(false);
    });

    it("has no buttons until the daemon has told the state of the map", () => {
      const wrapper = mount(SettingsForm, { props: { config: configValues(), lastError: null, send: vi.fn(() => true) } });
      expect(wrapper.find(".mapfetch").exists()).toBe(false);
    });

    it("has the radius in km, and no detail, no map source and no time for stations to leave the map: those are not on the page", () => {
      const { wrapper } = mount_();
      expect(wrapper.find<HTMLInputElement>("#set-map-radius_km").element.value).toBe("150");
      expect(wrapper.find("#set-map-radius_km").element.closest(".field")?.querySelector(".unit")?.textContent).toBe("km");
      for (const id of ["set-map-maxzoom", "set-map-source", "set-map-hide_after_min"]) expect(wrapper.find(`#${id}`).exists(), id).toBe(false);
      expect(
        wrapper
          .find("fieldset:has(#set-map-radius_km)")
          .findAll(".field label")
          .map((l) => l.text()),
      ).toEqual(["Radius"]);
    });

    it("turns the buttons off while a map setting is being saved, and on again when it is, and takes the radius when the field is left", async () => {
      const { wrapper, send } = mount_();
      const buttons = () => wrapper.findAll(".mapfetch button");
      await wrapper.find("#set-map-radius_km").setValue("60");
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true); // (typing sends nothing)
      await wrapper.find("#set-map-radius_km").trigger("blur");
      expect(send).toHaveBeenCalledWith({ cmd: "set_config", values: { "map/radius_km": "60" } });
      expect(buttons().every((b) => b.attributes("disabled") !== undefined && b.attributes("title") === "Saving…")).toBe(true);
      await wrapper.setProps({ config: configValues({ "map/radius_km": "60" }) });
      expect(buttons().every((b) => b.attributes("disabled") === undefined)).toBe(true);
    });
  });
});

describe("SettingsForm: the Location of our station (Beacon tab)", () => {
  const pick = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.find<HTMLButtonElement>("button.location-pick");
  const details = (wrapper: ReturnType<typeof make>["wrapper"]) => wrapper.find<HTMLDetailsElement>("details.disclosure");

  it("is a sub-section after the call: a primary Pick on the map, Cancel while the map waits, and the place in force as one line", async () => {
    const { wrapper } = make({}, "beacon");
    expect(wrapper.find("h3.subgroup").text()).toBe("Location");
    expect(pick(wrapper).classes()).toContain("primary");
    expect(pick(wrapper).text()).toBe("Pick on the map");
    expect(wrapper.find(".location-line").text()).toBe("60.17 N, 24.94 E · KP20le");
    await pick(wrapper).trigger("click");
    expect(wrapper.emitted("pickPosition")).toHaveLength(1);
    await wrapper.setProps({ picking: true });
    expect(pick(wrapper).text()).toBe("Cancel");
    const order = wrapper.findAll(".field label, h3.subgroup").map((e) => e.text());
    expect(order.slice(0, 4)).toEqual(["Call", "Location", "Latitude", "Longitude"]);
  });

  it("is only on the Beacon tab", () => {
    expect(make().wrapper.find(".location").exists()).toBe(false);
  });

  it("writes south and west as S and W, and says Not set while there is no place", () => {
    expect(make({ "station/lat": "-33.8568", "station/lon": "-70.1" }, "beacon").wrapper.find(".location-line").text()).toMatch(/^33\.8568 S, 70\.1 W · /);
    expect(make({ "station/lat": "", "station/lon": "" }, "beacon").wrapper.find(".location-line").text()).toBe("Not set");
  });

  it("keeps the coordinates behind Enter coordinates, closed while there is a place, open while there is none or one is wrong", async () => {
    const { wrapper } = make({}, "beacon");
    expect(details(wrapper).element.open).toBe(false);
    expect(details(wrapper).find("summary").text()).toBe("Enter coordinates");
    expect(details(wrapper).find("#set-station-lat").exists()).toBe(true);
    expect(make({ "station/lat": "", "station/lon": "" }, "beacon").wrapper.find<HTMLDetailsElement>("details.disclosure").element.open).toBe(true);
    await wrapper.find("#set-station-lat").setValue("95");
    await wrapper.find("#set-station-lat").trigger("blur");
    expect(details(wrapper).element.open).toBe(true);
  });

  it("applies a place picked on the map at once, latitude and longitude in one set_config", async () => {
    const { wrapper, send } = make({}, "beacon");
    await wrapper.setProps({ picked: { lat: 60.429449, lon: 24.1452399, n: 1 } });
    expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.42945", "station/lon": "24.14524" } }]]);
    await wrapper.setProps({ config: configValues({ "station/lat": "60.42945", "station/lon": "24.14524" }) });
    expect(wrapper.find(".location-line").text()).toContain("60.42945 N, 24.14524 E");
  });

  it("applies typed coordinates together when focus leaves the pair and both are right, and not before", async () => {
    const { wrapper, send } = make({ "station/lat": "", "station/lon": "" }, "beacon");
    await wrapper.find("#set-station-lat").setValue("60.5");
    await wrapper.find("#set-station-lat").trigger("blur", { relatedTarget: wrapper.find("#set-station-lon").element });
    expect(send).not.toHaveBeenCalled();
    await wrapper.find("#set-station-lon").setValue("24,5");
    await wrapper.find("#set-station-lon").trigger("blur");
    expect(send.mock.calls).toEqual([[{ cmd: "set_config", values: { "station/lat": "60.5", "station/lon": "24,5" } }]]);
  });

  it("sends nothing while only one of the two is given, and says which is missing", async () => {
    const { wrapper, send } = make({ "station/lat": "", "station/lon": "" }, "beacon");
    await wrapper.find("#set-station-lat").setValue("60.5");
    await wrapper.find("#set-station-lat").trigger("blur");
    expect(send).not.toHaveBeenCalled();
    expect(wrapper.find("#set-station-lon").element.closest(".field")?.querySelector(".field-error")?.textContent).toBe("Needed with the latitude");
  });
});
