import { describe, expect, it } from "vitest";
import { beaconBlock, beaconRadios, notConnectedWhy, pathKey, pathRows, radioValueOf, sendOnTicks, type BeaconRadio } from "@/lib/beaconstatus";
import { dateTimeText } from "@/lib/format";
import { pageRadio, type PageRadio } from "@/lib/radios";
import type { RadioRow } from "@/protocol/protocol";
import { NOW, ago, configValues, gpsOff, gpsState, radioRow, status } from "@/test/fixtures";

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

  it("says Beacon off, with the state off, while the interval of the settings is 0, whatever the daemon last said", () => {
    for (const interval of ["0", ""]) {
      const block = beaconBlock(timed(), gpsOff(), { "beacon/interval_min": interval }, NOW);
      expect(block).toEqual({
        moving: false,
        label: "Beacon",
        pill: { text: "off", tone: "beacon-off" },
        line: "No automatic beacon · Beacon now still sends",
        hover: undefined,
        radios: [],
        smart: null,
        problem: "",
      });
    }
    expect(beaconBlock(null, null, { "beacon/interval_min": "0" }, NOW)).toMatchObject({
      pill: { text: "off" },
      line: "No automatic beacon · Beacon now still sends",
    });
    expect(beaconBlock(timed(), gpsOff(), { "beacon/interval_min": "60" }, NOW).pill).toEqual({ text: "on", tone: "beacon-on" });
  });

  it("is off in the warn colour with RX only: nothing is sent in RX only, with or without a timer or a GPS", () => {
    const rx = { "station/transmit": "false" };
    expect(beaconBlock(timed(), gpsOff(), rx, NOW)).toMatchObject({
      pill: { text: "off", tone: "tnc-waiting" },
      line: "RX only: nothing is sent",
      smart: null,
    });
    expect(beaconBlock(timed(), gpsOff(), { ...rx, "beacon/interval_min": "0" }, NOW).line).toBe("RX only: nothing is sent");
    expect(beaconBlock(timed(), gpsState(), { ...rx, ...GPSD }, NOW)).toMatchObject({ pill: { tone: "gps-fix" }, smart: "RX only: nothing is sent" });
  });

  it("says none was sent yet, with the timer or without", () => {
    expect(beaconBlock(timed({ beacon_last_sent: null }), null, {}, NOW)).toMatchObject({
      line: "No beacon sent yet · next in 56 min (every 60 min)",
      hover: undefined,
      radios: [],
    });
    expect(beaconBlock(status(), null, {}, NOW).line).toBe("No beacon sent yet · no timed beacon");
  });

  it("is a time that has come: next now", () => {
    expect(beaconBlock(timed({ beacon_next_due: ago(3) }), null, {}, NOW).line).toBe("Last beacon 4 min ago · next now (every 60 min)");
  });

  it("has no pill and says no word before the daemon has told", () => {
    expect(beaconBlock(null, null, {}, NOW)).toMatchObject({ moving: false, pill: null, line: "No word from NeoAPRS yet.", hover: undefined });
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
      radios: [],
      smart: "No automatic beacon · Beacon now still sends",
      problem: "",
    });
    expect(beaconBlock(timed(), gpsState({ state: "no_fix", lat: null, lon: null, fix_at: null, problem: "no satellites" }), off, NOW)).toMatchObject({
      pill: { text: "no fix", tone: "gps-no_fix" },
      line: "No fix yet",
      smart: "No automatic beacon · Beacon now still sends",
      problem: "no satellites",
    });
    expect(beaconBlock(null, null, off, NOW)).toMatchObject({
      moving: true,
      label: "GPS",
      pill: null,
      line: "No word from NeoAPRS yet.",
      smart: "No automatic beacon · Beacon now still sends",
    });
    const on = beaconBlock(timed(), gpsState(), { ...GPSD, "beacon/interval_min": "30" }, NOW);
    expect(on).toMatchObject({ label: "GPS", pill: { text: "fix" } });
    expect(on.smart).not.toBe("No automatic beacon · Beacon now still sends");
  });

  it("is the same block as it was for a fixed station that is Off", () => {
    expect(beaconBlock(timed(), gpsOff(), { "beacon/interval_min": "0" }, NOW)).toEqual({
      moving: false,
      label: "Beacon",
      pill: { text: "off", tone: "beacon-off" },
      line: "No automatic beacon · Beacon now still sends",
      hover: undefined,
      radios: [],
      smart: null,
      problem: "",
    });
  });

  it("goes by what the daemon says the beacon does, and by the settings before it has said", () => {
    expect(beaconBlock(timed(), gpsState({ mobile: false }), GPSD, NOW).moving).toBe(false);
    expect(beaconBlock(timed(), gpsOff(), GPSD, NOW).moving).toBe(false);
    expect(beaconBlock(timed(), null, GPSD, NOW)).toMatchObject({ moving: true, label: "GPS", pill: null, line: "No word from NeoAPRS yet.", smart: null });
  });
});

