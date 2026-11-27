// The palette is designed once (styles/tokens.css) and written nowhere else: no colour literal in
// the page's source except in the tokens, the map's own style and the map layers that read the
// tokens. Every token has a light and a dark value. Every tone that stands as a small word reads
// at AA (4.5:1) at 11 px on every ground it stands on (the panel, the page, a selected or hovered
// row, a raised note, an input, a group while it flashes) in both themes, and so does every pair
// of a word and its plate (a tag, a filled button, the toast). A drag across text is told from
// every ground and the text reads on it. A warn word is never the bare --warn but its soft pair.
// The HF tag is told from every other tag by its lightness. Every variable the page uses is
// defined, docs/palette.md lists every token as the file has it, and the theme colours of the
// page and of the manifest are the palette's.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = join(SRC, "..", "..");
const tokens = readFileSync(join(SRC, "styles", "tokens.css"), "utf-8");
const DARK_AT = tokens.indexOf("@media (prefers-color-scheme: dark)");

/** The tokens of one theme: variable to value. */
const read = (text: string): Record<string, string> =>
  Object.fromEntries([...text.matchAll(/^\s*(--[\w-]+):\s*([^;]+);/gm)].map((m) => [m[1] ?? "", (m[2] ?? "").trim()]));
const light = read(tokens.slice(0, DARK_AT));
const dark = read(tokens.slice(DARK_AT));
const THEMES = [
  ["light", light],
  ["dark", { ...light, ...dark }],
] as const;
const COLOUR = /^(#|rgb)/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}
const strip = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, "");

/** Where a colour may be written besides tokens.css: the map's style, and the layers that give
 * it a colour (they read the tokens and keep a literal where there is no style sheet). */
const EXCEPTIONS = [/^lib\/basemapstyle\.ts$/, /^lib\/(layers\/)?[a-z]+layers\.ts$/];
const LITERAL = /(?<![\w&])#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|hwb)\(/;

/** The style the page is drawn with: the style sheets (but the tokens) and the <style> of every
 * component, by path under ui/src. */
const STYLE: [string, string][] = files(SRC)
  .map((path) => [relative(SRC, path).replaceAll("\\", "/"), path] as const)
  .filter(
    ([name]) =>
      (name.startsWith("styles/") && name.endsWith(".css") && name !== "styles/tokens.css") || name.endsWith(".vue"),
  )
  .map(([name, path]) => {
    const text = readFileSync(path, "utf-8");
    return [
      name,
      strip(
        name.endsWith(".vue")
          ? [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1] ?? "").join("\n")
          : text,
      ),
    ];
  });
/** Every rule of the style: where it is, its selector and its declarations (the innermost
 * braces: a rule inside a media query is found too). */
const RULES = STYLE.flatMap(([name, css]) =>
  [...css.matchAll(/([^{};]+)\{([^{}]*)\}/g)].map((m) => ({
    name,
    selector: (m[1] ?? "").trim().replace(/\s+/g, " "),
    body: m[2] ?? "",
  })),
);

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

/** The tones that stand as a small word on a ground of the page, and the grounds: each word on
 * each ground, 4.5 to 1. (--ok is the plain text; --neutral-soft-fg is the Dummy's tag, which
 * has no plate.) */
const WORDS = ["--text", "--muted", "--accent", "--ok", "--bad", "--neutral-soft-fg"];
/** --attention-bg is the flash of a whole group that a link brought into view: every word of the
 * group stands on it for a moment. */
const GROUNDS = ["--panel", "--bg", "--row-selected", "--row-hover", "--raised", "--input-bg", "--attention-bg"];
const TAGS = ["accent", "ok", "warn", "bad", "info", "neutral", "lora", "hf"];
/** A word and the plate it is read on, and only there: a tag, a filled button, the toast, the
 * map's signpost. */
