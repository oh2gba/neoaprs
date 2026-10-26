import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { PASSCODE_URL, igateCounts, igateStateText, igateStatus, passcodeLink } from "@/lib/igatestatus";
import { NOW, igateState } from "@/test/fixtures";

const values = { "station/call": "OH2GBA-10", "igate/password": "19628", "igate/server": "rotate.aprs2.net:14580" };

afterEach(() => setLocale("en"));

describe("igateStatus", () => {
  it("says what the iGate has done, as the radio status does for the radio", () => {
    expect(igateStatus(igateState(), values, NOW)).toBe("Connected to T2FINLAND, 1234 packets gated, last 12 s ago");
    expect(igateStatus(igateState({ gated: 1 }), values, NOW)).toBe("Connected to T2FINLAND, 1 packet gated, last 12 s ago");
  });

  it("says no packet has been gated yet, and uses the address when the server gave no name", () => {
    expect(igateStatus(igateState({ gated: 0, last_gated_at: null }), values, NOW)).toBe("Connected to T2FINLAND, no packet gated yet");
    expect(igateStatus(igateState({ server: "", gated: 0, last_gated_at: null }), values, NOW)).toBe(
      "Connected to rotate.aprs2.net:14580, no packet gated yet",
    );
  });

  it("is Off while the switch is off", () => {
    expect(igateStatus(igateState({ enabled: false, state: "off", server: "", gated: 0, dropped: {}, last_gated_at: null }), values, NOW)).toBe("Off");
  });

  it("says it is connected and listening only without a passcode, and nothing of the passcode while it connects", () => {
    const listening = igateState({ state: "listening", server: "T2FINLAND", problem: "", gated: 0, dropped: {}, last_gated_at: null });
    expect(igateStatus(listening, { ...values, "igate/password": "" }, NOW)).toBe("Connected, listening only");
    const connecting = igateState({ state: "connecting", server: "", problem: "", gated: 0, last_gated_at: null });
    expect(igateStatus(connecting, { ...values, "igate/password": "" }, NOW)).toBe("Connecting to rotate.aprs2.net:14580…");
  });

  it("says it is connecting, and why a connection is down", () => {
    const connecting = igateState({ state: "connecting", server: "", problem: "", gated: 0, last_gated_at: null });
    expect(igateStatus(connecting, values, NOW)).toBe("Connecting to rotate.aprs2.net:14580…");
    expect(igateStatus({ ...connecting, problem: "rotate.aprs2.net:14580: Connection refused" }, values, NOW)).toBe(
      "Not connected: rotate.aprs2.net:14580: Connection refused",
    );
  });

  it("says the server did not accept the passcode, and for which call", () => {
    expect(igateStatus(igateState({ state: "unverified", problem: "the server did not accept the passcode" }), values, NOW)).toBe(
      "The server did not accept the passcode, so NeoAPRS only listens. Check that it is the one for OH2GBA-10",
    );
  });

  it("is written in the language of the page", () => {
    setLocale("de");
    expect(igateStatus(igateState(), values, NOW)).toBe("Verbunden mit T2FINLAND, 1234 Pakete weitergegeben, zuletzt vor 12 s");
    expect(igateStateText("connected")).toBe("verbunden");
    setLocale("fr");
    expect(igateStatus(igateState({ gated: 1 }), values, NOW)).toContain("1 paquet transmis");
    setLocale("ja");
    expect(igateStatus(igateState(), values, NOW)).toContain("1234パケット転送");
  });
});

describe("igateCounts", () => {
  it("lists what was heard and not gated, the most first", () => {
    expect(igateCounts(igateState())).toBe("Not gated: already via the internet: 31, duplicate: 6, query: 3");
  });

  it("is empty when nothing was left out, and shows a reason it has no words for as it is", () => {
    expect(igateCounts(igateState({ dropped: {} }))).toBe("");
    expect(igateCounts(igateState({ dropped: { strange: 2 } }))).toBe("Not gated: strange: 2");
  });
});

describe("the state on the pill", () => {
  it("has a word for each state", () => {
    expect((["off", "connecting", "connected", "listening", "unverified"] as const).map(igateStateText)).toEqual([
      "off",
      "connecting",
      "connected",
      "listening",
      "not verified",
    ]);
  });
});

describe("passcodeLink", () => {
  it("is the author's request page, with the base call when there is one", () => {
    expect(PASSCODE_URL).toBe("https://oh2gba.eu/neoaprs/passcode");
    expect(passcodeLink("OH2GBA")).toBe("https://oh2gba.eu/neoaprs/passcode?call=OH2GBA");
    expect(passcodeLink("OH2GBA-10")).toBe("https://oh2gba.eu/neoaprs/passcode?call=OH2GBA");
    expect(passcodeLink("")).toBe(PASSCODE_URL);
    expect(passcodeLink("  ")).toBe(PASSCODE_URL);
  });
});
