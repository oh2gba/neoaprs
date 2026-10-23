import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { useCardEsc } from "@/composables/useCardEsc";

const mounted: { unmount: () => void }[] = [];
function setUp(blocked = false) {
  const closeAll = vi.fn(() => true);
  const state = { blocked };
  const wrapper = mount(
    defineComponent({
      setup() {
        useCardEsc(closeAll, () => state.blocked);
        return () => h("div", [h("input", { id: "field" }), h("button", { id: "plain" })]);
      },
    }),
    { attachTo: document.body },
  );
  mounted.push(wrapper);
  return { closeAll, state, wrapper };
}

const press = (target: Element | Document, key = "Escape") => target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.replaceChildren();
});

describe("useCardEsc", () => {
  it("closes the cards on Esc, and only on Esc", () => {
    const { closeAll, wrapper } = setUp();
    press(document.body, "a");
    expect(closeAll).not.toHaveBeenCalled();
    press(document.body);
    press(wrapper.find("#plain").element);
    expect(closeAll).toHaveBeenCalledTimes(2);
  });

  it("leaves the key to a field that has text in it, and takes it from an empty one", () => {
    const { closeAll, wrapper } = setUp();
    const field = wrapper.find("#field").element as HTMLInputElement;
    field.value = "OH2";
    press(field);
    expect(closeAll).not.toHaveBeenCalled();
    field.value = "";
    press(field);
    expect(closeAll).toHaveBeenCalledTimes(1);
  });

  it("takes it from the page, a row of a table and a button, where the focus is not in a field", () => {
    const { closeAll, wrapper } = setUp();
    press(wrapper.find("#plain").element);
    press(document.body);
    expect(closeAll).toHaveBeenCalledTimes(2);
  });

  it("leaves the key to what takes it first (the guide, the update panel), even when that has closed itself on the same key", () => {
    const { closeAll, state } = setUp(true);
    document.addEventListener("keydown", () => (state.blocked = false), { once: true }); // (the guide closes with Esc: it is not open any more when this listener comes)
    press(document.body);
    expect(closeAll).not.toHaveBeenCalled();
    press(document.body);
    expect(closeAll).toHaveBeenCalledTimes(1);
  });

  it("does not take a key that was handled already, and stops listening when it is gone", () => {
    const { closeAll, wrapper } = setUp();
    document.addEventListener("keydown", (event) => event.preventDefault(), { once: true, capture: true }); // (something took it before)
    press(document.body);
    expect(closeAll).not.toHaveBeenCalled();
    wrapper.unmount();
    press(document.body);
    expect(closeAll).not.toHaveBeenCalled();
  });
});
