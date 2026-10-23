// The catalogue and the code agree: every id the code asks for is in en.ts (TypeScript checks `t("id")` too; this covers a template, and an id built at run time), and every id of en.ts is asked for somewhere, so that a message
// nobody shows does not stay behind. An id made at run time (`t(\`tab.${id}\`)`, `error.${code}`) counts for all the ids that start with its static part.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const IDS = Object.keys(en);

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name);
    if (e.isDirectory()) return e.name === "test" ? [] : sources(path);
    return /\.(ts|vue)$/.test(e.name) && !e.name.endsWith(".test.ts") ? [path] : [];
  });
}

/** The code of the page apart from the catalogues themselves (the files of i18n/en/ and the other languages). */
const code = sources(SRC)
  .filter((file) => !/\/i18n\/(en\/|[a-z]{2}(-[A-Z]{2})?\.ts$)/.test(file.replaceAll("\\", "/")))
  .map((file) => ({ name: relative(SRC, file).replaceAll("\\", "/"), text: readFileSync(file, "utf-8") }));

describe("the ids of the catalogue", () => {
  it("are all there where the code asks for them with a literal id", () => {
    const asked = code.flatMap(({ name, text }) => [...text.matchAll(/\bt\(\s*["']([a-z][\w.]*)["']/g)].map((m) => ({ name, id: m[1] ?? "" })));
    expect(asked.length).toBeGreaterThan(10);
    expect(asked.filter(({ id }) => !IDS.includes(id))).toEqual([]);
  });

  it("are all asked for: by a literal id or by the static start of one made at run time", () => {
    const text = code.map((c) => c.text).join("\n");
    const prefixes = [...text.matchAll(/`([a-z][\w.]*\.)\$\{/g)].map((m) => m[1] ?? "");
    const unused = IDS.filter((id) => !text.includes(`"${id}"`) && !text.includes(`'${id}'`) && !prefixes.some((p) => id.startsWith(p)));
    expect(unused).toEqual([]);
  });

  it("are named area.thing.detail, in lower case", () => {
    expect(IDS.filter((id) => !/^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/.test(id))).toEqual([]);
  });
});
