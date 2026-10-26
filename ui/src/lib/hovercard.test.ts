import { describe, expect, it } from "vitest";
import { hoverRows } from "@/lib/hovercard";
import { NOW, ago, station, weather } from "@/test/fixtures";

describe("hoverRows", () => {
  it("has when it was heard, how far and which way, and the route", () => {
    const rows = hoverRows(station("OH2PU-9", { last_heard: ago(120), distance_km: 12.4, bearing_deg: 45, last_route: "via OH2RCH-2" }), NOW);
    expect(rows).toEqual([
      { label: "Heard", text: "2 min ago" },
      { label: "From us", text: "12 km, 45° NE" },
      { label: "Route", text: "via OH2RCH-2" },
    ]);
  });

  it("says how a station was heard when that is more than the radio alone: the internet, an iGate, or both", () => {
    const labelled = (extra: Parameters<typeof station>[1]) => hoverRows(station("OH2PU-9", extra), NOW).find((r) => r.label === "Heard on")?.text;
    expect(labelled({})).toBeUndefined();
    expect(labelled({ heard_is: 2 })).toBe("RF · Internet");
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
