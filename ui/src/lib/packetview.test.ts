import { describe, expect, it } from "vitest";
import { kindWords, packetFacts } from "@/lib/packetview";
import { packet } from "@/test/fixtures";
import type { PacketRow } from "@/protocol/protocol";

const withDecoded = (extra: Partial<PacketRow>, decoded: unknown): PacketRow => ({ ...packet(1, extra), decoded: decoded as PacketRow["decoded"] });
const facts = (row: PacketRow) => Object.fromEntries(packetFacts(row).map((f) => [f.label, f.text]));
const position = {
  lat: 60.164,
  lon: 24.88,
  symbol_table: "/",
  symbol_code: ">",
  comment: "Pekka on the road",
  course_deg: 96,
  speed_kmh: 85,
  altitude_m: 31,
  timestamp: null,
  messaging: false,
  compressed: false,
  ambiguity: 0,
  weather: null,
  extensions: null,
  timestamp_local: false,
  locator: null,
  frequency: null,
  storm: null,
  sign: null,
};

describe("packetFacts", () => {
  it("tells who sent a position, what kind of packet it is, where, how it moves, and how it reached us", () => {
    const row = withDecoded({ source: "OH2ZMA-9", route: "via OH2RCH-2" }, { type: "position", ...position });
    const f = facts(row);
    expect(f["From"]).toBe("OH2ZMA-9");
    expect(f["Kind"]).toBe("Position report");
    expect(f["Position"]).toBe("60.16400 N 24.88000 E");
    expect(f["Speed"]).toBe("85 km/h, course 96° E");
    expect(f["Altitude"]).toBe("31 m");
    expect(f["Comment"]).toBe("Pekka on the road");
    expect(f["Reached us"]).toBe("via OH2RCH-2");
    expect(f["Heard"]).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
    expect(packetFacts(row).find((x) => x.label === "Reached us")?.route).toBe(true);
  });

  it("says the channel a packet that was heard came by: RF, iGate or Internet, with what it means, and for the internet the path of the line", () => {
    const radio = facts(withDecoded({}, { type: "position", ...position }));
    expect(radio["Came by"]).toBe("RF - Heard on the radio");
    const gated = facts(withDecoded({ via: "rf-gated", gate: "OH7JHF-1", route: "via OH7JHF-1 (internet) → OH2RCH-3" }, { type: "position", ...position }));
    expect(gated["Came by"]).toBe("iGate - Heard on the radio from an iGate, which took it from the internet");
    const net = facts(withDecoded({ via: "is", route: "", path: ["TCPIP*", "qAC", "T2FINLAND"], source: "OH2ABC" }, { type: "position", ...position }));
    expect(net["Came by"]).toBe("Internet - Received over the internet (APRS-IS), not on the radio");
    expect(net["Path"]).toBe("TCPIP*,qAC,T2FINLAND");
    expect(net).not.toHaveProperty("Reached us");
  });

  it("does not say it for a packet we sent: that is the path we sent it by", () => {
    const sent = facts(withDecoded({ direction: "out", route: "", path: ["WIDE1-1"] }, { type: "position", ...position }));
    expect(sent).not.toHaveProperty("Came by");
    expect(sent["Sent via"]).toBe("WIDE1-1");
  });

  it("leaves out the speed of a station that stands still, an empty comment and a route that is none", () => {
    const f = facts(withDecoded({ route: "" }, { type: "position", ...position, speed_kmh: 0, comment: "" }));
    expect(f).not.toHaveProperty("Speed");
    expect(f).not.toHaveProperty("Comment");
    expect(f).not.toHaveProperty("Reached us");
  });

  it("says a position is approximate when digits of it were blanked out", () => {
    expect(facts(withDecoded({}, { type: "position", ...position, ambiguity: 2 }))["Position"]).toBe("60.16400 N 24.88000 E (approximate)");
  });

  it("tells a message with its addressee and its text, and an ack in words", () => {
    const text = { type: "message", addressee: "BLNL", text: "Field day at the lake", msg_id: null, ack_id: null, rej_id: null };
    expect(facts(withDecoded({ kind: "message" }, text))).toMatchObject({ Kind: "Message", To: "BLNL", Text: "Field day at the lake" });
    expect(facts(withDecoded({ kind: "message" }, { ...text, text: "", ack_id: "12" }))).toMatchObject({ To: "BLNL", Says: "received message 12" });
    expect(facts(withDecoded({ kind: "message" }, { ...text, text: "", rej_id: "12" }))).toMatchObject({ Says: "refuses message 12" });
  });

  it("tells an object with its name and its position, and one that is taken down", () => {
    const object = { type: "object", name: "MEETSPOT", alive: true, position, timestamp: null };
    expect(facts(withDecoded({ kind: "object" }, object))).toMatchObject({ Kind: "Object", Name: "MEETSPOT", Position: "60.16400 N 24.88000 E" });
    expect(facts(withDecoded({ kind: "object" }, { ...object, alive: false }))["Name"]).toBe("MEETSPOT (taken down)");
  });

  it("tells a status, a telemetry report, a packet not decoded and one of another kind", () => {
    expect(facts(withDecoded({ kind: "status" }, { type: "status", text: "on air", timestamp: null, locator: null, frequency: null }))).toMatchObject({
      Kind: "Status report",
      Status: "on air",
    });
    expect(facts(withDecoded({ kind: "other" }, { type: "telemetry", sequence: 5, analog: [], bits: "", comment: "" }))).toMatchObject({
      Kind: "Telemetry report",
      Report: "number 5",
    });
    expect(facts(withDecoded({ kind: "undecoded" }, { type: "undecoded", error: "no position", text: "!junk" }))).toMatchObject({
      Kind: "Could not be read",
      Why: "no position",
      Text: "!junk",
    });
    expect(facts(withDecoded({ kind: "other" }, { type: "other", kind: "weather", text: "_1234", weather: null, items: null, timestamp: null }))).toMatchObject(
      { Kind: "Weather report" },
    );
  });

  it("tells the weather a station sent with its position", () => {
    const weather = {
      wind_dir: 216,
      wind_kmh: 6,
      gust_kmh: 13,
      temp_c: 7.8,
      humidity: 79,
      pressure_hpa: 1021.5,
      rain_1h_mm: 0,
      rain_24h_mm: 7.4,
      rain_today_mm: 5.1,
      luminosity: null,
      snow_mm: null,
      rain_counter: null,
      raw: "",
    };
    expect(facts(withDecoded({}, { type: "position", ...position, weather }))["Weather"]).toBe("7.8 °C, wind 6 km/h");
  });

  it("tells a packet of ours by the path it was sent by, and says direct for none", () => {
    const sent = packetFacts(withDecoded({ direction: "out", source: "OH2GBA", route: "", path: ["WIDE1-1", "WIDE2-1"] }, { type: "position", ...position }));
    expect(sent.find((f) => f.label === "Sent via")?.text).toBe("WIDE1-1,WIDE2-1");
    expect(sent.map((f) => f.label)).toContain("Sent");
    expect(sent.map((f) => f.label)).not.toContain("Reached us");
    expect(facts(withDecoded({ direction: "out", route: "", path: [] }, { type: "position", ...position }))["Sent via"]).toBe("direct");
  });

  it("says the time the packet carries, in the sender's local clock when it was sent so", () => {
    const f = facts(withDecoded({}, { type: "position", ...position, timestamp: "2026-10-09T23:45:00.000000Z", timestamp_local: true }));
    expect(f["Time in the packet"]).toBe("09 23:45 local");
  });
});

