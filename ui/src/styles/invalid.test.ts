import { describe, expect, it } from "vitest";
import { cssRule } from "@/test/css";

// A field the page or the daemon holds wrong keeps its mark while it has the focus: the focus ring
// is drawn in the colour of the wrong border, not over it in the accent.
describe("a wrong field with the focus", () => {
  it("draws its focus ring in the colour of the wrong border, whichever way the field is marked", () => {
    for (const selector of [
      ".input.invalid:focus-visible",
      ".field.invalid .input:focus-visible",
      '.input[aria-invalid="true"]:focus-visible',
    ])
      expect(cssRule(selector), selector).toContain("outline-color: var(--bad);");
  });

  it("has the wrong border wherever it is marked for assistive technology alone", () => {
    expect(cssRule('.input[aria-invalid="true"]')).toContain("border-color: var(--bad);");
  });
});
