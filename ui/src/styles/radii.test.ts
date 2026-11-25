// The page's corners are three tokens, the site's shapes (styles/tokens.css): --radius (4 px) for
// a control, --radius-box (6 px) for a group, card, menu or bubble, --radius-pill for the tag. A
// corner written anywhere else is one of them, 0, or 50 % (a circle). The instruments keep their
// own: the level bar and the scope's picture stay as they are.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { cssRule } from "@/test/css";

const SRC = join(__dirname, "..");
const tokens = readFileSync(join(__dirname, "tokens.css"), "utf-8");
const DARK_AT = tokens.indexOf("@media (prefers-color-scheme: dark)");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}
const strip = (text: string): string => text.replace(/\/\*[\s\S]*?\*\//g, "");

/** A corner as the page may write it: each of its one to four parts a token, 0 or 50 %. */
const PART = /^(var\(--radius(?:-box|-pill)?\)|0|50%)$/;
/** The corners written as a number, each with its reason: the file, the value. A listed one that
 * is gone fails too, so the list cannot go stale. */
const KEPT: Record<string, string> = {
  "components/LevelBar.vue": "5px", // the level bar: an instrument's scale
  "components/HfScope.vue": "4px", // the scope's picture: an instrument
};

/** Every corner the page writes: where, and the value. A .vue file's <style> and its inline
 * styles are read, a .ts file's strings too. */
function corners(): { name: string; value: string }[] {
  return files(SRC)
    .map((path) => relative(SRC, path).replaceAll("\\", "/"))
    .filter(
      (name) =>
        /\.(vue|css|ts)$/.test(name) &&
        !/\.test\.ts$/.test(name) &&
        !name.startsWith("test/") &&
        name !== "styles/tokens.css",
    )
    .flatMap((name) =>
      [...strip(readFileSync(join(SRC, name), "utf-8")).matchAll(/border(?:-[a-z]+)*-radius\s*:\s*([^;"'}]+)/gi)].map(
        (m) => ({
          name,
          value: (m[1] ?? "").trim(),
        }),
      ),
    );
}

describe("the corners of the page", () => {
  it("are three tokens, the same in both themes: 4 px, 6 px and the pill", () => {
    expect(tokens.slice(0, DARK_AT)).toMatch(/^\s*--radius:\s*4px;/m);
    expect(tokens.slice(0, DARK_AT)).toMatch(/^\s*--radius-box:\s*6px;/m);
    expect(tokens.slice(0, DARK_AT)).toMatch(/^\s*--radius-pill:\s*999px;/m);
    expect(tokens.slice(DARK_AT)).not.toMatch(/--radius/);
  });

  it("are written nowhere as a number but by the instruments", () => {
    const all = corners();
    expect(all.length).toBeGreaterThan(50);
    const numbers = all.filter(({ value }) => !value.split(/\s+/).every((part) => PART.test(part)));
    expect(
      numbers.filter(({ name, value }) => KEPT[name] !== value).map(({ name, value }) => `${name}: ${value}`),
    ).toEqual([]);
    expect(
      Object.entries(KEPT).filter(([name, value]) => !numbers.some((c) => c.name === name && c.value === value)),
    ).toEqual([]);
  });

  it("give the tag round ends: the pill", () => {
    const tag = cssRule(".tag");
    expect(tag).toMatch(/height:\s*var\(--tag-h\)/);
    expect(tag).toMatch(/border-radius:\s*var\(--radius-pill\)/);
  });

  it("put a control's corner on the controls and a box's on the groups, cards and menus", () => {
    for (const control of [".btn", ".input"])
      expect(cssRule(control), control).toContain("border-radius: var(--radius);");
    for (const box of [".card", ".tabmenu-list", ".settings fieldset", ".bubble", ".toast"])
      expect(cssRule(box), box).toContain("border-radius: var(--radius-box);");
  });
});
