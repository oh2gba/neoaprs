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
  const labels = (nowMs: number, card = satelliteCard()) => satelliteRows(card, nowMs).map((row) => row.label);
  const SET_MS = Date.parse("2026-11-28T12:13:06Z");

  it("while it is up: the pass, the time left, the elevation and the Doppler now, then the frequencies", () => {
    const rows = text(satelliteRows(satelliteCard(), DURING + 2500));
    expect(rows.slice(1, 7)).toEqual([
      ["Duration", "10 min"],
      ["Set", expect.stringMatching(/^\d\d:\d\d$/)],
      ["Highest", "15°"],
      ["Time left", "9 min"],
      ["Elevation", "4°"],
      ["Doppler", "+8.4 kHz"],
    ]);
    expect(rows.map(([label]) => label)).toEqual([
      "Rise",
      "Duration",
      "Set",
      "Highest",
      "Time left",
      "Elevation",
      "Doppler",
      "Downlink",
      "Uplink",
      "Mode",
      "Altitude",
    ]);
    expect(rows.at(-3)).toEqual(["Uplink", "437.825 MHz"]);
    expect(rows.at(-2)).toEqual(["Mode", "AFSK 1200"]);
    expect(rows.at(-1)).toEqual(["Altitude", "420 km"]);
  });

  it("has the same rows before, during and after the pass, a dash where a value does not apply", () => {
    const before = Date.parse(RISE) - 60_000;
    expect(labels(before)).toEqual(labels(DURING));
    expect(labels(SET_MS + 1000)).toEqual(labels(DURING));
    const ahead = text(satelliteRows(satelliteCard(), before));
    expect(ahead.slice(4, 7)).toEqual([
      ["Time left", "–"],
      ["Elevation", "–"],
      ["Doppler", "–"],
    ]);
  });

  it("does not show a pass that has ended as the next one, in the rows or the table to tune", () => {
    const over = text(satelliteRows(satelliteCard(), SET_MS));
    expect(over.slice(0, 7).map(([, value]) => value)).toEqual(["–", "–", "–", "–", "–", "–", "–"]);
    expect(tuneRows(satelliteCard(), SET_MS)).toEqual([
      { label: "Downlink", cells: ["–", "–", "–"] },
      { label: "Uplink", cells: ["–", "–", "–"] },
    ]);
  });

  it("numbers the downlinks, their Doppler and the uplinks when there are several", () => {
    const two = satelliteCard({
      downlinks: [
        { hz: 145825000, rise_hz: 145828000, max_hz: 145825000, set_hz: 145822000 },
        { hz: 437825000, rise_hz: 437833777, max_hz: 437825004, set_hz: 437816223 },
      ],
      looks: [
        { at: "2026-11-28T12:05:00Z", el_deg: 4.0, down_hz: [2800, 8400], up_hz: [-8400] },
        { at: "2026-11-28T12:05:05Z", el_deg: 4.5, down_hz: [2700, 8300], up_hz: [-8300] },
      ],
    });
    const rows = text(satelliteRows(two, DURING));
    expect(rows.filter(([label]) => label.startsWith("Doppler"))).toEqual([
      ["Doppler 1", "+2.8 kHz"],
      ["Doppler 2", "+8.4 kHz"],
    ]);
    expect(rows.filter(([label]) => label.startsWith("Downlink"))).toEqual([
      ["Downlink 1", "145.825 MHz"],
      ["Downlink 2", "437.825 MHz"],
    ]);
    expect(rows.filter(([label]) => label.startsWith("Uplink"))).toEqual([["Uplink", "437.825 MHz"]]);
    expect(tuneRows(two, DURING).map((row) => row.label)).toEqual(["Downlink 1", "Downlink 2", "Uplink"]);
    expect(satelliteLabels()).toEqual(expect.arrayContaining(["Downlink 2", "Doppler 2", "Uplink 2"]));
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
    expect(tuneRows(card, DURING)).toEqual([]);
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
    expect(tuneRows(satelliteCard(), DURING)).toEqual([
      { label: "Downlink", cells: ["437.834", "437.825", "437.816"] },
      { label: "Uplink", cells: ["437.816", "437.825", "437.834"] },
    ]);
  });

  it("is up between the rise and the set", () => {
    expect(isUp(satelliteCard(), DURING)).toBe(true);
    expect(isUp(satelliteCard(), Date.parse(RISE) - 1000)).toBe(false);
  });
});
