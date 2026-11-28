import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { igateLook, internetStations } from "@/lib/igatestatus";
import { igateState, station } from "@/test/fixtures";

const values = { "station/call": "OH2GBA-10", "igate/server": "rotate.aprs2.net:14580", "map/radius_km": "50" };

afterEach(() => setLocale("en"));

describe("igateLook", () => {
  it("is connected, in the radio's word and colour, for a login that only shows the stations and is up, whatever the daemon says of the login: verified, listening or not accepted", () => {
    for (const state of ["connected", "listening", "unverified"] as const) {
      const look = igateLook(igateState({ state, gate: false }), values, 42);
      expect([look.state, look.tone, look.line], state).toEqual([
        "connected",
        "tnc-connected",
        "rotate.aprs2.net · 42 stations within 50 km",
      ]);
    }
  });

  it("says what was sent while only Send what I hear is on, and has no filter behind the arrow", () => {
    const look = igateLook(igateState({ enabled: false, gate: true, gated: 812 }), values, 42);
    expect([look.state, look.tone, look.line, look.filter, look.sent]).toEqual([
      "connected",
      "tnc-connected",
      "rotate.aprs2.net · 812 packets sent",
      "",
      "Sent: 812 packets since NeoAPRS started",
    ]);
    expect(igateLook(igateState({ enabled: false, gate: true, gated: 0 }), values, 0).line).toBe(
      "rotate.aprs2.net · nothing sent yet",
    );
  });

  it("says the stations with both on, and what was sent behind the arrow", () => {
    const look = igateLook(igateState({ gated: 1 }), values, 3);
    expect([look.line, look.filter, look.sent]).toEqual([
      "rotate.aprs2.net · 3 stations within 50 km",
      "Filter: stations within 50 km of your position",
      "Sent: 1 packet since NeoAPRS started",
    ]);
    expect(igateLook(igateState({ gate: false }), values, 3).sent).toBe("");
  });

  it("is waiting and says nothing is sent when Send what I hear is on and the server did not take the login", () => {
    for (const enabled of [true, false])
      expect(
        igateLook(igateState({ enabled, gate: true, state: "unverified", reason: "unverified" }), values, 3),
      ).toMatchObject({
        state: "waiting",
        tone: "tnc-waiting",
        line: "Not sending: the server did not accept the login",
      });
  });

  it("counts the stations in the line: one, none yet", () => {
    expect(igateLook(igateState(), values, 1).line).toBe("rotate.aprs2.net · 1 station within 50 km");
    expect(igateLook(igateState(), values, 0).line).toBe("rotate.aprs2.net · no stations within 50 km yet");
  });

  it("is stopped and says Off while the switch is off", () => {
    const look = igateLook(
      igateState({ enabled: false, state: "off", server: "", gated: 0, dropped: {}, last_gated_at: null }),
      values,
      0,
    );
    expect([look.state, look.line]).toEqual(["stopped", "Off"]);
  });

  it("says it is connecting, to the server it names or else to the one of the settings, and why it is not connected, in the radio's words and colours", () => {
    expect(igateLook(igateState({ state: "connecting", server: "T2FINLAND" }), values, 0)).toMatchObject({
      state: "connecting",
      tone: "tnc-connecting",
      line: "Connecting to T2FINLAND…",
    });
    expect(igateLook(igateState({ state: "connecting", server: "" }), values, 0).line).toBe(
      "Connecting to rotate.aprs2.net…",
    );
    expect(igateLook(igateState({ state: "connecting", reason: "unreachable" }), values, 0)).toMatchObject({
      state: "waiting",
      tone: "tnc-waiting",
      line: "Not connected: the server cannot be reached",
    });
  });

  it("says why it is not connected in the page's language, never with the daemon's English after it", () => {
    try {
      setLocale("nl");
      expect(igateLook(igateState({ state: "connecting", reason: "unreachable" }), {}, 0).line).toBe(
        "Niet verbonden: de server is niet bereikbaar",
      );
    } finally {
      setLocale("en");
    }
  });

  it("has the server and the filter behind the arrow", () => {
    const look = igateLook(igateState({ server: "T2FINLAND" }), values, 3);
    expect([look.server, look.filter]).toEqual([
      "Server: T2FINLAND (rotate.aprs2.net)",
      "Filter: stations within 50 km of your position",
    ]);
    expect(igateLook(igateState({ server: "" }), values, 3).server).toBe("Server: rotate.aprs2.net");
    expect(igateLook(igateState({ server: "finland.aprs2.net:14580" }), values, 3).server).toBe(
      "Server: finland.aprs2.net (rotate.aprs2.net)",
    );
    expect(igateLook(igateState({ server: "" }), { ...values, "igate/server": "[2001:db8::1]:14580" }, 3).server).toBe(
      "Server: 2001:db8::1",
    );
  });

  it("never says gated, a passcode or an iGate while only the stations are shown, and never a passcode at all, in any language", () => {
    for (const code of ["en", "de", "es", "fi", "fr", "it", "ja", "nl", "pt-BR"] as const) {
      setLocale(code);
      const look = (s: ReturnType<typeof igateState>): string => {
        const it = igateLook(s, values, 2);
        return `${it.state} ${it.line} ${it.server} ${it.filter} ${it.sent}`;
      };
      const said = [
        igateState({ gate: false }),
        igateState({ gate: false, state: "unverified" }),
        igateState({ gate: false, state: "connecting" }),
        igateState({ gate: false, state: "off" }),
      ].map(look);
      const sending = [igateState(), igateState({ state: "unverified" }), igateState({ enabled: false })].map(look);
      expect(sending.join(" "), code).not.toMatch(/passcode|Passcode|Codice|código|パスコード/i);
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
