import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { clockText } from "@/lib/format";
import { lineText, rowParts, rowPillClass, rowPillText, rowStatus, statsCounts } from "@/lib/tncstatus";
import type { ModemState, RadioProblem, RadioRow } from "@/protocol/protocol";
import { NOW, ago, fmRow, hfRow, lineStats, radioRow } from "@/test/fixtures";

// A radio's line as its row of the topic `radios` says it, in plain words: the same words for every
// radio.
describe("the line of a radio's row", () => {
  const row = (type: string, extra: Partial<RadioRow> = {}) => radioRow(3, type, extra);

  it("says the last packet while connected, no packet yet before the first, and searching instead of listing the ports", () => {
    expect(rowStatus(fmRow({ stats: lineStats({ packets: 412, last_packet: ago(120) }) }), NOW)).toBe(
      "Last packet 2 min ago",
    );
    expect(rowStatus(fmRow({ stats: lineStats({ packets: 0, last_packet: null }) }), NOW)).toBe("No packet yet");
    expect(rowStatus(fmRow({ state: "waiting", problem: { code: "radio.searching", params: {} } }), NOW)).toBe(
      "Searching for the radio…",
    );
  });

  it("says since when a silent radio has said nothing", () => {
    expect(
      rowStatus(fmRow({ state: "silent", problem: { code: "radio.silent", params: { since: ago(7 * 60) } } }), NOW),
    ).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says, while not connected, what its problem says in the page's words, never the daemon's English", () => {
    const down = (
      code: RadioProblem["code"],
      params: Record<string, string> = {},
      state: RadioRow["state"] = "waiting",
    ) => rowStatus(row("kiss", { state, problem: { code, params } }), NOW);
    expect(down("radio.not_connected", { name: "Mobile" })).toBe("Not connected");
    expect(down("radio.searching", {}, "connecting")).toBe("Searching for the radio…");
    expect(down("radio.not_connected", {}, "connecting")).toBe("Connecting…");
    expect(down("radio.silent", { since: ago(600) }, "silent")).toMatch(/^nothing heard since /);
    expect(down("modem.sound_card")).toBe("Sound card could not be opened: choose another");
    expect(down("radio.incoming_port", { port: "COM8" })).toBe(
      "COM8 is the computer's incoming Bluetooth port: choose the device's other port",
    );
    expect(down("radio.write_timeout", { seconds: "2" })).toBe("The port takes no data: nothing went through in 2 s");
    expect(rowStatus(row("kiss", { state: "waiting", problem: null }), NOW)).toBe("Not connected");
    expect(rowStatus(fmRow({ state: "stopped", problem: null }), NOW)).toBe("Not connected");
  });

  it("has the row's counts as its hover title", () => {
    expect(statsCounts(lineStats())).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(statsCounts(lineStats({ packets: 1 }))).toContain("1 packet heard");
  });
});

describe("lineText", () => {
  it("shows the time a log line was written, which the daemon tells in UTC, in the viewer's time", () => {
    const at = new Date(NOW - 10_000).toISOString();
    expect(lineText({ at, text: "NeoAPRS: opened /dev/x" })).toBe(`${clockText(at)}  NeoAPRS: opened /dev/x`);
  });

  it("takes the day from the line itself: a line of last week is a line of last week", () => {
    const at = new Date(NOW - 7 * 86_400_000).toISOString();
    expect(lineText({ at, text: "text" })).toBe(`${clockText(at)}  text`);
  });
});

describe("the Dummy radio", () => {
  afterEach(() => setLocale("en"));

  it("is a muted pill and a line that says nothing goes on the air, while its line is open", () => {
    const dummy = radioRow(1, "dummy");
    expect([rowPillText(dummy), rowPillClass(dummy), rowStatus(dummy, NOW)]).toEqual([
      "Dummy",
      "tnc-dummy",
      "Dummy radio: made-up traffic, nothing goes on the air",
    ]);
    const waiting = radioRow(1, "dummy", { state: "waiting" });
    expect([rowPillText(waiting), rowPillClass(waiting)]).toEqual(["waiting", "tnc-waiting"]);
    expect([rowPillText(fmRow()), rowPillClass(fmRow())]).toEqual(["connected", "tnc-connected"]);
  });

  it("says so in every language of the page, in that language", () => {
    const dummy = radioRow(1, "dummy");
    const english = rowStatus(dummy, NOW);
    for (const locale of LOCALES) {
      setLocale(locale.code);
      const line = rowStatus(dummy, NOW);
      expect(line, locale.code).not.toBe("");
      expect(rowPillText(dummy), locale.code).not.toBe("");
      if (locale.code !== "en") expect(line, locale.code).not.toBe(english);
    }
  });

  it("says of the Dummy Mercury radio what it is, in the muted pill", () => {
    const dummy = radioRow(2, "dummy-hf");
    expect([rowPillText(dummy), rowPillClass(dummy)]).toEqual(["Dummy", "tnc-dummy"]);
    expect(rowStatus(dummy, NOW)).toBe(
      "Dummy Mercury radio: made-up distant stations, your frames on the speakers, nothing goes on the air",
    );
  });
});

