import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { headerPills, type HeaderPill, type Link } from "@/lib/pills";
import { inApp } from "@/lib/shell";
import type { MapState } from "@/protocol/protocol";
import { pageRadios } from "@/lib/radios";
import type { RadioRow } from "@/protocol/protocol";
import { ago, gpsState, hfState, igateState, mapState, NOW, radioRow, radiosTopic, tncState } from "@/test/fixtures";

const link = (extra: Partial<Link> = {}): Link => ({ connection: "open", tnc: tncState(), hf: null, now: NOW, inApp: false, ...extra });
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

  // (no internals on the page: while the line is being opened the daemon's line of what it does names the port; the title says the state in the page's words, the log has the rest)
  it("says searching in its title while the line is being opened, never the port or the device the daemon tries", () => {
    for (const describe of ["listening on /dev/brainbox_1 for the radio", "/dev/brainbox_3 at 9600, entering KISS, 0 packets"]) {
      const mark = radio({ state: "connecting", problem: "", describe })!;
      expect(t(mark.title, mark.titleValues)).toBe("Searching for the radio. Settings → Radio");
    }
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

describe("the radio marks with the HF radio", () => {
  const BOTH = { "fm/enabled": "true", "hf/enabled": "true" };
  const HF_ONLY = { "fm/enabled": "false", "hf/enabled": "true" };
  const radios = (extra: Partial<Link>, values: Record<string, string>) => marks(extra, values).filter((p) => p.id.startsWith("radio"));
  const said = (p: HeaderPill) => t(p.text, p.textValues);

  it("is the one Radio mark, as it always was, while only the FM radio is on, whatever the hf topic holds", () => {
    for (const values of [{}, { "fm/enabled": "true", "hf/enabled": "false" }] as Record<string, string>[]) {
      expect(radios({ hf: hfState({ state: "stopped" }) }, values).map((p) => [p.id, said(p), p.focus])).toEqual([["radio", "Radio", "set-tnc-profile"]]);
      expect(radios({ hf: null }, values).map((p) => p.id)).toEqual(["radio"]);
    }
  });

  it("is the one Radio mark too for a station with the HF radio alone, in the state of the HF radio and leading to its box", () => {
    const hfDown = radios({ tnc: tncState({ state: "stopped" }), hf: hfState({ state: "waiting", problem: "Mercury is not in this installation" }) }, HF_ONLY);
    expect(hfDown.map((p) => [p.id, said(p), String(p.tone), p.focus])).toEqual([["radio", "Radio: not connected", "warn", "set-hf-profile"]]);
    expect(hfDown.map((p) => t(p.title, p.titleValues))).toEqual(["Mercury is not in this installation. Settings → Radio"]);
    expect(radios({ hf: hfState() }, HF_ONLY).map((p) => [said(p), String(p.tone)])).toEqual([["Radio", "ok"]]);
  });

  // (plan section 6, decision 1: the short name is the label everywhere; "FM radio" and "HF radio" were the two-radio texts, now the radio's name)
  it("is two marks, one for each radio by its short name, while both are on, each in the tone of its own radio and leading to its own box", () => {
    const two = radios({ hf: hfState() }, BOTH);
    expect(two.map((p) => [p.id, said(p), String(p.tone), p.target, p.focus])).toEqual([
      ["radio-1", "FM", "ok", "settings", "set-tnc-profile"],
      ["radio-2", "HF", "ok", "settings", "set-hf-profile"],
    ]);
    expect(two.map((p) => t(p.title, p.titleValues))).toEqual(["FM: connected. Settings → Radio", "HF: connected. Settings → Radio"]); // (plan section 6 "Texts": a name stands before a colon)
    const fmDown = radios({ tnc: tncState({ state: "waiting", problem: "no radio found" }), hf: hfState() }, BOTH);
    expect(fmDown.map((p) => [said(p), String(p.tone)])).toEqual([
      ["FM: not connected", "warn"],
      ["HF", "ok"],
    ]);
    const hfDown = radios({ hf: hfState({ state: "silent", silent_since: ago(7 * 60) }) }, BOTH);
    expect(hfDown.map((p) => [said(p), String(p.tone)])).toEqual([
      ["FM", "ok"],
      ["HF: silent", "warn"],
    ]);
  });

  it("says in words what each radio is doing, with its name in place of Radio", () => {
    const mark = (id: "radio-1" | "radio-2", extra: Partial<Link>) => radios(extra, BOTH).find((p) => p.id === id)!;
    expect(said(mark("radio-1", { tnc: tncState({ state: "connecting", problem: "", describe: "listening on /dev/brainbox_1 for the radio" }) }))).toBe(
      "FM: searching…",
    );
    expect(said(mark("radio-1", { tnc: tncState({ state: "connecting", problem: "", describe: "/dev/brainbox_3 at 9600, entering KISS, 0 packets" }) }))).toBe(
      "FM: entering KISS…",
    );
    const down = mark("radio-2", { hf: hfState({ state: "waiting", problem: "the Mercury program is not installed" }) });
    expect([said(down), t(down.title, down.titleValues)]).toEqual(["HF: not connected", "the Mercury program is not installed. Settings → Radio"]);
    expect(said(mark("radio-2", { hf: hfState({ state: "silent", silent_since: ago(300) }) }))).toBe("HF: silent");
    const waiting = mark("radio-2", { hf: null });
    expect([said(waiting), String(waiting.tone), t(waiting.title, waiting.titleValues)]).toEqual([
      "HF: waiting…",
      "warn",
      "No word from the TNC yet. Settings → Radio",
    ]);
    for (const connection of ["connecting", "closed"] as const) expect(said(mark("radio-2", { hf: hfState(), connection }))).toBe("HF: waiting…");
  });

  it("keeps the order of the marks, the two radios where the one was", () => {
    const all = headerPills(
      { ...BOTH, "station/transmit": "false", "gps/source": "gpsd" },
      gpsState({ state: "fix" }),
      igateState(),
      { version: "9.9.9", message: "", url: "" },
      link({ hf: hfState() }),
    );
    expect(all.map((p) => p.id)).toEqual(["update", "daemon", "radio-1", "radio-2", "rx", "gps", "internet"]);
  });
});

describe("the radio marks with any number of radios", () => {
  const radiosOf = (...rows: RadioRow[]) => pageRadios(radiosTopic(...rows), null);
  const SIX = [
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "mercury", { name: "20 m", number: 2 }),
    radioRow(5, "kantronics", { number: 3 }),
    radioRow(6, "dummy", { number: 4 }),
  ];
  const ofRadios = (rows: RadioRow[], extra: Partial<Link> = {}) =>
    marks({ hf: hfState(), radios: radiosOf(...rows), ...extra }).filter((p) => p.id.startsWith("radio"));
  const said = (p: HeaderPill) => t(p.text, p.textValues);
  const down = (id: number, problem: RadioRow["problem"] = { code: "radio.not_connected", params: {} }): Partial<RadioRow> => ({ state: "waiting", problem });

  it("is one mark Radios from three radios on, ok while every one is connected, its title each radio with its state, leading to the first box", () => {
    const [mark, ...more] = ofRadios(SIX);
    expect(more).toEqual([]);
    expect([mark?.id, mark && said(mark), String(mark?.tone), mark?.target, mark?.focus]).toEqual(["radios", "Radios", "ok", "settings", "set-tnc-profile"]);
    expect(mark && t(mark.title, mark.titleValues)).toBe(
      "FM: connected; HF: connected; Shack: connected; 20 m: connected; FM 3: connected; FM 4: connected. Settings → Radio",
    );
  });

  it("names the one radio in trouble in its words and leads to its box", () => {
    const rows = SIX.map((row) => (row.id === 4 ? { ...row, ...down(4) } : row));
    const [mark] = ofRadios(rows);
    expect([mark && said(mark), String(mark?.tone), mark?.focus]).toEqual(["20 m: not connected", "warn", "set-radio-4-enabled"]);
    expect(mark && t(mark.title, mark.titleValues)).toContain("; 20 m: not connected;"); // (the words of the mark itself)
    const silent = SIX.map((row) =>
      row.id === 3 ? { ...row, state: "silent" as const, problem: { code: "radio.silent" as const, params: { since: ago(300) } } } : row,
    );
    expect(ofRadios(silent).map(said)).toEqual(["Shack: silent"]);
    const searching = SIX.map((row) =>
      row.id === 5 ? { ...row, state: "connecting" as const, problem: { code: "radio.searching" as const, params: {} } } : row,
    );
    expect(ofRadios(searching).map(said)).toEqual(["FM 3: searching…"]);
    const [seeking] = ofRadios(searching);
    expect(seeking && t(seeking.title, seeking.titleValues)).toContain("; FM 3: searching…;");
  });

  it("says how many are in trouble when several are, and leads to the first of them", () => {
    const rows = SIX.map((row) => (row.id === 3 || row.id === 6 ? { ...row, ...down(row.id) } : row));
    const [mark] = ofRadios(rows);
    expect([mark && said(mark), String(mark?.tone), mark?.focus]).toEqual(["Radios: 2 not connected", "warn", "set-radio-3-enabled"]);
  });

  it("is waiting while the page's socket is not open", () => {
    for (const connection of ["connecting", "closed"] as const) {
      const [mark] = ofRadios(SIX, { connection });
      expect([mark && said(mark), String(mark?.tone)]).toEqual(["Radios: waiting…", "warn"]);
    }
  });

  it("is dashed only when every radio on is a Dummy", () => {
    const dummies = [radioRow(1, "dummy"), radioRow(2, "dummy-hf"), radioRow(3, "dummy", { number: 2 })];
    expect(ofRadios(dummies).map((p) => [said(p), String(p.tone)])).toEqual([["Radios", "dummy"]]);
    expect(ofRadios([...dummies, radioRow(4, "kiss", { number: 3 })]).map((p) => String(p.tone))).toEqual(["ok"]);
  });

  it("counts only the radios that are on: two on are two marks, one on is the Radio mark of today, whatever is removed or off", () => {
    const off = (row: RadioRow): RadioRow => ({ ...row, enabled: false, state: "stopped" });
    const two = [SIX[0], SIX[1], off(SIX[2]), { ...off(SIX[3]), removed: true }];
    expect(ofRadios(two).map((p) => [p.id, said(p)])).toEqual([
      ["radio-1", "FM"],
      ["radio-2", "HF"],
    ]);
    const named = [SIX[2], SIX[3]];
    expect(ofRadios(named).map((p) => [p.id, said(p), p.focus])).toEqual([
      ["radio-3", "Shack", "set-radio-3-enabled"],
      ["radio-4", "20 m", "set-radio-4-enabled"],
    ]);
    const one = [off(SIX[0]), SIX[2]];
    expect(ofRadios(one).map((p) => [p.id, said(p), String(p.tone), p.focus])).toEqual([["radio", "Radio", "ok", "set-radio-3-enabled"]]);
    const oneDown = [off(SIX[0]), { ...SIX[2], ...down(3, { code: "modem.not_installed", params: {} }) }];
    const [mark] = ofRadios(oneDown);
    expect([mark && said(mark), mark && t(mark.title, mark.titleValues)]).toEqual([
      "Radio: not connected",
      "This installation carries no Mercury. Settings → Radio",
    ]);
  });

  it("keeps its place among the marks: where the Radio mark is", () => {
    const all = headerPills({ "station/transmit": "false" }, null, igateState(), null, link({ hf: hfState(), radios: radiosOf(...SIX) }));
    expect(all.map((p) => p.id)).toEqual(["daemon", "radios", "rx", "internet"]);
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
    const working = mark(mapState({ state: "downloading", step: "build", percent: null }));
    expect(working && t(working.text, working.textValues)).toBe("Map…");
    expect(mark(mapState({ state: "estimating" }))).toBeUndefined();
    expect(mark(mapState({ state: "ready" }))).toBeUndefined();
    expect(mark(null)).toBeUndefined();
  });
});
