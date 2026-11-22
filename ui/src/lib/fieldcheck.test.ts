import { describe, expect, it } from "vitest";
import { onEarth, pairProblems, problemOf, sameValue } from "@/lib/fieldcheck";
import { LIMITS } from "@/protocol/lists";

describe("problemOf", () => {
  it("says the range of a whole number in the daemon's own figures", () => {
    for (const [key, { min, max }] of Object.entries(LIMITS.range)) {
      if (
        ![
          "serial/baud",
          "tcp/port",
          "beacon/power_w",
          "beacon/antenna_height_m",
          "beacon/antenna_gain_db",
          "map/radius_km",
        ].includes(key)
      )
        continue;
      expect(problemOf(key, String(min)), key).toBe("");
      expect(problemOf(key, String(max)), key).toBe("");
      expect(problemOf(key, String(max + 1)), key).toBe(`${min} to ${max}`);
    }
  });

  it("takes an empty field as a value where the setting has one, and in the guide (quiet) everywhere", () => {
    expect(problemOf("serial/baud", "")).toBe("");
    expect(problemOf("beacon/power_w", " ")).toBe("");
    expect(problemOf("tcp/port", "")).toBe("1 to 65535");
    expect(problemOf("tcp/port", "", true)).toBe("");
    expect(problemOf("map/radius_km", "", true)).toBe("");
    expect(problemOf("tcp/host", "")).toBe("Not an address");
    expect(problemOf("tcp/host", "", true)).toBe("");
    expect(problemOf("tcp/host", "a b", true)).toBe("Not an address");
  });

  it("says the most digipeaters a path may have", () => {
    expect(problemOf("beacon/path", "A,B,C,D,E,F,G,H,I")).toBe(
      `Calls separated by commas, ${LIMITS.path.maxCalls} at the most`,
    );
  });

  it("has nothing against a key it does not check", () => {
    expect(problemOf("station/comment", "x".repeat(100))).toBe("");
  });
});

describe("sameValue and pairProblems", () => {
  it("know a position or a number however it is written", () => {
    expect(sameValue("station/lat", "60.170", "60.17")).toBe(true);
    expect(sameValue("station/call", "oh2gba", "OH2GBA")).toBe(true);
    expect(sameValue("tcp/port", "8001 ", "8001")).toBe(true);
    expect(sameValue("station/comment", "a", "b")).toBe(false);
  });

  it("want both halves of a position", () => {
    expect(pairProblems(["station/lat", "station/lon"], { "station/lat": "60", "station/lon": "" })).toEqual({
      "station/lon": "Needed with the latitude",
    });
    expect(pairProblems(["station/lat"], { "station/lat": "60" })).toEqual({});
  });
});

describe("onEarth", () => {
  it("is a latitude and a longitude within the settings' limits", () => {
    expect(onEarth(90, 180)).toBe(true);
    expect(onEarth(-90, -180)).toBe(true);
    expect(onEarth(90.1, 0)).toBe(false);
    expect(onEarth(0, -180.1)).toBe(false);
  });
});

describe("a radio's own setting", () => {
  it("is checked as the same field of the radios of before: a speed, a TCP port and a host by their rules", () => {
    expect(problemOf("radio/3/baud", "12")).toBe(problemOf("serial/baud", "12"));
    expect(problemOf("radio/3/baud", "")).toBe("");
    expect(problemOf("radio/5/tcp_port", "70000")).toBe(problemOf("tcp/port", "70000"));
    expect(problemOf("radio/5/tcp_host", "a b")).toBe(problemOf("tcp/host", "a b"));
    expect(problemOf("radio/5/tcp_host", "a b")).not.toBe("");
    expect(problemOf("radio/6/keying", "anything")).toBe("");
    expect([sameValue("radio/3/baud", "09600", "9600"), sameValue("radio/3/port", "a", "b")]).toEqual([true, false]);
  });
});
