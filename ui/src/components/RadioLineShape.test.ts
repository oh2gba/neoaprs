// A radio's box keeps its shape while the radio receives and sends (a report from a Sound card radio on Windows, the panel 447 px wide: "Lines are jumping ... buttons also changing their position vertically"):
// the status line of a connected radio is drawn in the same parts, each on a line of its own that never wraps, through listening, a busy channel, transmitting, the tune tone and the keying test, an age of seconds, of
// minutes and none yet, in every language of the page; the numbers of the receive level and the transmit peak have their room; the radio's log is as high with one line as with many. jsdom lays nothing out: the
// parts and their classes are held here, the rules that keep them are read from the sheets, and work/par/r6/jumps/measure.py measures the built page in a browser.
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import RadioStatus from "@/components/RadioStatus.vue";
import { setLocale } from "@/i18n";
import { LOCALES } from "@/i18n/locales";
import { rowParts, rowStatus } from "@/lib/tncstatus";
import type { ModemState, RadioRow } from "@/protocol/protocol";
import { NOW, ago, fmRow, hfRow, lineStats, radioRow, soundCardModem } from "@/test/fixtures";

const HERE = dirname(fileURLToPath(import.meta.url));
const SETTINGS = readFileSync(join(HERE, "..", "styles", "settings.css"), "utf8");
const TABLES = readFileSync(join(HERE, "..", "styles", "tables.css"), "utf8");
const LEVELBAR = readFileSync(join(HERE, "LevelBar.vue"), "utf8");
const TXLEVEL = readFileSync(join(HERE, "HfLevelRow.vue"), "utf8");
/** The body of the last rule of `selector` in a sheet's or a component's source (the one of its own, after any it shares with others). */
function rule(source: string, selector: string): string {
  const at = source.lastIndexOf(`\n${selector} {`);
  if (at < 0) throw new Error(`no rule ${selector}`);
  return source.slice(at + selector.length + 3, source.indexOf("}", at));
}

/** What a modem does while it receives and sends, as its row says it. */
const DOINGS: readonly (readonly [string, Partial<ModemState>])[] = [
  ["listening", {}],
  ["busy", { busy: true }],
  ["transmitting", { keyed: true }],
  ["tune", { test: "tune", keyed: true }],
  ["key", { test: "key", keyed: true }],
  ["snr", { snr: -12.4 }],
];
/** When a packet last came: 5 s, 12 min, 3 h ago, and none yet. */
const AGES: readonly (string | null)[] = [ago(5), ago(12 * 60), ago(3 * 3600), null];
const soundCard = (modem: Partial<ModemState>, last: string | null): RadioRow =>
  radioRow(1, "direwolf", { modem: soundCardModem(modem), stats: lineStats({ last_packet: last }) });
const mercury = (modem: Partial<ModemState>, last: string | null): RadioRow => hfRow({ stats: lineStats({ last_packet: last }) }, modem);

afterEach(() => setLocale("en"));

describe("the line of a connected radio", () => {
  it("is two parts in every language, whatever the modem does and however old the last packet is: what the modem does, then the last packet", () => {
    for (const { code } of LOCALES) {
      setLocale(code);
      for (const make of [soundCard, mercury]) {
        for (const [, modem] of DOINGS) {
          for (const last of AGES) {
            const parts = rowParts(make(modem, last), NOW);
            expect(parts?.length, `${code} ${JSON.stringify(modem)} ${last}`).toBe(2);
            expect(parts?.[0]).not.toBe("");
            expect(parts?.join(" · ")).toBe(rowStatus(make(modem, last), NOW));
          }
        }
      }
    }
  });

  it("keeps the mode with what the modem does, and the SNR with the last packet", () => {
    expect(rowParts(soundCard({ busy: true }, ago(12)), NOW)).toEqual(["AFSK1200 · Channel busy, waiting", "Last packet 12 s ago"]);
    expect(rowParts(soundCard({}, null), NOW)).toEqual(["AFSK1200 · Listening", "No packet yet"]);
    expect(rowParts(mercury({ keyed: true, snr: 3.4 }, ago(120)), NOW)).toEqual(["DATAC3 · Transmitting…", "Last packet 2 min ago · SNR 3 dB"]);
  });

  it("is one part for a radio without a modem, and no parts for a line that is a sentence: not connected, searching, silent, the Dummy", () => {
    expect(rowParts(fmRow(), NOW)).toEqual(["Last packet 30 s ago"]);
    expect(rowParts(fmRow({ state: "waiting", problem: null }), NOW)).toBeNull();
    expect(rowParts(fmRow({ state: "waiting", problem: { code: "radio.searching", params: {} } }), NOW)).toBeNull();
    expect(rowParts(fmRow({ state: "silent", problem: { code: "radio.silent", params: { since: ago(600) } } }), NOW)).toBeNull();
    expect(rowParts(fmRow({ dummy: true }), NOW)).toBeNull();
  });

  it("is drawn in the same elements with the same classes through every state, and the whole line leads its hover title", async () => {
    const wrapper = mount(RadioStatus, { props: { row: soundCard({}, ago(5)), now: NOW } });
    const shape = () => wrapper.findAll(".tncstatus > span").map((span) => span.classes().join(" "));
    const first = shape();
    expect(first).toEqual(["statuspart", "statuspart-dot", "statuspart statuspart-more"]);
    expect(wrapper.find(".tncstatus").classes()).toContain("statusparts");
    expect(wrapper.find("summary").classes()).toEqual(["statushead", "statushead-parts"]);
    for (const [, modem] of DOINGS) {
      for (const last of AGES) {
        await wrapper.setProps({ row: soundCard(modem, last) });
        expect(shape()).toEqual(first);
        const title = wrapper.find(".tncstatus").attributes("title") ?? "";
        expect(title.split("\n")[0]).toBe(rowStatus(soundCard(modem, last), NOW));
        expect(title.split("\n")[1]).toMatch(/packets heard/);
      }
    }
  });

  it("is a sentence that may wrap while the radio is not connected, in the row of a radio (which keeps two lines' room)", () => {
    const wrapper = mount(RadioStatus, { props: { row: fmRow({ state: "waiting", problem: null }), now: NOW } });
    expect(wrapper.classes()).toContain("radiostatus");
    expect(wrapper.find(".tncstatus").classes()).not.toContain("statusparts");
    expect(wrapper.find("summary").classes()).toEqual(["statushead"]);
    expect(wrapper.findAll(".statuspart")).toHaveLength(0);
    expect(wrapper.find(".tncstatus").attributes("title")).toBe("11 packets heard, 2.0 kB in, 0 B out, 0 digipeated");
  });
});

