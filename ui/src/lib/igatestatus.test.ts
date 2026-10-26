import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { igateLook, internetStations } from "@/lib/igatestatus";
import { igateState, station } from "@/test/fixtures";

const values = { "station/call": "OH2GBA-10", "igate/server": "rotate.aprs2.net:14580", "map/radius_km": "50" };

afterEach(() => setLocale("en"));

describe("igateLook", () => {
  it("is connected, in the radio's word and colour, for a login that is up, whatever the daemon says of the login: verified, listening or not accepted", () => {
    for (const state of ["connected", "listening", "unverified"] as const) {
      const look = igateLook(igateState({ state }), values, 42);
      expect([look.state, look.tone, look.line], state).toEqual(["connected", "tnc-connected", "rotate.aprs2.net · 42 stations within 50 km"]);
    }
  });

  it("counts the stations in the line: one, none yet", () => {
    expect(igateLook(igateState(), values, 1).line).toBe("rotate.aprs2.net · 1 station within 50 km");
    expect(igateLook(igateState(), values, 0).line).toBe("rotate.aprs2.net · no stations within 50 km yet");
  });

  it("is stopped and says Off while the switch is off", () => {
    const look = igateLook(igateState({ enabled: false, state: "off", server: "", gated: 0, dropped: {}, last_gated_at: null }), values, 0);
    expect([look.state, look.line]).toEqual(["stopped", "Off"]);
  });

  it("says it is connecting, to the server it names or else to the one of the settings, and why it is not connected, in the radio's words and colours", () => {
    expect(igateLook(igateState({ state: "connecting", server: "T2FINLAND" }), values, 0)).toMatchObject({
      state: "connecting",
      tone: "tnc-connecting",
      line: "Connecting to T2FINLAND…",
    });
    expect(igateLook(igateState({ state: "connecting", server: "" }), values, 0).line).toBe("Connecting to rotate.aprs2.net:14580…");
    expect(igateLook(igateState({ state: "connecting", problem: "Connection refused" }), values, 0)).toMatchObject({
      state: "waiting",
      tone: "tnc-waiting",
      line: "Not connected: Connection refused",
    });
  });

  it("has the server and the filter behind the arrow", () => {
    const look = igateLook(igateState({ server: "T2FINLAND" }), values, 3);
    expect([look.server, look.filter]).toEqual(["Server: T2FINLAND (rotate.aprs2.net:14580)", "Filter: stations within 50 km of your position"]);
    expect(igateLook(igateState({ server: "" }), values, 3).server).toBe("Server: rotate.aprs2.net:14580");
  });

  it("never says gated, a passcode or an iGate, in any language", () => {
    for (const code of ["en", "de", "es", "fr", "it", "ja", "pt-BR"] as const) {
      setLocale(code);
      const said = [igateState(), igateState({ state: "unverified" }), igateState({ state: "connecting" }), igateState({ state: "off" })].map((s) => {
        const look = igateLook(s, values, 2);
        return `${look.state} ${look.line} ${look.server} ${look.filter}`;
      });
      expect(said.join(" "), code).not.toMatch(/gate|passcode|code d|Passcode|Codice|código|パスコード|転送/i);
    }
  });
});

describe("internetStations", () => {
  it("counts the stations heard over the internet, whatever else they were heard by, and not our own", () => {
    const rows = [
      station("A", { heard_is: 3 }),
      station("B", { heard_is: 1, heard_rf: 2 }),
      station("C", { heard_rf: 4 }),
      station("D", { heard_is: 5, is_me: true }),
    ];
    expect(internetStations(rows)).toBe(2);
  });
});
