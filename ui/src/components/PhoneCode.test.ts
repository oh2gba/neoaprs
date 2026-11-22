// The phone code: the QR code of its link as one path on a white field, in a box of one size
// whatever the link; an image named by the row's label, with no words of its own.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PhoneCode from "@/components/PhoneCode.vue";
import { qrMatrix, qrPath } from "@/lib/qr";

const SHORT = "http://10.0.0.7:7303/#key=2345-6789-abcd";
const LONG = "https://shack-pi-of-the-club-station-on-the-hill-by-the-old-water-tower.local:7304/#key=k7m2-x9pq-4hrt";
const code = (link: string) => mount(PhoneCode, { props: { link, labelledby: "the-label" } });
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "styles", "settings.css"), "utf-8");

describe("PhoneCode", () => {
  it("draws the matrix of its link: one white field and one path of the dark modules, a module a unit", () => {
    const svg = code(SHORT).find("svg");
    const { size, d } = qrPath(qrMatrix(SHORT));
    expect(svg.attributes("viewBox")).toBe(`0 0 ${size} ${size}`);
    expect(svg.attributes("shape-rendering")).toBe("crispEdges");
    expect(svg.find("rect.phonecode-field").attributes()).toMatchObject({ width: `${size}`, height: `${size}` });
    expect(svg.findAll("path")).toHaveLength(1);
    expect(svg.find("path.phonecode-dark").attributes("d")).toBe(d);
  });

  it("is an image named by the row's label, with no text of its own", () => {
    const wrapper = code(SHORT);
    expect(wrapper.find("svg").attributes()).toMatchObject({ role: "img", "aria-labelledby": "the-label" });
    expect(wrapper.text()).toBe("");
    expect(wrapper.find("title").exists()).toBe(false);
    expect(wrapper.html()).not.toContain("10.0.0.7");
  });

  it("keeps its box for a short and a long link: only the viewBox, the size in modules, differs", () => {
    const [short, long] = [code(SHORT).find("svg"), code(LONG).find("svg")];
    expect(short.attributes("viewBox")).toBe("0 0 37 37");
    expect(long.attributes("viewBox")).toBe("0 0 49 49");
    for (const svg of [short, long]) {
      expect(svg.attributes("class")).toBe("phonecode");
      expect(svg.attributes("width")).toBeUndefined();
      expect(svg.attributes("height")).toBeUndefined();
      expect(svg.attributes("style")).toBeUndefined();
    }
  });

  it("is a square of 196 px in the style sheet, dark on white in both themes", () => {
    const rule = (selector: string) => css.match(new RegExp(`\\n${selector.replace(".", "\\.")} \\{([^}]*)\\}`))?.[1] ?? "";
    expect(rule(".phonecode")).toMatch(/flex: 0 1 196px;[\s\S]*max-width: 196px;[\s\S]*aspect-ratio: 1;/);
    expect(rule(".phonecode-field")).toContain("fill: var(--code-field);");
    expect(rule(".phonecode-dark")).toContain("fill: var(--code-dark);");
  });
});
