import { describe, expect, it } from "vitest";
import { cardLabels, cardRows, hoverRows, thingSub, thingTitle } from "@/lib/layers/card";
import { shipKind } from "@/lib/layers/shipkinds";
import { NOW, ago } from "@/test/fixtures";
import { aircraft, ship } from "@/test/layerfixtures";

const pairs = (rows: { label: string; text: string }[]) => rows.map((row) => [row.label, row.text]);

describe("the card of a thing: its title", () => {
  it("names an aircraft by its flight, else its registration, else its address in capitals", () => {
    expect(thingTitle("aircraft", aircraft())).toBe("FIN7AB");
    expect(thingTitle("aircraft", aircraft({ name: "" }))).toBe("OH-LZA");
    expect(thingTitle("aircraft", aircraft({ name: "", registration: "", id: "~4ca1fe" }))).toBe("~4CA1FE");
  });

  it("names a ship by its name, else by its MMSI", () => {
    expect(thingTitle("ships", ship())).toBe("MADE UP STAR");
    expect(thingTitle("ships", ship({ name: "" }))).toBe("MMSI 230123456");
  });

  it("says under the title what kind of thing it is", () => {
    expect(thingSub("aircraft")).toBe("Aircraft");
    expect(thingSub("ships")).toBe("Ship");
  });
});

describe("the card of a thing: its rows", () => {
  it("has an aircraft's registration beside its flight, type, altitude, speed, heading and age, then the source", () => {
    expect(pairs(cardRows("aircraft", aircraft({ at: ago(12) }), "adsbfi", NOW))).toEqual([
      ["Registration", "OH-LZA"],
      ["Type", "AIRBUS A-321"],
      ["Altitude", "2438 m"],
      ["Speed", "421 km/h"],
      ["Heading", "225° SW"],
      ["Age", "12 s"],
      ["Source", "adsb.fi"],
    ]);
  });

  it("says an aircraft's vertical speed straight after its altitude with its sign, level flight as 0, and has no row where its source told none", () => {
    const rows = (v: number | null) =>
      pairs(cardRows("aircraft", aircraft({ at: ago(12), vertical_ms: v }), "radarcape", NOW));
    expect(rows(3.2)).toContainEqual(["Vertical speed", "+3.2 m/s"]);
    expect(rows(-10.7)).toContainEqual(["Vertical speed", "\u221210.7 m/s"]);
    expect(rows(0)).toContainEqual(["Vertical speed", "0 m/s"]);
    const labels = rows(3.2).map(([label]) => label);
    expect(labels.indexOf("Vertical speed")).toBe(labels.indexOf("Altitude") + 1);
    expect(rows(null).map(([label]) => label)).not.toContain("Vertical speed");
    expect(
      pairs(hoverRows("aircraft", aircraft({ at: ago(12), vertical_ms: 3.2 }), NOW)).map(([label]) => label),
    ).not.toContain("Vertical speed");
  });

  it("leaves out a row that has nothing, and the registration where it is the title", () => {
    const bare = aircraft({ name: "", type: "", altitude_m: null, speed_kmh: null, heading_deg: null, at: ago(3) });
    expect(pairs(cardRows("aircraft", bare, "receiver", NOW))).toEqual([
      ["Age", "3 s"],
      ["Source", "My own receiver"],
    ]);
  });

  it("ends a Radarcape's aircraft with Radarcape and the other own receiver's with My own receiver", () => {
    const bare = aircraft({ name: "", type: "", altitude_m: null, speed_kmh: null, heading_deg: null, at: ago(3) });
    expect(pairs(cardRows("aircraft", bare, "radarcape", NOW)).at(-1)).toEqual(["Source", "Radarcape"]);
    expect(pairs(cardRows("aircraft", bare, "receiver", NOW)).at(-1)).toEqual(["Source", "My own receiver"]);
  });

  it("says where an aircraft came from and where it goes as the place with the code in brackets, after its type and before its altitude", () => {
    const flying = aircraft({
      at: ago(12),
      origin: "ESSA",
      origin_place: "Stockholm",
      destination: "EFHK",
      destination_place: "Helsinki",
    });
    expect(pairs(cardRows("aircraft", flying, "radarcape", NOW))).toEqual([
      ["Registration", "OH-LZA"],
      ["Type", "AIRBUS A-321"],
      ["From", "Stockholm (ESSA)"],
      ["To", "Helsinki (EFHK)"],
      ["Altitude", "2438 m"],
      ["Speed", "421 km/h"],
      ["Heading", "225° SW"],
      ["Age", "12 s"],
      ["Source", "Radarcape"],
    ]);
  });

  it("says an airport the table does not know by its code alone, and leaves out From or To where there is no code", () => {
    const rows = (extra: Parameters<typeof aircraft>[0]) =>
      pairs(cardRows("aircraft", aircraft({ at: ago(1), ...extra }), "radarcape", NOW)).filter(
        ([label]) => label === "From" || label === "To",
      );
    expect(rows({ origin: "ZZZZ", destination: "EFHK", destination_place: "Helsinki" })).toEqual([
      ["From", "ZZZZ"],
      ["To", "Helsinki (EFHK)"],
    ]);
    expect(rows({ destination: "EFHK", destination_place: "Helsinki" })).toEqual([["To", "Helsinki (EFHK)"]]);
    expect(rows({})).toEqual([]);
  });

  it("prints a Radarcape's 16 050 ft, which the daemon sends as 4892 m, as 4892 m", () => {
    expect(pairs(cardRows("aircraft", aircraft({ altitude_m: 4892, at: ago(1) }), "radarcape", NOW))).toContainEqual([
      "Altitude",
      "4892 m",
    ]);
  });

  it("names every row a card of its layer may have, whatever the thing tells now, so that the card can keep the room of the widest label", () => {
    const bare = aircraft({
      name: "",
      registration: "",
      type: "",
      altitude_m: null,
      vertical_ms: null,
      speed_kmh: null,
      heading_deg: null,
      at: ago(1),
    });
    const all = [
      "Registration",
      "Type",
      "From",
      "To",
      "Altitude",
      "Vertical speed",
      "Speed",
      "Heading",
      "Age",
      "Source",
    ];
    expect(cardLabels("aircraft", bare, "receiver")).toEqual(all);
    expect(
      cardLabels(
        "aircraft",
        aircraft({ at: ago(1), origin: "ESSA", destination: "EFHK", vertical_ms: 3.2 }),
        "radarcape",
      ),
    ).toEqual(all);
    expect(cardLabels("ships", ship({ at: ago(1) }), "fintraffic")).toEqual([
      "Kind",
      "Speed",
      "Course",
      "Destination",
      "Age",
      "Source",
    ]);
  });

  it("has a ship's kind, speed, course, destination and age, then the source", () => {
    expect(pairs(cardRows("ships", ship({ at: ago(120) }), "fintraffic", NOW))).toEqual([
      ["Kind", "Passenger ship"],
      ["Speed", "22 km/h"],
      ["Course", "182° S"],
      ["Destination", "TALLINN"],
      ["Age", "2 min"],
      ["Source", "Fintraffic"],
    ]);
    expect(
      pairs(
        cardRows(
          "ships",
          ship({ ship_type: null, course_deg: null, destination: "", speed_kmh: null, at: ago(1) }),
          "receiver",
          NOW,
        ),
      ),
    ).toEqual([
      ["Age", "1 s"],
      ["Source", "My own receiver"],
    ]);
  });

  it("has nothing of a station: no path, no packets, no message", () => {
    const labels = [
      ...cardRows("aircraft", aircraft(), "adsblol", NOW),
      ...cardRows("ships", ship(), "fintraffic", NOW),
    ].map((row) => row.label);
    for (const word of ["Path", "Packets", "Message", "Comment", "Last heard"]) expect(labels).not.toContain(word);
  });
});

