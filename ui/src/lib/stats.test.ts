import { describe, expect, it } from "vitest";
import { historyPoints, mapStats, type StatSection } from "@/lib/stats";
import { NOW, ago, igateState, mapState, packet, station, status, table, tncState, weatherStation } from "@/test/fixtures";

const AGING = { defaultMin: 180 };

/** The lines of a section, as "label=value" (the label's id, the value's text). */
function lines(sections: StatSection[], title: string): string[] {
  const found = sections.find((s) => s.title === title);
  return found === undefined ? [] : found.lines.map((line) => `${line.label}=${line.value}`);
}

const stations = () =>
  table(
    station("OH2GBA", { is_me: true, lat: 60.17, lon: 24.94, distance_km: null, heard_via: [] }),
    station("OH2PU-9", {
      lat: 60.2,
      lon: 24.65,
      distance_km: 16,
      heard_direct: 3,
      heard_rf: 20,
      packets_hour: 12,
      device: "APRSdroid",
      heard_via: [["OH2RCH-2", 17]],
    }),
    station("OH2RDG", {
      symbol_table: "/",
      symbol_code: "#",
      lat: 60.12,
      lon: 24.49,
      distance_km: 25,
      heard_direct: 1,
      heard_rf: 5,
      packets_hour: 2,
      device: "Kenwood TH-D74",
      heard_via: [],
    }),
    station("OH5FAR", {
      lat: 61.0,
      lon: 26.0,
      distance_km: 110,
      heard_direct: 0,
      heard_rf: 4,
      packets_hour: 1,
      device: "APRSdroid",
      heard_via: [
        ["OH2RCH-2", 3],
        ["OH5RCH", 1],
      ],
    }),
    station("OH2NET", {
      lat: 60.3,
      lon: 25.1,
      distance_km: 12,
      heard_direct: 0,
      heard_rf: 0,
      heard_is: 9,
      packets_hour: 4,
      device: "APRSdroid",
      heard_via: [],
    }),
    station("OH2OLD", { lat: 60.4, lon: 25.2, distance_km: 30, last_position_at: ago(5 * 3600), heard_rf: 1, packets_hour: 0, heard_via: [] }),
    station("CLUB", { kind: "object", reported_by: "OH2RDG", lat: 60.1, lon: 24.5, distance_km: 20, packets_hour: 1, heard_via: [] }),
    station("OH2GW-10", { lat: 60.05, lon: 24.3, distance_km: 40, gated: 7, heard_rf: 7, packets_hour: 0, heard_via: [] }),
    weatherStation("OH2MUI", { distance_km: 9, heard_rf: 6, packets_hour: 6, heard_via: [] }),
  );

const packets = () =>
  new Map(
    [
      packet(1, { route: "direct", heard_at: ago(600) }),
      packet(2, { route: "via OH2RCH-2", heard_at: ago(500) }),
      packet(3, { kind: "message", route: "direct", heard_at: ago(400) }),
      packet(4, { via: "is", route: "", path: ["TCPIP*", "qAC", "T2FINLAND"], heard_at: ago(300) }),
      packet(5, { kind: "status", route: "via OH2RCH-2", heard_at: ago(0) }),
      packet(6, { direction: "out", route: "", heard_at: ago(0) }),
    ].map((row) => [String(row.id), row] as const),
  );

const input = (extra = {}) => ({
  stations: stations(),
  packets: packets(),
  status: status({ packets: 1234, started_at: ago(3 * 3600 + 100) }),
  tnc: tncState(),
  igate: igateState({ enabled: true, gated: 42 }),
  map: mapState({ aloha_km: 37.4 }),
  aging: AGING,
  now: NOW,
  ...extra,
});

