import { describe, expect, it } from "vitest";
import { callList, normalizeCall, parsePath, qrzUrl, validCall } from "@/lib/calls";

describe("calls", () => {
  it("takes calls with an SSID up to 15, in any case", () => {
    for (const ok of ["OH2RDG", "oh2rdg", " oh2rdg-7 ", "OH2RDG-0", "OH2RDG-15", "A", "WIDE1-1"]) expect(validCall(ok), ok).toBe(true);
    for (const bad of ["", " ", "OH2RDG-16", "OH2RDG-", "TOOLONGCALL", "OH2 RDG", "OH2RDG-1-2", "ÅÄÖ"]) expect(validCall(bad), bad).toBe(false);
    expect(normalizeCall(" oh2rdg-7 ")).toBe("OH2RDG-7");
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
