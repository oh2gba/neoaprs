import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { foldAway, headerPills, type HeaderPill, type Link } from "@/lib/pills";
import { inApp } from "@/lib/shell";
import type { MapState } from "@/protocol/protocol";
import { pageRadios } from "@/lib/radios";
import type { RadioRow } from "@/protocol/protocol";
import { ago, fmRow, gpsState, hfRow, igateState, mapState, NOW, radioRow, radiosTopic } from "@/test/fixtures";

const radiosOf = (...rows: RadioRow[]) => pageRadios(radiosTopic(...rows), null);
const link = (extra: Partial<Link> = {}): Link => ({
  connection: "open",
  radios: radiosOf(fmRow()),
  now: NOW,
  inApp: false,
  told: true,
  ...extra,
});
const marks = (extra: Partial<Link> = {}, values: Record<string, string> = {}): HeaderPill[] =>
  headerPills(values, null, null, null, link(extra));
const words = (pills: HeaderPill[]) => pills.map((p) => t(p.text, p.textValues));
const radio = (row: Partial<RadioRow>, extra: Partial<Link> = {}) =>
  marks({ radios: radiosOf(fmRow(row)), ...extra }).find((p) => p.id === "radio");
const problem = (code: NonNullable<RadioRow["problem"]>["code"], params: Record<string, string> = {}) => ({
  code,
  params,
});