describe("kindWords", () => {
  it("names a kind the way a person would", () => {
    expect(kindWords(packet(1))).toBe("Position report");
    expect(kindWords(withDecoded({ kind: "other" }, { type: "other", kind: "query", text: "?APRS?", weather: null, items: null, timestamp: null }))).toBe(
      "Query",
    );
    expect(kindWords(withDecoded({ kind: "other" }, { type: "other", kind: "agrelo-df", text: "", weather: null, items: null, timestamp: null }))).toBe(
      "Other packet (agrelo-df)",
    );
  });
});

describe("packetFacts of the local information", () => {
  const frequency = {
    mhz: 145.775,
    tone_hz: 118,
    tone_both: false,
    tone_off: false,
    dcs: null,
    tone_burst: false,
    narrow: false,
    offset_khz: -600,
    range_km: null,
    rx_mhz: null,
  };
  it("tells the frequency, the storm and the sign of a position, and the frequency of a status", () => {
    const storm = {
      storm_type: "TS",
      wind_kmh: 90,
      gust_kmh: null,
      pressure_hpa: null,
      hurricane_radius_km: null,
      storm_radius_km: 55.6,
      gale_radius_km: null,
    };
    const f = facts(withDecoded({}, { type: "object", name: "BRENDA", alive: true, timestamp: null, position: { ...position, frequency, storm, sign: "55" } }));
    expect(f["Frequency"]).toBe("145.775 MHz, tone 118 Hz, -600 kHz");
    expect(f["Storm"]).toBe("Tropical storm, wind 90 km/h, tropical storm winds out to 56 km");
    expect(f["Sign"]).toBe("55");
    const status = facts(withDecoded({}, { type: "status", text: "net tonight", timestamp: null, locator: null, frequency }));
    expect(status["Frequency"]).toBe("145.775 MHz, tone 118 Hz, -600 kHz");
    expect(status["Status"]).toBe("net tonight");
    expect(Object.keys(facts(withDecoded({}, { type: "status", text: "", timestamp: null, locator: null, frequency })))).not.toContain("Status");
  });
});
