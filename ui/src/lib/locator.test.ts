import { describe, expect, it } from "vitest";
import { locatorOfText, locatorProblem, locatorToPosition, placeOfText, positionToLocator } from "@/lib/locator";

describe("locatorToPosition", () => {
  it("is the centre of the subsquare of a locator of 6 characters", () => {
    expect(locatorToPosition("KP20ie")).toEqual({ lat: 60.1875, lon: 24.7083 }); // Helsinki
    expect(locatorToPosition("IO91wm")).toEqual({ lat: 51.5208, lon: -0.125 }); // London
    expect(locatorToPosition("JO65ma")).toEqual({ lat: 55.0208, lon: 13.0417 });
    expect(locatorToPosition("AA00aa")).toEqual({ lat: -89.9792, lon: -179.9583 });
    expect(locatorToPosition("RR99xx")).toEqual({ lat: 89.9792, lon: 179.9583 });
  });

  it("takes capitals and small letters alike, and spaces round it", () => {
    expect(locatorToPosition(" kp20IE ")).toEqual(locatorToPosition("KP20ie"));
  });

  it("is the centre of the square for 4 characters and of the finest square for 8", () => {
    expect(locatorToPosition("KP20")).toEqual({ lat: 60.5, lon: 25 });
    expect(locatorToPosition("KP20ie55")).toEqual({ lat: 60.1896, lon: 24.7125 });
  });

  it("is null for what is no locator", () => {
    for (const bad of ["", "KP", "KP2", "KP20i", "KP20ieX", "SS00aa", "KP20yy", "KP2Oie", "1P20ie", "KP20ie5", "KP20ie555"])
      expect(locatorToPosition(bad), bad).toBeNull();
  });
});

describe("positionToLocator", () => {
  it("writes the locator of 6 characters of a position, and its centre is in the same square", () => {
    expect(positionToLocator(60.17, 24.94)).toBe("KP20le");
    expect(positionToLocator(60.1875, 24.7083)).toBe("KP20ie");
    expect(positionToLocator(-33.86, 151.21)).toBe("QF56od");
    const centre = locatorToPosition("JO65ma");
    expect(centre && positionToLocator(centre.lat, centre.lon)).toBe("JO65ma");
  });

  it("holds the corners and refuses a place that is none", () => {
    expect(positionToLocator(-90, -180)).toBe("AA00aa");
    expect(positionToLocator(90, 180)).toBe("RR99xx");
    expect(positionToLocator(91, 0)).toBe("");
    expect(positionToLocator(NaN, 0)).toBe("");
  });
});

describe("placeOfText", () => {
  it("says the place two texts of a form hold in words: degrees with N or S, E or W, and the locator", () => {
    expect(placeOfText("60.17", "24.94")).toBe("60.17 N, 24.94 E · KP20le");
    expect(placeOfText("-33.8568", "-70.1")).toMatch(/^33\.8568 S, 70\.1 W · /);
    expect(placeOfText("60,17", "24,94")).toBe("60.17 N, 24.94 E · KP20le");
  });

  it("is null for what is no place: empty, not numbers, off the earth, or only one of the two", () => {
    for (const [lat, lon] of [
      ["", ""],
      ["x", "24"],
      ["60", ""],
      ["95", "24"],
      ["60", "181"],
    ] as const)
      expect(placeOfText(lat, lon), `${lat} ${lon}`).toBeNull();
  });
});

describe("locatorOfText", () => {
  it("is the locator of the place, and empty when there is none", () => {
    expect(locatorOfText("60.17", "24.94")).toBe("KP20le");
    expect(locatorOfText("95", "24")).toBe("");
    expect(locatorOfText("", "")).toBe("");
  });
});

describe("locatorProblem", () => {
  it("is said once there are 6 characters and they are not a locator, and not while it is being typed (7 is a locator of 8 on the way)", () => {
    expect(locatorProblem("SS00aa")).toBe("Not a locator");
    expect(locatorProblem("KP20iezz")).toBe("Not a locator");
    expect(locatorProblem("KP20i")).toBe("");
    expect(locatorProblem("KP20ie")).toBe("");
    expect(locatorProblem("KP20ie5")).toBe("");
    expect(locatorProblem("")).toBe("");
  });
});
