import { describe, expect, it } from "vitest";
import { portRow, radioRow } from "@/test/fixtures";
import { CONFIG_KEYS } from "@/protocol/lists";
import { BEACON_FOLDS, FIELDS, SUBGROUPS, fieldFor, groupKeys, reasonOf, shownByValues, storedFor, valueFor } from "@/lib/settings";
import {
  boxKeys,
  boxTitle,
  digiPlaces,
  fieldOfKey,
  inputId,
  isRadioKey,
  radioElementId,
  radioFieldOf,
  shownByRadios,
  shownFor,
  typeChoices,
  typeText,
  unnamed,
} from "@/lib/settingsradio";
import { pageRadio } from "@/lib/radios";
import type { RadioRow } from "@/protocol/protocol";
import { RADIO_TYPES, TNC_PROFILES } from "@/protocol/lists";
import { beaconOff, disabledByValues } from "@/lib/beaconoff";
import { PORT_OTHER, holderOf, portOptions } from "@/lib/portchoice";

describe("groupKeys", () => {
  it("gives the Settings tab the serial and TNC, Internet, ships, aircraft, digipeater, web, notifications and map keys, in the daemon's order", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "settings");
    expect(groups.map((g) => g.id)).toEqual(["serial", "igate", "ais", "adsb", "digi", "web", "notifications", "map"]);
    expect(groups.find((g) => g.id === "ais")?.keys).toEqual(["ais/enabled", "ais/types", "ais/hide_still", "ais/radius_km", "ais/track_min"]);
    expect(groups.find((g) => g.id === "adsb")?.keys).toEqual(["adsb/enabled", "adsb/radius_km", "adsb/track_min"]);
    expect(groups[0]?.keys).toEqual(["station/transmit", "serial/last_port"]); // (the radios' own fields are in their boxes)
    expect(groups[1]?.title).toBe("Internet stations");
    expect(groups[1]?.keys).toEqual(["igate/enabled"]); // (igate/server and igate/password are left to the shell)
    expect(groups[2]?.title).toBe("Ships (AIS)");
    expect(groups[3]?.title).toBe("Aircraft (ADS-B)");
    expect(groups[4]?.title).toBe("Digipeater");
    expect(groups[4]?.keys).toEqual([]); // (its fields are the radios' radio/<id>/digipeat: the form draws it while a radio may repeat)
    expect(groups[6]?.title).toBe("Notifications");
    expect(groups[6]?.keys).toEqual(["messages/alert", "messages/alert_command"]);
    expect(groups[7]?.keys).toEqual(["map/radius_km"]);
  });
  it("gives the My station tab the station keys first (the call, the place, the symbol), then how often and what the beacon says, the antenna and the path, and the status keys", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "beacon");
    expect(groups.map((g) => g.id)).toEqual(["station", "beacon", "status"]);
    expect(groups[0]?.keys).toEqual([
      "station/call",
      "gps/source",
      "gps/host",
      "gps/device",
      "gps/baud",
      "station/lat",
      "station/lon",
      "station/symbol_table",
      "station/symbol_code",
    ]);
    expect(groups[1]?.keys).toEqual([
      "beacon/interval_min",
      "beacon/travel",
      "station/comment",
      "beacon/power_w",
      "beacon/antenna_height_m",
      "beacon/antenna_gain_db",
      "beacon/antenna_direction",
    ]);
    expect(BEACON_FOLDS.map((f) => [f.group, f.title, f.keys.length])).toEqual([
      ["beacon", "Antenna", 4],
      ["beacon", "Advanced", 1],
    ]);
    expect(groups[2]?.keys).toEqual(["status/source", "status/interval_min", "station/status", "status/rigctld", "status/template"]);
  });
  it("has no Mobile group: the position choice and what it needs are in the Station group, Travelling in the Beacon group, and the old keys are gone", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "beacon");
    expect(groups.map((g) => g.title)).toEqual(["Station", "Beacon", "Status"]);
    const keys = groups.flatMap((g) => g.keys);
    expect(keys).not.toContain("beacon/mobile");
    expect(keys.filter((k) => k.startsWith("smart/"))).toEqual([]);
    expect((CONFIG_KEYS as readonly string[]).filter((k) => k === "beacon/mobile" || k.startsWith("smart/"))).toEqual([]);
    expect(groups[0]?.keys.filter((k) => k.startsWith("gps/"))).toEqual(["gps/source", "gps/host", "gps/device", "gps/baud"]);
    expect(groups[1]?.keys).toContain("beacon/travel");
    const settings = groupKeys(CONFIG_KEYS, "settings").flatMap((g) => g.keys);
    expect(settings).not.toContain("gps/source");
    expect(settings).not.toContain("beacon/travel");
  });
  it("has every key in one place only", () => {
    const shown = [...groupKeys(CONFIG_KEYS, "settings"), ...groupKeys(CONFIG_KEYS, "beacon")].flatMap((g) => g.keys);
    expect(shown.sort()).toEqual(
      CONFIG_KEYS.filter(
        (key) =>
          ![
            "update/url",
            "serial/pattern",
            "serial/skip",
            "web/port",
            "web/allowed_hosts",
            "igate/server",
            "igate/password",
            "map/maxzoom",
            "map/source",
            "map/station_hours",
          ].includes(key),
      ).sort(),
    );
  });
  it("has the Transmit tickbox first in the Radio group of the Settings tab and not on the My station tab", () => {
    expect(groupKeys(CONFIG_KEYS, "settings")[0]?.keys[0]).toBe("station/transmit");
    expect(groupKeys(CONFIG_KEYS, "beacon").flatMap((g) => g.keys)).not.toContain("station/transmit");
    expect(FIELDS["station/transmit"]?.kind).toBe("bool");
  });
  it("leaves the address of the update check off the page: it is set with neoaprs db set", () => {
    expect(groupKeys(CONFIG_KEYS, "settings").flatMap((g) => g.keys)).not.toContain("update/url");
    expect(FIELDS["update/url"]).toBeUndefined();
  });
  it("shows a key it does not know under Other", () => {
    expect(groupKeys(["web/network", "mystery/key"], "settings").map((g) => [g.id, g.keys])).toEqual([
      ["digi", []],
      ["web", ["web/network"]],
      ["other", ["mystery/key"]],
    ]);
  });
  it("heads the daemon's own alert in the Notifications group with a line that says where it runs", () => {
    expect(SUBGROUPS["messages/alert"]?.text).toBe("On the NeoAPRS computer");
    expect(Object.keys(SUBGROUPS)).toEqual(["messages/alert"]);
    expect([FIELDS["messages/alert"]?.label, FIELDS["messages/alert_command"]?.label]).toEqual(["Alert", "Command"]);
  });
  it("names the NeoAPRS computer in the (i) of the daemon's alert in a browser and this computer in the app's own window, after a reload too; the (i) of Alert names neither", () => {
    const tips = () => [...(SUBGROUPS["messages/alert"]?.tip ?? []), ...(FIELDS["messages/alert"]?.tip ?? [])];
    sessionStorage.clear();
    expect(FIELDS["messages/alert"]?.tip).toEqual(["With Alert on, the Command is run when a message arrives."]);
    expect(tips().filter((line) => line.includes("NeoAPRS computer"))).toHaveLength(1);
    expect(tips().join(" ")).not.toMatch(/this computer|window/);
    const browser = location.href;
    const at = (url: string) => (window as unknown as { happyDOM: { setURL(url: string): void } }).happyDOM.setURL(url);
    at("http://127.0.0.1:7303/#app");
    expect(tips().filter((line) => line.includes("this computer"))).toHaveLength(1);
    at("http://127.0.0.1:7303/"); // (the window's reload, without the fragment: the window still knows)
    expect(tips().join(" ")).toMatch(/this window/);
    expect(tips().join(" ")).not.toMatch(/NeoAPRS computer|browser/);
    sessionStorage.clear();
    at(browser);
  });
  it("keeps the radius of the map in a group of its own, and leaves off the page the detail and the source, which stay settings for neoaprs db set", () => {
    expect(groupKeys(["web/network", "map/radius_km"]).map((g) => g.id)).toEqual(["digi", "web", "map"]);
    const keys = groupKeys(CONFIG_KEYS, "settings").flatMap((g) => g.keys);
    for (const key of ["map/maxzoom", "map/source"]) {
      expect(keys).not.toContain(key);
      expect(CONFIG_KEYS).toContain(key);
      expect(FIELDS[key]).toBeUndefined();
    }
  });
  it("has no setting for the time stations stay on the map: it is fixed at 3 hours (a station has its own in its details)", () => {
    expect(CONFIG_KEYS).not.toContain("map/hide_after_min");
    expect(FIELDS["map/hide_after_min"]).toBeUndefined();
  });
  it("knows every key of the daemon: a short label for each, and no hint text anywhere", () => {
    for (const key of groupKeys(CONFIG_KEYS, "settings")
      .concat(groupKeys(CONFIG_KEYS, "beacon"))
      .flatMap((g) => g.keys)) {
      const info = FIELDS[key];
      expect(info?.label, key).toBeTruthy();
      expect(info?.label.length, key).toBeLessThanOrEqual(30);
      expect(Object.keys(info ?? {}), key).not.toContain("hint");
      expect(info?.title?.length ?? 0, key).toBeLessThanOrEqual(50);
    }
    expect(FIELDS["status/source"]?.kind).toBe("choice");
    expect(FIELDS["beacon/antenna_direction"]?.kind).toBe("choice");
  });
  it("explains the fields that a word cannot in an (i) of two to four sentences and an example, not on hover", () => {
    const keys = [
      "station/comment",
      "station/status",
      "status/source",
      "status/rigctld",
      "status/template",
      "status/interval_min",
      "beacon/interval_min",
      "beacon/path",
      "beacon/power_w",
      "beacon/antenna_height_m",
      "beacon/antenna_gain_db",
      "beacon/antenna_direction",
      "gps/source",
      "gps/host",
      "gps/device",
      "gps/baud",
      "beacon/travel",
    ];
    for (const key of keys) {
      const tip = FIELDS[key]?.tip ?? [];
      expect(tip.length, key).toBeGreaterThan(0);
      expect(tip.join(" ").split(/[.:;] /).length, key).toBeLessThanOrEqual(8);
      expect(FIELDS[key]?.title, key).toBeUndefined();
    }
  });
  it("shows the alert command only while the alert is on (an alert the values do not mention is on)", () => {
    expect(shownByValues("messages/alert_command", { "messages/alert": "true" })).toBe(true);
    expect(shownByValues("messages/alert_command", {})).toBe(true);
    expect(shownByValues("messages/alert_command", { "messages/alert": "false" })).toBe(false);
    expect(shownByValues("messages/alert", { "messages/alert": "false" })).toBe(true);
  });
  it("gives the numbers and the examples in the (i) of the fields that have them", () => {
    const tip = (key: string) => (FIELDS[key]?.tip ?? []).join(" ");
    expect(tip("station/comment")).toContain("43");
    expect(tip("station/status")).toContain("55");
    expect(tip("beacon/interval_min")).toContain("20");
    expect(tip("beacon/path")).toContain("WIDE1-1,WIDE2-1");
    expect(tip("beacon/path")).toContain("WIDE2-2");
    expect(tip("status/template")).toMatch(/\{freq\}.*\{mode\}/);
    expect(tip("status/template")).toContain("14.074 MHz USB");
  });
  it("shows the status fields its source needs and the antenna's figures once there is a power", () => {
    const shown = (values: Record<string, string>) =>
      ["status/source", "status/interval_min", "station/status", "status/rigctld", "status/template"].filter((k) => shownByValues(k, values));
    expect(shown({})).toEqual(["status/source"]);
    expect(shown({ "status/source": "text" })).toEqual(["status/source", "status/interval_min", "station/status"]);
    expect(shown({ "status/source": "rig" })).toEqual(["status/source", "status/interval_min", "status/rigctld", "status/template"]);
    expect(shown({ "status/rigctld": "127.0.0.1:4532" })).toEqual(["status/source", "status/interval_min", "status/rigctld", "status/template"]);
    expect(shown({ "station/status": "QRV" })).toEqual(["status/source", "status/interval_min", "station/status"]);
    expect(shown({ "status/source": "off", "station/status": "QRV", "status/rigctld": "127.0.0.1:4532" })).toEqual(["status/source"]);
    const antenna = (power: string) =>
      ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"].filter((k) =>
        shownByValues(k, { "beacon/power_w": power }),
      );
    expect(antenna("")).toEqual(["beacon/power_w"]);
    expect(antenna("5")).toHaveLength(4);
  });
  it("shows the GPS fields its source needs: the address for gpsd, the port and speed for a serial receiver, nothing for Fixed", () => {
    const gps = (values: Record<string, string>) => ["gps/source", "gps/host", "gps/device", "gps/baud"].filter((k) => shownByValues(k, values));
    expect(gps({ "gps/source": "off" })).toEqual(["gps/source"]);
    expect(gps({})).toEqual(["gps/source"]);
    expect(gps({ "gps/source": "gpsd" })).toEqual(["gps/source", "gps/host"]);
    expect(gps({ "gps/source": "serial" })).toEqual(["gps/source", "gps/device", "gps/baud"]);
  });
  it("shows the station's place (latitude and longitude) for a fixed station only, not while a GPS is chosen", () => {
    const place = (values: Record<string, string>) => ["station/lat", "station/lon"].filter((k) => shownByValues(k, values));
    expect(place({ "gps/source": "off" })).toEqual(["station/lat", "station/lon"]);
    expect(place({})).toEqual(["station/lat", "station/lon"]);
    expect(place({ "gps/source": "gpsd" })).toEqual([]);
    expect(place({ "gps/source": "serial", "station/lat": "60.17", "station/lon": "24.94" })).toEqual([]);
  });
  it("shows Travelling only for a moving station, the Beacon choice to both, and the antenna only for a fixed one", () => {
    const antenna = ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"];
    const fixed = { "gps/source": "off", "beacon/power_w": "5" };
    expect(shownByValues("beacon/travel", fixed)).toBe(false);
    expect(shownByValues("beacon/interval_min", fixed)).toBe(true);
    expect(antenna.filter((k) => shownByValues(k, fixed))).toEqual(antenna);
    for (const source of ["gpsd", "serial"]) {
      const moving = { "gps/source": source, "beacon/power_w": "5" };
      expect(shownByValues("beacon/travel", moving), source).toBe(true);
      expect(shownByValues("beacon/interval_min", moving), source).toBe(true);
      expect(
        antenna.filter((k) => shownByValues(k, moving)),
        source,
      ).toEqual([]);
    }
    expect(shownByValues("station/comment", { "gps/source": "gpsd" })).toBe(true);
    expect(shownByValues("beacon/path", { "gps/source": "gpsd" })).toBe(true);
  });
  it("gives the position choice and Travelling their words: Fixed, a GPS via gpsd, a GPS on a serial port; by car, by bicycle, on foot, by boat", () => {
    expect(FIELDS["gps/source"]).toMatchObject({ label: "Position", kind: "choice", name: "Position source" });
    expect(FIELDS["gps/source"]?.choices).toEqual([
      { value: "off", label: "Fixed" },
      { value: "gpsd", label: "A GPS via gpsd" },
      { value: "serial", label: "A GPS on a serial port" },
    ]);
    expect(FIELDS["beacon/travel"]).toMatchObject({ label: "Travelling", kind: "choice" });
    expect(FIELDS["beacon/travel"]?.choices).toEqual([
      { value: "car", label: "By car" },
      { value: "bicycle", label: "By bicycle" },
      { value: "foot", label: "On foot" },
      { value: "boat", label: "By boat" },
    ]);
    expect(FIELDS["beacon/travel"]?.tip).toHaveLength(1);
    expect(FIELDS["gps/baud"]?.unit).toBe("baud");
    expect(["beacon/mobile", "smart/fast_kmh", "smart/turn_slope"].map((k) => FIELDS[k])).toEqual([undefined, undefined, undefined]);
    const tip = (key: string) => (FIELDS[key]?.tip ?? []).join(" ");
    expect(tip("gps/host")).toContain("host:port");
  });
  it("gives a unit to the keys that are counted in one", () => {
    expect(["map/radius_km"].map((k) => FIELDS[k]?.unit)).toEqual(["km"]);
    expect(["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db"].map((k) => FIELDS[k]?.unit)).toEqual(["W", "m", "dB"]);
  });
  it("offers the status every 30 or 60 minutes or every 2 hours, and a stored interval that is none of them in words", () => {
    const info = FIELDS["status/interval_min"];
    expect(info?.kind).toBe("choice");
    expect(info?.choices).toEqual([
      { value: "30", label: "Every 30 min" },
      { value: "60", label: "Every 60 min" },
      { value: "120", label: "Every 2 hours" },
    ]);
    expect(info?.other?.("90")).toBe("Every 90 min");
  });
  it("offers the beacon as off, every 30 or 60 minutes or every 3 hours, and a stored interval that is none of them in words", () => {
    const info = FIELDS["beacon/interval_min"];
    expect(info?.kind).toBe("choice");
    expect(info?.choices).toEqual([
      { value: "0", label: "Off" },
      { value: "30", label: "Every 30 min" },
      { value: "60", label: "Every 60 min" },
      { value: "180", label: "Every 3 hours" },
    ]);
    expect(info?.other?.("20")).toBe("Every 20 min");
    expect(info?.other?.("15")).toBe("Every 15 min");
  });
});

