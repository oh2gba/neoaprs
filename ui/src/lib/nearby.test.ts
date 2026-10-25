import { describe, expect, it } from "vitest";
import {
  digipeaterLines,
  digipeaters,
  directLines,
  directRows,
  gateLines,
  gateRows,
  isDigipeaterSymbol,
  isIgateSymbol,
  rangeCircleOf,
  rangeOf,
  repeatedCounts,
  voiceLines,
  voiceRows,
} from "@/lib/nearby";
import { NOW, ago, station } from "@/test/fixtures";
import type { ExtensionValues, FrequencyValues, PhgValues } from "@/protocol/protocol";

const phg = (range_km: number): PhgValues => ({ power_w: 25, height_m: 12.2, gain_db: 5, direction_deg: null, range_km });
const extensions = (extra: Partial<ExtensionValues> = {}): ExtensionValues => ({
  phg: null,
  range_km: null,
  dfs: null,
  df_bearing: null,
  area: null,
  ...extra,
});
const frequency = (extra: Partial<FrequencyValues> = {}): FrequencyValues => ({
  mhz: 145.775,
  tone_hz: 118,
  tone_both: false,
  tone_off: false,
  dcs: null,
  tone_burst: false,
  narrow: false,
  offset_khz: -600,
  range_km: null,
  rx_mhz: null,
  ...extra,
});
const calls = (list: { call: string }[]): string[] => list.map((item) => item.call);

describe("the symbols", () => {
  it("know a digipeater by its code in the primary table, the alternate one and any overlay", () => {
    for (const table of ["/", "\\", "1", "S", "a"]) expect(isDigipeaterSymbol({ symbol_table: table, symbol_code: "#" })).toBe(true);
    expect(isDigipeaterSymbol({ symbol_table: "/", symbol_code: ">" })).toBe(false);
    expect(isDigipeaterSymbol({ symbol_table: "", symbol_code: "" })).toBe(false);
  });

  it("know an iGate by the overlay I on the gateway symbol", () => {
    expect(isIgateSymbol({ symbol_table: "I", symbol_code: "&" })).toBe(true);
    expect(isIgateSymbol({ symbol_table: "\\", symbol_code: "&" })).toBe(false);
    expect(isIgateSymbol({ symbol_table: "I", symbol_code: "#" })).toBe(false);
  });
});

describe("the digipeaters", () => {
  const rows = [
    station("OH2GBA", { is_me: true, distance_km: null, heard_via: [] }),
    station("OH2AAA", {
      heard_via: [
        ["OH2RCH-2", 30],
        ["?", 5],
        ["OH2RCH-3", 4],
      ],
    }),
    station("OH2BBB", { heard_via: [["OH2RCH-2", 10]] }),
    station("OH2RCH-2", { symbol_code: "#", distance_km: 12, heard_via: [], extensions: extensions({ phg: phg(21.4) }) }),
    station("OH2RCH-3", { symbol_code: "#", distance_km: 4, heard_via: [], extensions: extensions({ range_km: 40 }) }),
    station("OH2FILL", { symbol_table: "1", symbol_code: "#", distance_km: 30, heard_via: [] }),
    station("OH2CAR", { distance_km: 2, heard_via: [] }),
    station("DIGIOBJ", { kind: "object", symbol_code: "#", distance_km: 1, heard_via: [] }),
  ];

  it("add up the packets each call repeated for the stations, leaving out a hop that gave no call", () => {
    expect([...repeatedCounts(rows)]).toEqual([
      ["OH2RCH-2", 40],
      ["OH2RCH-3", 4],
    ]);
  });

  it("are the calls that repeated and the stations with the symbol, nearest first, and no car, no object, no us", () => {
    const list = digipeaters(rows);
    expect(calls(list)).toEqual(["OH2RCH-3", "OH2RCH-2", "OH2FILL"]);
    expect(list.map((d) => d.repeated)).toEqual([4, 40, 0]);
  });

  it("have the range a station gave: the PHG one, else the RNG one, else none", () => {
    expect(digipeaters(rows).map((d) => d.range)).toEqual([{ km: 40, phg: false }, { km: 21.4, phg: true }, null]);
    expect(rangeOf(extensions({ phg: phg(10), range_km: 50 }))).toEqual({ km: 10, phg: true });
    expect(rangeOf(null)).toBeNull();
  });

  it("list a call that only repeated, with no row of its own, after the ones with a distance", () => {
    const list = digipeaters([station("OH2AAA", { heard_via: [["OH2GHOST", 3]] }), station("OH2NEAR", { symbol_code: "#", distance_km: 50, heard_via: [] })]);
    expect(calls(list)).toEqual(["OH2NEAR", "OH2GHOST"]);
    expect(list[1]?.row).toBeNull();
    expect(digipeaterLines(list[1] as never)).toEqual(["3 packets repeated", "no packet of its own heard"]);
  });

  it("put a station with no distance after the ones with one, and order equals by call", () => {
    const list = digipeaters([
      station("B", { symbol_code: "#", distance_km: null, heard_via: [] }),
      station("A", { symbol_code: "#", distance_km: null, heard_via: [] }),
      station("C", { symbol_code: "#", distance_km: 99, heard_via: [] }),
    ]);
    expect(calls(list)).toEqual(["C", "A", "B"]);
  });

  it("say what they repeated and their range in words", () => {
    const [near, far, fill] = digipeaters(rows);
    expect(digipeaterLines(near as never)).toEqual(["4 packets repeated, range 40 km"]);
    expect(digipeaterLines(far as never)).toEqual(["40 packets repeated, PHG range 21 km"]);
    expect(digipeaterLines(fill as never)).toEqual(["digipeater symbol"]);
    expect(digipeaterLines({ call: "X", row: rows[3], repeated: 1, range: null })).toEqual(["1 packet repeated"]);
  });

  it("have a circle on the map for the selected one when it has a position and a range, else none", () => {
    expect(rangeCircleOf(rows, "OH2RCH-3")).toEqual({ call: "OH2RCH-3", lat: 60.2, lon: 24.9, km: 40 });
    expect(rangeCircleOf(rows, "OH2RCH-2")).toEqual({ call: "OH2RCH-2", lat: 60.2, lon: 24.9, km: 21.4 });
    expect(rangeCircleOf(rows, null)).toBeNull();
    expect(rangeCircleOf(rows, "OH2FILL")).toBeNull(); // (a digipeater with no range)
    expect(rangeCircleOf(rows, "OH2CAR")).toBeNull(); // (not a digipeater of the list)
    expect(rangeCircleOf(rows, "NOBODY")).toBeNull();
    expect(rangeCircleOf([station("X", { symbol_code: "#", lat: null, lon: null, extensions: extensions({ phg: phg(5) }) })], "X")).toBeNull();
    expect(rangeCircleOf([station("X", { symbol_code: "#", extensions: extensions({ range_km: 0 }) })], "X")).toBeNull();
    expect(rangeCircleOf([station("X", { symbol_code: "#", last_position_at: ago(5 * 3600), extensions: extensions({ range_km: 9 }) })], "X")?.km).toBe(9);
  });
});

