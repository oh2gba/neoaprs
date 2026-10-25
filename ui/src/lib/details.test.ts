import { describe, expect, it } from "vitest";
import { extensionRows, frequencyText, locatorText, sentTimeText, stormText, telemetryBitsText, telemetryText } from "@/lib/details";
import { packet } from "@/test/fixtures";
import type { ExtensionValues, FrequencyValues, PacketRow, StormValues, TelemetryValues } from "@/protocol/protocol";

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
      { label: "PHG", text: "25 W, 6 m, 3 dB, range 13 km", direction: { deg: 90, title: "E, 90°" } },
      { label: "Range", text: "81 km" },
      { label: "DF signal", text: "S2, 24 m, 6 dB", direction: { deg: null, title: "omni" } },
      { label: "DF bearing", text: "270°, range 6 km, quality 9, hits 7" },
      { label: "Area", text: "cyan filled ellipse, 1° down, 0.25° right" },
    ]);
  });
});

const frequency = (extra: Partial<FrequencyValues> = {}): FrequencyValues => ({
  mhz: 145.775,
  tone_hz: null,
  tone_both: false,
  tone_off: false,
  dcs: null,
  tone_burst: false,
  narrow: false,
  offset_khz: null,
  range_km: null,
  rx_mhz: null,
  ...extra,
});

describe("frequencyText", () => {
  it("is the frequency alone when that is all the sender said", () => {
    expect(frequencyText(frequency({ mhz: 146.52 }))).toBe("146.520 MHz");
  });
  it("adds the tone, the offset and the range in the order they are heard", () => {
    expect(frequencyText(frequency({ tone_hz: 118, offset_khz: -600, range_km: 40.2 }))).toBe("145.775 MHz, tone 118 Hz, -600 kHz, range 40 km");
    expect(frequencyText(frequency({ tone_hz: 107, tone_both: true, offset_khz: 5000, narrow: true }))).toBe(
      "145.775 MHz, tone 107 Hz both ways, narrow FM, +5000 kHz",
    );
  });
  it("says simplex for an offset of nothing and tells a DCS code, no tone, a tone burst and a receive frequency", () => {
    expect(frequencyText(frequency({ dcs: "023", offset_khz: 0, rx_mhz: 430.1 }))).toBe("145.775 MHz, DCS 023, simplex, receive 430.100 MHz");
    expect(frequencyText(frequency({ tone_off: true }))).toBe("145.775 MHz, no tone");
    expect(frequencyText(frequency({ tone_burst: true }))).toBe("145.775 MHz, 1750 Hz tone burst");
  });
});

describe("stormText", () => {
  const storm: StormValues = {
    storm_type: "HC",
    wind_kmh: 277.8,
    gust_kmh: 370.4,
    pressure_hpa: 980,
    hurricane_radius_km: 166.7,
    storm_radius_km: 55.6,
    gale_radius_km: null,
  };
  it("says the type, the winds, the pressure and the radii of the winds in kilometres, and leaves out what was not sent", () => {
    expect(stormText(storm)).toBe(
      "Hurricane, wind 278 km/h, gusts 370 km/h, pressure 980 hPa, hurricane winds out to 167 km, tropical storm winds out to 56 km",
    );
    expect(
      stormText({ ...storm, storm_type: "TD", wind_kmh: null, gust_kmh: null, pressure_hpa: null, hurricane_radius_km: null, storm_radius_km: null }),
    ).toBe("Tropical depression");
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
