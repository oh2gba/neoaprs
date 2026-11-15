import { describe, expect, it } from "vitest";
import {
  SYMBOL_CHOICES,
  degreesText,
  fieldsFrom,
  portChoices,
  NEW_STATION_BEACON_MIN,
  radioReady,
  radioStepKeys,
  setupChanges,
  stepOk,
  stepProblems,
  type RadioStep,
  type SetupFields,
} from "@/lib/setup";
import { callOk, callProblem, degreesProblem, parseNumber, symbolProblem } from "@/lib/fieldcheck";
import { pageRadios } from "@/lib/radios";
import { symbolLayers } from "@/lib/symbols";
import { SYMBOL_TABLES } from "@/protocol/lists";
import type { RadioRow } from "@/protocol/protocol";
import { configValues, portRow, radioRow, radiosTopic } from "@/test/fixtures";

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
    expect(stepOk(0, answered({ call: "" }))).toBe(false);
    expect(stepOk(0, answered({ call: "OH2ABC" }))).toBe(true);
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
    expect(stepOk(1, answered())).toBe(true);
    expect(stepOk(1, answered({ lon: "" }))).toBe(false);
    expect(stepProblems(1, answered({ lat: "95", lon: "x" }))).toEqual({ lat: "Between -90 and 90", lon: "Not a number" });
    expect(stepOk(1, answered({ lat: "95" }))).toBe(false);
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
    expect(stepOk(2, answered({ symbol: "" }))).toBe(false);
    expect(stepOk(2, answered({ symbol: "/>" }))).toBe(true);
    expect(stepOk(2, answered({ symbol: "a-" }))).toBe(false);
  });
});

