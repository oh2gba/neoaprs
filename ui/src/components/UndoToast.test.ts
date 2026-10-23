import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import UndoToast from "@/components/UndoToast.vue";

describe("UndoToast", () => {
  it("shows nothing while there is nothing to undo", () => {
    expect(
      mount(UndoToast, { props: { undo: null } })
        .find(".toast")
        .exists(),
    ).toBe(false);
  });

  it("says what changed, and offers Undo and a way to dismiss it", async () => {
    const wrapper = mount(UndoToast, { props: { undo: { label: "Beacon interval", values: { "beacon/interval_min": "0" }, n: 1 } } });
    expect(wrapper.find(".toast").attributes("role")).toBe("status");
    expect(wrapper.text()).toContain("Beacon interval changed");
    await wrapper.find(".undo-button").trigger("click");
    expect(wrapper.emitted("undo")).toHaveLength(1);
    await wrapper.find("button[aria-label='Dismiss']").trigger("click");
    expect(wrapper.emitted("dismiss")).toHaveLength(1);
  });
});
