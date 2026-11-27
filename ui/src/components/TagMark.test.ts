// One tag for the whole page: the header's count and the tabs', the state pills, the channel of a
// station, Receive only and the chips of a chain are all the Tag component, and its size is
// written once: no place that uses it gives it another height, font or padding.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TagMark from "@/components/TagMark.vue";
import { cssRule } from "@/test/css";

describe("TagMark", () => {
  it("is a span of the class tag with the tone's class, and a button when it is pressed", () => {
    expect(mount(TagMark, { slots: { default: "24" } }).html()).toBe('<span class="tag tag-accent">24</span>');
    expect(mount(TagMark, { props: { tone: "neutral" }, slots: { default: "RF" } }).classes()).toEqual([
      "tag",
      "tag-neutral",
    ]);
    const button = mount(TagMark, { props: { as: "button", tone: "outline" }, slots: { default: "OH2ABC ×" } });
    expect(button.html().startsWith("<button")).toBe(true);
    expect(button.attributes("type")).toBe("button");
  });

  it("has a tone of its own for the Mercury radio: the site's inverse pill, apart from the Packet radio's neutral grey in both themes", () => {
    const hf = mount(TagMark, { props: { tone: "hf" }, slots: { default: "Mercury" } });
    const fm = mount(TagMark, { props: { tone: "neutral" }, slots: { default: "Packet" } });
    expect(hf.classes()).toEqual(["tag", "tag-hf"]);
    expect(hf.classes()).not.toEqual(fm.classes());
    expect(cssRule(".tag-hf")).toMatch(/background:\s*var\(--hf-soft-bg\)/);
    expect(cssRule(".tag-hf")).toMatch(/color:\s*var\(--hf-soft-fg\)/);
  });

  it("has a tone of its own for a LoRa radio, sage, and for a removed radio, dimmed: the quiet words on no plate with a thin edge, of the one size", () => {
    expect(mount(TagMark, { props: { tone: "lora" }, slots: { default: "LoRa" } }).classes()).toEqual([
      "tag",
      "tag-lora",
    ]);
    expect(mount(TagMark, { props: { tone: "removed" }, slots: { default: "Shack" } }).classes()).toEqual([
      "tag",
      "tag-removed",
    ]);
    expect(cssRule(".tag-lora")).toMatch(/background:\s*var\(--lora-soft-bg\)/);
    expect(cssRule(".tag-lora")).toMatch(/color:\s*var\(--lora-soft-fg\)/);
    expect(cssRule(".tag-removed")).toMatch(/color:\s*var\(--muted\)/);
    expect(cssRule(".tag-removed")).toMatch(/background:\s*none/);
    expect(cssRule(".tag-removed")).toMatch(/border-color:\s*var\(--border\)/);
    for (const rule of [cssRule(".tag-lora"), cssRule(".tag-removed")])
      expect(rule).not.toMatch(/height|padding|font-size|border-width/);
  });

  it("has its size in one rule, the blue count's: 18 px high, 11 px, 6 px at each side, round, from the size tokens that only the header sets larger", () => {
    const rule = cssRule(".tag");
    expect(rule).toMatch(/height:\s*var\(--tag-h\)/);
    expect(rule).toMatch(/font-size:\s*var\(--tag-font\)/);
    expect(rule).toMatch(/padding:\s*0 var\(--tag-pad\)/);
    expect(rule).toMatch(/border-radius:\s*var\(--radius-pill\)/);
    const root = cssRule(":root");
    expect([/--tag-h:\s*18px/, /--tag-font:\s*11px/, /--tag-pad:\s*6px/].every((token) => token.test(root))).toBe(true);
    const sets = (selector: string) => /--tag-(h|font|pad):/.test(cssRule(selector));
    expect([".appheader", ".badge", ".rxswitch", ".headpill", ".headpills"].map(sets)).toEqual([
      true,
      false,
      false,
      false,
      false,
    ]);
  });

  it.each([
    ".badge",
    ".headmail.badge",
    ".fold-badge",
    ".conv .badge",
    ".statetext",
    ".grid.stations tr.internetonly td.heard .via",
    ".rxswitch",
    ".chip",
    ".chip-hop .hop-call",
    ".own-mark",
    ".grid.packets td.via .tag",
  ])("is not resized where %s places it", (selector) => {
    expect(cssRule(selector)).not.toMatch(
      /(^|[\s;])(height|min-height|font-size|padding[a-z-]*|line-height|border-radius):/,
    );
  });
});