describe("the Daemon mark", () => {
  it("is in a browser only, ok while the page is connected, warn while it connects and bad when the daemon is offline, with nothing to open", () => {
    const states = [
      ["open", "NeoAPRS", "ok"],
      ["connecting", "NeoAPRS: connecting…", "warn"],
      ["closed", "NeoAPRS: offline", "bad"],
    ] as const;
    for (const [connection, text, tone] of states) {
      const mark = marks({ connection }).find((p) => p.id === "daemon");
      expect([mark && t(mark.text), mark?.tone, mark?.target]).toEqual([text, tone, null]);
      expect(mark && t(mark.title)).not.toBe("");
    }
  });

  it("is not there in the app, where page and daemon are one, in any state of the connection", () => {
    for (const connection of ["open", "connecting", "closed"] as const)
      expect(marks({ inApp: true, connection }).some((p) => p.id === "daemon")).toBe(false);
  });

  it("is told by the fragment of the app's window", () => {
    expect(inApp("#app", null)).toBe(true);
    expect([inApp("", null), inApp("#", null), inApp("#application", null), inApp("#/app", null)]).toEqual([
      false,
      false,
      false,
      false,
    ]);
  });

  it("is remembered by the app's window, so a reload or a load without the fragment there is still the app; a browser tab never saw it", () => {
    const window = new Map<string, string>();
    const memory = {
      getItem: (k: string) => window.get(k) ?? null,
      setItem: (k: string, v: string) => void window.set(k, v),
    } as unknown as Storage;
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

describe("the mark of the one radio", () => {
  it("is always there, in the app too, under the radio's name, and says the state in the colour of the palette: connected ok, the rest warn", () => {
    expect(words(marks({ inApp: true }))).toEqual(["Packet"]);
    expect(words([radio({ name: "Kenwood" })!])).toEqual(["Kenwood"]);
    expect(radio({})?.tone).toBe("ok");
    for (const state of ["connecting", "waiting", "stopped", "silent"] as const)
      expect(radio({ state })?.tone, state).toBe("warn");
  });

  it("says what the radio is doing in words after its name, as a mark of two radios does: searching, not connected, silent", () => {
    const kenwood = { name: "Kenwood" };
    expect(words([radio({ ...kenwood, state: "connecting", problem: problem("radio.searching") })!])).toEqual([
      "Kenwood: searching…",
    ]);
    expect(words([radio({ ...kenwood, state: "waiting", problem: problem("radio.not_connected") })!])).toEqual([
      "Kenwood: not connected",
    ]);
    expect(words([radio({ state: "stopped", problem: null })!])).toEqual(["Packet: not connected"]);
    expect(
      words([
        radio({ ...kenwood, state: "silent", problem: problem("radio.silent", { since: ago(5 * 3600 + 120) }) })!,
      ]),
    ).toEqual(["Kenwood: silent"]);
  });

  it("has the reason as the hover title, with where it leads: the problem in the page's words, or since when it is silent", () => {
    const down = radio({ state: "waiting", problem: problem("modem.not_installed") })!;
    expect(t(down.title, down.titleValues)).toBe(
      "This installation does not carry this radio's modem. Settings → Radio",
    );
    const silent = radio({ state: "silent", problem: problem("radio.silent", { since: ago(5 * 3600 + 120) }) })!;
    expect(t(silent.title, silent.titleValues)).toMatch(/^nothing heard since \d\d:\d\d \(5 h\)\. Settings → Radio$/);
    const up = radio({ name: "Kenwood" })!;
    expect(t(up.title, up.titleValues)).toBe("Kenwood: connected. Settings → Radio");
  });

  it("takes its trouble look while the line is open and the radio carries a problem, and stays ok without one", () => {
    const ok = radio({ name: "Kenwood" })!;
    expect([ok.tone, t(ok.text, ok.textValues)]).toEqual(["ok", "Kenwood"]);
    for (const [code, words] of [
      ["modem.receive_deaf", "Mercury hears nothing (its receive side stalled): it is started again shortly"],
      ["modem.receive_stalled", "Mercury hears nothing, even after restarts: switch the radio off and on again"],
    ] as const) {
      const mark = radio({ name: "Kenwood", state: "connected", problem: problem(code) })!;
      expect([mark.tone, t(mark.text, mark.textValues), t(mark.title, mark.titleValues)]).toEqual([
        "warn",
        "Kenwood: not connected",
        `${words}. Settings → Radio`,
      ]);
    }
  });

  // (no internals on the page: while the line is being opened the title says the state in the
  // page's words, the log has the rest)
  it("says searching in its title while the line is being opened, never the port or the device the daemon tries", () => {
    for (const row of [
      { problem: problem("radio.searching") },
      { problem: problem("radio.not_connected", { name: "Packet" }) },
      { problem: null },
    ]) {
      const mark = radio({ state: "connecting", ...row })!;
      expect(t(mark.title, mark.titleValues)).toBe("Searching for the radio. Settings → Radio");
    }
  });

  it("is the Dummy's own tone while its line is open, and it is still the radio mark", () => {
    const dummy = marks({ radios: radiosOf(radioRow(1, "dummy", { name: "Kenwood" })) }).find((p) => p.id === "radio");
    expect([dummy?.tone, dummy && t(dummy.text, dummy.textValues)]).toEqual(["dummy", "Kenwood"]);
  });

  it("is waiting while the daemon has not told the radios, with no name while no radio is known, and under the radio's name while the page's socket is not open, titled then as the Daemon mark is", () => {
    const early = marks({ radios: [], told: false }).find((p) => p.id === "radio")!;
    expect([t(early.text), early.tone, early.focus]).toEqual(["Radio: waiting…", "warn", "set-radio-add"]);
    for (const connection of ["connecting", "closed"] as const) {
      const mark = radio({ name: "Kenwood" }, { connection })!;
      const daemon = marks({ connection }).find((p) => p.id === "daemon")!;
      expect([t(mark.text, mark.textValues), mark.tone, t(mark.title, mark.titleValues)]).toEqual([
        "Kenwood: waiting…",
        "warn",
        t(daemon.title),
      ]);
    }
  });

  it("is not there for a station the daemon has told has no radio: nothing is waited for, whether the socket is open or not, in a browser and in the app", () => {
    for (const connection of ["open", "connecting", "closed"] as const)
      for (const app of [false, true])
        expect(
          marks({ radios: [], told: true, connection, inApp: app }).filter((p) => p.id.startsWith("radio")),
        ).toEqual([]);
  });

  it("leads to Settings → Radio and flashes the radio's box", () => {
    expect([radio({})?.target, radio({})?.focus]).toEqual(["settings", "set-radio-1-enabled"]);
  });
});

describe("the radio marks with the Mercury radio", () => {
  const radios = (rows: RadioRow[], extra: Partial<Link> = {}) =>
    marks({ radios: radiosOf(...rows), ...extra }).filter((p) => p.id.startsWith("radio"));
  const said = (p: HeaderPill) => t(p.text, p.textValues);
  const HF_OFF = hfRow({ enabled: false, state: "stopped" });
  const FM_OFF = fmRow({ enabled: false, state: "stopped" });

  it("is the one mark under the Packet radio's name while only the Packet radio is on", () => {
    expect(radios([fmRow(), HF_OFF]).map((p) => [p.id, said(p), p.focus])).toEqual([
      ["radio", "Packet", "set-radio-1-enabled"],
    ]);
    expect(radios([fmRow()]).map((p) => p.id)).toEqual(["radio"]);
  });

  it("is the one mark too for a station with the Mercury radio alone, under its name, in the state of the Mercury radio and leading to its box", () => {
    const hfDown = radios([
      FM_OFF,
      hfRow(
        { state: "waiting", problem: problem("modem.not_installed") },
        { state: "waiting", reason: "not_installed" },
      ),
    ]);
    expect(hfDown.map((p) => [p.id, said(p), String(p.tone), p.focus])).toEqual([
      ["radio", "Mercury: not connected", "warn", "set-radio-2-enabled"],
    ]);
    expect(hfDown.map((p) => t(p.title, p.titleValues))).toEqual([
      "This installation does not carry this radio's modem. Settings → Radio",
    ]);
    expect(radios([FM_OFF, hfRow()]).map((p) => [said(p), String(p.tone)])).toEqual([["Mercury", "ok"]]);
  });

  // The short name is the label everywhere.
  it("is two marks, one for each radio by its short name, while both are on, each in the tone of its own radio and leading to its own box", () => {
    const two = radios([fmRow(), hfRow()]);
    expect(two.map((p) => [p.id, said(p), String(p.tone), p.target, p.focus])).toEqual([
      ["radio-1", "Packet", "ok", "settings", "set-radio-1-enabled"],
      ["radio-2", "Mercury", "ok", "settings", "set-radio-2-enabled"],
    ]);
    // A name stands before a colon.
    expect(two.map((p) => t(p.title, p.titleValues))).toEqual([
      "Packet: connected. Settings → Radio",
      "Mercury: connected. Settings → Radio",
    ]);
    const fmDown = radios([fmRow({ state: "waiting", problem: problem("radio.not_connected") }), hfRow()]);
    expect(fmDown.map((p) => [said(p), String(p.tone)])).toEqual([
      ["Packet: not connected", "warn"],
      ["Mercury", "ok"],
    ]);
    const hfDown = radios([
      fmRow(),
      hfRow({ state: "silent", problem: problem("radio.silent", { since: ago(7 * 60) }) }),
    ]);
    expect(hfDown.map((p) => [said(p), String(p.tone)])).toEqual([
      ["Packet", "ok"],
      ["Mercury: silent", "warn"],
    ]);
  });

  it("says in words what each radio is doing, with its name in place of Radio", () => {
    const mark = (id: "radio-1" | "radio-2", rows: RadioRow[], extra: Partial<Link> = {}) =>
      radios(rows, extra).find((p) => p.id === id)!;
    expect(said(mark("radio-1", [fmRow({ state: "connecting", problem: problem("radio.searching") }), hfRow()]))).toBe(
      "Packet: searching…",
    );
    const down = mark("radio-2", [
      fmRow(),
      hfRow(
        { state: "waiting", problem: problem("modem.not_installed") },
        { state: "waiting", reason: "not_installed" },
      ),
    ]);
    expect([said(down), t(down.title, down.titleValues)]).toEqual([
      "Mercury: not connected",
      "This installation does not carry this radio's modem. Settings → Radio",
    ]);
    expect(
      said(
        mark("radio-2", [fmRow(), hfRow({ state: "silent", problem: problem("radio.silent", { since: ago(300) }) })]),
      ),
    ).toBe("Mercury: silent");
    for (const connection of ["connecting", "closed"] as const) {
      const waiting = mark("radio-2", [fmRow(), hfRow()], { connection });
      expect([said(waiting), String(waiting.tone), t(waiting.title, waiting.titleValues)]).toEqual([
        "Mercury: waiting…",
        "warn",
        connection === "connecting"
          ? "The page is opening its connection to NeoAPRS"
          : "NeoAPRS does not answer. The page connects again by itself",
      ]);
    }
  });

  it("keeps the order of the marks, the two radios where the one was", () => {
    const all = headerPills(
      { "station/transmit": "false", "gps/source": "gpsd" },
      gpsState({ state: "fix" }),
      igateState(),
      { version: "9.9.9", message: "", url: "" },
      link({ radios: radiosOf(fmRow(), hfRow()) }),
    );
    expect(all.map((p) => p.id)).toEqual(["update", "daemon", "radio-1", "radio-2", "gps", "internet"]);
  });
});

describe("the radio marks with any number of radios", () => {
  const SIX = [
    radioRow(1, "kenwood-tnc2"),
    radioRow(2, "mercury"),
    radioRow(3, "kiss", { name: "Shack", number: 2 }),
    radioRow(4, "mercury", { name: "20 m", number: 2 }),
    radioRow(5, "kantronics", { number: 3 }),
    radioRow(6, "dummy", { number: 4 }),
  ];
  const ofRadios = (rows: RadioRow[], extra: Partial<Link> = {}) =>
    marks({ radios: radiosOf(...rows), ...extra }).filter((p) => p.id.startsWith("radio"));
  const said = (p: HeaderPill) => t(p.text, p.textValues);
  const down = (
    id: number,
    problem: RadioRow["problem"] = { code: "radio.not_connected", params: {} },
  ): Partial<RadioRow> => ({ state: "waiting", problem });

  it("is one mark Radios from three radios on, ok while every one is connected, its title each radio with its state, leading to the first box", () => {
    const [mark, ...more] = ofRadios(SIX);
    expect(more).toEqual([]);
    expect([mark?.id, mark && said(mark), String(mark?.tone), mark?.target, mark?.focus]).toEqual([
      "radios",
      "Radios",
      "ok",
      "settings",
      "set-radio-1-enabled",
    ]);
    expect(mark && t(mark.title, mark.titleValues)).toBe(
      "Packet: connected; Mercury: connected; Shack: connected; 20 m: connected; Packet 3: connected; Packet 4: connected. Settings → Radio",
    );
  });

  it("names the one radio in trouble in its words and leads to its box", () => {
    const rows = SIX.map((row) => (row.id === 4 ? { ...row, ...down(4) } : row));
    const [mark] = ofRadios(rows);
    expect([mark && said(mark), String(mark?.tone), mark?.focus]).toEqual([
      "20 m: not connected",
      "warn",
      "set-radio-4-enabled",
    ]);
    expect(mark && t(mark.title, mark.titleValues)).toContain("; 20 m: not connected;"); // The words of the mark itself
    const silent = SIX.map((row) =>
      row.id === 3
        ? { ...row, state: "silent" as const, problem: { code: "radio.silent" as const, params: { since: ago(300) } } }
        : row,
    );
    expect(ofRadios(silent).map(said)).toEqual(["Shack: silent"]);
    const searching = SIX.map((row) =>
      row.id === 5
        ? { ...row, state: "connecting" as const, problem: { code: "radio.searching" as const, params: {} } }
        : row,
    );
    expect(ofRadios(searching).map(said)).toEqual(["Packet 3: searching…"]);
    const [seeking] = ofRadios(searching);
    expect(seeking && t(seeking.title, seeking.titleValues)).toContain("; Packet 3: searching…;");
  });

  it("says how many are in trouble when several are, and leads to the first of them", () => {
    const rows = SIX.map((row) => (row.id === 3 || row.id === 6 ? { ...row, ...down(row.id) } : row));
    const [mark] = ofRadios(rows);
    expect([mark && said(mark), String(mark?.tone), mark?.focus]).toEqual([
      "Radios: 2 not connected",
      "warn",
      "set-radio-3-enabled",
    ]);
  });

  it("is waiting while the page's socket is not open", () => {
    for (const connection of ["connecting", "closed"] as const) {
      const [mark] = ofRadios(SIX, { connection });
      expect([mark && said(mark), String(mark?.tone), mark && t(mark.title, mark.titleValues)]).toEqual([
        "Radios: waiting…",
        "warn",
        t(`pill.daemon_${connection === "closed" ? "offline" : "connecting"}_title`),
      ]);
    }
  });

  it("is dashed only when every radio on is a Dummy", () => {
    const dummies = [radioRow(1, "dummy"), radioRow(2, "dummy-hf"), radioRow(3, "dummy", { number: 2 })];
    expect(ofRadios(dummies).map((p) => [said(p), String(p.tone)])).toEqual([["Radios", "dummy"]]);
    expect(ofRadios([...dummies, radioRow(4, "kiss", { number: 3 })]).map((p) => String(p.tone))).toEqual(["ok"]);
  });

  it("counts only the radios that are on: two on are two marks, one on is one mark under its name, whatever is removed or off", () => {
    const off = (row: RadioRow): RadioRow => ({ ...row, enabled: false, state: "stopped" });
    const two = [SIX[0], SIX[1], off(SIX[2]), { ...off(SIX[3]), removed: true }];
    expect(ofRadios(two).map((p) => [p.id, said(p)])).toEqual([
      ["radio-1", "Packet"],
      ["radio-2", "Mercury"],
    ]);
    const named = [SIX[2], SIX[3]];
    expect(ofRadios(named).map((p) => [p.id, said(p), p.focus])).toEqual([
      ["radio-3", "Shack", "set-radio-3-enabled"],
      ["radio-4", "20 m", "set-radio-4-enabled"],
    ]);
    const one = [off(SIX[0]), SIX[2]];
    expect(ofRadios(one).map((p) => [p.id, said(p), String(p.tone), p.focus])).toEqual([
      ["radio", "Shack", "ok", "set-radio-3-enabled"],
    ]);
    const oneDown = [off(SIX[0]), { ...SIX[2], ...down(3, { code: "modem.not_installed", params: {} }) }];
    const [mark] = ofRadios(oneDown);
    expect([mark && said(mark), mark && t(mark.title, mark.titleValues)]).toEqual([
      "Shack: not connected",
      "This installation does not carry this radio's modem. Settings → Radio",
    ]);
  });

  it("keeps its place among the marks: where the Radio mark is", () => {
    const all = headerPills(
      { "station/transmit": "false" },
      null,
      igateState(),
      null,
      link({ radios: radiosOf(...SIX) }),
    );
    expect(all.map((p) => p.id)).toEqual(["daemon", "radios", "internet"]);
  });
});

describe("the order of the marks", () => {
  it("is Update, Daemon, Radio, Beacon off, GPS, Internet, in every state", () => {
    const all = headerPills(
      { "station/transmit": "false", "gps/source": "gpsd" },
      gpsState({ state: "fix" }),
      igateState(),
      { version: "9.9.9", message: "", url: "" },
      link(),
    );
    expect(all.map((p) => p.id)).toEqual(["update", "daemon", "radio", "gps", "internet"]);
    const quiet = headerPills({ "beacon/interval_min": "0" }, null, null, null, link({ inApp: true }));
    expect(quiet.map((p) => p.id)).toEqual(["radio", "beacon_off"]);
  });

  it("stay in that order whatever the states: the socket, the GPS's fix, a radio in trouble", () => {
    const ids = (connection: Link["connection"], gps: "fix" | "no_fix", second: Partial<RadioRow>) =>
      headerPills(
        { "gps/source": "gpsd", "beacon/interval_min": "0" },
        gpsState({ state: gps }),
        igateState(),
        { version: "9.9.9", message: "", url: "" },
        link({ connection, radios: radiosOf(fmRow(), hfRow(second)) }),
      ).map((p) => p.id);
    const silent = { state: "silent", problem: problem("radio.silent", { since: ago(60) }) } as const;
    const all = ["update", "daemon", "radio-1", "radio-2", "beacon_off", "gps", "internet"];
    for (const connection of ["open", "connecting", "closed"] as const)
      for (const gps of ["fix", "no_fix"] as const)
        for (const second of [{}, silent]) expect(ids(connection, gps, second)).toEqual(all);
  });

  it("are the same whether transmitting is on or off: RX only is the switch after the count", () => {
    const cases: Record<string, string>[] = [{}, { "beacon/interval_min": "0" }, { "gps/source": "gpsd" }];
    for (const values of cases) {
      const ids = (transmit: string) =>
        headerPills({ ...values, "station/transmit": transmit }, null, igateState(), null, link()).map((p) => p.id);
      expect(ids("false"), JSON.stringify(values)).toEqual(ids("true"));
    }
    expect(
      headerPills({ "beacon/interval_min": "0", "station/transmit": "false" }, null, null).map((p) => p.id),
    ).toEqual(["beacon_off"]);
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

describe("the marks a narrow row hides", () => {
  type Tone = "ok" | "warn" | "bad" | "neutral" | "info";
  const mark = (id: HeaderPill["id"], tone: Tone) => ({ id, tone });
  const hidden = (marks: { id: HeaderPill["id"]; tone: Tone }[], room: number) =>
    [
      ...foldAway(
        marks,
        marks.map(() => 80),
        room,
        8,
      ),
    ].sort();

  it("are none while every mark fits", () => {
    expect(hidden([mark("daemon", "ok"), mark("radio", "ok"), mark("gps", "warn")], 3 * 80 + 2 * 8)).toEqual([]);
  });

  it("are the connected Daemon mark first, so that one radio keeps its name beside it", () => {
    expect(hidden([mark("daemon", "ok"), mark("radio", "ok")], 100)).toEqual(["daemon"]);
  });

  it("keep the Daemon mark that is not connected, and hide a mark that is well before it", () => {
    expect(hidden([mark("daemon", "bad"), mark("radio", "ok")], 100)).toEqual(["radio"]);
    expect(hidden([mark("daemon", "warn"), mark("radio", "ok")], 100)).toEqual(["radio"]);
  });

  it("hide the marks that are well before the marks in trouble, and among equals the last in the row first", () => {
    const row = [
      mark("daemon", "ok"),
      mark("radio-1", "ok"),
      mark("radio-2", "warn"),
      mark("beacon_off", "neutral"),
      mark("gps", "warn"),
      mark("internet", "info"),
    ];
    expect(hidden(row, 2 * 80 + 8)).toEqual(["beacon_off", "daemon", "internet", "radio-1"]);
    expect(hidden(row, 3 * 80 + 2 * 8)).toEqual(["beacon_off", "daemon", "internet"]);
    expect(hidden(row, 80)).toEqual(["beacon_off", "daemon", "gps", "internet", "radio-1"]);
  });

  it("always leave one mark, which the row shortens", () => {
    expect(hidden([mark("daemon", "ok"), mark("radio", "warn")], 10)).toEqual(["daemon"]);
    expect(hidden([mark("radio", "ok")], 10)).toEqual([]);
  });
});