describe("the voice frequencies", () => {
  const rows = [
    station("OH2FAR", { distance_km: 40, frequency: frequency() }),
    station("OH2NONE", { distance_km: 1 }),
    station("OH2NEAR", { distance_km: 5, frequency: frequency({ mhz: 433.5, tone_hz: null, offset_khz: null }) }),
    station("R-HELSINKI", { kind: "object", reported_by: "OH2XYZ", distance_km: null, frequency: frequency({ mhz: 145.6, offset_khz: -600 }) }),
  ];

  it("are every station, object and item that gave one, nearest first", () => {
    expect(calls(voiceRows(rows))).toEqual(["OH2NEAR", "OH2FAR", "R-HELSINKI"]);
  });

  it("are worded as the card words them, with who reported an object", () => {
    const [near, far, object] = voiceRows(rows);
    expect(voiceLines(near as never)).toEqual(["433.500 MHz"]);
    expect(voiceLines(far as never)).toEqual(["145.775 MHz, tone 118 Hz, -600 kHz"]);
    expect(voiceLines(object as never)).toEqual(["145.600 MHz, tone 118 Hz, -600 kHz", "reported by OH2XYZ"]);
  });
});

describe("the iGates", () => {
  const rows = [
    station("OH2GBA", { is_me: true, gated: 9 }),
    station("OH7JHF-1", { distance_km: 30, gated: 12, igate: true }),
    station("OH2SAYS", { distance_km: 10, igate: true }),
    station("OH2SYM", { distance_km: 20, symbol_table: "I", symbol_code: "&" }),
    station("OH2CAR", { distance_km: 1 }),
    station("OBJ", { kind: "object", gated: 3 }),
  ];

  it("are the stations that put third-party packets on the air, said so or have the symbol, nearest first", () => {
    expect(calls(gateRows(rows))).toEqual(["OH2SAYS", "OH2SYM", "OH7JHF-1"]);
  });

  it("say why", () => {
    const [says, symbol, gate] = gateRows(rows);
    expect(gateLines(gate as never)).toEqual(["12 third-party packets put on the air"]);
    expect(gateLines(station("X", { gated: 1 }))).toEqual(["1 third-party packet put on the air"]);
    expect(gateLines(says as never)).toEqual(["says it is an iGate"]);
    expect(gateLines(symbol as never)).toEqual(["iGate symbol"]);
  });
});

describe("the stations heard direct", () => {
  const rows = [
    station("OH2GBA", { is_me: true, heard_direct: 4 }),
    station("OH2FAR", { distance_km: 15, heard_direct: 1, last_direct_at: ago(60) }),
    station("OH2NEAR", { distance_km: 3, heard_direct: 7, last_direct_at: ago(7200) }),
    station("OH2VIA", { distance_km: 1, heard_direct: 0 }),
    station("OH2OLD", { distance_km: null, bearing_deg: null, heard_direct: 2, last_direct_at: ago(900) }),
    station("OH2NEW", { distance_km: null, bearing_deg: null, heard_direct: 1, last_direct_at: ago(30) }),
    station("OBJ", { kind: "object", heard_direct: 1 }),
  ];

  it("are those with a packet heard direct, nearest first, a missing distance last and then the newest direct packet first", () => {
    expect(calls(directRows(rows))).toEqual(["OH2NEAR", "OH2FAR", "OH2NEW", "OH2OLD"]);
  });

  it("say when the last direct packet was heard", () => {
    expect(directLines(station("X", { last_direct_at: ago(180) }), NOW)).toEqual(["last heard direct 3 min ago"]);
    expect(directLines(station("X", { last_direct_at: null }), NOW)).toEqual([]);
  });
});