describe("reasonOf", () => {
  it("gives the reason without the command and the setting in front, from the catalogue by its code", () => {
    const text = "set_config: station/lat: 95 is not between -90 and 90";
    expect(reasonOf({ cmd: "set_config", key: "station/lat", text, code: "setting.range", params: { value: 95, min: -90, max: 90 } })).toBe(
      "95 is not between -90 and 90",
    );
    expect(reasonOf({ cmd: "alert_test", key: null, text: "alert_test: no alert command", code: "alert.no_command" })).toBe("no alert command");
  });
  it("never gives the daemon's English: a refusal without a code the page has is its plain words of a failure", () => {
    expect(reasonOf({ cmd: "", key: null, text: "Not connected to the daemon." })).toBe(
      "That did not work; try again. If it keeps happening, send the logs (Settings → Help).",
    );
    expect(reasonOf({ cmd: "set_config", key: "station/lat", text: "something else", code: "other" })).not.toContain("something else");
  });
});

describe("the map's fields", () => {
  it("name the radius in km", () => {
    expect(FIELDS["map/radius_km"]).toMatchObject({ label: "Radius", unit: "km" });
  });
});

describe("shownFor", () => {
  it("shows the access key and HTTPS only while the network is let in, and never the port the search found last", () => {
    const keys = ["web/key", "web/https", "serial/last_port", "station/call"];
    expect(keys.filter((k) => shownFor(k, true))).toEqual(["web/key", "web/https", "station/call"]);
    expect(keys.filter((k) => shownFor(k, false))).toEqual(["station/call"]);
  });
});

