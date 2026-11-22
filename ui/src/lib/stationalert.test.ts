import { describe, expect, it } from "vitest";
import { clockText } from "@/lib/format";
import { alertSummary, canAlert, firedLine, firedText } from "@/lib/stationalert";
import { takeUnits } from "@/lib/units";
import { station } from "@/test/fixtures";

const at = "2026-10-21T12:03:00Z";

describe("the alerts set on stations", () => {
  it("are for a station heard, not for us, our objects or an object", () => {
    expect(canAlert(station("OH2RDG"))).toBe(true);
    expect([
      canAlert(station("OH2GBA", { is_me: true })),
      canAlert(station("LEADER", { kind: "object", own: true })),
      canAlert(station("STORM", { kind: "item" })),
    ]).toEqual([false, false, false]);
  });

  it("say what they watch in a few words, in the order of the box", () => {
    expect(alertSummary({ on_air: true, within_km: 25, direct: true })).toBe("on the air, within 25 km, heard direct");
    expect(alertSummary({ on_air: false, within_km: null, direct: true })).toBe("heard direct");
  });

  it("say what happened in the page's words, with the time of the packet for the toast", () => {
    expect(firedText({ call: "OH2XYZ", kind: "on_air", km: null })).toBe("OH2XYZ is on the air");
    expect(firedText({ call: "OH2XYZ", kind: "within", km: 8.24 })).toBe("OH2XYZ is 8.2 km from you");
    expect(firedText({ call: "OH2XYZ", kind: "within", km: 42 })).toBe("OH2XYZ is 42 km from you");
    expect(firedLine({ type: "station_alert", call: "OH2XYZ", kind: "direct", at, km: null })).toBe(
      `${clockText(at).slice(0, 5)} OH2XYZ is heard direct`,
    );
  });
});

describe("an alert in the non-metric units", () => {
  it("says how far the station is in miles, and the distance typed for the alert as typed", () => {
    takeUnits({ "units/non_metric": "true" });
    expect(firedText({ call: "OH2XYZ", kind: "within", km: 8.24 })).toBe("OH2XYZ is 5.1 mi from you");
    expect(firedText({ call: "OH2XYZ", kind: "within", km: 42 })).toBe("OH2XYZ is 26 mi from you");
    expect(alertSummary({ on_air: false, within_km: 25, direct: false })).toBe("within 25 km");
  });
});
