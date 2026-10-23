import { describe, expect, it } from "vitest";
import { bestText, directShare, directText, directWords, heardDirectRecently, heardText, pathWords, viaName } from "@/lib/routes";
import { NOW, ago, station } from "@/test/fixtures";

describe("heardText", () => {
  it("counts the packets direct and by each repeater, the most first as the daemon sends them", () => {
    const row = station("OH2RDG", {
      heard_direct: 12,
      heard_via: [
        ["OH2RCH-2", 30],
        ["OH2RCH-3", 4],
      ],
      heard_gated: 0,
    });
    expect(heardText(row)).toBe("12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3");
  });

  it("leaves out what is zero, names an unnamed repeater and counts the packets from the internet", () => {
    expect(heardText(station("A", { heard_direct: 0, heard_via: [["?", 3]], heard_gated: 2 }))).toBe("3 via an unnamed repeater, 2 from the internet");
    expect(heardText(station("A", { heard_direct: 1, heard_via: [], heard_gated: 0 }))).toBe("1 direct");
  });

  it("is a dash before any packet is counted", () => {
    expect(heardText(station("A", { heard_direct: 0, heard_via: [], heard_gated: 0 }))).toBe("-");
  });
});

describe("bestText", () => {
  it("says the route and the path to send by", () => {
    expect(bestText({ best_route: "via OH2RCH-2", suggested_path: "OH2RCH-2" })).toBe("via OH2RCH-2; send by OH2RCH-2");
    expect(bestText({ best_route: "via OH2RCH-1 → OH2RCH-3", suggested_path: "OH2RCH-3,OH2RCH-1" })).toBe("via OH2RCH-1 → OH2RCH-3; send by OH2RCH-3,OH2RCH-1");
    expect(bestText({ best_route: "direct", suggested_path: "" })).toBe("direct; send direct");
  });

  it("says when a repeater gave no call, and when there is nothing to say", () => {
    expect(bestText({ best_route: "via ? → OH2RCH-2", suggested_path: "WIDE1-1,WIDE2-1" })).toBe("via ? → OH2RCH-2; unknown repeater, send by WIDE1-1,WIDE2-1");
    expect(bestText({ best_route: "", suggested_path: null })).toBe("-");
  });
});

describe("pathWords and viaName", () => {
  it("writes an empty path as direct and ? as an unnamed repeater", () => {
    expect([pathWords(""), pathWords("OH2RCH-2")]).toEqual(["direct", "OH2RCH-2"]);
    expect([viaName("?"), viaName("OH2RCH-2")]).toEqual(["an unnamed repeater", "OH2RCH-2"]);
  });
});

describe("what is direct", () => {
  const near = station("OH2PU-9", { last_direct_at: ago(300), heard_direct: 2, heard_via: [["OH2RCH-2", 3]], heard_gated: 0 });

  it("takes the share of the packets counted, the ones from the internet and by a repeater with the direct ones", () => {
    expect(directShare(near)).toBe(40);
    expect(directShare(station("A", { heard_direct: 1, heard_via: [["OH2RCH-2", 1]], heard_gated: 1 }))).toBe(33);
    expect(directShare(station("A", { heard_direct: 3, heard_via: [], heard_gated: 0 }))).toBe(100);
    expect(directShare(station("A", { heard_direct: 0, heard_via: [], heard_gated: 0 }))).toBeNull();
  });

  it("writes when it was last heard direct and the share, as the Direct column and the card have it", () => {
    expect(directText(near, NOW)).toBe("5 min, 40 %");
    expect(directWords(near, NOW)).toBe("heard direct 5 min ago, 40 % of its packets");
    expect(directText(station("A", { last_direct_at: null }), NOW)).toBe("-");
    expect(directWords(station("A", { last_direct_at: null }), NOW)).toBe("not heard direct");
    const nocount = station("A", { last_direct_at: ago(30), heard_direct: 0, heard_via: [], heard_gated: 0 });
    expect([directText(nocount, NOW), directWords(nocount, NOW)]).toEqual(["30 s", "heard direct 30 s ago"]);
  });

  it("is recent for an hour", () => {
    expect(heardDirectRecently(station("A", { last_direct_at: ago(3600) }), NOW)).toBe(true);
    expect(heardDirectRecently(station("A", { last_direct_at: ago(3601) }), NOW)).toBe(false);
    expect(heardDirectRecently(station("A", { last_direct_at: null }), NOW)).toBe(false);
  });
});
