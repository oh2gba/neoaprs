import { describe, expect, it } from "vitest";
import { beaconBlock } from "@/lib/beaconstatus";
import { NOW, ago, gpsOff, gpsState, status } from "@/test/fixtures";

const later = (seconds: number) => new Date(NOW + seconds * 1000).toISOString();
const timed = (extra = {}) => status({ beacon_interval_min: 60, beacon_last_sent: ago(240), beacon_next_due: later(56 * 60), ...extra });
const GPSD = { "gps/source": "gpsd", "gps/host": "127.0.0.1:2947" };

describe("beaconBlock of a fixed station", () => {
  it("says when the last beacon went and when the timer sends the next, with the pill on", () => {
    const block = beaconBlock(timed(), gpsOff(), {}, NOW);
    expect(block).toMatchObject({ moving: false, label: "Beacon", pill: { text: "on", tone: "beacon-on" }, smart: null, problem: "" });
    expect(block.line).toBe("Last beacon 4 min ago · next in 56 min (every 60 min)");
    expect(block.hover).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
  });

  it("says no timed beacon, with the pill off, when the daemon has no next time", () => {
    for (const extra of [{ beacon_interval_min: 0, beacon_next_due: null }, { beacon_next_due: null }]) {
      const block = beaconBlock(timed(extra), null, {}, NOW);
      expect(block.pill).toEqual({ text: "off", tone: "beacon-off" });
      expect(block.line).toBe("Last beacon 4 min ago · no timed beacon");
    }
  });

  it("says Beacon off, with the pill off, while the interval of the settings is 0, whatever the daemon last said", () => {
    for (const interval of ["0", ""]) {
      const block = beaconBlock(timed(), gpsOff(), { "beacon/interval_min": interval }, NOW);
      expect(block).toEqual({
        moving: false,
        label: "Beacon",
        pill: { text: "off", tone: "beacon-off" },
        line: "Beacon off",
        hover: undefined,
        smart: null,
        problem: "",
      });
    }
    expect(beaconBlock(null, null, { "beacon/interval_min": "0" }, NOW)).toMatchObject({ pill: { text: "off", tone: "beacon-off" }, line: "Beacon off" });
    expect(beaconBlock(timed(), gpsOff(), { "beacon/interval_min": "60" }, NOW).pill).toEqual({ text: "on", tone: "beacon-on" });
  });

  it("says none was sent yet, with the timer or without", () => {
    expect(beaconBlock(timed({ beacon_last_sent: null }), null, {}, NOW)).toMatchObject({
      line: "No beacon sent yet · next in 56 min (every 60 min)",
      hover: undefined,
    });
    expect(beaconBlock(status(), null, {}, NOW).line).toBe("No beacon sent yet · no timed beacon");
  });

  it("is a time that has come: next now", () => {
    expect(beaconBlock(timed({ beacon_next_due: ago(3) }), null, {}, NOW).line).toBe("Last beacon 4 min ago · next now (every 60 min)");
  });

  it("has no pill and says no word before the daemon has told", () => {
    expect(beaconBlock(null, null, {}, NOW)).toMatchObject({ moving: false, pill: null, line: "No word from the daemon yet.", hover: undefined });
  });
});

describe("beaconBlock of a moving station", () => {
  it("is the GPS: its state on the pill, the fix, and the SmartBeaconing line", () => {
    const gps = gpsState({ next_beacon_at: later(42), last_beacon_at: ago(12), last_beacon_reason: "turn" });
    const block = beaconBlock(timed(), gps, GPSD, NOW);
    expect(block).toMatchObject({ moving: true, label: "GPS", pill: { text: "fix", tone: "gps-fix" }, problem: "", hover: undefined });
    expect(block.line).toBe("Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago");
    expect(block.smart).toBe("SmartBeaconing: next timed beacon in 42 s, last sent 12 s ago (turn)");
  });

  it("says no beacon without a fix and gives the problem of the daemon", () => {
    const gps = gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "the receiver has no position fix yet" });
    expect(beaconBlock(null, gps, GPSD, NOW)).toMatchObject({
      pill: { text: "no fix", tone: "gps-no_fix" },
      line: "No fix yet",
      smart: "No beacon: no GPS fix",
      problem: "the receiver has no position fix yet",
    });
  });

  it("says what it is connecting to, from the settings", () => {
    const gps = gpsState({ state: "connecting", lat: null, lon: null, fix_at: null });
    expect(beaconBlock(null, gps, GPSD, NOW).line).toBe("Connecting to gpsd at 127.0.0.1:2947");
    expect(beaconBlock(null, { ...gps, source: "serial" }, { "gps/source": "serial", "gps/device": "/dev/ttyUSB1", "gps/baud": "4800" }, NOW).line).toBe(
      "Opening /dev/ttyUSB1 at 4800 baud",
    );
  });

  it("keeps showing the GPS while the interval of the settings is 0, so that the fix can be watched, and says Beacon off on the line under it", () => {
    const off = { ...GPSD, "beacon/interval_min": "0" };
    expect(beaconBlock(timed(), gpsState({ next_beacon_at: later(42), last_beacon_at: ago(12), last_beacon_reason: "turn" }), off, NOW)).toEqual({
      moving: true,
      label: "GPS",
      pill: { text: "fix", tone: "gps-fix" },
      line: "Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago",
      hover: undefined,
      smart: "Beacon off",
      problem: "",
    });
    expect(beaconBlock(timed(), gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "no satellites" }), off, NOW)).toMatchObject({
      pill: { text: "no fix", tone: "gps-no_fix" },
      line: "No fix yet",
      smart: "Beacon off",
      problem: "no satellites",
    });
    expect(beaconBlock(null, null, off, NOW)).toMatchObject({
      moving: true,
      label: "GPS",
      pill: null,
      line: "No word from the daemon yet.",
      smart: "Beacon off",
    });
    const on = beaconBlock(timed(), gpsState(), { ...GPSD, "beacon/interval_min": "30" }, NOW);
    expect(on).toMatchObject({ label: "GPS", pill: { text: "fix" } });
    expect(on.smart).not.toBe("Beacon off");
  });

  it("is the same block as it was for a fixed station that is Off", () => {
    expect(beaconBlock(timed(), gpsOff(), { "beacon/interval_min": "0" }, NOW)).toEqual({
      moving: false,
      label: "Beacon",
      pill: { text: "off", tone: "beacon-off" },
      line: "Beacon off",
      hover: undefined,
      smart: null,
      problem: "",
    });
  });

  it("goes by what the daemon says the beacon does, and by the settings before it has said", () => {
    expect(beaconBlock(timed(), gpsState({ mobile: false }), GPSD, NOW).moving).toBe(false);
    expect(beaconBlock(timed(), gpsOff(), GPSD, NOW).moving).toBe(false);
    expect(beaconBlock(timed(), null, GPSD, NOW)).toMatchObject({ moving: true, label: "GPS", pill: null, line: "No word from the daemon yet.", smart: null });
  });
});
