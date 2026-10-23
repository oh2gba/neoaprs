// The guard rail of the translation: no component writes words into its template. A file that has not been converted yet is in unconverted.json with the number of literals it still has (a ratchet: the number only goes down, a
// file that gets to 0 leaves the list, and no file outside the list may have one). `I18N_REPORT=1` prints every literal with its line; `I18N_UPDATE=1` writes the list from what is found, which is what a conversion ends with.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { findLiterals } from "@/test/literals";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const LIST = join(SRC, "i18n", "unconverted.json");

function components(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? components(join(dir, e.name)) : e.name.endsWith(".vue") ? [join(dir, e.name)] : [],
  );
}

const found: Record<string, number> = {};
for (const file of components(SRC)) {
  const literals = findLiterals(readFileSync(file, "utf-8"));
  const name = relative(SRC, file).replaceAll("\\", "/");
  if (literals.length > 0) found[name] = literals.length;
  if (process.env["I18N_REPORT"]) for (const l of literals) process.stdout.write(`${name}:${l.line}  ${l.text}\n`);
}
const listed = JSON.parse(readFileSync(LIST, "utf-8")) as Record<string, number>;
if (process.env["I18N_UPDATE"]) writeFileSync(LIST, JSON.stringify(Object.fromEntries(Object.entries(found).sort()), null, 2) + "\n");

describe("the words of the templates", () => {
  it("come from the catalogue: a component that is not in unconverted.json has no literal text", () => {
    const strict = Object.entries(found).filter(([file]) => !(file in listed));
    expect(strict, "write the words into src/i18n/en/ and use t(); `I18N_REPORT=1 npx vitest run src/i18n/literals.test.ts` lists them").toEqual([]);
  });

  it("are no more than unconverted.json says, and a file that has none is not in it", () => {
    const stale = Object.entries(listed).filter(([file, count]) => (found[file] ?? 0) !== count);
    expect(
      stale.map(([file, count]) => `${file}: ${count} listed, ${found[file] ?? 0} found`),
      "lower the number (or remove the file) in src/i18n/unconverted.json: `I18N_UPDATE=1`",
    ).toEqual([]);
  });

  it("are counted", () => {
    const total = Object.values(found).reduce((sum, n) => sum + n, 0);
    if (process.env["I18N_REPORT"]) process.stdout.write(`unconverted: ${total} literals in ${Object.keys(found).length} components\n`);
    expect(total).toBe(Object.values(listed).reduce((sum, n) => sum + n, 0));
  });
});
