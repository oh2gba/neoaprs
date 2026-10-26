// One tag for the whole page: the header's count and the tabs', the state pills, the channel of a station, Receive only and the chips of a chain are all the Tag component, and its size is written once: no place that uses it gives it another height, font or padding.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TagMark from "@/components/TagMark.vue";
import { cssRule } from "@/test/css";

describe("TagMark", () => {
  it("is a span of the class tag with the tone's class, and a button when it is pressed", () => {
    expect(mount(TagMark, { slots: { default: "24" } }).html()).toBe('<span class="tag tag-count">24</span>');
    expect(mount(TagMark, { props: { tone: "quiet" }, slots: { default: "RF" } }).classes()).toEqual(["tag", "tag-quiet"]);
    const button = mount(TagMark, { props: { as: "button", tone: "outline" }, slots: { default: "OH2ABC ×" } });
    expect(button.html().startsWith("<button")).toBe(true);
    expect(button.attributes("type")).toBe("button");
  });

  it("has its size in one rule, the blue count's: 18 px high, 11 px, 6 px at each side, round", () => {
    const rule = cssRule(".tag");
    expect(rule).toMatch(/height:\s*18px/);
    expect(rule).toMatch(/font-size:\s*11px/);
    expect(rule).toMatch(/padding:\s*0 6px/);
    expect(rule).toMatch(/border-radius:\s*9px/);
  });

  it.each([
    ".badge",
    ".headmail.badge",
    ".fold-badge",
    ".conv .badge",
    ".statetext",
    ".grid.stations td.call .via",
    ".rxonly",
    ".chip",
    ".chip-hop .hop-call",
    ".own-mark",
    ".grid.packets td.via .tag",
  ])("is not resized where %s places it", (selector) => {
    expect(cssRule(selector)).not.toMatch(/(^|[\s;])(height|min-height|font-size|padding[a-z-]*|line-height|border-radius):/);
  });
});
