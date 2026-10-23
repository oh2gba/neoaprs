import { describe, expect, it } from "vitest";
import { CONFIG_KEYS } from "@/protocol/lists";
import { FIELDS, SUBGROUPS, changedValues, errorKey, errorReason, groupKeys, shownByValues, shownFor } from "@/lib/settings";
import { PORT_OTHER, portOptions } from "@/lib/portchoice";

describe("groupKeys", () => {
  it("gives the Settings tab the serial and TNC, web, notifications and map keys, in the daemon's order", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "settings");
    expect(groups.map((g) => g.id)).toEqual(["serial", "digi", "web", "notifications", "map"]);
    expect(groups[0]?.keys).toEqual(["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "tnc/check_sec", "serial/last_port"]);
    expect(groups[1]?.title).toBe("Digipeater");
    expect(groups[1]?.keys).toEqual(["digi/enabled"]);
    expect(groups[3]?.title).toBe("Notifications");
    expect(groups[3]?.keys).toEqual(["messages/alert", "messages/alert_command"]);
    expect(groups[4]?.keys).toEqual(["map/hide_after_min", "map/radius_km", "map/maxzoom", "map/source"]);
  });
  it("gives the Beacon tab the station keys first (the call is its first field), then the beacon keys and the status keys", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "beacon");
    expect(groups.map((g) => g.id)).toEqual(["station", "beacon", "status"]);
    expect(groups[1]?.keys).toEqual(["beacon/interval_min", "beacon/path"]);
    expect(groups[0]?.keys).toEqual([
      "station/call",
      "station/lat",
      "station/lon",
      "station/symbol_table",
      "station/symbol_code",
      "station/comment",
      "beacon/power_w",
      "beacon/antenna_height_m",
      "beacon/antenna_gain_db",
      "beacon/antenna_direction",
    ]);
    expect(groups[2]?.keys).toEqual(["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"]);
  });
  it("has every key in one place only", () => {
    const shown = [...groupKeys(CONFIG_KEYS, "settings"), ...groupKeys(CONFIG_KEYS, "beacon")].flatMap((g) => g.keys);
    expect(shown.sort()).toEqual(
      CONFIG_KEYS.filter((key) => !["update/url", "serial/pattern", "serial/skip", "web/port", "web/allowed_hosts"].includes(key)).sort(),
    );
  });
  it("leaves the address of the update check off the page: it is set with neoaprs db set", () => {
    expect(groupKeys(CONFIG_KEYS, "settings").flatMap((g) => g.keys)).not.toContain("update/url");
    expect(FIELDS["update/url"]).toBeUndefined();
  });
  it("shows a key it does not know under Other", () => {
    expect(groupKeys(["web/network", "mystery/key"], "settings").map((g) => [g.id, g.keys])).toEqual([
      ["web", ["web/network"]],
      ["other", ["mystery/key"]],
    ]);
  });
  it("heads the daemon's own alert in the Notifications group with a line that says where it runs", () => {
    expect(SUBGROUPS["messages/alert"]?.text).toBe("On the NeoAPRS computer");
    expect(Object.keys(SUBGROUPS)).toEqual(["messages/alert"]);
    expect([FIELDS["messages/alert"]?.label, FIELDS["messages/alert_command"]?.label]).toEqual(["Alert", "Command"]);
  });
  it("keeps the timeout of the map in a group of its own", () => {
    expect(groupKeys(["web/network", "map/hide_after_min"]).map((g) => g.id)).toEqual(["web", "map"]);
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
  it("has a gone-from-the-page setting nowhere: the tocall, the compressed form and the DAO are the program's", () => {
    expect(CONFIG_KEYS).not.toContain("beacon/destination");
    expect(CONFIG_KEYS).not.toContain("beacon/compressed");
    expect(CONFIG_KEYS).not.toContain("beacon/dao");
    expect(Object.keys(FIELDS).filter((k) => ["beacon/destination", "beacon/compressed", "beacon/dao"].includes(k))).toEqual([]);
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
    ];
    for (const key of keys) {
      const tip = FIELDS[key]?.tip ?? [];
      expect(tip.length, key).toBeGreaterThan(0);
      expect(tip.join(" ").split(/[.:;] /).length, key).toBeLessThanOrEqual(8);
      expect(FIELDS[key]?.title, key).toBeUndefined();
    }
    expect(FIELDS["station/comment"]?.tip?.join(" ")).toContain("43");
    expect(FIELDS["station/status"]?.tip?.join(" ")).toContain("55");
    expect(FIELDS["beacon/interval_min"]?.tip?.join(" ")).toContain("10");
    expect(FIELDS["status/template"]?.tip?.join(" ")).toMatch(/\{freq\}.*\{mode\}/);
    expect(FIELDS["status/template"]?.tip?.at(-1)).toContain("14.074 MHz USB");
  });
  it("shows the status fields its source needs and the antenna's figures once there is a power", () => {
    const shown = (values: Record<string, string>) =>
      ["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"].filter((k) => shownByValues(k, values));
    expect(shown({})).toEqual(["status/source"]);
    expect(shown({ "status/source": "text" })).toEqual(["status/source", "station/status", "status/interval_min"]);
    expect(shown({ "status/source": "rig" })).toEqual(["status/source", "status/rigctld", "status/template", "status/interval_min"]);
    expect(shown({ "status/rigctld": "127.0.0.1:4532" })).toEqual(["status/source", "status/rigctld", "status/template", "status/interval_min"]);
    expect(shown({ "station/status": "QRV" })).toEqual(["status/source", "station/status", "status/interval_min"]);
    expect(shown({ "status/source": "off", "station/status": "QRV", "status/rigctld": "127.0.0.1:4532" })).toEqual(["status/source"]);
    const antenna = (power: string) =>
      ["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db", "beacon/antenna_direction"].filter((k) =>
        shownByValues(k, { "beacon/power_w": power }),
      );
    expect(antenna("")).toEqual(["beacon/power_w"]);
    expect(antenna("5")).toHaveLength(4);
  });
  it("gives a unit to the keys that are counted in one, and a word for 0 where 0 is a state", () => {
    expect(["tnc/check_sec", "map/hide_after_min", "beacon/interval_min"].map((k) => FIELDS[k]?.unit)).toEqual(["s", "min", "min"]);
    expect(["beacon/power_w", "beacon/antenna_height_m", "beacon/antenna_gain_db"].map((k) => FIELDS[k]?.unit)).toEqual(["W", "m", "dB"]);
    expect(["map/hide_after_min", "tnc/check_sec", "beacon/interval_min"].map((k) => FIELDS[k]?.zero)).toEqual(["never", "off", "off"]);
  });
});

