// The palette is designed once (styles/tokens.css) and written nowhere else: no colour literal in the page's source but in the tokens, the map's own style and the map layers that read the tokens; every token has a light and a dark value; every soft pair of a tag reads at AA (4.5:1) at 11 px in both themes;
// every variable the page uses is defined; and docs/palette.md lists the tokens as the file has them.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(SRC, "..", "..");
const tokens = readFileSync(join(SRC, "styles", "tokens.css"), "utf-8");
const DARK_AT = tokens.indexOf("@media (prefers-color-scheme: dark)");

/** The colours of one theme: variable to value. */
const read = (text: string): Record<string, string> =>
  Object.fromEntries([...text.matchAll(/^\s*(--[\w-]+):\s*([^;]+);/gm)].map((m) => [m[1] ?? "", (m[2] ?? "").trim()]));
const light = read(tokens.slice(0, DARK_AT));
const dark = read(tokens.slice(DARK_AT));
const COLOUR = /^(#|rgb)/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

/** Where a colour may be written besides tokens.css: the map's style, and the layers that give it a colour (they read the tokens, and keep a literal for where there is no style sheet). */
const EXCEPTIONS = [/^lib\/basemapstyle\.ts$/, /^lib\/[a-z]+layers\.ts$/];
const LITERAL = /(?<![\w&])#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|hwb)\(/;

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

describe("the palette", () => {
  it("is the only place a colour is written in the page's source, but for the map's style and the map layers", () => {
    const found: string[] = [];
    for (const path of files(SRC)) {
      const name = relative(SRC, path).replaceAll("\\", "/");
      if (
        !/\.(vue|css|ts)$/.test(name) ||
        /\.test\.ts$/.test(name) ||
        name.startsWith("test/") ||
        name === "styles/tokens.css" ||
        EXCEPTIONS.some((e) => e.test(name))
      )
        continue;
      readFileSync(path, "utf-8")
        .split("\n")
        .forEach((line, i) => {
          if (LITERAL.test(line.replace(/\/\*.*?\*\//g, ""))) found.push(`${name}:${i + 1}: ${line.trim().slice(0, 80)}`);
        });
    }
    expect(found).toEqual([]);
  });

  it("has every colour token in the light and in the dark theme, and each theme's own where the colour changes", () => {
    const colours = Object.keys(light).filter((k) => COLOUR.test(light[k] ?? ""));
    expect(colours.length).toBeGreaterThan(30);
    for (const meaning of ["accent", "ok", "warn", "bad", "info", "neutral"]) {
      for (const part of ["bg", "fg"]) expect(dark, `--${meaning}-soft-${part} for dark`).toHaveProperty(`--${meaning}-soft-${part}`);
    }
    for (const strong of ["--ok", "--warn", "--bad", "--info", "--accent", "--text", "--panel", "--border", "--muted"])
      expect(dark, strong).toHaveProperty(strong);
    expect(Object.keys(dark).filter((k) => !(k in light))).toEqual([]);
  });

  it("makes every soft pair of a tag readable at 11 px: 4.5 to 1 in the light and in the dark theme", () => {
    for (const [name, theme] of [
      ["light", light],
      ["dark", { ...light, ...dark }],
    ] as const) {
      for (const meaning of ["accent", "ok", "warn", "bad", "info", "neutral"]) {
        const ratio = contrast(theme[`--${meaning}-soft-bg`] ?? "#000000", theme[`--${meaning}-soft-fg`] ?? "#000000");
        expect({ name, meaning, ok: ratio >= 4.5 }).toEqual({ name, meaning, ok: true });
      }
    }
  });

  it("defines every variable the page's style sheets and components use", () => {
    const defined = new Set([...Object.keys(light), ...Object.keys(dark), "--panel-width"]);
    const used = new Set<string>();
    for (const path of files(SRC)) {
      if (!/\.(vue|css|ts)$/.test(path) || /\.test\.ts$/.test(path)) continue;
      for (const m of readFileSync(path, "utf-8").matchAll(/var\((--[\w-]+)/g)) used.add(m[1] ?? "");
    }
    const local = [...used].filter(
      (v) =>
        !defined.has(v) &&
        !new RegExp(`(?:^|[\\s;{])${v}\\s*:`).test(
          files(SRC)
            .filter((f) => /\.(vue|css)$/.test(f))
            .map((f) => readFileSync(f, "utf-8"))
            .join("\n"),
        ),
    );
    expect(local).toEqual([]);
  });

  it("is written in docs/palette.md with the light and the dark value of every colour token", () => {
    const doc = readFileSync(join(ROOT, "docs", "palette.md"), "utf-8");
    for (const key of Object.keys(light).filter((k) => COLOUR.test(light[k] ?? ""))) {
      expect(doc, key).toContain(`| \`${key}\` | \`${light[key]}\` | \`${dark[key] ?? light[key]}\` |`);
    }
  });
});
