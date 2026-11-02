import { afterEach, describe, expect, it } from "vitest";
import { setLocale } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { clockText } from "@/lib/format";
import { lineText, pillClass, pillText, searchedPorts, tncCounts, tncStatus } from "@/lib/tncstatus";
import type { ModemState } from "@/protocol/protocol";
import { NOW, ago, hfState, tncState } from "@/test/fixtures";

const searching = () =>
  tncState({
    state: "waiting",
    path: "",
    describe: "listening on /dev/ttyUSB0, /dev/serial/by-id/usb-X-if00 for the radio",
    searching: ["/dev/ttyUSB0", "/dev/serial/by-id/usb-X-if00"],
    stats: { ...tncState().stats, packets: 0 },
  });

describe("tncStatus", () => {
  it("says what it is connected to and when the last packet came", () => {
    const tnc = tncState({ path: "/dev/ttyUSB0", stats: { ...tncState().stats, packets: 412, last_packet: ago(120) } });
    expect(tncStatus(tnc, NOW)).toBe("Last packet 2 min ago");
  });

  it("says so when no packet has been heard", () => {
    expect(tncStatus(tncState({ stats: { ...tncState().stats, packets: 0, last_packet: null } }), NOW)).toBe("No packet yet");
  });

  it("says it is searching for the radio instead of listing the ports", () => {
    expect(tncStatus(searching(), NOW)).toBe("Searching for the radio…");
  });

  it("says since when a silent radio has said nothing", () => {
    expect(tncStatus(tncState({ state: "silent", silent_since: ago(7 * 60) }), NOW)).toMatch(/^nothing heard since \d\d:\d\d \(7 min\)$/);
  });

  it("says why it is not connected: the problem, else the last error, else nothing more", () => {
    expect(tncStatus(tncState({ state: "waiting", problem: "no KISS frames", last_error: "busy" }), NOW)).toBe("Not connected: no KISS frames");
    expect(tncStatus(tncState({ state: "waiting", last_error: "busy" }), NOW)).toBe("Not connected: busy");
    expect(tncStatus(tncState({ state: "stopped" }), NOW)).toBe("Not connected");
  });

  it("says that the Mercury HF modem transmits, or that the channel is busy, while it does; else the last packet as for any radio", () => {
    const modem = {
      state: "running" as const,
      problem: "",
      reason: "" as const,
      mode: "DATAC3",
      keyed: false,
      busy: false,
      test: "" as const,
      snr: null,
      frames_keyed: 0,
      max_frame: 123,
      sound_card: "",
      keying: "vox",
    };
    expect(tncStatus(tncState({ modem: { ...modem, keyed: true } }), NOW)).toBe("DATAC3 · Transmitting… · Last packet 30 s ago");
    expect(tncStatus(tncState({ modem: { ...modem, busy: true } }), NOW)).toBe("DATAC3 · Channel busy, waiting · Last packet 30 s ago");
    expect(tncStatus(tncState({ modem }), NOW)).toBe("DATAC3 · Listening · Last packet 30 s ago");
    expect(tncStatus(tncState({ modem: { ...modem, keyed: true }, state: "waiting", problem: "the Mercury program is not installed" }), NOW)).toBe(
      "Not connected: the Mercury program is not installed",
    );
  });

  it("says what it is connecting to", () => {
    expect(tncStatus(tncState({ state: "connecting" }), NOW)).toBe("Connecting to /dev/brainbox_3…");
    expect(tncStatus(tncState({ state: "connecting", path: "" }), NOW)).toBe("Connecting…");
  });
});

describe("tncCounts", () => {
  it("says how much came in and went out, for the hover title of the line", () => {
    expect(tncCounts(tncState())).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
    expect(tncCounts(tncState({ stats: { ...tncState().stats, packets: 1 } }))).toContain("1 packet heard");
  });
});

describe("searchedPorts", () => {
  it("lists the ports the daemon listens to while it searches", () => {
    expect(searchedPorts(searching())).toEqual(["/dev/ttyUSB0", "/dev/serial/by-id/usb-X-if00"]);
  });

  it("is null when a port is open or the line says something else", () => {
    expect(searchedPorts(tncState())).toBeNull();
    expect(searchedPorts(tncState({ path: "", describe: "socket://127.0.0.1:8001, waiting" }))).toBeNull();
    expect(searchedPorts(tncState({ searching: ["/dev/ttyUSB0"] }))).toBeNull();
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
    const dummy = tncState({ dummy: true, path: "the dummy radio" });
    expect([pillText(dummy), pillClass(dummy), tncStatus(dummy, NOW)]).toEqual(["Dummy", "tnc-dummy", "Dummy radio: made-up traffic, nothing goes on the air"]);
    const waiting = tncState({ dummy: true, state: "waiting", path: "", problem: "x" });
    expect([pillText(waiting), pillClass(waiting)]).toEqual(["waiting", "tnc-waiting"]);
    expect([pillText(tncState()), pillClass(tncState())]).toEqual(["connected", "tnc-connected"]);
  });

  it("says so in every language of the page, in that language", () => {
    const dummy = tncState({ dummy: true });
    const english = tncStatus(dummy, NOW);
    for (const locale of LOCALES) {
      setLocale(locale.code);
      const line = tncStatus(dummy, NOW);
      expect(line, locale.code).not.toBe("");
      expect(pillText(dummy), locale.code).not.toBe("");
      if (locale.code !== "en") expect(line, locale.code).not.toBe(english);
    }
  });
});