describe("the rules that keep a radio's box still", () => {
  it("keep a radio's status row two lines high in every state, its words from the top", () => {
    const row = rule(SETTINGS, ".statusflat.radiostatus");
    expect(SETTINGS).toContain(".radiostatus > .statushead,\n.statusflat.radiostatus {");
    expect(row).toMatch(/min-height: calc\(2\.8em \+ 4px\)/);
    expect(row).toMatch(/align-items: flex-start/);
  });

  it("lay a line in parts out as the row's two lines: the first beside the state, the second under it for the whole width", () => {
    expect(rule(SETTINGS, ".statushead-parts")).toMatch(/flex-wrap: wrap/);
    expect(rule(SETTINGS, ".statushead-parts")).toMatch(/row-gap: 0/);
    expect(rule(SETTINGS, ".statushead-parts > .statusparts")).toMatch(/display: contents/);
    expect(rule(SETTINGS, ".statusparts > .statuspart")).toMatch(/min-width: 0/);
    expect(rule(SETTINGS, ".statusparts > .statuspart-more")).toMatch(/flex: 0 0 calc\(100% - 16px\)/);
    expect(rule(SETTINGS, ".statusparts > .statuspart-more")).toMatch(/margin-left: 16px/);
  });

  it("never wrap a part of the line: it is cut with an ellipsis, and the dot between the parts is not drawn", () => {
    const part = rule(SETTINGS, ".statuspart");
    expect(part).toMatch(/display: block/);
    expect(part).toMatch(/white-space: nowrap/);
    expect(part).toMatch(/text-overflow: ellipsis/);
    expect(part).toMatch(/overflow: hidden/);
    expect(rule(SETTINGS, ".statuspart-dot")).toMatch(/display: none/);
    expect(rule(SETTINGS, ".tncstatus")).toMatch(/min-width: 0/);
    expect(rule(SETTINGS, ".tncstatus")).toMatch(/font-variant-numeric: tabular-nums/);
  });

  it("give the radio's log one height, so that a new line moves nothing above or under it", () => {
    const log = rule(TABLES, ".tnclines");
    expect(log).toMatch(/(^|\n)\s*height: 16em/);
    expect(log).not.toMatch(/max-height/);
    expect(log).toMatch(/overflow: auto/);
  });

  it("give the receive level's number, the transmit peak and the gain their room, each on one line", () => {
    expect(rule(LEVELBAR, ".levelvalue")).toMatch(/min-width: 9ch/);
    expect(rule(TXLEVEL, ".txlevel-peak")).toMatch(/min-height: 1.4em/);
    expect(rule(TXLEVEL, ".txlevel-value")).toMatch(/min-width: 6ch/);
    for (const [source, selector] of [
      [LEVELBAR, ".levelvalue"],
      [TXLEVEL, ".txlevel-peak"],
      [TXLEVEL, ".txlevel-value"],
    ] as const) {
      expect(rule(source, selector), selector).toMatch(/white-space: nowrap/);
    }
  });
});
