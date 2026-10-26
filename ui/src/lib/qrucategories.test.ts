import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { LOCALES } from "@/i18n/locales";
import { CATEGORY_CODES, categoryLabel, categoryMessage, isStandardCategory } from "@/lib/qrucategories";
import { qruProblem } from "@/lib/ownobjects";

describe("the standard categories of local info", () => {
  it("are codes the daemon accepts, each once", () => {
    expect(new Set(CATEGORY_CODES).size).toBe(CATEGORY_CODES.length);
    expect(CATEGORY_CODES.filter((code) => qruProblem(code) !== "")).toEqual([]);
  });

  it("have a name in every language, and none of them is the code or says QRU", () => {
    for (const locale of LOCALES) {
      const messages = locale.messages as Record<string, unknown>;
      for (const code of CATEGORY_CODES) {
        const text = messages[categoryMessage(code)];
        expect(typeof text, `${locale.code} ${code}`).toBe("string");
        expect(text, `${locale.code} ${code}`).not.toBe("");
        expect(String(text), `${locale.code} ${code}`).not.toMatch(/QRU/);
      }
    }
  });

  it("show the plain name of a standard group (in any case) and any other code as itself", () => {
    expect(categoryLabel("RP2M")).toBe("2 m repeater");
    expect(categoryLabel("rp70")).toBe("70 cm repeater");
    expect(categoryLabel("FOOD")).toBe("Food");
    expect(categoryLabel("MYNET")).toBe("MYNET");
    expect(isStandardCategory("MYNET")).toBe(false);
    expect(Object.keys(en).filter((id) => id.startsWith("objects.category.") && !id.endsWith(".none") && !id.endsWith(".other"))).toHaveLength(
      CATEGORY_CODES.length,
    );
  });
});
