// The page's made-up rows against the daemon's own. tests/fixtures/wire/rows.json is what the daemon's views make of a world with a row of every kind, and tests/test_wire_rows.py holds it to those views and to
// the models; so a maker of ui/src/test/fixtures.ts that gives a field the daemon does not send, or lacks one it sends, fails here, and the one source of the radios (lib/radios.ts) is tried on the daemon's
// topic `radios` and its settings as they come.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { emailRadio, mainRadio, pageRadios, problemText, typeOf } from "@/lib/radios";
import type { ConfigValues, RadioRow } from "@/protocol/protocol";
import {
  attemptRow,
  bulletin,
  configValues,
  gpsState,
  igateState,
  message,
  ownBulletin,
  ownObject,
  packet,
  qruState,
  radioRow,
  station,
} from "@/test/fixtures";

const FILE = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "tests", "fixtures", "wire", "rows.json");
const ROWS = JSON.parse(readFileSync(FILE, "utf8")) as Record<string, Record<string, unknown> | unknown[]>;

/** The daemon's rows of a topic: a keyed topic's values, a whole one's list. */
const rows = (topic: string): Record<string, unknown>[] => Object.values(ROWS[topic] ?? []) as Record<string, unknown>[];
const keys = (row: object): string[] => Object.keys(row).sort();
/** The keys of an object field that has the same keys in every row (a radio's `can`, its `stats`), as `field.key`; the fields keyed by a radio or a call are left out. */
const inner = (row: Record<string, unknown>, fields: readonly string[]): string[] =>
  fields
    .flatMap((field) => {
      const value = row[field];
      return value !== null && typeof value === "object" && !Array.isArray(value) ? Object.keys(value).map((key) => `${field}.${key}`) : [];
    })
    .sort();

const RADIO_PARTS = ["can", "allowed", "limits", "choices", "beacon", "stats"] as const;

describe("the makers of rows, against the daemon's own", () => {
  const cases: [string, () => object][] = [
    ["stations", () => station("OH2ABC")],
    ["packets", () => packet(1)],
    ["messages", () => message(1)],
    ["own_objects", () => ownObject("MARK")],
    ["own_bulletins", () => ownBulletin("BLN1")],
    ["bulletins", () => bulletin("BLN1")],
    ["radios", () => radioRow(1, "kiss")],
    ["config", () => configValues()],
    ["gps", () => gpsState()],
    ["igate", () => igateState()],
    ["qru", () => qruState()],
  ];
  for (const [topic, make] of cases)
    it(`give a row of ${topic} the fields the daemon sends, no more and no fewer`, () => {
      const theirs = rows(topic);
      expect(theirs.length, topic).toBeGreaterThan(0);
      for (const row of theirs) expect(keys(make()), topic).toEqual(keys(row));
    });

  it("give a radio the parts of the daemon's row (what it can, may and does), and an attempt the fields of the daemon's", () => {
    for (const row of rows("radios")) expect(inner(radioRow(1, "kiss") as unknown as Record<string, unknown>, RADIO_PARTS)).toEqual(inner(row, RADIO_PARTS));
    const attempts = rows("messages").flatMap((row) => row["attempts_detail"] as Record<string, unknown>[]);
    expect(attempts.length).toBeGreaterThan(0);
    for (const attempt of attempts) expect(keys(attemptRow())).toEqual(keys(attempt));
  });
});

describe("the one source of the radios, on the daemon's topic", () => {
  const topic = new Map((rows("radios") as unknown as RadioRow[]).map((row) => [String(row.id), row]));
  const [config] = rows("config") as unknown as ConfigValues[];
  const radios = pageRadios(topic, config ?? null);

  it("has every radio of the topic by its place, removed ones too, each of a type of the page's list", () => {
    expect(radios.map((radio) => radio.id)).toEqual([...topic.values()].sort((a, b) => a.position - b.position || a.id - b.id).map((row) => row.id));
    expect(radios.map((radio) => [radio.id, radio.enabled, radio.removed, radio.connected])).toEqual(
      [...topic.values()]
        .sort((a, b) => a.position - b.position || a.id - b.id)
        .map((row) => [row.id, row.enabled && !row.removed, row.removed, row.enabled && !row.removed && row.state === "connected"]),
    );
    expect(radios.filter((radio) => typeOf(radio) === undefined).map((radio) => radio.type)).toEqual([]);
  });

  it("takes each radio's own settings from the daemon's radio_values by the key of the field", () => {
    for (const radio of radios) {
      const told = Object.entries(config?.radio_values ?? {}).filter(([key]) => key.startsWith(`radio/${radio.id}/`));
      expect(Object.entries(radio.settings).map(([key, value]) => [`radio/${radio.id}/${key}`, value])).toEqual(told);
    }
    expect(radios.some((radio) => Object.keys(radio.settings).length > 0)).toBe(true);
  });

  it("has words for every problem the daemon's rows name, the device another radio holds in the sentence of its refusal", () => {
    const named = radios.flatMap((radio) => (radio.problem === null ? [] : [[radio.problem.code, problemText(radio.problem)]]));
    expect(named).toEqual([
      ["radio.not_connected", "Not connected"],
      ["radio.resource_held", "the device is in use by radio Mobile: choose another"],
    ]);
  });

  it("finds the main radio and the email radio the status names among them", () => {
    const fm = radios.find((radio) => radio.kind === "fm" && radio.enabled);
    expect(fm).toBeDefined();
    expect(mainRadio(radios, { main_radio: fm?.id ?? null })?.id).toBe(fm?.id);
    expect(emailRadio(radios, { email_radio: fm?.id ?? null })?.id).toBe(fm?.id);
  });
});