describe("shownByRadios", () => {
  const keys = ["beacon/interval_min", "beacon/path", "gps/source", "gps/host", "gps/device", "gps/baud", "beacon/travel", "station/comment"];
  const radioOf = (id: number, type: string, extra: Partial<RadioRow> = {}) => pageRadio(radioRow(id, type, extra));
  const shown = (radios: readonly ReturnType<typeof radioOf>[]) => keys.filter((k) => shownByRadios(k, radios));
  it("leaves nothing out while a radio with SmartBeaconing is on", () => {
    expect(shown([radioOf(1, "kiss")])).toEqual(keys);
    expect(shown([radioOf(1, "kiss"), radioOf(2, "mercury")])).toEqual(keys);
  });
  it("keeps the one Beacon choice and the Position's keys while only radios without SmartBeaconing and paths are on, and leaves out Travelling and the Path", () => {
    expect(shown([radioOf(2, "mercury"), radioOf(1, "kiss", { enabled: false })])).toEqual(keys.filter((k) => k !== "beacon/travel" && k !== "beacon/path"));
  });
  it("shows no Beacon choice while no radio is on, nor before the daemon has told one", () => {
    const none = keys.filter((k) => k !== "beacon/travel" && k !== "beacon/interval_min" && k !== "beacon/path");
    expect(shown([radioOf(1, "kiss", { enabled: false })])).toEqual(none);
    expect(shown([])).toEqual(none);
  });
});

