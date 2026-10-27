import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { headerPills, type HeaderPill, type Link } from "@/lib/pills";
import { inApp } from "@/lib/shell";
import type { MapState } from "@/protocol/protocol";
import { ago, gpsState, igateState, mapState, NOW, tncState } from "@/test/fixtures";

const link = (extra: Partial<Link> = {}): Link => ({ connection: "open", tnc: tncState(), now: NOW, inApp: false, ...extra });
const marks = (extra: Partial<Link> = {}, values: Record<string, string> = {}): HeaderPill[] => headerPills(values, null, null, null, link(extra));
const words = (pills: HeaderPill[]) => pills.map((p) => t(p.text));
const radio = (tnc: Partial<ReturnType<typeof tncState>>, extra: Partial<Link> = {}) => marks({ tnc: tncState(tnc), ...extra }).find((p) => p.id === "radio");

describe("the Daemon mark", () => {
  it("is in a browser only, ok while the page is connected, warn while it connects and bad when the daemon is offline, with nothing to open", () => {
    const states = [
      ["open", "Server", "ok"],
      ["connecting", "Server: connecting…", "warn"],
      ["closed", "Server: offline", "bad"],
    ] as const;
    for (const [connection, text, tone] of states) {
      const mark = marks({ connection }).find((p) => p.id === "daemon");
      expect([mark && t(mark.text), mark?.tone, mark?.target]).toEqual([text, tone, null]);
      expect(mark && t(mark.title)).not.toBe("");
    }
  });

  it("is not there in the app, where page and daemon are one, in any state of the connection", () => {
    for (const connection of ["open", "connecting", "closed"] as const) expect(marks({ inApp: true, connection }).some((p) => p.id === "daemon")).toBe(false);
  });

  it("is told by the fragment of the app's window", () => {
    expect(inApp("#app", null)).toBe(true);
    expect([inApp("", null), inApp("#", null), inApp("#application", null), inApp("#/app", null)]).toEqual([false, false, false, false]);
  });

  it("is remembered by the app's window, so a reload or a load without the fragment there is still the app; a browser tab never saw it", () => {
    const window = new Map<string, string>();
    const memory = { getItem: (k: string) => window.get(k) ?? null, setItem: (k: string, v: string) => void window.set(k, v) } as unknown as Storage;
    expect(inApp("", memory)).toBe(false);
    expect(inApp("#app", memory)).toBe(true);
    expect(inApp("", memory)).toBe(true);
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect([inApp("#app", broken), inApp("", broken)]).toEqual([true, false]);
  });
});

describe("the Radio mark", () => {
  it("is always there, in the app too, and says the state in the colour of the palette: connected ok, the rest warn", () => {
    expect(words(marks({ inApp: true }))).toEqual(["Radio"]);
    expect(radio({})?.tone).toBe("ok");
    for (const state of ["connecting", "waiting", "stopped", "silent"] as const) expect(radio({ state })?.tone, state).toBe("warn");
  });

  it("says what the radio is doing in words, as the footer used to: searching, entering KISS, not connected, silent", () => {
    expect(words([radio({ state: "connecting", problem: "", describe: "listening on /dev/brainbox_1 for the radio" })!])).toEqual(["Radio: searching…"]);
    expect(words([radio({ state: "connecting", problem: "", describe: "/dev/brainbox_3 at 9600, entering KISS, 0 packets" })!])).toEqual([
      "Radio: entering KISS…",
    ]);
    expect(words([radio({ state: "waiting", problem: "no radio found" })!])).toEqual(["Radio: not connected"]);
    expect(words([radio({ state: "stopped", problem: "" })!])).toEqual(["Radio: not connected"]);
    expect(words([radio({ state: "silent", silent_since: ago(5 * 3600 + 120) })!])).toEqual(["Radio: silent"]);
  });

  it("has the reason as the hover title, with where it leads: the problem, what the TNC says, or since when it is silent", () => {
    expect(t(radio({ state: "waiting", problem: "no radio found" })!.title, radio({ state: "waiting", problem: "no radio found" })!.titleValues)).toBe(
      "no radio found. Settings → Radio",
    );
    const silent = radio({ state: "silent", silent_since: ago(5 * 3600 + 120) })!;
    expect(t(silent.title, silent.titleValues)).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)\. Settings → Radio$/);
    expect(t(radio({})!.title)).toBe("Radio connected. Settings → Radio");
  });

  it("is the Dummy's own tone while its line is open, and it is still the radio mark", () => {
    const dummy = radio({ dummy: true });
    expect([dummy?.tone, dummy && t(dummy.text)]).toEqual(["dummy", "Radio"]);
  });

  it("is waiting while the daemon has not told the radio, and while the page's socket is not open, whatever the radio was", () => {
    expect(words([marks({ tnc: null }).find((p) => p.id === "radio")!])).toEqual(["Radio: waiting…"]);
    for (const connection of ["connecting", "closed"] as const) {
      const mark = radio({}, { connection })!;
      expect([t(mark.text), mark.tone]).toEqual(["Radio: waiting…", "warn"]);
    }
  });

  it("leads to Settings → Radio and flashes the group of the type of TNC", () => {
    expect([radio({})?.target, radio({})?.focus]).toEqual(["settings", "set-tnc-profile"]);
  });
});

describe("the order of the marks", () => {
  it("is Update, Daemon, Radio, RX only, GPS, Internet: the last folds first on a narrow screen, so the daemon and the radio stay longest after the update", () => {
    const all = headerPills(
      { "station/transmit": "false", "gps/source": "gpsd" },
      gpsState({ state: "fix" }),
      igateState(),
      { version: "9.9.9", message: "", url: "" },
      link(),
    );
    expect(all.map((p) => p.id)).toEqual(["update", "daemon", "radio", "rx", "gps", "internet"]);
    const quiet = headerPills({ "beacon/interval_min": "0" }, null, null, null, link({ inApp: true }));
    expect(quiet.map((p) => p.id)).toEqual(["radio", "beacon_off"]);
  });

  it("has no Daemon or Radio mark where no link is given", () => {
    expect(headerPills({}, null, null).map((p) => p.id)).toEqual([]);
  });
});

describe("the Map mark", () => {
  it("is there while the detailed map is being downloaded, with the percent of the step (none while the step cannot say), and opens Settings → Map; not for an estimate, nor when nothing runs", () => {
    const mark = (map: MapState | null) => headerPills({}, null, null, null, null, map).find((p) => p.id === "map");
    const running = mark(mapState({ state: "downloading", step: "area", percent: 42 }));
    expect([running && t(running.text, running.textValues), running?.tone, running?.target, running?.focus]).toEqual([
      "Map 42 %",
      "info",
      "settings",
      "set-map-fetch",
    ]);
    expect(running && t(running.title)).toBe("Downloading the map of your area. Settings → Map");
    const working = mark(mapState({ state: "downloading", step: "tool", percent: null }));
    expect(working && t(working.text, working.textValues)).toBe("Map…");
    expect(mark(mapState({ state: "estimating" }))).toBeUndefined();
    expect(mark(mapState({ state: "ready" }))).toBeUndefined();
    expect(mark(null)).toBeUndefined();
  });
});
