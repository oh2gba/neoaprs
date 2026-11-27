import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { isUp, lookAt, satelliteLabels, satelliteRows, shiftText, tuneRows } from "@/lib/layers/satellitecard";
import { takeUnits } from "@/lib/units";
import { DURING, RISE, satelliteCard } from "@/test/satellitefixtures";

const text = (rows: { label: string; text: string }[]) => rows.map((row) => [row.label, row.text]);

afterEach(() => {
  setLocale("en");
  takeUnits({});
});

describe("satelliteRows: the card's rows", () => {
  it("while it is up: the time left, the elevation and the Doppler now, then the pass and the frequencies", () => {
    const rows = text(satelliteRows(satelliteCard(), DURING + 2500));
    expect(rows.slice(0, 3)).toEqual([
      ["Time left", "9 min"],
      ["Elevation", "4°"],
      ["Doppler", "+8.4 kHz"],
    ]);
    expect(rows.map(([label]) => label)).toEqual([
      "Time left",
      "Elevation",
      "Doppler",
      "Highest",
      "Set",
      "Downlink",
      "Uplink",
      "Mode",
      "Altitude",
    ]);
    expect(rows.at(-3)).toEqual(["Uplink", "437.825 MHz"]);
    expect(rows.at(-2)).toEqual(["Mode", "AFSK 1200"]);
    expect(rows.at(-1)).toEqual(["Altitude", "420 km"]);
  });

  it("before the pass: the rise and how soon, how long it lasts, the set and the highest point", () => {
    const before = Date.parse(RISE) - 2 * 3600000;
    const rows = text(satelliteRows(satelliteCard(), before));
    expect(rows.slice(0, 4).map(([label]) => label)).toEqual(["Rise", "Duration", "Set", "Highest"]);
    expect(rows[0]?.[1]).toMatch(/^\d\d:\d\d \(in 2 h\)$/);
    expect(rows[1]).toEqual(["Duration", "10 min"]);
    expect(rows[3]).toEqual(["Highest", "15°"]);
  });

  it("without a pass (no position): only the frequencies, the mode and the altitude", () => {
    const card = satelliteCard({ next_pass: null, looks: [], mode: null, uplinks: [] });
    expect(text(satelliteRows(card, DURING))).toEqual([
      ["Downlink", "437.825 MHz"],
      ["Altitude", "420 km"],
    ]);
    expect(tuneRows(card)).toEqual([]);
  });

  it("says the altitude by the page's unit switch and the figures in the language's own", () => {
    takeUnits({ "units/non_metric": "true" });
    setLocale("de");
    const rows = text(satelliteRows(satelliteCard({ next_pass: null }), DURING));
    expect(rows[0]).toEqual(["Downlink", "437,825 MHz"]);
    expect(rows.at(-1)?.[1]).toBe("261 mi");
  });

  it("keeps the room of every label it may have", () => {
    const labels = satelliteLabels();
    for (const [label] of text(satelliteRows(satelliteCard(), DURING))) expect(labels).toContain(label);
    expect(labels).toContain("Rise");
    expect(labels).toContain("Path");
  });
});

describe("the Doppler and the table of where to tune", () => {
  it("tells now between the daemon's samples, and nothing outside them", () => {
    const now = lookAt(satelliteCard().looks, DURING + 2500);
    expect(now?.el_deg).toBeCloseTo(4.25, 5);
    expect(now?.down_hz[0]).toBeCloseTo(8350, 5);
    expect(lookAt(satelliteCard().looks, DURING + 60000)).toBeNull();
  });

  it("writes a shift with its sign in kHz", () => {
    expect([shiftText(8350), shiftText(-10450), shiftText(0)]).toEqual(["+8.4 kHz", "−10.5 kHz", "0.0 kHz"]);
  });

  it("gives where to tune at rise, highest point and set: the downlink above then below, the uplink the other way", () => {
    expect(tuneRows(satelliteCard())).toEqual([
      { label: "Downlink", cells: ["437.834", "437.825", "437.816"] },
      { label: "Uplink", cells: ["437.816", "437.825", "437.834"] },
    ]);
  });

  it("is up between the rise and the set", () => {
    expect(isUp(satelliteCard(), DURING)).toBe(true);
    expect(isUp(satelliteCard(), Date.parse(RISE) - 1000)).toBe(false);
  });
});
