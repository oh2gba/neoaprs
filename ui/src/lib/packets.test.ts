import { describe, expect, it } from "vitest";
import { decodedJson, filterPackets, newestFirst } from "@/lib/packets";
import { packet } from "@/test/fixtures";

describe("packets", () => {
  const rows = [
    packet(1, { source: "OH2RDG" }),
    packet(3, { source: "OH2PU-9", summary: "status text", kind: "status" }),
    packet(2, { direction: "out", source: "OH2GBA" }),
  ];

  it("lists the highest id first", () => {
    expect(newestFirst(rows).map((r) => r.id)).toEqual([3, 2, 1]);
    expect(newestFirst(new Map(rows.map((r) => [String(r.id), r])).values()).map((r) => r.id)).toEqual([3, 2, 1]);
  });
  it("filters by the line, the summary, the source or the kind", () => {
    expect(filterPackets(rows, "").length).toBe(3);
    expect(filterPackets(rows, "oh2pu").map((r) => r.id)).toEqual([3]);
    expect(filterPackets(rows, "STATUS").map((r) => r.id)).toEqual([3]);
    expect(filterPackets(rows, "out").map((r) => r.id)).toEqual([2]);
    expect(filterPackets(rows, "zzz")).toEqual([]);
  });
  it("shows the decoded part as indented JSON", () => {
    expect(decodedJson(packet(1))).toContain('"type": "position"');
  });
});