describe("changedValues", () => {
  it("is the keys whose draft differs", () => {
    expect(changedValues({ a: "1", b: "3", c: "x" }, { a: "1", b: "2", c: "x" })).toEqual({ b: "3" });
    expect(changedValues({ a: "1" }, { a: "1" })).toEqual({});
  });
  it("leaves out a key the daemon does not have", () => {
    expect(changedValues({ a: "1", z: "9" }, { a: "1" })).toEqual({});
  });
});

describe("errorKey", () => {
  const keys = ["station/lat", "station/lon", "serial/port", "serial/baud"];
  it("finds the key an error begins with, behind the command's name or not", () => {
    expect(errorKey("set_config: station/lat: 95 is not between -90 and 90", keys)).toBe("station/lat");
    expect(errorKey("serial/baud: 5 is not between 300 and 921600", keys)).toBe("serial/baud");
  });
  it("is none for an error about something else", () => {
    expect(errorKey("forget_station: call: is missing", keys)).toBeNull();
    expect(errorKey("Not connected to the daemon.", keys)).toBeNull();
  });
  it("gives the reason without the command and the key", () => {
    expect(errorReason("set_config: station/lat: 95 is not between -90 and 90", "station/lat")).toBe("95 is not between -90 and 90");
    expect(errorReason("something else", "station/lat")).toBe("something else");
  });
});

describe("the map's fields", () => {
  it("name the radius in km, the detail as a choice with a word for each zoom, and the source with its default as the placeholder", () => {
    expect(FIELDS["map/radius_km"]).toMatchObject({ label: "Radius", unit: "km" });
    expect(FIELDS["map/maxzoom"]).toMatchObject({ label: "Detail", kind: "choice" });
    expect(FIELDS["map/maxzoom"]?.choices).toEqual([
      { value: "10", label: "10 town" },
      { value: "12", label: "12 streets" },
      { value: "14", label: "14 houses" },
    ]);
    expect(FIELDS["map/source"]).toMatchObject({ label: "Map data", empty: "daily build" });
  });
});

describe("shownFor in the TNC group", () => {
  const keys = ["serial/port", "serial/baud", "serial/pattern", "serial/skip", "serial/last_port", "tcp/host", "tcp/port", "tnc/check_sec"];
  const shown = (profile: string, search = true) => keys.filter((k) => shownFor(k, profile, true, search));
  it("shows the port, the speed and the search for a serial TNC, the keep-alive only for one that can be asked, and never the port found", () => {
    expect(shown("kenwood-tnc2")).toEqual(["serial/port", "serial/baud", "serial/pattern", "serial/skip", "tnc/check_sec"]);
    expect(shown("kiss")).toEqual(["serial/port", "serial/baud", "serial/pattern", "serial/skip"]);
  });
  it("leaves the search out where the daemon does not search", () => {
    expect(shown("kiss", false)).toEqual(["serial/port", "serial/baud"]);
  });
  it("shows only the host and the port for KISS over TCP", () => {
    expect(shown("kiss-tcp")).toEqual(["tcp/host", "tcp/port"]);
  });
});

describe("portOptions", () => {
  const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
  const ports = (search = true) => ({ type: "ports" as const, search, ports: [row("/dev/ttyUSB0", "FT232R"), row("/dev/ttyACM0", "n/a")] });
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
      search: true,
      ports: [row("/dev/ttyUSB0", "FT232R"), { ...row("bt://AA:BB:CC:DD:EE:01", "Bluetooth: TH-D74"), hwid: "" }],
    };
    const options = portOptions(listed, "bt://AA:BB:CC:DD:EE:01/2", "");
    expect(options.map((c) => c.value)).toEqual(["", "/dev/ttyUSB0", "bt://AA:BB:CC:DD:EE:01", "bt://AA:BB:CC:DD:EE:01/2", PORT_OTHER]);
    expect(options[2].label).toBe("bt://AA:BB:CC:DD:EE:01 - Bluetooth: TH-D74");
  });
  it("calls the empty port none chosen where the daemon does not search", () => {
    expect(portOptions(ports(false), "", "")[0]).toEqual({ value: "", label: "none chosen" });
  });
});
