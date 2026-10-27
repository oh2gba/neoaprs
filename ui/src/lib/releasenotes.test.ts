import { describe, expect, it } from "vitest";
import { noteBlocks, noteParts } from "@/lib/releasenotes";

describe("the release notes as blocks", () => {
  it("reads a heading, bullets and paragraphs, the lines of a paragraph joined, blank lines between blocks", () => {
    const text = "Bug fixes on the air.\nNothing to set up.\n\n- **Fixed:** one thing.\n* Another, with `code`.\n\n### Under the hood\n\nSmaller cleanups.\n";
    expect(noteBlocks(text)).toEqual([
      { kind: "paragraph", parts: [{ text: "Bug fixes on the air. Nothing to set up." }] },
      { kind: "bullet", parts: [{ text: "Fixed:", bold: true }, { text: " one thing." }] },
      { kind: "bullet", parts: [{ text: "Another, with " }, { text: "code", code: true }, { text: "." }] },
      { kind: "heading", parts: [{ text: "Under the hood" }] },
      { kind: "paragraph", parts: [{ text: "Smaller cleanups." }] },
    ]);
    expect(noteBlocks("")).toEqual([]);
  });

  it("reduces a link to its text and leaves other marks as they stand", () => {
    expect(noteParts("see [the manual](docs/MANUAL.md) and *this*")).toEqual([{ text: "see the manual and *this*" }]);
    expect(noteParts("**all bold**")).toEqual([{ text: "all bold", bold: true }]);
  });
});
