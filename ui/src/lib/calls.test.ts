import { describe, expect, it } from "vitest";
import { callList, mayTransmitAs, normalizeCall, parsePath, parsePathSetting, pathCalls, placeholderCall, qrzUrl, validCall } from "@/lib/calls";

describe("calls", () => {
  it("takes calls with an SSID up to 15, in any case", () => {
    for (const ok of ["OH2RDG", "oh2rdg", " oh2rdg-7 ", "OH2RDG-0", "OH2RDG-15", "A", "WIDE1-1"]) expect(validCall(ok), ok).toBe(true);
    for (const bad of ["", " ", "OH2RDG-16", "OH2RDG-", "TOOLONGCALL", "OH2 RDG", "OH2RDG-1-2", "ÅÄÖ"]) expect(validCall(bad), bad).toBe(false);
    expect(normalizeCall(" oh2rdg-7 ")).toBe("OH2RDG-7");
  });

  it("takes the SSID with a leading zero and nothing but ASCII, as the daemon does", () => {
    for (const ok of ["OH2RDG-07", "OH2RDG-00", "oh2rdg-15"]) expect(validCall(ok), ok).toBe(true);
    for (const bad of ["OH2RDG-007", "OH2RDG-16", "\u00df1A", "OH2RD\u00c4"]) expect(validCall(bad), bad).toBe(false);
  });

  it("tells the calls a station may transmit under from the ones that merely parse", () => {
    for (const ok of ["OH2RDG", "oh2rdg-7", "A1B", "W1AW"]) expect(mayTransmitAs(ok), ok).toBe(true);
    for (const bad of ["N0CALL", "nocall-5", "MYCALL", "AB", "ABC", "123", "WIDE1-1X", "OH2RDG-16", ""]) expect(mayTransmitAs(bad), bad).toBe(false);
    expect(placeholderCall("n0call-9")).toBe(true);
    expect(placeholderCall("OH2RDG")).toBe(false);
    expect(validCall("WIDE1-1") && !mayTransmitAs("TCPIP")).toBe(true);
  });

  it("reads a list separated by commas as calls are typed, leaving out the empty pieces", () => {
    expect(callList(" wide1-1 , ,wide2-1,")).toEqual(["WIDE1-1", "WIDE2-1"]);
    expect(callList("")).toEqual([]);
    expect(callList("BAD CALL")).toEqual(["BAD CALL"]);
  });
});

describe("calls: a path", () => {
  it("is calls separated by commas, at most 8, in capitals; empty is a path with none", () => {
    expect(parsePath(" wide1-1 , wide2-1,")).toEqual(["WIDE1-1", "WIDE2-1"]);
    expect(parsePath("")).toEqual([]);
    expect(parsePath("OH2RCH-2")).toEqual(["OH2RCH-2"]);
    expect(parsePath("A,B,C,D,E,F,G,H")).toHaveLength(8);
    expect(parsePath("A,B,C,D,E,F,G,H,I")).toBeNull();
    expect(parsePath("WIDE 1")).toBeNull();
    expect(parsePath("WIDE1-16")).toBeNull();
    expect(parsePath("DIRECT")).toBeNull(); // (DIRECT is no digipeater: the word for none, see parsePathSetting)
  });
});

describe("calls: the QRZ page", () => {
  it("is the base call's, with the SSID off, in capitals", () => {
    expect(qrzUrl("OH2GBA-7")).toBe("https://www.qrz.com/db/OH2GBA");
    expect(qrzUrl(" oh2gba ")).toBe("https://www.qrz.com/db/OH2GBA");
    expect(qrzUrl("OH2RCH-15")).toBe("https://www.qrz.com/db/OH2RCH");
  });

  it("is none for a name that is no call", () => {
    for (const name of ["Big Storm", "OH2GBA-16", "TOOLONGCALL", ""]) expect(qrzUrl(name)).toBeNull();
  });
});

describe("a path setting", () => {
  it("is empty (automatic or recommended), the word DIRECT (no digipeaters), or digipeaters", () => {
    expect(parsePathSetting("")).toEqual({ kind: "auto" });
    expect(parsePathSetting("  , ")).toEqual({ kind: "auto" });
    expect(parsePathSetting(" direct ")).toEqual({ kind: "direct" });
    expect(parsePathSetting("wide1-1, wide2-1")).toEqual({ kind: "calls", calls: ["WIDE1-1", "WIDE2-1"] });
  });

  it("is none when the word is among calls, a piece is no call or there are too many", () => {
    expect(parsePathSetting("DIRECT,WIDE1-1")).toBeNull();
    expect(parsePathSetting("WIDE1-1,direct")).toBeNull();
    expect(parsePathSetting("WIDE 1")).toBeNull();
    expect(parsePathSetting("A,B,C,D,E,F,G,H,I")).toBeNull();
  });

  it("stands for the recommended calls when empty, for none at all as DIRECT, else for the calls", () => {
    expect(pathCalls("", "WIDE1-1,WIDE2-1")).toEqual(["WIDE1-1", "WIDE2-1"]);
    expect(pathCalls("", "WIDE2-1")).toEqual(["WIDE2-1"]);
    expect(pathCalls("direct", "WIDE2-1")).toEqual([]);
    expect(pathCalls("wide2-2", "WIDE2-1")).toEqual(["WIDE2-2"]);
    expect(pathCalls("DIRECT,A1", "WIDE2-1")).toBeNull();
  });
});
