// What a path means hop by hop (lib/pathreach.ts): the Hops choice and the tick that make the aliases, how they go with the digipeaters named, the hops in all, and which paths are more than the network allows or no path.
import { describe, expect, it } from "vitest";
import { aliasesFor, homeFirst, meaningOf, reachOf, splitPath, withCall, withReach } from "@/lib/pathreach";

const kinds = (hops: string[]): string[][] => meaningOf(hops).parts.map((part) => part.kinds);

describe("the Hops choice", () => {
  it("makes the aliases for Direct and 1 to 3 hops, WIDE1-1 first when home digipeaters may take the first hop", () => {
    const table = [0, 1, 2, 3].map((count) => [count, withReach([], count, true).join(","), withReach([], count, false).join(",")]);
    expect(table).toEqual([
      [0, "", ""],
      [1, "WIDE1-1", "WIDE2-1"],
      [2, "WIDE1-1,WIDE2-1", "WIDE2-2"],
      [3, "WIDE1-1,WIDE2-2", "WIDE3-3"],
    ]);
  });

  it("replaces the aliases of the path, and keeps the digipeaters named first as far as they go, with wide hops after them", () => {
    expect(withReach(["WIDE1-1", "WIDE2-1"], 1, false)).toEqual(["WIDE2-1"]);
    expect(withReach(["OH2RDK-7", "WIDE2-1"], 3, true)).toEqual(["OH2RDK-7", "WIDE2-2"]);
    expect(withReach(["OH2RDK-7"], 2, true)).toEqual(["OH2RDK-7", "WIDE2-1"]);
    expect(withReach(["OH2RDK-7", "OH2RCH-2"], 2, true)).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(withReach(["OH2RDK-7", "OH2RCH-2", "WIDE2-1"], 1, true)).toEqual(["OH2RDK-7"]);
    expect(withReach(["OH2RDK-7", "OH2RCH-2"], 0, true)).toEqual([]);
  });

  it("is the hops in all of a sound path of no more than three, and none for any other", () => {
    expect(reachOf([])).toBe(0);
    expect(reachOf(["WIDE2-2"])).toBe(2);
    expect(reachOf(["OH2RDK-7", "WIDE2-1"])).toBe(2);
    expect(reachOf(["WIDE1-1", "WIDE2-2"])).toBe(3);
    expect(reachOf(["WIDE2-2", "WIDE2-2"])).toBeNull();
    expect(reachOf(["WIDE1-2"])).toBeNull();
  });

  it("splits a path into the digipeaters named and the aliases after them", () => {
    expect(splitPath(["OH2RDK-7", "WIDE2-1"])).toEqual({ lead: ["OH2RDK-7"], tail: ["WIDE2-1"] });
    expect(splitPath(["WIDE1-1", "WIDE2-1"])).toEqual({ lead: [], tail: ["WIDE1-1", "WIDE2-1"] });
    expect(splitPath(["OH2RDK-7"])).toEqual({ lead: ["OH2RDK-7"], tail: [] });
  });

  it("makes wide hops of any number up to 7 and WIDE1-1 first when asked", () => {
    expect(aliasesFor(4, true)).toEqual(["WIDE1-1", "WIDE3-3"]);
    expect(aliasesFor(9, false)).toEqual(["WIDE7-7"]);
  });
});

describe("a digipeater picked", () => {
  it("takes the place of an alias hop after the ones named, so that the path keeps its hops", () => {
    expect(withCall(["WIDE1-1", "WIDE2-1"], "OH2RDK-7")).toEqual(["OH2RDK-7", "WIDE2-1"]);
    expect(withCall(["OH2RDK-7", "WIDE2-1"], "OH2RCH-2")).toEqual(["OH2RDK-7", "OH2RCH-2"]);
    expect(withCall(["WIDE3-3"], "OH2RDK-7")).toEqual(["OH2RDK-7", "WIDE2-2"]);
  });

  it("is one hop more when the path has no alias hop to give", () => {
    expect(withCall([], "OH2RDK-7")).toEqual(["OH2RDK-7"]);
    expect(withCall(["OH2RDK-7"], "OH2RCH-2")).toEqual(["OH2RDK-7", "OH2RCH-2"]);
  });
});

describe("what a path means", () => {
  it("is a node for each hop: any digi for WIDE1-1, a wide digi for each N of a WIDEn-N, the one named for a call", () => {
    expect(kinds(["WIDE1-1", "WIDE2-1"])).toEqual([["any"], ["wide"]]);
    expect(kinds(["WIDE2-2"])).toEqual([["wide", "wide"]]);
    expect(kinds(["WIDE3-3"])).toEqual([["wide", "wide", "wide"]]);
    expect(kinds(["OH2RDK-7", "WIDE2-1"])).toEqual([["named"], ["wide"]]);
    expect(kinds(["RELAY"])).toEqual([["named"]]);
    expect(meaningOf(["OH2RDK-7", "WIDE2-2"]).parts.map((part) => part.first)).toEqual([1, 2]);
  });

  it("counts the Ns of the aliases and one for each call", () => {
    expect(
      [[], ["WIDE1-1"], ["WIDE2-2"], ["WIDE1-1", "WIDE2-1"], ["WIDE3-3"], ["OH2RDK-7", "WIDE2-1"], ["OH2RDK-7", "OH2RCH-2", "WIDE2-2"]].map(
        (hops) => meaningOf(hops).hops,
      ),
    ).toEqual([0, 1, 2, 2, 3, 2, 4]);
  });

  it("is more than the network usually allows past two hops, with the reason", () => {
    expect(meaningOf(["WIDE2-2"]).level).toBe("ok");
    expect(meaningOf(["WIDE3-3"])).toMatchObject({ level: "many", reason: "3 hops: more than the 2 that most networks allow" });
    expect(meaningOf(["WIDE1-1", "WIDE2-2"]).level).toBe("many");
  });

  it("is no path for an N over n, an N of 0 or an n or N out of 1 to 7, with the reason", () => {
    expect(meaningOf(["WIDE1-2"])).toMatchObject({
      level: "bad",
      reason: "WIDE1-2 is no path: N (2) is never more than n (1); home digipeaters answer only WIDE1-1",
    });
    expect(meaningOf(["WIDE2-3"]).level).toBe("bad");
    expect(meaningOf(["WIDE2-0"])).toMatchObject({ level: "bad", reason: "WIDE2-0 has no hops left: no digipeater repeats it" });
    expect(meaningOf(["WIDE2"]).level).toBe("bad");
    expect(meaningOf(["WIDE8-8"])).toMatchObject({ level: "bad", reason: "WIDE8-8 is no path: in WIDEn-N, n and N go from 1 to 7" });
    expect(kinds(["WIDE1-2"])).toEqual([["none"]]);
    expect(meaningOf(["WIDE1-2", "WIDE2-1"]).hops).toBe(1);
  });
});

describe("home digipeaters for the first hop", () => {
  it("are what the path says: yes for WIDE1-1 first, no for a wide alias first, nothing for none or a call", () => {
    expect(homeFirst(["WIDE1-1", "WIDE2-1"])).toBe(true);
    expect(homeFirst(["WIDE2-1"])).toBe(false);
    expect(homeFirst([])).toBeNull();
    expect(homeFirst(["OH2RDK-7", "WIDE1-1"])).toBeNull();
  });
});
