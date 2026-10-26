import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { igateStatus } from "@/lib/igatestatus";
import { igateState } from "@/test/fixtures";

const values = { "station/call": "OH2GBA-10", "igate/server": "rotate.aprs2.net:14580" };

afterEach(() => setLocale("en"));

describe("igateStatus", () => {
  it("says Connected, receiving for a login that is up, whatever the daemon says of the login: verified, listening or not accepted", () => {
    for (const state of ["connected", "listening", "unverified"] as const) {
      expect(igateStatus(igateState({ state }), values), state).toBe("Connected, receiving");
    }
  });

  it("is Off while the switch is off", () => {
    expect(igateStatus(igateState({ enabled: false, state: "off", server: "", gated: 0, dropped: {}, last_gated_at: null }), values)).toBe("Off");
  });

  it("says it is connecting, to the server it names or else to the one of the settings, and why it is not connected", () => {
    expect(igateStatus(igateState({ state: "connecting", server: "T2FINLAND" }), values)).toBe("Connecting to T2FINLAND…");
    expect(igateStatus(igateState({ state: "connecting", server: "" }), values)).toBe("Connecting to rotate.aprs2.net:14580…");
    expect(igateStatus(igateState({ state: "connecting", problem: "Connection refused" }), values)).toBe("Not connected: Connection refused");
  });

  it("never says gated, a passcode or an iGate, in any language", () => {
    for (const code of ["en", "de", "es", "fr", "it", "ja", "pt-BR"] as const) {
      setLocale(code);
      const said = [igateState(), igateState({ state: "unverified" }), igateState({ state: "connecting" }), igateState({ state: "off" })].map(
        (s) => `${igateStatus(s, values)}`,
      );
      expect(said.join(" "), code).not.toMatch(/gate|passcode|code d|Passcode|Codice|código|パスコード|転送/i);
    }
  });
});
