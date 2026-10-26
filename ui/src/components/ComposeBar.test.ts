import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ComposeBar from "@/components/ComposeBar.vue";

function bar(props: Record<string, unknown> = {}) {
  return mount(ComposeBar, {
    props: { label: "Write", ...props },
    slots: {
      default: '<input id="field" />',
      aside: '<button type="button" id="aside">Pick</button>',
      buttons: '<button type="button" id="cancel">Cancel</button><button type="submit" id="go" class="primary">Go</button>',
    },
    attachTo: document.body,
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("ComposeBar", () => {
  it("is no box and has no legend as the chat line under a conversation (inline): the field, the counter and the button directly in the form", () => {
    const wrapper = bar({ inline: true, left: 5 });
    expect(wrapper.classes()).not.toContain("boxed");
    expect(wrapper.find("fieldset").exists()).toBe(false);
    expect(wrapper.find("legend").exists()).toBe(false);
    expect(wrapper.find(".composebar-aside").exists()).toBe(false);
    wrapper.unmount();
  });

  it("is a form with a group box (fieldset and legend) around the fields, and under them one line: what is aside, the counter, the buttons", () => {
    const wrapper = bar({ left: 12 });
    const form = wrapper.find("form");
    expect(form.element).toBe(wrapper.element);
    expect(wrapper.attributes("aria-label")).toBe("Write");
    expect([...wrapper.find("fieldset.composebox").element.children].map((c) => c.className || c.tagName.toLowerCase())).toEqual([
      "legend",
      "composebar-fields",
      "composebar-foot",
    ]);
    expect(wrapper.find("fieldset > legend").text()).toBe("Write");
    expect(wrapper.find(".composebar-fields #field").exists()).toBe(true);
    expect([...wrapper.find(".composebar-foot").element.children].map((c) => c.id || c.className)).toEqual([
      "composebar-aside",
      "compose-left mono",
      "cancel",
      "go",
    ]);
    wrapper.unmount();
  });

  it("counts what is left beside the buttons, red when it is over, and has no counter when it is not given one", async () => {
    const wrapper = bar({ left: 67, leftTitle: "67 of 67 characters left" });
    expect(wrapper.find(".compose-left").text()).toBe("67 left");
    expect(wrapper.find(".compose-left").attributes("title")).toBe("67 of 67 characters left");
    await wrapper.setProps({ left: -3 });
    expect(wrapper.find(".compose-left").text()).toBe("3 over");
    expect(wrapper.find(".compose-left").classes()).toContain("over");
    await wrapper.setProps({ left: undefined });
    expect(wrapper.find(".compose-left").exists()).toBe(false);
    wrapper.unmount();
  });

  it("sends submit when the form is submitted", async () => {
    const wrapper = bar();
    await wrapper.trigger("submit");
    expect(wrapper.emitted("submit")).toEqual([[]]);
    wrapper.unmount();
  });

  it("brings the field that takes the focus into view once the keyboard is up", async () => {
    const wrapper = bar();
    const field = wrapper.find<HTMLInputElement>("#field").element;
    const into = vi.fn();
    field.scrollIntoView = into;
    await wrapper.find("#field").trigger("focusin");
    expect(into).not.toHaveBeenCalled();
    vi.advanceTimersByTime(400);
    expect(into).toHaveBeenCalledWith({ block: "nearest" });
    wrapper.unmount();
  });
});
