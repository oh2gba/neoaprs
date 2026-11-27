import { describe, expect, it } from "vitest";
import { CHART_HOURS, channelLines, chartOf, dayHours, ownLines, throughLines } from "@/lib/packetstats";
import { pageRadios } from "@/lib/radios";
import type { PacketStatsMessage } from "@/protocol/protocol";
import { radioRow, radiosTopic } from "@/test/fixtures";

const RADIOS = pageRadios(
  radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury"), radioRow(3, "kiss", { name: "Shack", number: 2 })),
  null,
);

/**
 * An answer of `hours` hours from midnight UTC: FM 2 an hour, Mercury 1 (5 in the running hour),
 * the internet 10.
 */
function answer(hours: number, more: Partial<PacketStatsMessage> = {}): PacketStatsMessage {
  return {
    type: "packet_stats",
    start: "2026-10-20T00:00:00Z",
    hours,
    heard: [
      { radio: 1, counts: Array.from({ length: hours }, () => 2) },
      { radio: 2, counts: Array.from({ length: hours }, (_, i) => (i === hours - 1 ? 5 : 1)) },
      { radio: null, counts: Array.from({ length: hours }, () => 10) },
    ],
    sent: [
      { radio: 1, beacons: 3, messages: 2, acks: 1, objects: 4, other: 0, repeated: 7 },
      { radio: 3, beacons: 1, messages: 0, acks: 0, objects: 0, other: 0, repeated: 0 },
    ],
    packets: 40,
    frames: 46,
    repeated_hour: 2,
    gated_hour: 5,
    ...more,
  };
}

describe("the statistics card's counts from the packet log", () => {
  it("makes the bars of the last 24 hours of each radio's and the internet's parts, their sum the whole bar", () => {
    const chart = chartOf(answer(30), RADIOS);
    expect(chart.points).toHaveLength(CHART_HOURS);
    expect(chart.to - chart.from).toBe(CHART_HOURS * 3_600_000);
    expect(chart.parts.map((part) => [part.label, part.tone])).toEqual([
      ["Packet", "series-0"],
      ["Mercury", "series-1"],
      ["Internet", "series-net"],
    ]);
    expect(chart.points.at(-1)?.v).toBe(2 + 5 + 10);
    expect(chart.points[0]?.v).toBe(13);
  });

  it("fills the hours before the oldest packet with nothing, and leaves out a radio the page does not know", () => {
    const short = answer(3, {
      heard: [
        { radio: 9, counts: [1, 1, 1] },
        { radio: 1, counts: [1, 2, 3] },
      ],
    });
    const chart = chartOf(short, RADIOS);
    expect(chart.parts.map((part) => part.label)).toEqual(["Packet"]);
    expect(chart.points.map((p) => p.v).slice(-4)).toEqual([0, 1, 2, 3]);
  });

  it("names each radio with what it heard and sent that day, and the copies that came again by another way", () => {
    const lines = channelLines(answer(24), RADIOS, true).map(
      (line) => `${String(line.params?.name ?? line.label)}=${line.value}`,
    );
    expect(lines).toEqual([
      "Packet=48 heard · 17 sent",
      "Mercury=28 heard · 0 sent",
      "Shack=0 heard · 1 sent",
      "Internet=240 heard",
      "stats.copies=6 copies of 40 packets",
    ]);
    expect(channelLines(answer(24), RADIOS, true).map((line) => line.key)).toEqual([
      "radio-1",
      "radio-2",
      "radio-3",
      "is",
      undefined,
    ]);
  });

  it("adds up what we sent ourselves by kind, every kind, 0 for one we sent none of and a dash before the answer", () => {
    expect(ownLines(answer(24)).map((line) => `${line.label}=${line.value}`)).toEqual([
      "stats.own.beacons=4",
      "stats.own.messages=2",
      "stats.own.acks=1",
      "stats.own.objects=4",
      "stats.own.other=0",
    ]);
    expect(ownLines(null).map((line) => line.value)).toEqual(["–", "–", "–", "–", "–"]);
  });

  it("gives each radio the colour of its place among the radios, which stays when another radio starts to hear", () => {
    const silentFm = answer(24, { heard: [{ radio: 2, counts: Array.from({ length: 24 }, () => 1) }] });
    const tones = (stats: PacketStatsMessage) =>
      Object.fromEntries(chartOf(stats, RADIOS).parts.map((part) => [part.label, part.tone]));
    expect(tones(silentFm)).toEqual({ Mercury: "series-1" });
    expect(tones(answer(24))).toMatchObject({ Packet: "series-0", Mercury: "series-1" });
    expect(channelLines(silentFm, RADIOS, false).map((line) => line.tone)).toEqual([
      "series-0",
      "series-1",
      "series-2",
      undefined,
    ]);
  });

  it("keeps the lines of the radios that are on and of the internet while its link is on, with a dash before the answer, so that the card keeps its shape", () => {
    const before = channelLines(null, RADIOS, true);
    const after = channelLines(answer(24, { heard: [], sent: [] }), RADIOS, true);
    expect(before.map((line) => line.key ?? line.label)).toEqual(after.map((line) => line.key ?? line.label));
    expect(before.map((line) => line.value)).toEqual([
      "– heard · – sent",
      "– heard · – sent",
      "– heard · – sent",
      "– heard",
      "–",
    ]);
    expect(after.map((line) => line.value)).toEqual([
      "0 heard · 0 sent",
      "0 heard · 0 sent",
      "0 heard · 0 sent",
      "0 heard",
      "6 copies of 40 packets",
    ]);
    expect(channelLines(answer(24, { heard: [] }), RADIOS, false).some((line) => line.key === "is")).toBe(false);
    const off = pageRadios(
      radiosTopic(radioRow(1, "kenwood-tnc2"), radioRow(2, "mercury", { enabled: false, state: "stopped" })),
      null,
    );
    expect(channelLines(answer(24, { heard: [], sent: [] }), off, false).map((line) => line.key)).toEqual([
      "radio-1",
      undefined,
    ]);
    expect(channelLines(answer(24, { sent: [] }), off, false).map((line) => line.key)).toEqual([
      "radio-1",
      "radio-2",
      "is",
      undefined,
    ]);
  });

  it("says what went through us in the last hour and since the start, the iGate only while it is on", () => {
    expect(throughLines(answer(24), { repeated: 30, gated: 100, digipeater: false }).map((line) => line.value)).toEqual(
      ["2 in the last hour · 30 since the start", "5 in the last hour · 100 since the start"],
    );
    expect(throughLines(answer(24, { repeated_hour: 0 }), { repeated: 0, gated: null, digipeater: false })).toEqual([]);
    expect(throughLines(null, { repeated: 0, gated: null, digipeater: true }).map((line) => line.value)).toEqual([
      "– in the last hour · 0 since the start",
    ]);
  });

  it("finds the busiest and the quietest hour of the day in the viewer's time over the whole hours, once a day is counted", () => {
    const busy = answer(49, {
      heard: [{ radio: 1, counts: Array.from({ length: 49 }, (_, i) => (i % 24 === 17 ? 50 : i % 24 === 4 ? 0 : 5)) }],
    });
    const hours = dayHours(busy);
    expect(hours?.busiest).toBe(new Date(Date.parse("2026-10-20T17:00:00Z")).getHours());
    expect(hours?.quietest).toBe(new Date(Date.parse("2026-10-20T04:00:00Z")).getHours());
    expect(dayHours(answer(24))).toBeNull();
  });
});
