// Every measured value the page shows goes through lib/units.ts, so that the station's units
// reach it: no other source file writes a unit of length, speed, temperature, pressure or rain.
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "..");
// A unit after a value, a unit as a heading or a field's unit, or a unit as a template's text.
const UNIT =
  /km\/h|°C|°F|\bhPa\b|\binHg\b|\bmph\b|ft\/min|\bm\/s\b|\}\s(?:km|mi|ft|m|mm|kn)\b|(?:title|unit):\s*["'`](?:km|mi|ft|m|mm|kn)["'`]|>\s*(?:km|mi|ft|mm|kn)\s*</;

/** What may write a unit, and why: an input the operator types stays metric. */
const ALLOWED: Record<string, string> = {
  "lib/units.ts": "the formatter itself",
  "lib/settings.ts": "the units after the Radius and Antenna height inputs, which stay metric",
  "components/ObjectForm.vue": "the unit after the object's speed input, which goes on the air as typed",
};

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return ["i18n", "protocol", "test"].includes(entry.name) ? [] : files(path);
    return /\.(ts|vue)$/.test(entry.name) && !entry.name.endsWith(".test.ts") ? [path] : [];
  });
}

/** The code without its comments, which may give an example with a unit. */
const code = (text: string): string =>
  text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

describe("the units of measure", () => {
  it("are written by lib/units.ts alone, but for the inputs that stay metric", () => {
    const writers = files(SRC)
      .map((path) => relative(SRC, path))
      .filter((path) => UNIT.test(code(readFileSync(join(SRC, path), "utf-8"))));
    expect(writers.filter((path) => !(path in ALLOWED))).toEqual([]);
    expect(
      Object.keys(ALLOWED).filter((path) => !writers.includes(path)),
      "listed but writes no unit",
    ).toEqual([]);
  });
});
