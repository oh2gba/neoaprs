// The (i) at the top of a tab: a thin bar with the (i) at its right end, whose note says what the tab is for.
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import TabHelp from "@/components/TabHelp.vue";
import { cssRule } from "@/test/css";

describe("TabHelp", () => {
  it("is a bar with an (i) named by its label, closed, that opens to the lines of its slot and, if given, a picture", async () => {
    const wrapper = mount(TabHelp, {
      props: { label: "About objects", picture: "object" },
      slots: { default: '<span class="info-line">What it is.</span>' },
      attachTo: document.body,
    });
    const toggle = wrapper.find(".tab-help > .infotip > button");
    expect(toggle.attributes("aria-label")).toBe("About objects");
    expect(wrapper.find(".info-text").exists()).toBe(false);
    await toggle.trigger("click");
    expect(wrapper.find(".info-text .info-line").text()).toBe("What it is.");
    expect(wrapper.find(".info-text svg[data-picture='object']").exists()).toBe(true);
    wrapper.unmount();
  });

  it("is a thin bar with the (i) at the right whose note opens leftward, as the Email tab's bar is", () => {
    expect(cssRule(".tab-help")).toMatch(/justify-content:\s*flex-end/);
    expect(cssRule(".tab-help")).toMatch(/flex:\s*none/);
    expect(cssRule(".info-text")).toMatch(/position:\s*fixed/); // (the note is fixed in the window and placed by the (i), so that it opens leftward from the corner and no edge clips it)
  });
});
