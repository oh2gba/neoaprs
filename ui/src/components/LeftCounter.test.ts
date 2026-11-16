import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import LeftCounter from "@/components/LeftCounter.vue";
import { cssRule } from "@/test/css";

describe("LeftCounter", () => {
  it("says what is left, with its title, and in orange when the limit shrank under the text", async () => {
    const wrapper = mount(LeftCounter, { props: { left: 12, max: 67, title: "12 of 67 bytes left" } });
    expect(wrapper.text()).toBe("12 left");
    expect(wrapper.attributes("title")).toBe("12 of 67 bytes left");
    expect(wrapper.classes()).toEqual(["compose-left", "mono"]);
    await wrapper.setProps({ left: -3 });
    expect(wrapper.text()).toBe("3 over");
    expect(wrapper.classes()).toContain("over");
  });

  it("keeps the room of the widest it says (the full limit left, as many over) whatever the number, so that the field beside it keeps its width in every language", async () => {
    const wrapper = mount(LeftCounter, { props: { left: 55, max: 55 } });
    const room = () => [wrapper.attributes("data-room"), wrapper.attributes("data-over")];
    expect(room()).toEqual(["55 left", "55 over"]);
    for (const left of [100, 10, 5, 1, 0, -3]) {
      await wrapper.setProps({ left });
      expect(room()).toEqual(["55 left", "55 over"]);
    }
    expect(wrapper.text()).toBe("3 over");
    const rule = cssRule(".compose-left::before");
    expect(rule).toMatch(/content:\s*attr\(data-room\)\s*"\\A"\s*attr\(data-over\)/);
    expect(rule).toMatch(/height:\s*0/);
    expect(rule).toMatch(/visibility:\s*hidden/);
    expect(rule).toMatch(/white-space:\s*pre/);
    expect(rule).toMatch(/font-weight:\s*600/);
    expect(rule).toMatch(/display:\s*block/);
  });

  it("is one line, in the monospaced font, the number at its right end, never shrunk by the field beside it", () => {
    const rule = cssRule(".compose-left");
    expect(rule).toMatch(/white-space:\s*nowrap/);
    expect(rule).toMatch(/text-align:\s*right/);
    expect(rule).toMatch(/flex:\s*none/);
    expect(rule).toMatch(/display:\s*inline-block/);
    expect(cssRule(".mono")).toMatch(/font-family/);
  });
});