describe("the HF radio's line", () => {
  const modem = { ...hfState().modem! };
  const hf = (extra: Partial<typeof modem> = {}, more: Parameters<typeof hfState>[0] = {}) => hfState({ modem: { ...modem, ...extra }, ...more });

  it("says the mode, what the modem does, the SNR once a frame was decoded, and the last packet, with nothing of the socket", () => {
    expect(tncStatus(hf(), NOW)).toBe("DATAC3 · Listening · Last packet 30 s ago");
    expect(tncStatus(hf({ snr: 3.4 }), NOW)).toBe("DATAC3 · Listening · SNR 3 dB · Last packet 30 s ago");
    expect(tncStatus(hf({ keyed: true, snr: -2.5 }), NOW)).toBe("DATAC3 · Transmitting… · SNR -2 dB · Last packet 30 s ago");
    expect(tncStatus(hf({ busy: true }), NOW)).toBe("DATAC3 · Channel busy, waiting · Last packet 30 s ago");
    expect(tncStatus(hf({ test: "tune", keyed: true }), NOW)).toBe("DATAC3 · Tuning… · Last packet 30 s ago");
    expect(tncStatus(hf({ test: "key", keyed: true }), NOW)).toBe("DATAC3 · Keyed · Last packet 30 s ago");
    expect(tncStatus(hf({}, { stats: { ...hfState().stats, last_packet: null } }), NOW)).toBe("DATAC3 · Listening · No packet yet");
  });

  it("never shows the address the modem is reached on: Connecting… while the line opens", () => {
    expect(tncStatus(hf({}, { state: "connecting", path: "socket://127.0.0.1:8100" }), NOW)).toBe("Connecting…");
  });

  it("says why the program does not run in the page's words by the daemon's code, never in the daemon's English", () => {
    const down = (reason: ModemState["reason"], problem = "Mercury stopped (exit 1); the log says why") =>
      tncStatus(hf({ state: "waiting", problem, reason }, { state: "waiting", problem }), NOW);
    expect(down("not_installed", "the Mercury program is not in this installation of NeoAPRS (...)")).toBe("This installation carries no Mercury");
    expect(down("stopped")).toBe("Not running");
    expect(down("network")).toBe("Not run: Mercury would be open to the network");
    expect(down("no_port", "no free port for Mercury: [Errno 98]")).toBe("Not running: no free port");
    expect(down("not_started", "Mercury could not be started: [Errno 2]")).toBe("Mercury could not be started");
    expect(down("firewall")).toBe("Not run: the Windows Firewall rule of the installer is missing");
    expect(down("sound_card", "the sound card could not be opened: choose another one in the Sound card field")).toBe(
      "Sound card could not be opened: choose another",
    );
    expect(down("")).toBe("Not connected");
  });

  it("says Connecting… while the program starts or runs and the line is between two attempts, and never the problem of the line", () => {
    expect(tncStatus(hf({ state: "starting" }, { state: "waiting", problem: "no KISS frames" }), NOW)).toBe("Connecting…");
    expect(tncStatus(hf({ state: "running" }, { state: "waiting", last_error: "refused" }), NOW)).toBe("Connecting…");
    expect(tncStatus(hf({ state: "stopped" }, { state: "stopped", problem: "x" }), NOW)).toBe("Not connected");
  });

  it("says the reason in every language of the page, in that language", () => {
    const english = tncStatus(hf({ state: "waiting", reason: "no_port" }, { state: "waiting" }), NOW);
    try {
      for (const locale of LOCALES) {
        setLocale(locale.code);
        const line = tncStatus(hf({ state: "waiting", reason: "no_port" }, { state: "waiting" }), NOW);
        if (locale.code !== "en") expect(line, locale.code).not.toBe(english);
      }
    } finally {
      setLocale("en");
    }
  });

  it("says of the Dummy HF radio what it is, in the muted pill", () => {
    const dummy = hfState({ dummy: true, modem: null });
    expect(pillText(dummy)).toBe("Dummy");
    expect(pillClass(dummy)).toBe("tnc-dummy");
    expect(tncStatus(dummy, NOW)).toBe("Dummy HF radio: made-up distant stations, your frames on the speakers, nothing goes on the air");
  });
});
