import { describe, expect, it } from "vitest";
import { hoverRows } from "@/lib/hovercard";
import { pageRadios } from "@/lib/radios";
import type { RadioRow, StationRow } from "@/protocol/protocol";
import { ago, heardBy, NOW, radioRow, radiosTopic, station, weather } from "@/test/fixtures";

describe("hoverRows", () => {
  it("has when it was heard, how far and which way, and the route", () => {
    const rows = hoverRows(station("OH2PU-9", { last_heard: ago(120), distance_km: 12.4, bearing_deg: 45, last_route: "via OH2RCH-2" }), NOW);
    expect(rows).toEqual([
      { label: "Heard", text: "2 min ago" },
      { label: "From us", text: "12 km, 45° NE" },
      { label: "Route", text: "via OH2RCH-2" },
    ]);
  });

  it("says how a station was heard when that is more than the one radio alone: the internet, an iGate, or both, the radio by its name", () => {
    const one = (row: RadioRow) => ({ all: { value: pageRadios(radiosTopic(row), null) } });
    const labelled = (extra: Parameters<typeof station>[1], radio = radioRow(1, "kenwood-tnc2")) =>
      hoverRows(station("OH2PU-9", extra), NOW, one(radio)).find((r) => r.label === "Heard on")?.text;
    expect(labelled({})).toBeUndefined();
    // An HF radio alone, treated as an FM one: every station was heard on it.
    expect(labelled({}, radioRow(1, "mercury"))).toBeUndefined();
    expect(labelled({ heard_is: 2 })).toBe("FM · Internet");
    expect(labelled({ heard_is: 2 }, radioRow(1, "kenwood-tnc2", { name: "2 m" }))).toBe("2 m · Internet");
    expect(labelled({ heard_rf: 0, heard_rf_gated: 1 })).toBe("iGate");
    expect(labelled({ heard_rf: 0, heard_is: 2, last_rf_at: null })).toBe("Received over the internet (APRS-IS), not on the radio");
  });

  it("adds the status, the comment and the temperature of a weather station when there are any", () => {
    const rows = hoverRows(station("OH2MUI", { last_status: "On the roof", last_comment: "Davis", weather: weather({ temp_c: 10 }) }), NOW);
    expect(rows.map((r) => r.label)).toEqual(["Heard", "Status", "Comment", "From us", "Temperature", "Route"]);
    expect(rows.find((r) => r.label === "Temperature")?.text).toBe("10.0 °C");
  });

  it("says heard direct for a station that came direct, and has no temperature for weather without one", () => {
    const rows = hoverRows(station("OH2NEAR", { last_route: "direct", weather: weather({ temp_c: null }) }), NOW);
    expect(rows.find((r) => r.label === "Route")?.text).toBe("heard direct");
    expect(rows.some((r) => r.label === "Temperature")).toBe(false);
  });

  it("leaves out a distance and a route that are not there, and the route of our own station", () => {
    const none = hoverRows(station("X", { distance_km: null, bearing_deg: null, last_route: "" }), NOW);
    expect(none.map((r) => r.label)).toEqual(["Heard"]);
    expect(hoverRows(station("OH2GBA", { is_me: true, last_route: "direct" }), NOW).some((r) => r.label === "Route")).toBe(false);
  });
});

describe("hoverRows with several radios", () => {
  const radiosOf = (...rows: RadioRow[]) => ({ all: { value: pageRadios(radiosTopic(...rows), null) } });
  const SIX = radiosOf(
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "dummy-hf", { name: "20 m", number: 2 }),
    radioRow(5, "kantronics", { number: 3 }),
    radioRow(6, "dummy", { number: 4 }),
  );
  const heardOn = (row: StationRow, radios: Parameters<typeof hoverRows>[2]) => hoverRows(row, NOW, radios).find((r) => r.label === "Heard on")?.text;

  it("lists every radio that heard the station with its time, then the internet", () => {
    const row = station("OH2SIX", {
      heard_rf: 4,
      heard_is: 1,
      last_is_at: ago(20),
      heard: { "1": { count: 1, last_at: ago(600) }, "4": { count: 3, last_at: ago(30) } },
    });
    expect(heardOn(row, SIX)).toBe("FM: 10 min ago · 20 m: 30 s ago · Internet: 20 s ago");
  });

  it("says FM and Mercury with their times for the two radios of the owner, and the words of today for the one radio", () => {
    const both = station("OH2FMHF", { heard_rf: 5, heard: heardBy([1, 3, ago(180)], [2, 2, ago(60)]) });
    const two = radiosOf(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"));
    expect(heardOn(both, two)).toBe("FM 3 min ago · Mercury 1 min ago");
    expect(heardOn(station("OH2RF"), two)).toBe("FM 1 min ago");
  });
});
