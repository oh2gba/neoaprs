import { describe, expect, it } from "vitest";
import {
  SYMBOL_CHOICES,
  baudShown,
  degreesText,
  fieldsFrom,
  portChoices,
  radioChanges,
  NEW_STATION_BEACON_MIN,
  setupChanges,
  stepOk,
  stepProblems,
  type SetupFields,
} from "@/lib/setup";
import { callOk, callProblem, degreesProblem, parseNumber, symbolProblem } from "@/lib/fieldcheck";
import { symbolLayers } from "@/lib/symbols";
import { SYMBOL_TABLES } from "@/protocol/lists";
import { configValues } from "@/test/fixtures";

/** The settings of a fresh install: no call, no position. */
const fresh = () =>
  configValues({
    "beacon/interval_min": "0",
    "station/call": "",
    "station/lat": "",
    "station/lon": "",
    "tnc/profile": "kenwood-tnc2",
    "serial/baud": "",
    "serial/port": "",
  }).values;
const answered = (extra: Partial<SetupFields> = {}): SetupFields => ({ ...fieldsFrom(fresh()), call: "oh2abc", lat: "60.17", lon: "24.94", ...extra });

describe("the call step", () => {
  it("takes a call with an optional SSID in any case, as lib/calls.ts does", () => {
    for (const ok of ["OH2ABC", "oh2abc-9", " OH2ABC-15 ", "K1A"]) expect(callOk(ok), ok).toBe(true);
    for (const bad of ["OH2ABC-16", "OH2ABC-", "TOOLONGCALL", "OH2 ABC", "ÅÄÖ"]) {
      expect(callOk(bad), bad).toBe(false);
      expect(callProblem(bad), bad).toBe("Not a call");
    }
  });

  it("refuses what the daemon would not transmit under: NOCALL and MYCALL, and a call that has no digit or no letter or is 1 or 2 characters", () => {
    for (const bad of ["NOCALL", "mycall-3"]) expect(callProblem(bad), bad).toBe(`${bad.split("-")[0]?.toUpperCase()} is not a call`);
    for (const bad of ["AB", "A1", "ABC", "123", "1234"]) {
      expect(callOk(bad), bad).toBe(false);
      expect(callProblem(bad), bad).toBe("Not a call");
    }
    for (const ok of ["A1B", "W1AW", "OH2ABC-07", "OH2ABC-00"]) expect(callOk(ok), ok).toBe(true);
  });

  it("refuses N0CALL with or without an SSID, and says nothing about an empty call, which only waits", () => {
    for (const bad of ["N0CALL", "n0call", "N0CALL-7"]) {
      expect(callOk(bad), bad).toBe(false);
      expect(callProblem(bad), bad).toBe("N0CALL is not a call");
    }
    expect(callProblem("")).toBe("");
    expect(callOk("")).toBe(false);
    expect(stepOk(0, answered({ call: "" }), null)).toBe(false);
    expect(stepOk(0, answered({ call: "OH2ABC" }), null)).toBe(true);
  });
});

describe("the position step", () => {
  it("takes decimal degrees within the limits, with a comma for the point", () => {
    expect(parseNumber("60,17")).toBe(60.17);
    expect(parseNumber(" -24.94 ")).toBe(-24.94);
    expect(parseNumber("60.")).toBe(60);
    for (const bad of ["", "abc", "60.1.2", "6e1", "--5"]) expect(parseNumber(bad), bad).toBeNull();
    expect(degreesProblem("95", 90)).toBe("Between -90 and 90");
    expect(degreesProblem("-90", 90)).toBe("");
    expect(degreesProblem("181", 180)).toBe("Between -180 and 180");
    expect(degreesProblem("north", 90)).toBe("Not a number");
    expect(degreesProblem("", 90)).toBe("");
  });

  it("needs both, and says which is wrong", () => {
    expect(stepOk(1, answered(), null)).toBe(true);
    expect(stepOk(1, answered({ lon: "" }), null)).toBe(false);
    expect(stepProblems(1, answered({ lat: "95", lon: "x" }))).toEqual({ lat: "Between -90 and 90", lon: "Not a number" });
    expect(stepOk(1, answered({ lat: "95" }), null)).toBe(false);
  });

  it("writes degrees without trailing zeros and at most six decimals", () => {
    expect(degreesText(60.17)).toBe("60.17");
    expect(degreesText(24.123456789)).toBe("24.123457");
    expect(degreesText(60)).toBe("60");
  });
});

