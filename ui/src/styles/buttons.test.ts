import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { cssRule, mediaRule } from "@/test/css";

// One size for the buttons of the page: a text button, an input and a select are --control-h high (32 px), the compact `.btn.small` is --control-h-small (24 px), and nothing else sets the size of a `.btn`.
const STYLES = resolve(__dirname);
const SRC = resolve(__dirname, "..");
const strip = (css: string): string => css.replace(/\/\*[\s\S]*?\*\//g, "");

function files(dir: string, extension: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? files(resolve(dir, entry.name), extension) : entry.name.endsWith(extension) ? [resolve(dir, entry.name)] : [],
  );
}

describe("the sizes of the buttons", () => {
  it("have two heights in tokens.css, and the text button, the input and the compact button take them", () => {
    const tokens = strip(readFileSync(resolve(STYLES, "tokens.css"), "utf8"));
    expect(tokens).toMatch(/--control-h:\s*32px/);
    expect(tokens).toMatch(/--control-h-small:\s*24px/);
    expect(cssRule(".btn")).toContain("min-height: var(--control-h);");
    expect(cssRule(".btn.small")).toContain("min-height: var(--control-h-small);");
    expect(cssRule(".input")).toContain("height: var(--control-h);");
  });

  it("are at least a finger high (40 px) on a touch screen, the compact button too", () => {
    const sheet = strip(readFileSync(resolve(STYLES, "responsive.css"), "utf8"));
    const coarse = sheet.slice(sheet.indexOf("@media (pointer: coarse)"));
    expect(mediaRule("(pointer: coarse)", ".btn")).toContain("min-height: 40px");
    expect(mediaRule("(pointer: coarse)", ".btn.small")).toContain("min-height: 40px");
    expect(coarse).toContain(".input,");
  });

  it("are not given a height, padding or font size by any rule of another style sheet (a width or a place is fine)", () => {
    const sizes = /(^|;)\s*(min-height|max-height|height|padding[a-z-]*|font-size|line-height)\s*:/;
    const found: string[] = [];
    for (const file of files(STYLES, ".css")) {
      if (file.endsWith("controls.css")) continue;
      for (const match of strip(readFileSync(file, "utf8")).matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
        const selector = (match[1] ?? "").trim();
        if (!/\.btn(?![\w-])/.test(selector) || !sizes.test(match[2] ?? "")) continue;
        if (file.endsWith("responsive.css") && /^\.btn,\s*\.btn\.small,/.test(selector) && !/padding|font-size|line-height/.test(match[2] ?? "")) continue; // (the finger's minimum)
        found.push(`${file.slice(STYLES.length + 1)}: ${selector.replace(/\s+/g, " ")}`);
      }
    }
    expect(found).toEqual([]);
  });

  it("are not given an inline style in a component", () => {
    const inline = /<(button|a)\b[^>]*\s:?style=/s;
    const found = files(SRC, ".vue").filter((file) => inline.test(readFileSync(file, "utf8").replaceAll("=>", "")));
    expect(found).toEqual([]);
  });

  it("are small only inside a line of text or a list row: the components listed here; every other button is the normal height", () => {
    const allowed = new Set(["ConversationThread", "EmailRow", "CopyField", "PopupHelp", "UpdateSteps", "RouteMenu", "ObjectsQru"]); // (message rows, the groups in a server's row, a copy beside a command, the route in a conversation's header line)
    const small = files(resolve(SRC, "components"), ".vue")
      .filter((file) => /class="btn small/.test(readFileSync(file, "utf8")))
      .map((file) => file.replace(/^.*\//, "").replace(/\.vue$/, ""));
    expect(small.filter((name) => !allowed.has(name))).toEqual([]);
  });
});