// The Radio step is live, as the Radio group of the Settings tab is (plan section 6): it has no answers, and Finish waits for "one enabled radio with no field in error" over the page's radios and settings.
describe("the radio step", () => {
  /** The step as the form holds it for these settings (radio 1 a serial TNC, radio 2 the Mercury modem, off), with what is being changed, the complaints, and whether the daemon searches the ports. */
  function ready(extra: Record<string, string> = {}, more: Partial<RadioStep> = {}, rows: RadioRow[] | null = null): boolean {
    const config = configValues();
    const values = { ...config.values, ...config.radio_values, ...extra };
    const step: RadioStep = { values, draft: { ...values, ...more.draft }, errors: more.errors ?? {}, search: more.search ?? true };
    const radios = pageRadios(radiosTopic(...(rows ?? [radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false })])), null);
    return radioReady(radios, step);
  }

  it("needs no port where the daemon searches, and a picked one where it does not", () => {
    expect(ready({ "radio/1/port": "" }, { search: null })).toBe(true); // the daemon has not said yet
    expect(ready({ "radio/1/port": "" }, { search: true })).toBe(true);
    expect(ready({ "radio/1/port": "" }, { search: false })).toBe(false);
    expect(ready({ "radio/1/port": "COM3" }, { search: false })).toBe(true);
    expect(ready({ "radio/1/port": "" }, { search: false, draft: { "radio/1/port": "COM3" } })).toBe(true); // (as the form holds it)
  });

  it("is not ready while a field of the radio has a complaint, the page's or the daemon's, and a field the radio's type does not show does not count", () => {
    expect(ready({}, { errors: { "radio/1/baud": "300 to 921600" } })).toBe(false);
    expect(ready({}, { errors: { "radio/1/port": "no such port" } })).toBe(false);
    expect(ready({}, { errors: { "radio/1/baud": "" } })).toBe(true);
    expect(ready({}, { errors: { "radio/1/tcp_port": "1 to 65535", "station/call": "Not a call" } })).toBe(true); // (a serial TNC has no TCP port; the call is not the radio's)
  });

  it("takes a TNC over TCP with its host and port, the defaults where they are empty, and leaves the serial port alone then", () => {
    const tcp = [radioRow(1, "kiss-tcp")];
    expect(ready({ "radio/1/port": "" }, { search: false }, tcp)).toBe(true);
    expect(ready({ "radio/1/tcp_host": "", "radio/1/tcp_port": "" }, { search: false }, tcp)).toBe(true);
    expect(ready({}, { errors: { "radio/1/tcp_port": "1 to 65535" } }, tcp)).toBe(false);
    expect(ready({}, { errors: { "radio/1/tcp_host": "Not an address" } }, tcp)).toBe(false);
    expect(ready({}, { errors: { "radio/1/baud": "300 to 921600" } }, tcp)).toBe(true);
  });

  it("needs no port, no speed and no host for the Dummy radio, even where the daemon does not search the ports", () => {
    const dummy = [radioRow(1, "dummy")];
    expect(ready({ "radio/1/port": "" }, { search: false }, dummy)).toBe(true);
    expect(ready({}, { errors: { "radio/1/baud": "300 to 921600" } }, dummy)).toBe(true); // (what is left in the hidden fields is not looked at)
  });

  it("needs one radio on that is right: another on with a complaint, one that is off or removed with one, or none at all do not stop it, and only one that is right lets it go", () => {
    const hf = [radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury")];
    expect(ready({}, { errors: { "radio/1/baud": "300 to 921600" } }, hf)).toBe(true); // (the HF radio is right)
    expect(ready({}, { errors: { "radio/1/baud": "300 to 921600", "radio/2/keying": "no such port" } }, hf)).toBe(false);
    expect(ready({}, { search: false }, [radioRow(1, "kenwood-tnc2", { enabled: false }), radioRow(2, "mercury")])).toBe(true); // (the HF radio alone needs no serial port)
    expect(ready({}, {}, [radioRow(1, "kenwood-tnc2", { enabled: false }), radioRow(2, "mercury", { enabled: false })])).toBe(false); // (no radio on)
    expect(ready({}, {}, [])).toBe(false);
    const own = [
      radioRow(1, "kenwood-tnc2", { removed: true, enabled: false }),
      radioRow(3, "kiss", { number: 2 }),
      radioRow(4, "kiss-tcp", { number: 3, enabled: false }),
    ];
    expect(ready({ "radio/3/port": "" }, { search: false }, own)).toBe(false);
    expect(ready({ "radio/3/port": "" }, { search: false, draft: { "radio/3/port": "/dev/ttyACM0" } }, own)).toBe(true);
    expect(ready({}, { errors: { "radio/3/baud": "300 to 921600" } }, own)).toBe(false);
    expect(ready({}, { errors: { "radio/4/tcp_port": "1 to 65535", "radio/3/tcp_port": "1 to 65535" } }, own)).toBe(true); // (radio 4 is off, and radio 3 has no TCP port)
  });

  it("has RX only as the group's own row: the radios' fields are their boxes'", () => {
    const values = configValues().values;
    expect(radioStepKeys(values, values)).toEqual(["station/transmit"]);
  });

  it("lists the ports with what the system calls them: Automatic first where the daemon searches, a blank where it does not", () => {
    const row = (device: string, description: string) => portRow(device, description);
    const list = {
      type: "ports" as const,
      sound_cards: [],
      keying: "",
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

describe("what the guide starts with", () => {
  it("is the daemon's settings: the call, the place and the symbol (the radios have no answers: the Radio step is live)", () => {
    const f = fieldsFrom(configValues({ "serial/baud": "9600", "station/symbol_table": "\\", "station/symbol_code": "k" }).values);
    expect(f).toEqual({ call: "OH2GBA", lat: "60.17", lon: "24.94", symbol: "\\k" });
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
    expect(setupChanges(answered({ symbol: "/>" }), fresh())).toEqual({
      "station/call": "OH2ABC",
      "station/lat": "60.17",
      "station/lon": "24.94",
      "station/symbol_code": ">",
      "beacon/interval_min": "30",
    });
  });

  it("is nothing when the answers are what the daemon has, however a number is written", () => {
    const values = configValues().values;
    expect(setupChanges({ ...fieldsFrom(values), lat: "60.170", lon: "24,94", call: "oh2gba" }, values)).toEqual({});
  });

  it("has nothing of a radio, whatever the settings of the radios are: they were saved as they were changed (plan section 6: the call, the place, the symbol and the beacon still go at Finish)", () => {
    const values = { ...fresh(), "fm/enabled": "false", "hf/enabled": "true", "tnc/profile": "kiss-tcp", "serial/port": "/dev/ttyUSB0" };
    expect(Object.keys(setupChanges(answered(), values))).toEqual(["station/call", "station/lat", "station/lon", "beacon/interval_min"]);
  });
});
