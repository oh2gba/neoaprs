// The pictures of the (i) notes: each draws, says what it shows to a screen reader, has no words of a language in it, and is made of the page's own colours (classes of helppictures.css that are variables of tokens.css, which are defined for light and for dark), so that it follows the theme.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { PICTURE_NAMES } from "@/help/names";
import { PICTURES } from "@/help/pictures";
import { en } from "@/i18n/en";

const HERE = dirname(fileURLToPath(import.meta.url));
const STYLES = join(HERE, "..", "styles");
const css = readFileSync(join(STYLES, "helppictures.css"), "utf-8");
const tokens = readFileSync(join(STYLES, "tokens.css"), "utf-8");
const sources = readdirSync(HERE)
  .filter((f) => f.endsWith(".vue") || f === "draw.ts")
  .map((f) => ({ name: f, text: readFileSync(join(HERE, f), "utf-8") }));

/** The part of tokens.css for the dark theme (the media query) and the rest for the light one. */
const DARK_AT = tokens.indexOf("prefers-color-scheme: dark");
const light = tokens.slice(0, DARK_AT);
const dark = tokens.slice(DARK_AT);
const defines = (block: string, token: string): boolean => new RegExp(`${token}\\s*:`).test(block);

describe("the pictures of the (i) notes", () => {
  it("are one for each name, every name has a description for a screen reader, and every picture is drawn in the same frame", () => {
    expect(Object.keys(PICTURES).sort()).toEqual([...PICTURE_NAMES].sort());
    for (const name of PICTURE_NAMES) {
      expect(en).toHaveProperty(`help.picture.${name}`);
      const svg = mount(PICTURES[name]).find("svg.hp");
      expect(svg.attributes("viewBox")).toBe("0 0 280 150");
      expect(svg.attributes("role")).toBe("img");
      expect(svg.attributes("aria-label")).toBe((en as Record<string, unknown>)[`help.picture.${name}`]);
      expect(svg.attributes("data-picture")).toBe(name);
    }
  });

  it("draw the symbols of the map from the sheets of the page, and have lines and shapes besides", () => {
    for (const name of PICTURE_NAMES) {
      const svg = mount(PICTURES[name]).find("svg.hp");
      const sheets = svg.findAll("image").map((image) => image.attributes("href"));
      expect(sheets.length > 0 || name === "accesskey" || name === "logs", name).toBe(true);
      expect(sheets.every((href) => /^symbols\/(primary|alternate|overlay)\.png$/.test(href ?? ""))).toBe(true);
      expect(svg.findAll("path, rect, circle").length).toBeGreaterThan(2);
    }
  });

  it("have no words but calls, frequencies and codes that are the same in every language", () => {
    for (const name of PICTURE_NAMES) {
      const words = mount(PICTURES[name])
        .findAll("text")
        .map((text) => text.text());
      expect(words.filter((word) => !/^[A-Z0-9][A-Z0-9 .,-]*$/.test(word))).toEqual([]);
    }
  });

  it("are made of the style sheet's classes only, with no colour of their own", () => {
    const defined = new Set([...css.matchAll(/\.([a-z][\w-]*)/g)].map((m) => m[1]));
    for (const name of PICTURE_NAMES) {
      const html = mount(PICTURES[name]).html();
      const used = [...html.matchAll(/class="([^"]*)"/g)].flatMap((m) => (m[1] ?? "").split(/\s+/)).filter(Boolean);
      expect(used.filter((c) => !defined.has(c))).toEqual([]);
      expect(html).not.toMatch(/(fill|stroke|stop-color|color)="(?!none|currentColor)/);
      expect(html).not.toContain("style=");
    }
    for (const { name, text } of sources) expect({ name, colours: text.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/g) }).toEqual({ name, colours: null });
  });

  it("take every colour from a variable of the page that has a value for light and another for dark", () => {
    const colours = css
      .split("}")
      .flatMap((rule) => rule.split("{").slice(1).join("{").split(";"))
      .filter((d) => /^\s*(fill|stroke|color)\s*:/.test(d));
    const tokensUsed = new Set(colours.flatMap((d) => [...d.matchAll(/var\((--[\w-]+)\)/g)].map((m) => m[1] ?? "")));
    expect(tokensUsed.size).toBeGreaterThan(4);
    for (const token of tokensUsed) {
      expect({ token, light: defines(light, token) }).toEqual({ token, light: true });
      expect({ token, dark: defines(dark, token) }).toEqual({ token, dark: true });
    }
    expect(colours.filter((d) => !/var\(--|currentColor|none/.test(d))).toEqual([]);
  });
});