const PLATES: [string, string][] = [
  ...TAGS.map((tone): [string, string] => [`--${tone}-soft-fg`, `--${tone}-soft-bg`]),
  ["--accent-text", "--accent"],
  ["--on-strong", "--bad"],
  ["--panel", "--text"],
  ["--map-sign-ink", "--map-sign-bg"],
];
/** A word of the map's own colours, drawn with its halo: the palette does not reach it. */
const MAP_WORDS = ["--map-label", "--map-own"];

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
          if (LITERAL.test(line.replace(/\/\*.*?\*\//g, "")))
            found.push(`${name}:${i + 1}: ${line.trim().slice(0, 80)}`);
        });
    }
    expect(found).toEqual([]);
  });

  it("has every colour token in the light and in the dark theme, and each theme's own where the colour changes", () => {
    const colours = Object.keys(light).filter((k) => COLOUR.test(light[k] ?? ""));
    expect(colours.length).toBeGreaterThan(30);
    for (const tone of TAGS) {
      for (const part of ["bg", "fg"])
        expect(dark, `--${tone}-soft-${part} for dark`).toHaveProperty(`--${tone}-soft-${part}`);
    }
    for (const strong of [
      "--ok",
      "--warn",
      "--bad",
      "--info",
      "--accent",
      "--accent-text",
      "--on-strong",
      "--text",
      "--panel",
      "--bg",
      "--border",
      "--muted",
      "--row-selected",
      "--row-hover",
      "--selection",
      "--raised",
      "--input-bg",
      "--attention-bg",
    ])
      expect(dark, strong).toHaveProperty(strong);
    expect(Object.keys(dark).filter((k) => !(k in light))).toEqual([]);
  });

  it("makes every tone that stands as a small word readable at 11 px on every ground it stands on: 4.5 to 1 in the light and in the dark theme", () => {
    const low: string[] = [];
    for (const [name, theme] of THEMES) {
      for (const word of WORDS) {
        for (const ground of GROUNDS) {
          const ratio = contrast(theme[word] ?? "#000000", theme[ground] ?? "#000000");
          if (!(ratio >= 4.5)) low.push(`${name}: ${word} on ${ground} ${ratio.toFixed(2)}`);
        }
      }
    }
    expect(low).toEqual([]);
  });

  it("gives a drag across text a tone of its own: the text reads on it, and it is told from every ground it is dragged over, our own bubble and the selected row among them, in both themes", () => {
    expect(readFileSync(join(SRC, "styles", "base.css"), "utf-8")).toMatch(
      /::selection \{\s*background: var\(--selection\);\s*color: var\(--text\);/,
    );
    const low: string[] = [];
    for (const [name, theme] of THEMES) {
      const text = contrast(theme["--text"] ?? "#000000", theme["--selection"] ?? "#000000");
      if (!(text >= 4.5)) low.push(`${name}: --text on --selection ${text.toFixed(2)}`);
      for (const ground of GROUNDS.filter((g) => g !== "--attention-bg")) {
        const apart = contrast(theme["--selection"] ?? "#000000", theme[ground] ?? "#000000");
        if (!(apart >= 1.2)) low.push(`${name}: --selection on ${ground} ${apart.toFixed(2)}`);
      }
    }
    expect(low).toEqual([]);
  });

  it("makes every word on its own plate readable at 11 px, the tags' soft pairs and the filled ones: 4.5 to 1 in the light and in the dark theme", () => {
    const low: string[] = [];
    for (const [name, theme] of THEMES) {
      for (const [fg, bg] of PLATES) {
        const ratio = contrast(theme[fg] ?? "#000000", theme[bg] ?? "#000000");
        if (!(ratio >= 4.5)) low.push(`${name}: ${fg} on ${bg} ${ratio.toFixed(2)}`);
      }
    }
    expect(low).toEqual([]);
  });

  it("checks every tone the page gives a text: each is a word on the grounds, a word on its plate, or the map's", () => {
    const known = new Set([...WORDS, ...PLATES.map(([fg]) => fg), ...MAP_WORDS]);
    const unchecked: string[] = [];
    // A text's colour, with a fallback or without: `color`, `-webkit-text-fill-color` and the
    // `fill` of an SVG text.
    const TEXT_COLOUR = /(?<![\w-])(?:color|-webkit-text-fill-color):\s*var\((--[\w-]+)(?:,[^)]*)?\)/g;
    const SVG_FILL = /(?<![\w-])fill:\s*var\((--[\w-]+)(?:,[^)]*)?\)/g;
    for (const { name, selector, body } of RULES) {
      const svgText = selector.split(",").some((part) => /(?:^|[\s>+~])text$/.test(part.trim()));
      for (const m of [...body.matchAll(TEXT_COLOUR), ...(svgText ? body.matchAll(SVG_FILL) : [])])
        if (!known.has(m[1] ?? "")) unchecked.push(`${name}: ${selector}: ${m[1]}`);
    }
    expect(unchecked).toEqual([]);
    expect(RULES.length).toBeGreaterThan(500);
  });

  it("never writes a warn word in the bare --warn: a warn word is the soft pair, its word on its plate", () => {
    const words = RULES.filter(({ body }) =>
      /(?<![\w-])(?:color|-webkit-text-fill-color):\s*var\(--warn(?:,[^)]*)?\)/.test(body),
    ).map(({ name, selector }) => `${name}: ${selector}`);
    expect(words).toEqual([]);
    const plated = RULES.filter(({ body }) => /(?<![\w-])color:\s*var\(--warn-soft-fg\)/.test(body));
    expect(plated.length).toBeGreaterThan(5);
    expect(
      plated
        .filter(({ body }) => !/background:\s*var\(--warn-soft-bg\)/.test(body))
        .map(({ name, selector }) => `${name}: ${selector}`),
    ).toEqual([]);
  });

  it("tells the Mercury radio's tag, the site's inverse pill, from every other tag by its lightness, in both themes: 3 to 1 between the plates at least", () => {
    for (const [name, theme] of THEMES) {
      for (const tone of TAGS.filter((t) => t !== "hf")) {
        const ratio = contrast(theme["--hf-soft-bg"] ?? "#000000", theme[`--${tone}-soft-bg`] ?? "#000000");
        expect({ name, tone, apart: ratio >= 3 }).toEqual({ name, tone, apart: true });
      }
    }
    // A dark plate on the light panel.
    expect(luminance(light["--hf-soft-bg"] ?? "")).toBeLessThan(luminance(light["--panel"] ?? ""));
    // A light plate on the dark one.
    expect(luminance(dark["--hf-soft-bg"] ?? "")).toBeGreaterThan(luminance(dark["--panel"] ?? ""));
  });

  it("gives the LoRa radio's tag and a removed radio's tag a tone of their own, each read at AA in both themes: LoRa a plate of its own, a removed radio the quiet word on no plate", () => {
    const rule = (selector: string) =>
      RULES.filter((r) => r.name === "styles/tag.css" && r.selector === selector)
        .map((r) => r.body)
        .join(";");
    expect(rule(".tag-lora")).toMatch(/background:\s*var\(--lora-soft-bg\)/);
    expect(rule(".tag-lora")).toMatch(/(?<![\w-])color:\s*var\(--lora-soft-fg\)/);
    expect(rule(".tag-removed")).toMatch(/(?<![\w-])color:\s*var\(--muted\)/);
    expect(rule(".tag-removed")).toMatch(/background:\s*none/);
    const low: string[] = [];
    for (const [name, theme] of THEMES) {
      const lora = contrast(theme["--lora-soft-fg"] ?? "#000000", theme["--lora-soft-bg"] ?? "#000000");
      if (!(lora >= 4.5)) low.push(`${name}: --lora-soft-fg on --lora-soft-bg ${lora.toFixed(2)}`);
      for (const ground of GROUNDS) {
        const removed = contrast(theme["--muted"] ?? "#000000", theme[ground] ?? "#000000");
        if (!(removed >= 4.5)) low.push(`${name}: --muted (a removed radio's tag) on ${ground} ${removed.toFixed(2)}`);
      }
      // Dimmed: a removed radio's word is quieter than the text, and apart from the Packet radio's
      // neutral plate it has none.
      expect(contrast(theme["--muted"] ?? "", theme["--panel"] ?? "")).toBeLessThan(
        contrast(theme["--text"] ?? "", theme["--panel"] ?? ""),
      );
    }
    expect(low).toEqual([]);
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

  it("is written in docs/palette.md with the light and the dark value of every token", () => {
    const doc = readFileSync(join(ROOT, "docs", "palette.md"), "utf-8");
    expect(Object.keys(light).length).toBeGreaterThan(60);
    for (const key of Object.keys(light)) {
      expect(doc, key).toContain(`| \`${key}\` | \`${light[key]}\` | \`${dark[key] ?? light[key]}\` |`);
    }
  });

  it("gives the page's theme colour and the manifest's the palette's: the header's surface, and the page behind it", () => {
    const index = readFileSync(join(SRC, "..", "index.html"), "utf-8");
    const theme = (scheme: string): string | undefined =>
      index.match(
        new RegExp(`<meta name="theme-color" content="(#[0-9a-f]{6})" media="\\(prefers-color-scheme: ${scheme}\\)"`),
      )?.[1];
    expect([theme("light"), theme("dark")]).toEqual([light["--panel"], dark["--panel"]]);
    const manifest = JSON.parse(readFileSync(join(SRC, "..", "public", "manifest.webmanifest"), "utf-8")) as {
      theme_color: string;
      background_color: string;
    };
    expect([manifest.theme_color, manifest.background_color]).toEqual([light["--panel"], light["--bg"]]);
  });
});