describe("the statistics of the map", () => {
  it("counts the stations: heard, on the map, direct, internet only, objects, digipeaters, iGates, weather, and what they run", () => {
    expect(lines(mapStats(input()), "stats.section.stations")).toEqual([
      "stats.stations=7", // (not ourselves, not the object)
      "stats.on_map=7", // (not ourselves, not OH2OLD past its timeout)
      "stats.direct=2",
      "stats.internet_only=1",
      "stats.objects=1",
      "stats.digipeaters=3", // OH2RDG by its symbol, OH2RCH-2 and OH5RCH heard repeating
      "stats.igates=1",
      "stats.weather=1",
      "stats.devices=APRSdroid (3), Kenwood TH-D74 (1)",
    ]);
  });

  it("says how far we reach: the farthest direct, the farthest on the radio, and the digipeaters most used", () => {
    expect(lines(mapStats(input()), "stats.section.reach")).toEqual([
      "stats.aloha=37 km",
      "stats.farthest_direct=OH2RDG, 25 km",
      "stats.farthest_rf=OH5FAR, 110 km",
      "stats.most_used=OH2RCH-2 (20), OH5RCH (1)",
    ]);
  });

  it("counts the packets: the database, the last hour, the busiest station, and the latest heard by kind, channel, direct share and rate", () => {
    expect(lines(mapStats(input()), "stats.section.packets")).toEqual([
      "stats.packets_total=1234",
      "stats.packets_hour=26",
      "stats.busiest=OH2PU-9, 12 in the last hour",
      "stats.by_kind=3 positions · 1 messages · 1 status",
      "stats.by_channel=4 RF · 1 Internet",
      "stats.direct_share=50 % of those on the radio",
      "stats.rate=0.5 a minute", // 5 heard over 10 minutes
    ]);
    expect(
      mapStats(input())
        .find((s) => s.title === "stats.section.packets")
        ?.lines.find((l) => l.label === "stats.by_kind")?.params,
    ).toEqual({ n: "5" });
  });

  it("says what the radio did since the daemon started", () => {
    const tnc = tncState();
    tnc.stats = { ...tnc.stats, frames_in: 2500, rejected: 12, bytes_in: 300_000, bytes_out: 2048, digipeated: 9 };
    expect(lines(mapStats(input({ tnc })), "stats.section.radio")).toEqual([
      "stats.running=3 h",
      "stats.frames=2500, 12 unreadable",
      "stats.bytes=293.0 kB · 2.0 kB",
      "stats.digipeated=9",
      "stats.gated=42",
    ]);
  });

  it("leaves out a line with nothing to say, and a section with no line", () => {
    const sections = mapStats({ stations: new Map(), packets: new Map(), status: null, tnc: null, igate: null, map: null, aging: AGING, now: NOW });
    expect(sections.map((s) => s.title)).toEqual(["stats.section.stations", "stats.section.packets"]);
    expect(lines(sections, "stats.section.packets")).toEqual(["stats.packets_hour=0"]);
    expect(lines(sections, "stats.section.stations")).toEqual([
      "stats.stations=0",
      "stats.on_map=0",
      "stats.direct=0",
      "stats.digipeaters=0",
      "stats.igates=0",
    ]);
    const quiet = mapStats(input({ igate: igateState({ enabled: false }), packets: new Map([["6", packet(6, { direction: "out" })]]) }));
    expect(lines(quiet, "stats.section.radio").some((l) => l.startsWith("stats.gated"))).toBe(false);
    expect(lines(quiet, "stats.section.packets")).toHaveLength(3);
  });

  it("gives no rate for packets that came within a minute, and no direct share without a packet on the radio", () => {
    const sections = mapStats(
      input({
        packets: new Map([
          ["4", packet(4, { via: "is", route: "", heard_at: ago(30) })],
          ["5", packet(5, { via: "is", route: "", heard_at: ago(0) })],
        ]),
      }),
    );
    const found = lines(sections, "stats.section.packets");
    expect(found.some((l) => l.startsWith("stats.rate"))).toBe(false);
    expect(found.some((l) => l.startsWith("stats.direct_share"))).toBe(false);
  });

  it("makes the bars of the packets by the hour: a point in the middle of each hour from the start, the axis over the whole hours", () => {
    const bars = historyPoints({ type: "packet_history", hours: 3, start: "2026-10-21T10:00:00Z", counts: [41, 0, 12] });
    const start = Date.parse("2026-10-21T10:00:00Z");
    expect(bars.from).toBe(start);
    expect(bars.to).toBe(start + 3 * 3_600_000);
    expect(bars.points).toEqual([
      { t: start + 1_800_000, v: 41 },
      { t: start + 5_400_000, v: 0 },
      { t: start + 9_000_000, v: 12 },
    ]);
  });
});