describe("the symbol step", () => {
  it("offers 12 symbols of the primary table, each one the sprite draws", () => {
    expect(SYMBOL_CHOICES).toHaveLength(12);
    expect(SYMBOL_CHOICES.map((s) => s.name)).toEqual([
      "House",
      "Car",
      "Truck",
      "Van",
      "Motorcycle",
      "Bike",
      "Walker",
      "Boat",
      "Digipeater",
      "Weather station",
      "Portable",
      "Antenna",
    ]);
    expect(new Set(SYMBOL_CHOICES.map((s) => s.table + s.code)).size).toBe(12);
    for (const s of SYMBOL_CHOICES) expect(symbolLayers(s.table, s.code), s.name).toHaveLength(1);
  });

  it("takes any table and code the daemon takes: / \\ or an overlay character, and one printable character", () => {
    for (const ok of ["/-", "\\k", "S#", "0>", "A~"]) {
      expect(symbolProblem(ok), ok).toBe("");
      expect(SYMBOL_TABLES).toContain(ok[0]);
    }
    expect(symbolProblem("/")).toBe("Table and code");
    expect(symbolProblem("/--")).toBe("Table and code");
    expect(symbolProblem("a-")).toBe("Table: / \\ 0-9 A-Z");
    expect(symbolProblem("/ ")).toBe("Code: one printable character");
    expect(symbolProblem("")).toBe("");
    expect(stepOk(2, answered({ symbol: "" }), null)).toBe(false);
    expect(stepOk(2, answered({ symbol: "/>" }), null)).toBe(true);
    expect(stepOk(2, answered({ symbol: "a-" }), null)).toBe(false);
  });
});

describe("the radio step", () => {
  it("needs no port where the daemon searches, and a picked one where it does not", () => {
    expect(stepOk(3, answered({ port: "" }), null)).toBe(true); // the daemon has not said yet
    expect(stepOk(3, answered({ port: "" }), true)).toBe(true);
    expect(stepOk(3, answered({ port: "" }), false)).toBe(false);
    expect(stepOk(3, answered({ port: "COM3" }), false)).toBe(true);
  });

  it("checks the speed when there is one, and leaves an empty one to the profile", () => {
    expect(stepOk(3, answered({ baud: "" }), true)).toBe(true);
    expect(stepOk(3, answered({ baud: "57600" }), true)).toBe(true);
    for (const bad of ["12", "fast", "9600.5", "999999"]) {
      expect(stepOk(3, answered({ baud: bad }), true), bad).toBe(false);
      expect(stepProblems(3, answered({ baud: bad })).baud, bad).toBe("300 to 921600");
    }
  });

  it("needs a host and a port for a TCP profile, and ignores the serial fields then", () => {
    const direwolf = answered({ profile: "kiss-tcp", host: "127.0.0.1", tcpPort: "8001", baud: "x", port: "" });
    expect(stepOk(3, direwolf, false)).toBe(true);
    expect(stepOk(3, { ...direwolf, host: "" }, true)).toBe(false);
    expect(stepOk(3, { ...direwolf, tcpPort: "" }, true)).toBe(false);
    expect(stepProblems(3, { ...direwolf, tcpPort: "70000" }).tcpPort).toBe("1 to 65535");
    expect(stepProblems(3, { ...direwolf, host: "my pi" }).host).toBe("Not an address");
  });

  it("lists the ports with what the system calls them: Automatic first where the daemon searches, a blank where it does not", () => {
    const row = (device: string, description: string) => ({ device, description, hwid: "n/a", vid: null, pid: null });
    const list = {
      type: "ports" as const,
      search: true,
      find: true,
      ports: [row("/dev/ttyUSB0", "FT232R USB UART"), row("/dev/ttyS0", "n/a"), row("COM1", "COM1")],
    };
    expect(portChoices(list)).toEqual([
      { value: "", label: "Automatic" },
      { value: "/dev/ttyUSB0", label: "/dev/ttyUSB0 - FT232R USB UART" },
      { value: "/dev/ttyS0", label: "/dev/ttyS0" },
      { value: "COM1", label: "COM1" },
    ]);
    expect(portChoices({ ...list, search: false })[0]).toEqual({ value: "", label: "-" });
    expect(portChoices(null)).toEqual([{ value: "", label: "Automatic" }]);
  });
});

