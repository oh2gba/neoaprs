// The chrome of the page is not text to select: a drag across a button, a label, a legend, a heading, the head of a table, a menu, the app's header, the tab bar or the header of a conversation paints nothing blue (base.css); what is content stays selectable, and on a touch screen
// what has a copy menu (`copysource`) gives the long press to the menu, not to the system's selection (responsive.css).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { cssRule, mediaRule } from "@/test/css";

/** The style sheets as one, with their comments and their indentation: a rule at the left edge is one outside every media query. */
const SHEETS = ["base.css", "responsive.css"].map((file) => readFileSync(resolve(__dirname, file), "utf8")).join("\n");

const CHROME = [
  "button",
  "label",
  "legend",
  "summary",
  "th",
  "dt",
  "h1",
  "h2",
  "h3",
  "h4",
  '[role="menu"]',
  ".appheader",
  ".tabbar",
  ".convo-head",
  ".convlist-head",
  ".card-head",
  ".foot",
  ".tab-help",
];
const CONTENT = [".bubble-text", ".grid td", ".card-fields dd", ".bulletin-text", ".info-text", ".json"];

describe("what is text to select", () => {
  it("is not the chrome of the page", () => {
    for (const selector of CHROME) expect(cssRule(selector), selector).toContain("user-select: none;");
  });

  it("is the content", () => {
    for (const selector of CONTENT) expect(cssRule(selector), selector).not.toContain("user-select");
  });

  it("gives a long press on a thing with a copy menu to the menu on a touch screen", () => {
    expect(mediaRule("(pointer: coarse)", ".copysource")).toContain("user-select: none;");
    expect(mediaRule("(pointer: coarse)", ".copysource")).toContain("-webkit-touch-callout: none;");
    expect(SHEETS.match(/^\.copysource/m)).toBeNull(); // (with a mouse the text stays selectable: no rule at the left edge, outside the media query)
  });

  it("says a newer version in the accent colour, not in the white that is read on it", () => {
    expect(cssRule(".statetext.update-available")).toContain("color: var(--accent);");
  });
});
