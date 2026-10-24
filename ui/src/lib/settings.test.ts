import { describe, expect, it } from "vitest";
import { CONFIG_KEYS } from "@/protocol/lists";
import { BEACON_FOLDS, FIELDS, SUBGROUPS, groupKeys, reasonOf, shownByValues, shownFor } from "@/lib/settings";
import { PORT_OTHER, portOptions } from "@/lib/portchoice";

describe("groupKeys", () => {
  it("gives the Settings tab the serial and TNC, web, notifications and map keys, in the daemon's order", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "settings");
    expect(groups.map((g) => g.id)).toEqual(["serial", "digi", "web", "notifications", "map"]);
    expect(groups[0]?.keys).toEqual(["tnc/profile", "serial/port", "serial/baud", "tcp/host", "tcp/port", "serial/last_port"]);
    expect(groups[1]?.title).toBe("Digipeater");
    expect(groups[1]?.keys).toEqual(["digi/enabled"]);
    expect(groups[3]?.title).toBe("Notifications");
    expect(groups[3]?.keys).toEqual(["messages/alert", "messages/alert_command"]);
    expect(groups[4]?.keys).toEqual(["map/radius_km"]);
  });
  it("gives the Beacon tab the station keys first (the call, the place, the symbol), then how often and what the beacon says, the antenna and the path, and the status keys", () => {
    const groups = groupKeys([...CONFIG_KEYS].reverse(), "beacon");
    expect(groups.map((g) => g.id)).toEqual(["station", "beacon", "status"]);
    expect(groups[0]?.keys).toEqual(["station/call", "station/lat", "station/lon", "station/symbol_table", "station/symbol_code"]);
    expect(groups[1]?.keys).toEqual([
      "beacon/interval_min",
      "station/comment",
      "beacon/power_w",
      "beacon/antenna_height_m",
      "beacon/antenna_gain_db",
      "beacon/antenna_direction",
      "beacon/path",
    ]);
    expect(BEACON_FOLDS.map((f) => [f.title, f.keys.length])).toEqual([
      ["Antenna", 4],
      ["Advanced", 1],
    ]);
    expect(groups[2]?.keys).toEqual(["status/source", "station/status", "status/rigctld", "status/template", "status/interval_min"]);
  });
  it("has every key in one place only", () => {
    const shown = [...groupKeys(CONFIG_KEYS, "settings"), ...groupKeys(CONFIG_KEYS, "beacon")].flatMap((g) => g.keys);
    expect(shown.sort()).toEqual(
      CONFIG_KEYS.filter(
        (key) =>
          !["update/url", "serial/pattern", "serial/skip", "web/port", "web/allowed_hosts", "map/maxzoom", "map/source", "map/station_hours"].includes(key),
      ).sort(),
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
  it("keeps the radius of the map in a group of its own, and leaves off the page the detail and the source, which stay settings for neoaprs db set", () => {
    expect(groupKeys(["web/network", "map/radius_km"]).map((g) => g.id)).toEqual(["web", "map"]);
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
    ];
    for (const key of keys) {
      const tip = FIELDS[key]?.tip ?? [];
      expect(tip.length, key).toBeGreaterThan(0);
      expect(tip.join(" ").split(/[.:;] /).length, key).toBeLessThanOrEqual(8);
      expect(FIELDS[key]?.title, key).toBeUndefined();
    }
  });
  it("gives the numbers and the examples in the (i) of the fields that have them", () => {
    const tip = (key: string) => (FIELDS[key]?.tip ?? []).join(" ");
    expect(tip("station/comment")).toContain("43");
    expect(tip("station/status")).toContain("55");
    expect(tip("beacon/interval_min")).toContain("20");
    expect(tip("beacon/path")).toContain("WIDE1-1,WIDE2-1");
    expect(tip("beacon/path")).toContain("WIDE2-1");
    expect(tip("status/template")).toMatch(/\{freq\}.*\{mode\}/);
    expect(tip("status/template")).toContain("14.074 MHz USB");
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
  it("gives the reason without the command and the setting in front", () => {
    expect(reasonOf({ cmd: "set_config", key: "station/lat", text: "set_config: station/lat: 95 is not between -90 and 90" })).toBe(
      "95 is not between -90 and 90",
    );
    expect(reasonOf({ cmd: "alert_test", key: null, text: "alert_test: no alert command" })).toBe("no alert command");
  });
  it("leaves a sentence that does not begin with them as it is", () => {
    expect(reasonOf({ cmd: "", key: null, text: "Not connected to the daemon." })).toBe("Not connected to the daemon.");
    expect(reasonOf({ cmd: "set_config", key: "station/lat", text: "something else" })).toBe("something else");
  });
});

describe("the map's fields", () => {
  it("name the radius in km", () => {
    expect(FIELDS["map/radius_km"]).toMatchObject({ label: "Radius", unit: "km" });
  });
});

describe("shownFor in the TNC group", () => {
  const keys = ["serial/port", "serial/baud", "serial/last_port", "tcp/host", "tcp/port"];
  const shown = (profile: string) => keys.filter((k) => shownFor(k, profile, true));
  it("shows the port and the speed for a serial TNC, and never the port found", () => {
    expect(shown("kenwood-tnc2")).toEqual(["serial/port", "serial/baud"]);
    expect(shown("kiss")).toEqual(["serial/port", "serial/baud"]);
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