describe("beaconBlock with several radios", () => {
  // (plan 6a: "each radio's line behind the status arrow shows its own interval"; the lines are each radio's own timer, its row of the topic `radios`, by the radio's name)
  const beacon = (last: string | null, next: string | null, interval = 30): BeaconRadio["beacon"] => ({
    last_sent: last,
    next_due: next,
    interval_min: interval,
    problem: null,
  });
  const two = (extra = {}) => status({ beacon_interval_min: 20, beacon_last_sent: ago(240), beacon_next_due: later(16 * 60), ...extra });
  const radios = (hf = beacon(ago(120), later(29 * 60))): BeaconRadio[] => [
    { name: "FM", beacon: beacon(ago(240), later(16 * 60), 20), smart: true },
    { name: "HF", beacon: hf, smart: false },
  ];

  it("takes the latest beacon of any radio and the next due of any radio for the row's line, and a line for each radio behind its arrow with its own interval", () => {
    const block = beaconBlock(two(), gpsOff(), {}, NOW, radios());
    expect(block.line).toBe("Last beacon 2 min ago · next in 16 min (every 20 min)");
    expect(block.radios).toEqual(["FM: last beacon 4 min ago · next in 16 min (every 20 min)", "HF: last beacon 2 min ago · next in 29 min (every 30 min)"]);
    expect(block.hover).toBe(dateTimeText(ago(120)));
  });

  it("says a radio that has sent nothing yet, and one with no timed beacon, in its own line, by the name the radio has", () => {
    expect(beaconBlock(two(), gpsOff(), {}, NOW, radios(beacon(null, null, 0))).radios).toEqual([
      "FM: last beacon 4 min ago · next in 16 min (every 20 min)",
      "HF: no beacon sent yet · no timed beacon",
    ]);
    expect(beaconBlock(two(), gpsOff(), {}, NOW, radios(beacon(ago(600), null, 30))).radios[1]).toBe("HF: last beacon 10 min ago · no timed beacon");
    const named = [{ name: "20 m", beacon: beacon(null, later(5 * 60), 30), smart: false }, ...radios()];
    expect(beaconBlock(two(), gpsOff(), {}, NOW, named).radios[0]).toBe("20 m: no beacon sent yet · next in 5 min (every 30 min)");
  });

  it("goes by the radios' timers and not by the status's, for any number of radios", () => {
    const six = ["FM", "HF", "LoRa", "Mobile12", "20 m", "FM 2"].map((name, i) => ({
      name,
      beacon: beacon(ago(60 * (i + 3)), later(60 * (i + 10)), 30),
      smart: i !== 1,
    }));
    const block = beaconBlock(two({ beacon_last_sent: null, beacon_next_due: null }), gpsOff(), {}, NOW, six);
    expect(block.line).toBe("Last beacon 3 min ago · next in 10 min (every 20 min)");
    expect(block.radios).toHaveLength(6);
    expect(block.radios[3]).toBe("Mobile12: last beacon 6 min ago · next in 13 min (every 30 min)");
    expect(
      beaconBlock(
        two(),
        gpsOff(),
        {},
        NOW,
        radios().map((r) => ({ ...r, beacon: beacon(null, null, 0) })),
      ),
    ).toMatchObject({
      pill: { text: "off", tone: "beacon-off" },
      line: "No beacon sent yet · no timed beacon",
    });
  });

  it("has no lines of radios while one radio is on, and the row as it was: the FM beacon alone, or the HF beacon alone", () => {
    const fm = beaconBlock(timed(), gpsOff(), {}, NOW);
    expect([fm.radios, fm.line]).toEqual([[], "Last beacon 4 min ago · next in 56 min (every 60 min)"]);
    const hf = beaconBlock(
      status({ beacon_interval_min: 30, beacon_last_sent: ago(120), beacon_next_due: later(29 * 60) }),
      gpsOff(),
      { "fm/enabled": "false", "hf/enabled": "true" },
      NOW,
    );
    expect([hf.radios, hf.line, hf.pill?.text]).toEqual([[], "Last beacon 2 min ago · next in 29 min (every 30 min)", "on"]);
  });

  it("has a line for each radio of a moving station too: the radio with SmartBeaconing its next by time, the one without its own interval (plan rule 3.1)", () => {
    const moving = beaconBlock(two(), gpsState(), GPSD, NOW, radios());
    expect(moving).toMatchObject({ moving: true, label: "GPS" });
    expect(moving.smart).not.toBeNull();
    expect(moving.radios).toEqual(["FM: last beacon 4 min ago · next in 16 min", "HF: last beacon 2 min ago · next in 29 min (every 30 min)"]);
    expect(beaconBlock(two(), gpsOff(), {}, NOW, radios()).radios[0]).toBe("FM: last beacon 4 min ago · next in 16 min (every 20 min)"); // (a fixed station's FM keeps its interval)
  });

  it("has no lines of radios while the beacon is Off or in RX only, moving or not", () => {
    const cases: Record<string, string>[] = [{ "beacon/interval_min": "0" }, { "station/transmit": "false" }];
    for (const values of cases) {
      expect(beaconBlock(two(), gpsOff(), values, NOW, radios()).radios).toEqual([]);
      expect(beaconBlock(two(), gpsState(), { ...GPSD, ...values }, NOW, radios()).radios).toEqual([]);
    }
    expect(beaconBlock(two(), gpsOff(), {}, NOW, radios()).radios).toHaveLength(2);
  });
});