describe("the hover box of a thing", () => {
  it("has an aircraft's altitude, speed and age", () => {
    expect(pairs(hoverRows("aircraft", aircraft({ at: ago(4) }), NOW))).toEqual([
      ["Altitude", "2438 m"],
      ["Speed", "421 km/h"],
      ["Age", "4 s"],
    ]);
  });

  it("has a ship's speed, course, destination and age", () => {
    expect(pairs(hoverRows("ships", ship({ at: ago(4) }), NOW))).toEqual([
      ["Speed", "22 km/h"],
      ["Course", "182° S"],
      ["Destination", "TALLINN"],
      ["Age", "4 s"],
    ]);
  });
});

describe("the kinds of ship", () => {
  it("names a kind by its figure or its ten, and none for a type that names no kind", () => {
    const kinds: [number | null, string | null][] = [
      [30, "layers.kind.fishing"],
      [31, "layers.kind.towing"],
      [36, "layers.kind.sailing"],
      [37, "layers.kind.pleasure"],
      [52, "layers.kind.tug"],
      [55, "layers.kind.law"],
      [60, "layers.kind.passenger"],
      [69, "layers.kind.passenger"],
      [70, "layers.kind.cargo"],
      [84, "layers.kind.tanker"],
      [99, "layers.kind.other"],
      [21, "layers.kind.wing_in_ground"],
      [45, "layers.kind.high_speed"],
      [1, null],
      [19, null],
      [38, null],
      [56, null],
      [57, null],
      [null, null],
      [0, null],
      [100, null],
    ];
    for (const [type, kind] of kinds) expect([type, shipKind(type)]).toEqual([type, kind]);
  });
});