describe("the Mercury radio's line", () => {
  const hf = (modem: Partial<ModemState> = {}, extra: Partial<RadioRow> = {}) =>
    hfRow({ stats: lineStats(), ...extra }, modem);

  it("says the mode, what the modem does, the last packet, and the SNR once a frame was decoded, with nothing of the socket", () => {
    expect(rowStatus(hf(), NOW)).toBe("DATAC3 · Listening · Last packet 30 s ago");
    expect(rowStatus(hf({ snr: 3.4 }), NOW)).toBe("DATAC3 · Listening · Last packet 30 s ago · SNR 3 dB");
    expect(rowStatus(hf({ keyed: true, snr: -2.5 }), NOW)).toBe(
      "DATAC3 · Transmitting… · Last packet 30 s ago · SNR -2 dB",
    );
    expect(rowStatus(hf({ busy: true }), NOW)).toBe("DATAC3 · Channel busy, waiting · Last packet 30 s ago");
    expect(rowStatus(hf({ test: "tune", keyed: true }), NOW)).toBe("DATAC3 · Tuning… · Last packet 30 s ago");
    expect(rowStatus(hf({ test: "key", keyed: true }), NOW)).toBe("DATAC3 · Keyed · Last packet 30 s ago");
    expect(rowStatus(hf({}, { stats: lineStats({ last_packet: null }) }), NOW)).toBe(
      "DATAC3 · Listening · No packet yet",
    );
  });

  it("says the modem's problem instead of listening while the line is open, and the usual line without one", () => {
    const deaf = { code: "modem.receive_deaf", params: {} } as const;
    const stalled = { code: "modem.receive_stalled", params: {} } as const;
    expect(rowStatus(hf({}, { state: "connected", problem: deaf }), NOW)).toBe(
      "Mercury hears nothing (its receive side stalled): it is started again shortly",
    );
    expect(rowStatus(hf({}, { state: "connected", problem: stalled }), NOW)).toBe(
      "Mercury hears nothing, even after restarts: switch the radio off and on again",
    );
    expect(rowParts(hf({}, { problem: deaf }), NOW)).toBeNull();
    expect(rowStatus(hf({}, { problem: null }), NOW)).toBe("DATAC3 · Listening · Last packet 30 s ago");
    expect(rowParts(hf(), NOW)).toEqual(["DATAC3 · Listening", "Last packet 30 s ago"]);
  });

  it("never shows the address the modem is reached on: Connecting… while the line opens", () => {
    expect(rowStatus(hf({}, { state: "connecting" }), NOW)).toBe("Connecting…");
  });

  it("says why the program does not run in the page's words by the daemon's code, never in the daemon's English", () => {
    const down = (reason: ModemState["reason"]) =>
      rowStatus(hf({ state: "waiting", reason }, { state: "waiting" }), NOW);
    expect(down("not_installed")).toBe("This installation does not carry this radio's modem");
    expect(down("stopped")).toBe("Not running");
    expect(down("network")).toBe("Not run: the modem would be open to the network");
    expect(down("no_port")).toBe("Not running: no free port");
    expect(down("not_started")).toBe("The modem could not be started");
    expect(down("sound_card")).toBe("Sound card could not be opened: choose another");
    expect(down("receive_stalled")).toBe(
      "Mercury hears nothing, even after restarts: switch the radio off and on again",
    );
    expect(down("")).toBe("Not connected");
  });

  it("says Connecting… while the program starts or runs and the line is between two attempts, and never the problem of the line", () => {
    expect(
      rowStatus(
        hf({ state: "starting" }, { state: "waiting", problem: { code: "radio.not_connected", params: {} } }),
        NOW,
      ),
    ).toBe("Connecting…");
    expect(rowStatus(hf({ state: "running" }, { state: "waiting" }), NOW)).toBe("Connecting…");
    expect(rowStatus(hf({ state: "stopped" }, { state: "stopped" }), NOW)).toBe("Not connected");
  });

  it("says the reason in every language of the page, in that language", () => {
    const english = rowStatus(hf({ state: "waiting", reason: "no_port" }, { state: "waiting" }), NOW);
    try {
      for (const locale of LOCALES) {
        setLocale(locale.code);
        const line = rowStatus(hf({ state: "waiting", reason: "no_port" }, { state: "waiting" }), NOW);
        if (locale.code !== "en") expect(line, locale.code).not.toBe(english);
      }
    } finally {
      setLocale("en");
    }
  });
});