describe("portOptions", () => {
  const row = (device: string, description: string) => portRow(device, description);
  const ports = (search = true) => ({
    type: "ports" as const,
    sound_cards: [],
    keying: "",
    search,
    find: true,
    ports: [row("/dev/ttyUSB0", "FT232R"), row("/dev/ttyACM0", "n/a")],
    radio: null,
  });
  it("offers automatic first, the listed ports, the port in force and the port found when unlisted, and Other last", () => {
    expect(portOptions(ports(), "/dev/brainbox_3", "/dev/by-id/x").map((c) => c.value)).toEqual([
      "",
      "/dev/ttyUSB0",
      "/dev/ttyACM0",
      "/dev/brainbox_3",
      "/dev/by-id/x",
      PORT_OTHER,
    ]);
  });
  it("lists a port once whichever way it is known", () => {
    expect(portOptions(ports(), "/dev/ttyUSB0", "/dev/ttyUSB0").map((c) => c.value)).toEqual(["", "/dev/ttyUSB0", "/dev/ttyACM0", PORT_OTHER]);
    expect(portOptions(null, "", "").map((c) => c.label)).toEqual(["find automatically", "Other..."]);
  });
  it("lists a paired Bluetooth device by its name, after the serial ports, and keeps a typed bt:// address with a channel", () => {
    const listed = {
      type: "ports" as const,
      sound_cards: [],
      keying: "",
      search: true,
      find: true,
      ports: [row("/dev/ttyUSB0", "FT232R"), { ...row("bt://AA:BB:CC:DD:EE:01", "Bluetooth: TH-D74"), hwid: "" }],
      radio: null,
    };
    const options = portOptions(listed, "bt://AA:BB:CC:DD:EE:01/2", "");
    expect(options.map((c) => c.value)).toEqual(["", "/dev/ttyUSB0", "bt://AA:BB:CC:DD:EE:01", "bt://AA:BB:CC:DD:EE:01/2", PORT_OTHER]);
    expect(options[2].label).toBe("bt://AA:BB:CC:DD:EE:01 - Bluetooth: TH-D74");
  });
  it("calls the empty port not set for a port that is never searched for, whether the daemon searches or not", () => {
    expect(portOptions(ports(), "", "", true)[0]).toEqual({ value: "", label: "not set" });
    expect(portOptions(ports(false), "", "", true)[0]).toEqual({ value: "", label: "not set" });
    expect(portOptions(null, "", "", true).map((c) => c.label)).toEqual(["not set", "Other..."]);
  });
  it("labels each listed port with what the system calls it, where that says more than the port", () => {
    const listed = { ...ports(), ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyS0", "n/a"), row("COM1", "COM1")] };
    expect(portOptions(listed, "", "").slice(1, -1)).toEqual([
      { value: "/dev/ttyUSB0", label: "/dev/ttyUSB0 - FT232R USB UART" },
      { value: "/dev/ttyS0", label: "/dev/ttyS0" },
      { value: "COM1", label: "COM1" },
    ]);
  });
  it("greys a port another radio or the GPS receiver holds, with the holder's name, but not in the holder's own box nor the port in force", () => {
    const held = {
      ...ports(),
      ports: [
        { ...row("/dev/ttyUSB0", "FT232R"), held_by: 2 },
        { ...row("/dev/ttyACM0", "n/a"), held_by: 0 },
        { ...row("/dev/ttyS0", "n/a"), held_by: 1 },
      ],
    };
    const names = (id: number) => ({ 1: "FM", 2: "Mobile" })[id];
    const listedOf = (own: number, current = "") => portOptions(held, current, "", false, holderOf(own, names)).slice(1, -1);
    expect(listedOf(1)).toEqual([
      { value: "/dev/ttyUSB0", label: "Mobile: /dev/ttyUSB0 - FT232R", disabled: true },
      { value: "/dev/ttyACM0", label: "GPS: /dev/ttyACM0", disabled: true },
      { value: "/dev/ttyS0", label: "/dev/ttyS0" },
    ]);
    expect(listedOf(2).map((c) => c.disabled ?? false)).toEqual([false, true, true]);
    expect(listedOf(0).map((c) => c.disabled ?? false)).toEqual([true, false, true]);
    expect(listedOf(1, "/dev/ttyUSB0")[0]).toEqual({ value: "/dev/ttyUSB0", label: "/dev/ttyUSB0 - FT232R" });
    expect(portOptions(held, "", "").every((c) => c.disabled !== true)).toBe(true); // (a box that gives no holder)
  });
  it("greys a port a radio the page does not know holds, with its own label", () => {
    const held = { ...ports(), ports: [{ ...row("/dev/ttyUSB0", "FT232R"), held_by: 9 }] };
    expect(
      portOptions(
        held,
        "",
        "",
        false,
        holderOf(1, () => undefined),
      ).slice(1, -1),
    ).toEqual([{ value: "/dev/ttyUSB0", label: "/dev/ttyUSB0 - FT232R", disabled: true }]);
  });
  it("calls the empty port not set where the daemon does not search", () => {
    expect(portOptions(ports(false), "", "")[0]).toEqual({ value: "", label: "not set" });
  });
});

describe("the beacon being Off", () => {
  const off = { "beacon/interval_min": "0" };
  const beaconKeys = [
    "beacon/travel",
    "station/comment",
    "beacon/power_w",
    "beacon/antenna_height_m",
    "beacon/antenna_gain_db",
    "beacon/antenna_direction",
    "beacon/path",
  ];
  const statusKeys = ["status/source", "status/rigctld", "status/template", "status/interval_min", "station/status"];

  it("is an interval of 0 or empty, for a fixed and a moving station alike, and not a settings list that lacks the interval", () => {
    expect([beaconOff(off), beaconOff({ "beacon/interval_min": " 0 " }), beaconOff({ "beacon/interval_min": "" })]).toEqual([true, true, true]);
    expect([beaconOff({ "beacon/interval_min": "30" }), beaconOff({ "beacon/interval_min": "20" }), beaconOff({})]).toEqual([false, false, false]);
    expect(beaconOff({ "beacon/interval_min": "0", "hf/enabled": "true", "fm/enabled": "false" })).toBe(true); // (one interval for both radios: Off switches both beacons off)
  });
  it("greys only the timing, Travelling and the status's Every, and nothing of what is sent, of the Station group or of the Beacon choice", () => {
    for (const values of [off, { ...off, "gps/source": "gpsd" }]) {
      expect(["beacon/travel", "status/interval_min"].filter((key) => !disabledByValues(key, values))).toEqual([]);
      const never = [...CONFIG_KEYS.filter((key) => key.startsWith("station/")).map(String)].concat(
        "gps/source",
        "gps/host",
        "gps/device",
        "gps/baud",
        "beacon/interval_min",
        "status/source",
        "status/rigctld",
        "status/template",
        ...beaconKeys.filter((k) => k !== "beacon/travel"),
      );
      expect(never.filter((key) => disabledByValues(key, values))).toEqual([]);
    }
  });
  it("greys all that the beacon says while transmitting is off (RX only), whatever the beacon choice, and not the Station group or the choice", () => {
    for (const values of [
      { "station/transmit": "false", "beacon/interval_min": "30" },
      { "station/transmit": "false", ...off },
    ]) {
      expect([...beaconKeys, ...statusKeys].filter((key) => !disabledByValues(key, values))).toEqual([]);
      expect(
        ["station/call", "station/lat", "gps/source", "beacon/interval_min", "station/symbol_code"].filter((key) => disabledByValues(key, values)),
      ).toEqual([]);
    }
  });
  it("greys nothing while the beacon is On", () => {
    for (const interval of ["30", "60", "180"]) {
      expect([...beaconKeys, ...statusKeys].filter((key) => disabledByValues(key, { "beacon/interval_min": interval }))).toEqual([]);
    }
  });
  it("gives a fixed station the intervals and a moving one Off and On (SmartBeaconing), with the interval it keeps shown as On", () => {
    expect(fieldFor("beacon/interval_min", { "gps/source": "off" }).choices).toEqual(FIELDS["beacon/interval_min"]?.choices);
    expect((fieldFor("beacon/interval_min", { "gps/source": "off" }).choices ?? []).map((c) => (typeof c === "string" ? c : c.label))).toEqual([
      "Off",
      "Every 30 min",
      "Every 60 min",
      "Every 3 hours",
    ]);
    for (const source of ["gpsd", "serial"]) {
      const moving = fieldFor("beacon/interval_min", { "gps/source": source });
      expect(moving).toMatchObject({ label: "Beacon", kind: "bool", name: "Beacon interval" });
      expect(valueFor("beacon/interval_min", { "gps/source": source, "beacon/interval_min": "180" })).toBe("true");
      expect(valueFor("beacon/interval_min", { "gps/source": source, "beacon/interval_min": "0" })).toBe("false");
      expect([storedFor("beacon/interval_min", { "gps/source": source }, "true"), storedFor("beacon/interval_min", { "gps/source": source }, "false")]).toEqual(
        ["30", "0"],
      );
    }
    expect(valueFor("beacon/interval_min", { "gps/source": "off", "beacon/interval_min": "180" })).toBe("180");
    expect(storedFor("beacon/interval_min", { "gps/source": "off" }, "60")).toBe("60");
    expect(fieldFor("station/comment", { "gps/source": "gpsd" })).toBe(FIELDS["station/comment"]);
  });
});

// The radios' own settings (`radio/3/port`) and the station's of the radios (`email/radio`): no group of the form places them; the boxes of the Radio group, the Email tab's list and the Digipeater group do.
describe("the radios' own settings in the form", () => {
  it("are in no group: the radios' places show them", () => {
    const groups = groupKeys([...CONFIG_KEYS, "radio/3/port", "radio/3/digipeat", "radio/1/port", "email/radio"], "settings");
    expect(groups.flatMap((g) => g.keys).filter((k) => k.startsWith("radio/") || k === "email/radio")).toEqual([]);
    expect(groups.map((g) => g.id)).not.toContain("other");
    expect(groupKeys(["station/call", "email/radio", "radio/3/beacon"], "beacon").flatMap((g) => g.keys)).toEqual(["station/call"]);
  });

  it("say what the same field of the radios of before says", () => {
    expect(fieldFor("radio/3/port")).toBe(FIELDS["serial/port"]);
    expect(fieldFor("radio/7/keying")).toBe(FIELDS["mercury/keying"]);
    expect(fieldFor("radio/4/digipeat")).toBe(FIELDS["digi/enabled"]);
    expect(fieldFor("radio/5/tcp_host", {})).toBe(FIELDS["tcp/host"]);
    expect(fieldFor("radio/3/nothing")).toEqual({ label: "radio/3/nothing" });
  });

  it("name the types of radio in the catalogue's words, the radio type of before's list too", () => {
    const flat = new Set<string>(TNC_PROFILES.map((profile) => profile.key)); // (the FM types the setting of before takes: a type with no TNC profile, the Sound card's, is the radios' own alone)
    expect(FIELDS["tnc/profile"]?.choices?.map((c) => (typeof c === "string" ? c : c.label))).toEqual(
      typeChoices("fm")
        .filter((c) => flat.has(c.value))
        .map((c) => c.label),
    );
    expect(FIELDS["hf/profile"]?.choices?.map((c) => (typeof c === "string" ? c : c.value))).toEqual(["mercury", "dummy-hf"]);
    expect(typeChoices().map((c) => c.value)).toEqual(RADIO_TYPES.map((type) => type.key));
    expect([typeText("kiss-tcp"), typeText("dummy-hf"), typeText("nothing")]).toEqual(["Your own Direwolf or soundmodem", "Dummy Mercury radio", "nothing"]);
    for (const type of RADIO_TYPES) expect(typeText(type.key), type.key).not.toBe(type.key); // (every type the daemon lists has its name in the catalogue: no type's key on the page)
  });
});

describe("the keys of a radio's box", () => {
  const radioOf = (id: number, type: string, extra: Partial<RadioRow> = {}) => pageRadio(radioRow(id, type, extra));

  it("are a radio's own fields, radios 1 and 2 as every other, by its type: the port and speed of a serial TNC, the host and port of one over TCP, the card and keying of a modem", () => {
    expect(boxKeys(radioOf(1, "kiss"))).toEqual(["radio/1/port", "radio/1/baud"]);
    expect(boxKeys(radioOf(2, "mercury"))).toEqual(["radio/2/sound_card", "radio/2/keying"]);
    expect(boxKeys(radioOf(3, "kiss"))).toEqual(["radio/3/port", "radio/3/baud"]);
    expect(boxKeys(radioOf(4, "kiss-tcp"))).toEqual(["radio/4/tcp_host", "radio/4/tcp_port"]);
    expect(boxKeys(radioOf(5, "mercury"))).toEqual(["radio/5/sound_card", "radio/5/keying"]);
    expect(boxKeys(radioOf(6, "dummy"))).toEqual([]);
    expect([
      isRadioKey("radio/3/port"),
      radioFieldOf("radio/12/tcp_port"),
      radioFieldOf("serial/port"),
      fieldOfKey("serial/port"),
      fieldOfKey("radio/3/baud"),
    ]).toEqual([true, { id: 12, field: "tcp_port" }, null, "serial/port", "baud"]);
    expect([inputId("radio/3/tcp_port"), inputId("serial/port"), radioElementId({ id: 3 }, "name")]).toEqual([
      "set-radio-3-tcp_port",
      "set-serial-port",
      "set-radio-3-name",
    ]);
  });

  it("have the legend of the name typed while the radio is named, else the box's word of the kind with the number from the second", () => {
    expect([
      boxTitle(radioOf(1, "kiss"), true),
      boxTitle(radioOf(2, "mercury"), true),
      boxTitle(radioOf(5, "mercury", { number: 3 }), true),
      boxTitle(radioOf(3, "kiss", { name: "Mobile" }), true),
      boxTitle(radioOf(3, "kiss", { name: "Mobile" }), false),
    ]).toEqual(["FM radio", "Mercury radio", "Mercury radio 3", "Mobile", "FM radio"]);
    expect([unnamed(radioOf(3, "kiss", { name: "Mobile", number: 2 })), unnamed(radioOf(1, "kiss"))]).toEqual(["FM 2", "FM"]);
  });

  it("put a Digipeater Enable for each radio that may repeat and is on, with a legend while several radios are on", () => {
    const radios = [radioOf(1, "kiss"), radioOf(2, "mercury"), radioOf(3, "kiss", { name: "Mobile" }), radioOf(4, "dummy", { enabled: false })];
    const both = digiPlaces(radios);
    expect(both.keys).toEqual(["radio/1/digipeat", "radio/3/digipeat"]);
    expect(Object.values(both.boxes).map((b) => b.text)).toEqual(["FM radio", "Mobile"]);
    expect(both.links["radio/3/digipeat"]?.stats).toEqual(radios[2]?.row.stats);
    const one = digiPlaces([radioOf(1, "kiss", { enabled: false }), radioOf(2, "mercury", { enabled: false }), radios[2]]); // (radio 3 the only radio on)
    expect([one.keys, one.boxes]).toEqual([["radio/3/digipeat"], {}]);
    // plan section 6: "each row with the radio's name when there are several": one radio that may repeat beside another radio that is on says its radio
    const other = digiPlaces([radioOf(1, "kiss", { enabled: false }), radios[2], radioOf(4, "dummy-hf", { kind: "hf", number: 2 })]);
    expect([other.keys, Object.values(other.boxes).map((b) => b.text)]).toEqual([["radio/3/digipeat"], ["Mobile"]]);
  });
});