describe("the radios of the Beacon group", () => {
  const fm = (id: number, extra: Partial<RadioRow> = {}) => pageRadio(radioRow(id, "kenwood-tnc2", { number: id, ...extra }));
  const hf = (id: number, extra: Partial<RadioRow> = {}) => pageRadio(radioRow(id, "mercury", extra));
  const off = (radio: PageRadio, beacon = false) => pageRadio({ ...radio.row, choices: { ...radio.row.choices, beacon } });

  it("send the beacon on the one radio that is on whatever its Send on says, else on the radios ticked, and on the main radio when none is", () => {
    expect(beaconRadios([off(hf(2))], null).map((r) => r.id)).toEqual([2]);
    expect(beaconRadios([fm(1), hf(2), fm(3)], fm(1)).map((r) => r.id)).toEqual([1, 2, 3]);
    expect(beaconRadios([fm(1), off(hf(2)), fm(3)], fm(1)).map((r) => r.id)).toEqual([1, 3]);
    expect(beaconRadios([off(fm(1)), off(hf(2))], hf(2)).map((r) => r.id)).toEqual([2]);
    expect(beaconRadios([off(fm(1)), off(hf(2))], null)).toEqual([]);
    expect(beaconRadios([], null)).toEqual([]);
  });

  it("say which of them is not connected, a line for each, and nothing while one is", () => {
    const waiting = fm(1, { state: "waiting" });
    expect(notConnectedWhy([waiting, hf(2, { state: "connecting", name: "20 m" })])).toBe("FM: not connected\n20 m: not connected");
    expect(notConnectedWhy([waiting, hf(2)])).toBeUndefined();
    expect(notConnectedWhy([])).toBeUndefined();
  });

  it("have a tick of Send on for each radio that is on, the last one ticked greyed", () => {
    const radios = [fm(1), hf(2), fm(3, { name: "Mobile12" })];
    const on = new Set(["radio/1/beacon", "radio/3/beacon"]);
    expect(sendOnTicks(radios, (key) => on.has(key), radios[0] ?? null)).toEqual([
      { id: 1, key: "radio/1/beacon", name: "FM", on: true, last: false, held: false },
      { id: 2, key: "radio/2/beacon", name: "HF", on: false, last: false, held: false },
      { id: 3, key: "radio/3/beacon", name: "Mobile12", on: true, last: false, held: false },
    ]);
    on.delete("radio/1/beacon");
    expect(sendOnTicks(radios, (key) => on.has(key), radios[0] ?? null).map((tick) => [tick.on, tick.last, tick.held])).toEqual([
      [false, false, false],
      [false, false, false],
      [true, true, false],
    ]);
    expect(sendOnTicks(radios, (_key, radio) => radio.row.choices.beacon, radios[0] ?? null).every((tick) => tick.on && !tick.last)).toBe(true);
  });

  it("show the main radio's tick ticked and greyed while none is ticked, for the beacon goes out on it (plan rule 3.1: a beacon with every radio unticked cannot happen)", () => {
    const radios = [hf(2), fm(3, { name: "Mobile12" })];
    expect(sendOnTicks(radios, () => false, radios[0] ?? null).map((tick) => [tick.id, tick.on, tick.last, tick.held])).toEqual([
      [2, true, true, true],
      [3, false, false, false],
    ]);
    expect(sendOnTicks(radios, () => false, null).some((tick) => tick.on || tick.last)).toBe(false);
  });

  it("have a Path row for each radio that is on and may carry a path, named while several are on", () => {
    expect(pathRows([fm(1)])).toEqual([{ key: "radio/1/path", radio: 1, name: null }]);
    expect(pathRows([hf(2)])).toEqual([]);
    expect(pathRows([fm(1), hf(2)])).toEqual([{ key: "radio/1/path", radio: 1, name: "FM" }]);
    expect(pathRows([fm(1), hf(2), fm(3, { number: 2 })])).toEqual([
      { key: "radio/1/path", radio: 1, name: "FM" },
      { key: "radio/3/path", radio: 3, name: "FM 2" },
    ]);
    expect(pathRows([fm(3)])).toEqual([{ key: "radio/3/path", radio: 3, name: null }]);
    expect(pathRows([pageRadio(radioRow(1, "mercury")), fm(4)])).toEqual([{ key: "radio/4/path", radio: 4, name: "FM 4" }]);
    expect(pathKey({ id: 1 })).toBe("radio/1/path");
  });

  it("read a radio's own setting in the settings' values once they hold it, else in radio_values", () => {
    const config = configValues({ "radio/3/path": "WIDE2-2" });
    expect(radioValueOf(config, "radio/3/path")).toBe("WIDE2-2");
    expect(radioValueOf({ ...config, radio_values: { ...config.radio_values, "radio/4/path": "DIRECT" } }, "radio/4/path")).toBe("DIRECT");
    expect(radioValueOf(config, "radio/9/path")).toBeUndefined();
    expect(radioValueOf(null, "radio/3/path")).toBeUndefined();
  });
});
