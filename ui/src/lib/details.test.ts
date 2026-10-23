import { describe, expect, it } from "vitest";
import { extensionRows, locatorText, sentTimeText, telemetryBitsText, telemetryText } from "@/lib/details";
import { packet } from "@/test/fixtures";
import type { ExtensionValues, PacketRow, TelemetryValues } from "@/protocol/protocol";

const none: ExtensionValues = { phg: null, range_km: null, dfs: null, df_bearing: null, area: null };

describe("extensionRows", () => {
  it("has a row for each extension and none for a position without", () => {
    expect(extensionRows(null)).toEqual([]);
    expect(extensionRows(none)).toEqual([]);
    const rows = extensionRows({
      phg: { power_w: 25, height_m: 6.1, gain_db: 3, direction_deg: 90, range_km: 12.8 },
      range_km: 80.5,
      dfs: { strength: 2, height_m: 24.4, gain_db: 6, direction_deg: null },
      df_bearing: { bearing_deg: 270, hits: 7, range_km: 6.4, quality: 9 },
      area: { shape: "filled ellipse", colour: "cyan", lat_offset_deg: 1, lon_offset_deg: 0.25 },
    });
    expect(rows).toEqual([
      { label: "PHG", text: "25 W, 6 m, 3 dB, 90°, range 13 km" },
      { label: "Range", text: "81 km" },
      { label: "DF signal", text: "S2, 24 m, 6 dB, omni" },
      { label: "DF bearing", text: "270°, range 6 km, quality 9, hits 7" },
      { label: "Area", text: "cyan filled ellipse, 1° down, 0.25° right" },
    ]);
  });
});

describe("locatorText", () => {
  it("gives the grid and the centre of the square", () => {
    expect(locatorText({ grid: "IO91sx", lat: 51.97917, lon: -0.45833, symbol_table: "/", symbol_code: "-" })).toBe("IO91sx, 51.97917 N 0.45833 W");
    expect(locatorText(null)).toBe("-");
  });
});

const telemetry: TelemetryValues = {
  sequence: 5,
  channels: [
    { name: "Battery", unit: "v/100", raw: 199, value: 1034.8 },
    { name: "A2", unit: "", raw: 0, value: 0.456 },
  ],
  bits: [
    { name: "Camra", on: true },
    { name: "B2", on: false },
  ],
  project: "",
  comment: "",
};

describe("telemetry", () => {
  it("writes the channels with their names and units, and the bits on or off", () => {
    expect(telemetryText(telemetry)).toBe("#5: Battery 1034.8 v/100, A2 0.46");
    expect(telemetryText({ ...telemetry, sequence: null })).toBe("Battery 1034.8 v/100, A2 0.46");
    expect(telemetryBitsText(telemetry)).toBe("Camra on, B2 off");
    expect(telemetryText(null)).toBe("-");
    expect(telemetryBitsText(null)).toBe("-");
  });
});

describe("sentTimeText", () => {
  const position = (extra: object): PacketRow => {
    const row = packet(1);
    return { ...row, decoded: { ...row.decoded, ...extra } };
  };
  it("says local for a time the sender gave in its local clock, as it was sent", () => {
    expect(sentTimeText(position({ timestamp: "2026-10-09T23:45:00.000000Z", timestamp_local: true }))).toBe("09 23:45 local");
  });
  it("gives a zulu time in the viewer's time and nothing for a packet without a time", () => {
    expect(sentTimeText(position({ timestamp: "2026-10-09T23:45:00.000000Z" }))).toMatch(/^2026-10-\d\d \d\d:\d\d:00$/);
    expect(sentTimeText(packet(1))).toBeNull();
    expect(sentTimeText({ ...packet(1), decoded: { type: "undecoded", error: "x", text: "" } })).toBeNull();
  });
  it("reads the time of an object and its local flag from the position inside", () => {
    const row = packet(1);
    const inner = row.decoded as PacketRow["decoded"] & { type: "position" };
    const object = {
      ...row,
      decoded: { type: "object", name: "X", alive: true, position: { ...inner, timestamp_local: true }, timestamp: "2026-10-09T23:45:00.000000Z" },
    } as PacketRow;
    expect(sentTimeText(object)).toBe("09 23:45 local");
  });
});