describe("the map step", () => {
  it("takes a radius of 10 to 1000 km", () => {
    expect(stepOk(4, answered({ radius: "150" }), null)).toBe(true);
    expect(stepOk(4, answered({ radius: "10" }), null)).toBe(true);
    expect(stepOk(4, answered({ radius: "1000" }), null)).toBe(true);
    for (const bad of ["9", "1001", "far", "1e2"]) expect(stepProblems(4, answered({ radius: bad })).radius, bad).toBe("10 to 1000");
    expect(stepOk(4, answered({ radius: "" }), null)).toBe(false);
  });
});

describe("what the guide starts with", () => {
  it("is the daemon's settings, with the profile's own speed left empty for the placeholder", () => {
    const f = fieldsFrom(configValues({ "serial/baud": "9600", "station/symbol_table": "\\", "station/symbol_code": "k" }).values);
    expect(f).toMatchObject({
      call: "OH2GBA",
      lat: "60.17",
      lon: "24.94",
      symbol: "\\k",
      profile: "kenwood-tnc2",
      baud: "",
      host: "127.0.0.1",
      tcpPort: "8001",
      radius: "150",
    });
    expect(baudShown("kenwood-tnc2", "57600")).toBe("57600");
    expect(baudShown("kenwood-tnc2", " 9600 ")).toBe("");
    expect(fieldsFrom({}).symbol).toBe("/-");
  });
});

describe("the beacon of a new station", () => {
  it("is every 30 minutes with the first call, when the daemon has no call and its beacon is off or empty", () => {
    expect(NEW_STATION_BEACON_MIN).toBe("30");
    expect(setupChanges(answered(), fresh())["beacon/interval_min"]).toBe("30");
    expect(setupChanges(answered(), { ...fresh(), "beacon/interval_min": "0" })["beacon/interval_min"]).toBe("30");
    expect(setupChanges(answered(), { ...fresh(), "beacon/interval_min": "" })["beacon/interval_min"]).toBe("30");
  });

  it("is left alone when the station has a beacon of its own or already has a call (the guide run again never starts one)", () => {
    expect(setupChanges(answered(), { ...fresh(), "beacon/interval_min": "60" })["beacon/interval_min"]).toBeUndefined();
    expect(setupChanges(answered(), { ...fresh(), "station/call": "OH2GBA", "beacon/interval_min": "0" })["beacon/interval_min"]).toBeUndefined();
  });
});

