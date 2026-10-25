import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { gpsProblem, gpsStateText, gpsStatus, hasFix, isMoving, mobileBeaconText, reasonText } from "@/lib/gpsstatus";
import { NOW, ago, gpsOff, gpsState } from "@/test/fixtures";

const later = (seconds: number): string => new Date(NOW + seconds * 1000).toISOString();
const values = { "gps/host": "127.0.0.1:2947", "gps/device": "/dev/ttyUSB1", "gps/baud": "9600" };

afterEach(() => setLocale("en"));

describe("gpsStatus", () => {
  it("says Off while there is no source", () => {
    expect(gpsStatus(gpsOff(), values, NOW)).toBe("Off");
    expect(gpsStateText("off")).toBe("off");
  });

  it("says what it is connecting to: the gpsd address, or the port and speed of the receiver", () => {
    expect(gpsStatus(gpsState({ state: "connecting", lat: null, lon: null }), values, NOW)).toBe("Connecting to gpsd at 127.0.0.1:2947");
    expect(gpsStatus(gpsState({ source: "serial", state: "connecting", lat: null, lon: null }), values, NOW)).toBe("Opening /dev/ttyUSB1 at 9600 baud");
    expect(gpsStatus(gpsState({ state: "connecting" }), {}, NOW)).toBe("Connecting…");
  });

  it("says there is no fix yet", () => {
    expect(gpsStatus(gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null }), values, NOW)).toBe("No fix yet");
  });

  it("gives the fix with its place, speed, course, altitude, satellites and age", () => {
    expect(gpsStatus(gpsState(), values, NOW)).toBe("Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago");
  });

  it("leaves out what the receiver did not give, and writes the south and the west", () => {
    expect(gpsStatus(gpsState({ speed_kmh: null, course_deg: null, altitude_m: null, satellites: null }), values, NOW)).toBe(
      "Fix: 60.4295 N 24.1452 E, 2 s ago",
    );
    expect(gpsStatus(gpsState({ lat: -33.8688, lon: -70.5, satellites: 1, course_deg: 0 }), values, NOW)).toBe(
      "Fix: 33.8688 S 70.5000 W, 48 km/h, course 0°, 103 m, 1 satellite, 2 s ago",
    );
  });

  it("says a fix that is old was lost, and when", () => {
    const stale = gpsState({ state: "stale", fix_at: ago(180), problem: "the latest fix is 180 s old" });
    expect(gpsStatus(stale, values, NOW)).toBe("Fix lost 3 min ago (stale)");
  });

  it("says the state with a word for the pill", () => {
    expect(["off", "connecting", "no_fix", "fix", "stale"].map((s) => gpsStateText(s as never))).toEqual(["off", "connecting", "no fix", "fix", "stale"]);
  });

  it("is written in the language of the page", () => {
    setLocale("de");
    expect(gpsStatus(gpsState(), values, NOW)).toBe("Fix: 60,4295 N 24,1452 E, 48 km/h, Kurs 215°, 103 m, 9 Satelliten, vor 2 s");
  });
});

describe("gpsProblem", () => {
  it("gives the daemon's line while there is no fix, and not for a fix or for an old one, which the line says", () => {
    expect(gpsProblem(gpsState({ state: "connecting", problem: "Connection refused" }))).toBe("Connection refused");
    expect(gpsProblem(gpsState({ state: "no_fix", problem: "the receiver has no position fix yet" }))).toBe("the receiver has no position fix yet");
    expect(gpsProblem(gpsState({ state: "stale", problem: "the latest fix is 180 s old" }))).toBe("");
    expect(gpsProblem(gpsState())).toBe("");
  });
});

describe("isMoving", () => {
  it("is a station whose position is a GPS's: gpsd or a serial port, and not Fixed", () => {
    expect(isMoving({ "gps/source": "gpsd" })).toBe(true);
    expect(isMoving({ "gps/source": "serial" })).toBe(true);
    expect(isMoving({ "gps/source": "off" })).toBe(false);
    expect(isMoving({ "gps/source": "" })).toBe(false);
    expect(isMoving({})).toBe(false);
  });
});

describe("mobileBeaconText", () => {
  it("is nothing for a fixed station, or before the daemon has told", () => {
    expect(mobileBeaconText(gpsState({ mobile: false, next_beacon_at: later(42) }), NOW)).toBeNull();
    expect(mobileBeaconText(null, NOW)).toBeNull();
  });

  it("says there is no beacon without a fix", () => {
    for (const state of ["off", "connecting", "no_fix", "stale"] as const)
      expect(mobileBeaconText(gpsState({ mobile: true, state }), NOW), state).toBe("No beacon: no GPS fix");
  });

  it("says when SmartBeaconing sends next by time", () => {
    expect(mobileBeaconText(gpsState({ mobile: true, next_beacon_at: later(42) }), NOW)).toBe("SmartBeaconing: next by time in 42 s");
    expect(mobileBeaconText(gpsState({ mobile: true, next_beacon_at: ago(1) }), NOW)).toBe("SmartBeaconing: next by time now");
  });

  it("adds when the last one went and why", () => {
    const gps = gpsState({ mobile: true, next_beacon_at: later(42), last_beacon_at: ago(12), last_beacon_reason: "turn" });
    expect(mobileBeaconText(gps, NOW)).toBe("SmartBeaconing: next by time in 42 s, last sent 12 s ago (turn)");
  });

  it("says the last one alone when no time is due, and that the first goes with the first fix", () => {
    expect(mobileBeaconText(gpsState({ mobile: true, last_beacon_at: ago(12), last_beacon_reason: "request" }), NOW)).toBe(
      "SmartBeaconing: last sent 12 s ago (Beacon now)",
    );
    expect(mobileBeaconText(gpsState({ mobile: true }), NOW)).toBe("SmartBeaconing: the first beacon goes now");
  });

  it("names the reasons", () => {
    expect(["start", "time", "turn", "request", ""].map((r) => reasonText(r as never))).toEqual(["first fix", "time", "turn", "Beacon now", "-"]);
  });
});

describe("hasFix", () => {
  it("is a fresh fix with a place", () => {
    expect(hasFix(gpsState())).toBe(true);
    expect(hasFix(gpsState({ state: "stale" }))).toBe(false);
    expect(hasFix(gpsState({ lat: null }))).toBe(false);
    expect(hasFix(null)).toBe(false);
  });
});
