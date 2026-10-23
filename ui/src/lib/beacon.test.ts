import { describe, expect, it } from "vitest";
import { beaconText, compressedPosition, daoText, phgText, statusText, uncompressedPosition } from "@/lib/beacon";
import { configValues } from "@/test/fixtures";

const settings = (extra: Record<string, string> = {}) => configValues(extra).values;

describe("uncompressedPosition", () => {
  it("writes degrees and minutes to the hundredth, N/S and E/W, the symbol table between the two and the code after", () => {
    expect(uncompressedPosition(60.17, 24.94, "/", "-")).toBe("6010.20N/02456.40E-");
    expect(uncompressedPosition(-33.8688, -151.2093, "\\", ">")).toBe("3352.13S\\15112.56W>");
    expect(uncompressedPosition(0, 0, "/", "-")).toBe("0000.00N/00000.00E-");
  });
  it("carries a rounding that reaches 60 minutes into the degrees", () => {
    expect(uncompressedPosition(59.999999, 24.999999, "/", "-")).toBe("6000.00N/02500.00E-");
  });
});

describe("the DAO", () => {
  it("cuts the position at the hundredth and leaves the digit after it to !Wxy!", () => {
    expect(uncompressedPosition(60.1738, 24.9433, "/", "-", true)).toBe("6010.42N/02456.59E-");
    expect(daoText(60.1738, 24.9433)).toBe("!W88!");
    expect(uncompressedPosition(-33.8688, 151.2093, "/", "-", true)).toBe("3352.12S/15112.55E-");
    expect(daoText(-33.8688, 151.2093)).toBe("!W88!");
    expect(uncompressedPosition(60.1749999, 24.9999999, "/", "-", true)).toBe("6010.50N/02500.00E-");
    expect(daoText(60.1749999, 24.9999999)).toBe("!W00!");
    expect(uncompressedPosition(-0.00001, -0.00001, "/", "-", true)).toBe("0000.00S/00000.00W-");
  });
});

describe("phgText", () => {
  it("is power, height, gain and directivity, as the daemon makes it", () => {
    expect(phgText(2, 3, 2, "omni")).toBe("PHG1020");
    expect(phgText(25, 12, 3, "N")).toBe("PHG5238");
    expect(phgText(25, 6, 3, "E")).toBe("PHG5132");
    expect(phgText(0, 0, 0, "omni")).toBe("PHG0000");
    expect(phgText(9999, 9999, 9, "NW")).toBe("PHG9997");
    expect(["omni", "NE", "E", "SE", "S", "SW", "W", "NW", "N"].map((d) => phgText(1, 0, 0, d).slice(-1))).toEqual("012345678".split(""));
  });
});

describe("compressedPosition", () => {
  it("is 13 characters and writes an overlay digit as a letter", () => {
    const text = compressedPosition(49.5, -72.75, "/", "-");
    expect(text).toHaveLength(13);
    expect(text.startsWith("/")).toBe(true);
    expect(text.endsWith("-  A")).toBe(true);
    expect(compressedPosition(60.17, 24.94, "5", ">")[0]).toBe("f");
  });
  it("is what the daemon makes, which rounds the last cell (the specification's example truncates it: 5L!!<*e7)", () => {
    expect(compressedPosition(49.5, -72.75, "/", "-")).toBe("/5L!!<*e8-  A");
  });
});

describe("beaconText", () => {
  it("is the packet of the default settings", () => {
    expect(beaconText(settings())).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS");
  });
  it("follows the form: the call in capitals, no path, the compressed form", () => {
    expect(beaconText(settings({ "station/call": "oh2gba-9", "beacon/path": "", "station/comment": "" }))).toBe("OH2GBA-9>APZNEO:=6010.20N/02456.40E-");
    expect(beaconText(settings({ "beacon/compressed": "true", "beacon/path": " wide1-1 , " }))).toMatch(/^OH2GBA>APZNEO,WIDE1-1:=\/.{12}NeoAPRS$/);
  });
  it("has the PHG after the symbol and the DAO after the comment, when they are asked for", () => {
    const antenna = { "beacon/power_w": "2", "beacon/antenna_height_m": "3", "beacon/antenna_gain_db": "2" };
    expect(beaconText(settings(antenna))).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-PHG1020NeoAPRS");
    expect(beaconText(settings({ ...antenna, "beacon/dao": "true", "station/lat": "60.1738", "station/lon": "24.9433" }))).toBe(
      "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.42N/02456.59E-PHG1020NeoAPRS!W88!",
    );
    expect(
      beaconText(settings({ "beacon/power_w": "25", "beacon/antenna_height_m": "12", "beacon/antenna_gain_db": "3", "beacon/antenna_direction": "n" })),
    ).toContain("-PHG5238NeoAPRS");
  });
  it("has no PHG without a power, whatever the antenna says, and no DAO in the compressed form", () => {
    expect(beaconText(settings({ "beacon/antenna_height_m": "30", "beacon/antenna_gain_db": "9" }))).toBe(
      "OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS",
    );
    expect(beaconText(settings({ "beacon/compressed": "true", "beacon/dao": "true" }))).toBe(beaconText(settings({ "beacon/compressed": "true" })));
  });
  it("is null while the settings do not make a packet", () => {
    expect(beaconText(settings({ "beacon/power_w": "lots" }))).toBeNull();
    expect(beaconText(settings({ "beacon/power_w": "5", "beacon/antenna_gain_db": "12" }))).toBeNull();
    expect(beaconText(settings({ "beacon/power_w": "5", "beacon/antenna_direction": "up" }))).toBeNull();
    expect(beaconText(settings({ "station/call": "" }))).toBeNull();
    expect(beaconText(settings({ "station/call": "TOOLONGCALL" }))).toBeNull();
    expect(beaconText(settings({ "station/lat": "95" }))).toBeNull();
    expect(beaconText(settings({ "station/lon": "" }))).toBeNull();
    expect(beaconText(settings({ "station/lon": "east" }))).toBeNull();
    expect(beaconText(settings({ "station/symbol_table": "" }))).toBeNull();
    expect(beaconText(settings({ "station/symbol_code": "" }))).toBeNull();
    expect(beaconText(settings({ "beacon/destination": "" }))).toBeNull();
    expect(beaconText(settings({ "beacon/path": "WIDE1-1,BAD CALL" }))).toBeNull();
  });
});

describe("statusText", () => {
  const at = new Date("2026-10-21T12:07:00Z");
  it("is the static status report: the same header, `>`, the day, hour and minute in UTC with a z, then the text", () => {
    expect(statusText(settings({ "station/status": "On the road, QRV 145.500" }), at)).toBe("OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211207zOn the road, QRV 145.500");
    expect(statusText(settings({ "station/status": "x", "station/call": "oh2gba-9", "beacon/path": "" }), new Date("2026-11-03T04:05:00Z"))).toBe(
      "OH2GBA-9>APZNEO:>030405zx",
    );
  });
  it("is null while the status is empty or the settings make no frame", () => {
    expect(statusText(settings(), at)).toBeNull();
    expect(statusText(settings({ "station/status": "   " }), at)).toBeNull();
    expect(statusText(settings({ "station/status": "x", "station/call": "" }), at)).toBeNull();
    expect(statusText(settings({ "station/status": "x", "beacon/path": "BAD CALL" }), at)).toBeNull();
  });
  it("is null while a radio makes the status", () => {
    expect(statusText(settings({ "station/status": "x", "status/rigctld": "127.0.0.1:4532" }), at)).toBeNull();
  });
});
