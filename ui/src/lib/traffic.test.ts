// The ships and the aircraft of the map in the page's words (lib/traffic.ts): the features the layers draw (the icon by the colour group or the kind, turned by the bearing, a round one for a still ship, the full name, the
// picked one), the facts of the card in their order and units, and the status row of each feed in each state.
import { describe, expect, it } from "vitest";
import { aircraftFacts, aircraftFeatures, aircraftName, feedLook, shipFacts, shipFeatures, shipName, trafficTitle } from "@/lib/traffic";
import { NOW, aircraftRow, feedState, ship } from "@/test/fixtures";

const props = (collection: { features: { properties: object }[] }) => collection.features.map((f) => f.properties);

describe("the features of the map", () => {
  it("draw a ship in the colour of its group, turned the way it heads, with its full name, and a still one round", () => {
    const rows = [ship(), ship({ mmsi: 230000001, name: "", category: "cargo", bearing_deg: null })];
    expect(props(shipFeatures(rows, "230145760"))).toEqual([
      { key: "230145760", icon: "ship-special", rotate: 101, label: "DUNKER", picked: 1 },
      { key: "230000001", icon: "ship-cargo-still", rotate: 0, label: "MMSI 230000001", picked: 0 },
    ]);
    expect(shipFeatures(rows, null).features[0]?.geometry.coordinates).toEqual([24.95, 60.16]);
  });

  it("draw an aircraft by its kind, turned by its track, named by its flight or else its registration or address, and red in an emergency", () => {
    const rows = [aircraftRow(), aircraftRow({ hex: "abc123", flight: "", registration: "", kind: "rotor", emergency: "general", track_deg: null })];
    expect(props(aircraftFeatures(rows, "abc123"))).toEqual([
      { key: "461fa7", icon: "aircraft-jet", rotate: 84, label: "FIN1336", picked: 0 },
      { key: "abc123", icon: "aircraft-rotor-alert", rotate: 0, label: "ABC123", picked: 1 },
    ]);
    expect(aircraftName(aircraftRow({ flight: "" }))).toBe("OH-LZR");
  });
});

describe("the card", () => {
  it("has the facts of a ship in the units of the sea, and leaves out what it does not know", () => {
    const facts = Object.fromEntries(shipFacts(ship(), NOW).map((f) => [f.label, f.value]));
    expect(Object.keys(facts)).toEqual([
      "Type",
      "MMSI",
      "Call sign",
      "IMO",
      "Status",
      "Speed",
      "Course",
      "Heading",
      "Size",
      "Draught",
      "Destination",
      "ETA",
      "Distance",
      "Position",
      "Heard",
    ]);
    expect(facts).toMatchObject({
      Type: "Tug",
      Status: "Moored",
      Speed: "0.0 kn",
      Heading: "101°",
      Size: "31 × 10 m",
      Draught: "5.0 m",
      Destination: "HARBOUR ASSISTANCE",
      Distance: "1.2 km",
    });
    const bare = shipFacts(
      ship({ call_sign: "", imo: null, nav_status: null, length_m: null, beam_m: null, draught_m: null, destination: "", eta: null, heading_deg: null }),
      NOW,
    );
    expect(bare.map((f) => f.label)).toEqual(["Type", "MMSI", "Speed", "Course", "Distance", "Position", "Heard"]);
  });

  it("has the facts of an aircraft in feet and knots with the metric figure beside", () => {
    const facts = Object.fromEntries(aircraftFacts(aircraftRow(), NOW).map((f) => [f.label, f.value]));
    expect(facts).toMatchObject({
      Type: "AIRBUS A-321 (A321)",
      Flight: "FIN1336",
      "ICAO address": "461FA7",
      Altitude: "3850 ft (1173 m)",
      Speed: "220 kn (408 km/h)",
      "Vertical rate": "-640 ft/min",
    });
    expect(aircraftFacts(aircraftRow({ on_ground: true, altitude_ft: null, emergency: "minfuel" }), NOW).slice(0, 1)).toEqual([
      { label: "Emergency", value: "Minimum fuel" },
    ]);
    expect(Object.fromEntries(aircraftFacts(aircraftRow({ on_ground: true }), NOW).map((f) => [f.label, f.value])).Altitude).toBe("On the ground");
  });

  it("is titled by the full name", () => {
    expect(trafficTitle({ kind: "ship", key: "230145760" }, ship(), undefined)).toBe("Ship DUNKER");
    expect(trafficTitle({ kind: "aircraft", key: "461fa7" }, undefined, aircraftRow())).toBe("Aircraft FIN1336");
    expect(shipName(ship({ name: "" }))).toBe("MMSI 230145760");
  });
});

describe("the status row of a feed", () => {
  it("says what it receives, what it waits for and why it fails", () => {
    expect(feedLook("ais", feedState())).toMatchObject({ state: "receiving", tone: "tnc-connected", line: "Digitraffic · 3 ships within 450 km" });
    expect(feedLook("adsb", feedState({ count: 1 })).line).toBe("adsb.fi · 1 aircraft within 450 km");
    expect(feedLook("ais", feedState({ count: 0 })).line).toBe("Digitraffic · no ships within 450 km");
    expect(feedLook("ais", feedState({ state: "waiting" }))).toMatchObject({ tone: "tnc-waiting", line: "Waiting for your position" });
    expect(feedLook("adsb", feedState({ state: "failing", problem: "HTTP 503" }))).toMatchObject({ state: "not reachable", line: "adsb.fi: HTTP 503" });
    expect(feedLook("ais", feedState({ state: "connecting", updated_at: null }))).toMatchObject({ line: "Asking Digitraffic…", updated: "" });
    expect(feedLook("ais", feedState({ state: "off" })).line).toBe("Off");
    expect(feedLook("ais", feedState()).licence).toBe("Data: Fintraffic / digitraffic.fi, licence CC BY 4.0");
  });
});
