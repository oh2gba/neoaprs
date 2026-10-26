import { describe, expect, it } from "vitest";
import {
  callInput,
  callList,
  joinCall,
  mayTransmitAs,
  normalizeCall,
  parsePath,
  parsePathSetting,
  pathCalls,
  placeholderCall,
  qrzUrl,
  splitCall,
  SSIDS,
  validCall,
} from "@/lib/calls";

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

describe("calls: the SSID taken apart from the call and put together again", () => {
  it("splits the call the settings keep: the SSID after the dash, none for no SSID and for -0", () => {
    expect(splitCall("OH2GBA-9")).toEqual({ base: "OH2GBA", ssid: "9" });
    expect(splitCall("oh2gba-15")).toEqual({ base: "OH2GBA", ssid: "15" });
    expect(splitCall("OH2GBA-07")).toEqual({ base: "OH2GBA", ssid: "7" });
    expect(splitCall("OH2GBA")).toEqual({ base: "OH2GBA", ssid: "" });
    expect(splitCall("OH2GBA-0")).toEqual({ base: "OH2GBA", ssid: "" });
    expect(splitCall("")).toEqual({ base: "", ssid: "" });
  });

  it("leaves a text that has no SSID of the daemon's kind as it is, all call", () => {
    expect(splitCall("OH2GBA-16")).toEqual({ base: "OH2GBA-16", ssid: "" });
    expect(splitCall("OH2GBA-")).toEqual({ base: "OH2GBA-", ssid: "" });
  });

  it("joins them the way the settings keep a call, and a call that is not there has no SSID", () => {
    expect(joinCall("OH2GBA", "9")).toBe("OH2GBA-9");
    expect(joinCall("OH2GBA", "")).toBe("OH2GBA");
    expect(joinCall("OH2GBA", "0")).toBe("OH2GBA");
    expect(joinCall("", "9")).toBe("");
  });

  it("is the same call after a split and a join, and the SSIDs are 1 to 15", () => {
    for (const call of ["OH2GBA", "OH2GBA-1", "OH2GBA-15", "W1AW-9"]) {
      const { base, ssid } = splitCall(call);
      expect(joinCall(base, ssid), call).toBe(call);
    }
    expect(SSIDS).toHaveLength(15);
    expect(SSIDS[0]).toBe("1");
    expect(SSIDS[14]).toBe("15");
  });
});

describe("calls: what is typed into the field of the call", () => {
  it("is letters and digits in capitals, and nothing else is let in", () => {
    expect(callInput("oh2gba")).toEqual({ base: "OH2GBA", ssid: null, text: "OH2GBA" });
    expect(callInput(" oh2 gba! ")).toEqual({ base: "OH2GBA", ssid: null, text: "OH2GBA" });
    expect(callInput("OH2/GBA")).toEqual({ base: "OH2GBA", ssid: null, text: "OH2GBA" });
    expect(callInput("ÅÄÖ1")).toEqual({ base: "1", ssid: null, text: "1" });
    expect(callInput("")).toEqual({ base: "", ssid: null, text: "" });
  });

  it("takes a dash with a number of 0 to 15 after it as the SSID, and a -0 as none", () => {
    expect(callInput("OH2GBA-9")).toEqual({ base: "OH2GBA", ssid: "9", text: "OH2GBA-9" });
    expect(callInput("oh2gba-15")).toEqual({ base: "OH2GBA", ssid: "15", text: "OH2GBA-15" });
    expect(callInput("OH2GBA-09")).toEqual({ base: "OH2GBA", ssid: "9", text: "OH2GBA-09" });
    expect(callInput("OH2GBA-0")).toEqual({ base: "OH2GBA", ssid: "", text: "OH2GBA-0" });
  });

  it("keeps a dash that is being typed, and a number the dropdown does not have is no SSID", () => {
    expect(callInput("OH2GBA-")).toEqual({ base: "OH2GBA", ssid: null, text: "OH2GBA-" });
    expect(callInput("OH2GBA-16")).toEqual({ base: "OH2GBA", ssid: null, text: "OH2GBA-16" });
    expect(callInput("-9")).toEqual({ base: "", ssid: "9", text: "" });
  });

  it("has no more than one dash and one number: anything else is cleaned to letters and digits", () => {
    expect(callInput("OH2-GBA-9")).toEqual({ base: "OH2GBA9", ssid: null, text: "OH2GBA9" });
    expect(callInput("OH2GBA-9x")).toEqual({ base: "OH2GBA9X", ssid: null, text: "OH2GBA9X" });
  });
});
