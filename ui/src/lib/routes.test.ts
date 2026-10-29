import { describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { bestText, heardDirect, heardDirectRecently, heardText, internetText, reachedText, routeWords, viaName } from "@/lib/routes";
import { NOW, ago, station } from "@/test/fixtures";

describe("heardText", () => {
  it("counts the packets direct and by each repeater, the most first as the daemon sends them", () => {
    const row = station("OH2RDG", {
      heard_direct: 12,
      heard_via: [
        ["OH2RCH-2", 30],
        ["OH2RCH-3", 4],
      ],
      heard_rf_gated: 0,
    });
    expect(heardText(row)).toBe("12 direct, 30 via OH2RCH-2, 4 via OH2RCH-3");
  });

  it("leaves out what is zero, names an unnamed repeater and counts the packets from the internet", () => {
    expect(heardText(station("A", { heard_direct: 0, heard_via: [["?", 3]], heard_rf_gated: 2 }))).toBe("3 via an unnamed repeater, 2 via an iGate");
    expect(heardText(station("A", { heard_direct: 1, heard_via: [], heard_rf_gated: 0 }))).toBe("1 direct");
  });

  it("is a dash before any packet is counted", () => {
    expect(heardText(station("A", { heard_direct: 0, heard_via: [], heard_rf_gated: 0 }))).toBe("-");
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

describe("viaName", () => {
  it("writes ? as an unnamed repeater", () => {
    expect([viaName("?"), viaName("OH2RCH-2")]).toEqual(["an unnamed repeater", "OH2RCH-2"]);
  });
});

describe("routeWords", () => {
  it("writes a route of the daemon in the words of the page", () => {
    expect(routeWords("direct")).toBe("direct");
    expect(routeWords("via OH2RCH-2")).toBe("via OH2RCH-2");
    expect(routeWords("via OH7JHF-1 (internet) → OH2RCH-3")).toBe("via OH7JHF-1 (internet) → OH2RCH-3");
  });
  it("keeps a repeater with no call as ? unless it is told how to write one, and text that is no route as it is", () => {
    expect(routeWords("via ? → OH2RCH-2")).toBe("via ? → OH2RCH-2");
    expect(routeWords("via ? → OH2RCH-2", "a repeater")).toBe("via a repeater → OH2RCH-2");
    expect(routeWords("")).toBe("");
  });
  it("is in the language of the page", () => {
    setLocale("en-XA");
    expect(routeWords("direct")).toMatch(/^\[!! /);
    expect(routeWords("via OH2RCH-2")).toMatch(/OH2RCH-2/);
    expect(routeWords("via OH2RCH-2")).not.toBe("via OH2RCH-2");
  });
});

describe("what is direct", () => {
  it("is recent for an hour", () => {
    expect(heardDirectRecently(station("A", { last_direct_at: ago(3600) }), NOW)).toBe(true);
    expect(heardDirectRecently(station("A", { last_direct_at: ago(3601) }), NOW)).toBe(false);
    expect(heardDirectRecently(station("A", { last_direct_at: null }), NOW)).toBe(false);
  });

  it("has the check mark for a station heard direct at some time, not for our own station, an object or a station never heard direct", () => {
    expect(heardDirect(station("A", { last_direct_at: ago(86400) }))).toBe(true);
    expect(heardDirect(station("A", { last_direct_at: null }))).toBe(false);
    expect(heardDirect(station("A", { last_direct_at: ago(60), is_me: true }))).toBe(false);
    expect(heardDirect(station("A", { last_direct_at: ago(60), kind: "object" }))).toBe(false);
  });
});

describe("reachedText", () => {
  const none = { last_route: "", heard_direct: 0, heard_via: [] as [string, number][], heard_rf_gated: 0 };

  it("is the way of the latest packet, in words", () => {
    expect(reachedText({ ...none, last_route: "direct" })).toBe("direct");
    expect(reachedText({ ...none, last_route: "via OH2RCH-2" })).toBe("via OH2RCH-2");
    expect(reachedText({ ...none, last_route: "via OH7JHF-1 (internet)" })).toBe("via OH7JHF-1 (internet)");
  });

  it("calls a repeater that put no call in the packet a repeater", () => {
    expect(reachedText({ ...none, last_route: "via ? → OH2RCH-2" })).toBe("via a repeater → OH2RCH-2");
  });

  it("falls back on how most of the packets came when the latest way is not known", () => {
    expect(reachedText({ ...none, heard_direct: 2, heard_via: [["OH2RCH-2", 9]] })).toBe("direct");
    expect(reachedText({ ...none, heard_via: [["OH2RCH-2", 9]] })).toBe("via OH2RCH-2");
    expect(reachedText({ ...none, heard_via: [["?", 9]] })).toBe("via a repeater");
    expect(reachedText({ ...none, heard_rf_gated: 1 })).toBe("via an iGate");
  });

  it("is null before any packet is counted", () => {
    expect(reachedText(none)).toBeNull();
  });
});

describe("internetText", () => {
  const book = new Map([
    ["OH2GW-10", station("OH2GW-10", { lat: 60.05, lon: 24.3 })],
    ["OH2NOPOS", station("OH2NOPOS", { lat: null, lon: null })],
  ]);
  const reach = (igate: string, hops: string[]) => ({ internet_reach: { kind: "igate" as const, igate, hops } });

  it("names the iGate that heard it and the digipeaters before it, or says it heard it direct", () => {
    expect(internetText(reach("OH2GW-10", ["OH2RCH-2"]), book)).toBe("Heard by iGate OH2GW-10 via OH2RCH-2");
    expect(internetText(reach("OH2GW-10", ["OH2RCH-1", "OH2RCH-3"]), book)).toBe("Heard by iGate OH2GW-10 via OH2RCH-1 → OH2RCH-3");
    expect(internetText(reach("OH2GW-10", ["?", "OH2RCH-2"]), book)).toBe("Heard by iGate OH2GW-10 via a repeater → OH2RCH-2");
    expect(internetText(reach("OH2GW-10", []), book)).toBe("Heard by iGate OH2GW-10 directly");
  });

  it("says that the iGate's position is not known, for an iGate not in the book and one with no position", () => {
    expect(internetText(reach("OH2NOPOS", ["OH2RCH-2"]), book)).toBe("Heard by iGate OH2NOPOS via OH2RCH-2 (iGate position unknown)");
    expect(internetText(reach("OH2UNKNOWN", []), book)).toBe("Heard by iGate OH2UNKNOWN directly (iGate position unknown)");
  });

  it("says that a packet from an app never was on the air, and nothing when the way is not known", () => {
    expect(internetText({ internet_reach: { kind: "app", igate: "", hops: [] } }, book)).toBe("Sent over the internet, not heard on the air");
    expect(internetText({ internet_reach: null }, book)).toBeNull();
    const app = { internet_reach: { kind: "app" as const, igate: "", hops: [] } };
    expect(internetText({ ...app, kind: "object", reported_by: "OH2HCY" }, book)).toBe("Sent over the internet by OH2HCY, not heard on the air");
    expect(internetText({ ...app, kind: "item", reported_by: "" }, book)).toBe("Sent over the internet, not heard on the air");
  });
});