describe("setupChanges", () => {
  it("is the keys whose answer differs from the daemon's, a fresh install's every answer that is not already its default", () => {
    expect(setupChanges(answered(), fresh())).toEqual({
      "station/call": "OH2ABC",
      "station/lat": "60.17",
      "station/lon": "24.94",
      "beacon/interval_min": "30",
    });
    expect(setupChanges(answered({ symbol: "/>", radius: "200", profile: "kantronics", port: "/dev/ttyUSB0", baud: "4800" }), fresh())).toEqual({
      "station/call": "OH2ABC",
      "station/lat": "60.17",
      "station/lon": "24.94",
      "station/symbol_code": ">",
      "tnc/profile": "kantronics",
      "serial/port": "/dev/ttyUSB0",
      "serial/baud": "4800",
      "map/radius_km": "200",
      "beacon/interval_min": "30",
    });
  });

  it("is nothing when the answers are what the daemon has, however a number is written", () => {
    const values = configValues().values;
    expect(setupChanges({ ...fieldsFrom(values), lat: "60.170", lon: "24,94", call: "oh2gba" }, values)).toEqual({});
    expect(setupChanges({ ...fieldsFrom(values), baud: "9600" }, values)).toEqual({}); // the profile's speed is the empty one
  });

  it("sends a speed that is not the profile's, and an empty speed that clears one", () => {
    const values = configValues({ "serial/baud": "57600" }).values;
    expect(fieldsFrom(values).baud).toBe("57600");
    expect(setupChanges({ ...fieldsFrom(values), baud: "" }, values)).toEqual({ "serial/baud": "" });
    expect(setupChanges({ ...fieldsFrom(values), baud: "19200" }, values)).toEqual({ "serial/baud": "19200" });
  });

  it("sends the host and port of a TCP profile and clears a serial device the daemon holds, and none of the serial keys", () => {
    const values = { ...fresh(), "serial/port": "/dev/ttyUSB0" };
    const changes = setupChanges(answered({ profile: "kiss-tcp", host: " 192.168.1.5 ", tcpPort: "8002", port: "/dev/ttyUSB0", baud: "4800" }), values);
    expect(changes).toEqual({
      "station/call": "OH2ABC",
      "station/lat": "60.17",
      "station/lon": "24.94",
      "tnc/profile": "kiss-tcp",
      "tcp/host": "192.168.1.5",
      "tcp/port": "8002",
      "serial/port": "",
      "beacon/interval_min": "30",
    });
    expect(setupChanges(answered({ profile: "kiss-tcp" }), { ...fresh(), "serial/port": "socket://127.0.0.1:8001" })).not.toHaveProperty("serial/port");
  });

  it("sends the serial keys and none of the TCP ones for a serial profile", () => {
    const changes = setupChanges(answered({ host: "other", tcpPort: "9", port: "COM3" }), fresh());
    expect(changes).toMatchObject({ "serial/port": "COM3" });
    expect(Object.keys(changes).filter((k) => k.startsWith("tcp/"))).toEqual([]);
  });
});

describe("the Dummy radio in the radio step", () => {
  const dummy = (extra: Partial<SetupFields> = {}) => answered({ profile: "dummy", ...extra });

  it("needs no port, no speed and no host: the step is right with none, even where the daemon does not search the ports", () => {
    expect(stepOk(3, dummy({ port: "", baud: "" }), false)).toBe(true);
    expect(stepOk(3, dummy({ port: "", baud: "" }), null)).toBe(true);
    expect(stepOk(3, answered({ port: "" }), false)).toBe(false); // (a serial TNC does)
    expect(stepProblems(3, dummy({ baud: "12", host: "", tcpPort: "70000" }))).toEqual({}); // (what is left in the hidden fields is not looked at)
  });

  it("sends the type and none of the port, speed, host and TCP port, and leaves what the daemon holds", () => {
    const values = { ...fresh(), "serial/port": "COM3", "serial/baud": "57600" };
    const changes = setupChanges(dummy({ port: "COM9", baud: "4800", host: "x", tcpPort: "9" }), values);
    expect(changes["tnc/profile"]).toBe("dummy");
    expect(Object.keys(changes).filter((k) => k.startsWith("serial/") || k.startsWith("tcp/"))).toEqual([]);
  });

  it("is a radio like the others when it is the daemon's: the fields start from its settings", () => {
    expect(fieldsFrom({ ...fresh(), "tnc/profile": "dummy" }).profile).toBe("dummy");
    expect(setupChanges(fieldsFrom({ ...fresh(), "tnc/profile": "dummy" }), { ...fresh(), "tnc/profile": "dummy" })).not.toHaveProperty("tnc/profile");
  });
});

describe("radioChanges", () => {
  it("is the keys of the radio among the changes, not the call, the position or the map", () => {
    const f = answered({ port: "COM5", baud: "57600", radius: "99" });
    expect(radioChanges(f, fresh())).toEqual({ "serial/port": "COM5", "serial/baud": "57600" });
    expect(radioChanges(answered({ profile: "kiss-tcp", host: "10.0.0.5" }), fresh())).toEqual({ "tnc/profile": "kiss-tcp", "tcp/host": "10.0.0.5" });
    expect(radioChanges(fieldsFrom(fresh()), fresh())).toEqual({});
  });
});
