import { describe, expect, it } from "vitest";
import { fmOn, hasPaths, hfOn, radioFor, stationRadio } from "@/lib/radiosides";
import { station } from "@/test/fixtures";

describe("which radios are on", () => {
  it("has FM on unless the setting says false, as the daemon's default is, and HF off unless it says true", () => {
    const fm: Record<string, string>[] = [{}, { "fm/enabled": "true" }, { "fm/enabled": "false" }, { "fm/enabled": "" }];
    const hf: Record<string, string>[] = [{}, { "hf/enabled": "false" }, { "hf/enabled": "true" }, { "hf/enabled": "" }];
    expect(fm.map((values) => fmOn(values))).toEqual([true, true, false, true]);
    expect(hf.map((values) => hfOn(values))).toEqual([false, false, true, false]);
  });
});

describe("the radio a station is messaged on", () => {
  it("is HF only for a station heard on HF alone, and FM for one heard on FM, on both or on neither", () => {
    const heard = (fm: number, hf: number) => stationRadio(station("OH2XYZ", { heard_fm: fm, heard_hf: hf }));
    expect([heard(3, 0), heard(0, 2), heard(3, 2), heard(0, 0)]).toEqual(["fm", "hf", "fm", "fm"]);
    expect([stationRadio(null), stationRadio(undefined)]).toEqual(["fm", "fm"]);
  });
});

describe("the path controls", () => {
  const hfOnly = station("OH2HF", { heard_fm: 0, heard_hf: 4 });
  const fm = station("OH2FM", { heard_fm: 4, heard_hf: 0 });

  it("are there for the requests while the FM radio is on, whatever HF does", () => {
    const all: Record<string, string>[] = [
      {},
      { "fm/enabled": "true", "hf/enabled": "true" },
      { "fm/enabled": "false" },
      { "fm/enabled": "false", "hf/enabled": "true" },
    ];
    expect(all.map((values) => hasPaths(values))).toEqual([true, true, false, false]);
  });

  it("are there for a station while FM is on and it is messaged on FM: not when it was heard on HF alone, and for one unknown", () => {
    const on = { "fm/enabled": "true", "hf/enabled": "true" };
    expect([hasPaths(on, fm), hasPaths(on, hfOnly), hasPaths(on, null), hasPaths({ "fm/enabled": "false" }, fm)]).toEqual([true, false, true, false]);
  });
});

describe("the radio a message goes over, as the daemon's table has it", () => {
  const heard = (fm: number, hf: number) => station("OH2XYZ", { heard_fm: fm, heard_hf: hf });
  const cases = [heard(3, 0), heard(0, 2), heard(3, 2), heard(0, 0), null];

  it("is FM for every station while the HF radio is off, whatever was heard", () => {
    for (const values of [{}, { "fm/enabled": "true", "hf/enabled": "false" }] as Record<string, string>[]) {
      expect(cases.map((row) => radioFor(row, values))).toEqual(["fm", "fm", "fm", "fm", "fm"]);
    }
  });

  it("is HF for every station while the FM radio is off", () => {
    expect(cases.map((row) => radioFor(row, { "fm/enabled": "false", "hf/enabled": "true" }))).toEqual(["hf", "hf", "hf", "hf", "hf"]);
  });

  it("is FM for a station heard on FM, on both or on neither, and HF for one heard on HF alone, while both radios are on", () => {
    expect(cases.map((row) => radioFor(row, { "fm/enabled": "true", "hf/enabled": "true" }))).toEqual(["fm", "hf", "fm", "fm", "fm"]);
  });
});
